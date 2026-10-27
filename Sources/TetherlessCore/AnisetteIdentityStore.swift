// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

public enum AnisetteIdentityFailure: String, Error, LocalizedError, Sendable {
    case unavailable, invalidRecord, unsupportedVersion, readbackMismatch, staleResult
    public var errorDescription: String? { "Anisette identity needs attention: \(rawValue)." }
}

/// Device-local provisioning material, not an Apple account or proof of login.
/// The identifier and blob must always refer to the same provisioning generation.
public struct AnisetteIdentityRecord: Codable, Equatable, Sendable {
    public enum Phase: String, Codable, Sendable { case prepared, ready, reset }
    public let schemaVersion: Int
    public let generation: UUID
    public let phase: Phase
    public let identifier: UUID?
    public let blob: Data?
    public static let maximumBlobBytes = 32_768

    public init(generation: UUID = UUID(), phase: Phase, identifier: UUID? = nil, blob: Data? = nil) throws {
        schemaVersion = 1; self.generation = generation; self.phase = phase
        self.identifier = identifier; self.blob = blob
        try validate()
    }
    public func validate() throws {
        guard schemaVersion == 1 else { throw AnisetteIdentityFailure.unsupportedVersion }
        switch phase {
        case .prepared:
            guard identifier != nil, blob == nil else { throw AnisetteIdentityFailure.invalidRecord }
        case .ready:
            guard identifier != nil, let blob, !blob.isEmpty,
                  blob.count <= Self.maximumBlobBytes else { throw AnisetteIdentityFailure.invalidRecord }
        case .reset:
            guard identifier == nil, blob == nil else { throw AnisetteIdentityFailure.invalidRecord }
        }
    }
}

public struct LegacyAnisetteIdentity: Sendable {
    public let identifier: String?
    public let blob: String?
    public init(identifier: String?, blob: String?) { self.identifier = identifier; self.blob = blob }

    public func record() throws -> AnisetteIdentityRecord {
        guard let identifier else {
            guard blob == nil else { throw AnisetteIdentityFailure.invalidRecord }
            return try AnisetteIdentityRecord(phase: .prepared, identifier: UUID())
        }
        let uuid: UUID
        if identifier.utf8.count == 36, let parsed = UUID(uuidString: identifier) {
            uuid = parsed
        } else {
            // Accept the historical 16-byte Base64 UUID, without an unaligned load.
            guard identifier.utf8.count == 24, let data = Data(base64Encoded: identifier),
                  data.count == 16, data.base64EncodedString() == identifier else {
                throw AnisetteIdentityFailure.invalidRecord
            }
            let b = Array(data)
            uuid = UUID(uuid: (b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7],
                              b[8], b[9], b[10], b[11], b[12], b[13], b[14], b[15]))
        }
        guard let blob else { return try AnisetteIdentityRecord(phase: .prepared, identifier: uuid) }
        guard !blob.isEmpty, blob.utf8.count <= 4 * ((AnisetteIdentityRecord.maximumBlobBytes + 2) / 3),
              let data = Data(base64Encoded: blob), data.base64EncodedString() == blob else {
            throw AnisetteIdentityFailure.invalidRecord
        }
        return try AnisetteIdentityRecord(phase: .ready, identifier: uuid, blob: data)
    }
}

/// Callers must own the native mutation lease for the entire read/fetch/save
/// operation. Compare-again guards stale callbacks; it is not a replacement lock.
public struct VerifiedAnisetteIdentityStore: Sendable {
    private let storage: any AuthenticationRecordStorage
    public init(storage: any AuthenticationRecordStorage) { self.storage = storage }
    public func read() throws -> AnisetteIdentityRecord? {
        let data: Data?
        do { data = try storage.read() } catch { throw AnisetteIdentityFailure.unavailable }
        guard let data else { return nil }
        guard !data.isEmpty, data.count <= 65_536 else { throw AnisetteIdentityFailure.invalidRecord }
        let record: AnisetteIdentityRecord
        do { record = try JSONDecoder().decode(AnisetteIdentityRecord.self, from: data) }
        catch { throw AnisetteIdentityFailure.invalidRecord }
        try record.validate()
        return record
    }

    /// A new coherent item is authoritative even if legacy cleanup was interrupted.
    /// Never fall back to split fields through an unreadable item or reset marker.
    public func prepare(readLegacy: () throws -> LegacyAnisetteIdentity,
                        removeLegacy: () throws -> Void) throws -> AnisetteIdentityRecord {
        let record: AnisetteIdentityRecord
        if let current = try read() {
            if current.phase == .reset {
                record = try AnisetteIdentityRecord(phase: .prepared, identifier: UUID())
                try commit(record)
            } else { record = current }
        } else {
            let legacy: LegacyAnisetteIdentity
            do { legacy = try readLegacy() } catch { throw AnisetteIdentityFailure.unavailable }
            record = try legacy.record()
            try commit(record)
        }
        do { try removeLegacy() } catch { throw AnisetteIdentityFailure.unavailable }
        return record
    }

    /// Persist fresh material before returning generated headers. A dropped write
    /// is failure, not provisioning success. Never attach it to a changed identity.
    public func accept(_ blob: Data?, for expected: AnisetteIdentityRecord) throws {
        try expected.validate()
        guard expected.phase != .reset, try read() == expected else { throw AnisetteIdentityFailure.staleResult }
        guard let blob else { return }
        let next = try AnisetteIdentityRecord(generation: expected.generation, phase: .ready,
                                              identifier: expected.identifier, blob: blob)
        if next != expected { try commit(next) }
    }

    /// Explicit reset only. The durable new generation prevents late provisioning
    /// or old split fields from restoring erased state after failed cleanup.
    public func reset(keepingIdentifier: Bool, removeLegacy: () throws -> Void) throws {
        let current = try read() // Corrupt/future envelopes are not silently replaced.
        let next: AnisetteIdentityRecord
        if keepingIdentifier, let identifier = current?.identifier {
            next = try AnisetteIdentityRecord(phase: .prepared, identifier: identifier)
        } else { next = try AnisetteIdentityRecord(phase: .reset) }
        try commit(next)
        do { try removeLegacy() } catch { throw AnisetteIdentityFailure.unavailable }
    }

    /// The native wrapper supplies the cross-process lease and reentrancy guard.
    /// Do not publish headers until any returned provisioning blob is durable.
    public func use<Value: Sendable>(readLegacy: () throws -> LegacyAnisetteIdentity,
                                    removeLegacy: () throws -> Void,
                                    fetch: (AnisetteIdentityRecord) async throws -> (Value, Data?)) async throws -> Value {
        try Task.checkCancellation()
        let record = try prepare(readLegacy: readLegacy, removeLegacy: removeLegacy)
        try Task.checkCancellation()
        let (value, freshBlob) = try await fetch(record)
        // Preserve returned provisioning material even when cancellation arrived
        // during the provider call. It must never be saved into a newer record.
        try accept(freshBlob, for: record)
        try Task.checkCancellation()
        return value
    }

    private func commit(_ record: AnisetteIdentityRecord) throws {
        try record.validate()
        let bytes = try JSONEncoder().encode(record)
        guard bytes.count <= 65_536 else { throw AnisetteIdentityFailure.invalidRecord }
        do { try storage.write(bytes) } catch { throw AnisetteIdentityFailure.unavailable }
        let saved: Data?
        do { saved = try storage.read() } catch { throw AnisetteIdentityFailure.unavailable }
        guard saved == bytes else { throw AnisetteIdentityFailure.readbackMismatch }
    }
}
