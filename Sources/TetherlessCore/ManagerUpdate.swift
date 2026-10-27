// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

public enum ManagerUpdateFailure: String, Error, LocalizedError, Sendable {
    case invalidRecord, unsupportedSchema, pendingUpdate, wrongGeneration
    case identityMismatch, notInstalled, storageMismatch, requiresForeground
    public var errorDescription: String? {
        switch self {
        case .pendingUpdate: return "A manager update is unresolved. Reconcile it before starting another update."
        case .notInstalled: return "The expected manager update has not been observed. Its recovery record was retained."
        case .identityMismatch: return "The running manager does not match the recorded update. No recovery data was applied."
        case .requiresForeground: return "Updating the manager requires explicit foreground confirmation."
        default: return "Manager update recovery failed: \(rawValue). The existing recovery record was not discarded."
        }
    }
}

/// Hashes describe the exact signed input and observed running bundle. They are
/// not an independent certificate trust decision or a claim about unattended use.
public struct ManagerUpdateComponent: Codable, Equatable, Sendable {
    public let bundleID: String
    public let profileSHA256: String
    public let executableSHA256: String
    public init(bundleID: String, profileSHA256: String, executableSHA256: String) {
        self.bundleID = bundleID; self.profileSHA256 = profileSHA256
        self.executableSHA256 = executableSHA256
    }
}
public struct ManagerUpdateIdentity: Codable, Equatable, Sendable {
    public let bundleID: String
    public let teamID: String
    public let version: String
    public let build: String
    public let components: [ManagerUpdateComponent]
    public init(bundleID: String, teamID: String, version: String, build: String,
                components: [ManagerUpdateComponent]) {
        self.bundleID = bundleID; self.teamID = teamID; self.version = version; self.build = build
        self.components = components.sorted { $0.bundleID < $1.bundleID }
    }
    public func validate() throws {
        guard Self.identifier(bundleID), teamID.utf8.count == 10,
              teamID.utf8.allSatisfy({ (48...57).contains($0) || (65...90).contains($0) }),
              Self.shortString(version), Self.shortString(build),
              !components.isEmpty, components.count <= 64,
              Set(components.map(\.bundleID)).count == components.count,
              components == components.sorted(by: { $0.bundleID < $1.bundleID }),
              components.contains(where: { $0.bundleID == bundleID }) else {
            throw ManagerUpdateFailure.invalidRecord
        }
        for part in components {
            guard Self.identifier(part.bundleID),
                  part.bundleID == bundleID || part.bundleID.hasPrefix(bundleID + "."),
                  Self.digest(part.profileSHA256), Self.digest(part.executableSHA256) else {
                throw ManagerUpdateFailure.invalidRecord
            }
        }
    }
    static func identifier(_ value: String) -> Bool {
        !value.isEmpty && value.utf8.count <= 255 &&
        value.split(separator: ".", omittingEmptySubsequences: false).allSatisfy { part in
            !part.isEmpty && part.utf8.allSatisfy {
                (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) || $0 == 45 || $0 == 95
            }
        }
    }
    static func shortString(_ value: String) -> Bool {
        !value.isEmpty && value.utf8.count <= 128 && value.utf8.allSatisfy { (32...126).contains($0) }
    }
    static func digest(_ value: String) -> Bool {
        value.utf8.count == 64 && value.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
    }
}

/// Only manager-specific public fields, not a serialized Core Data graph.
/// There is no ability to restore arbitrary accounts, settings or relationships.
public struct ManagerUpdateMetadata: Codable, Equatable, Sendable {
    public let originalBundleID: String
    public let cacheFingerprint: String
    public let certificateSerial: String
    public let storeBuild: String?
    public let extensionOriginalIDs: [String: String]
    public init(originalBundleID: String, cacheFingerprint: String, certificateSerial: String,
                storeBuild: String?, extensionOriginalIDs: [String: String]) {
        self.originalBundleID = originalBundleID; self.cacheFingerprint = cacheFingerprint
        self.certificateSerial = certificateSerial; self.storeBuild = storeBuild
        self.extensionOriginalIDs = extensionOriginalIDs
    }
}
public enum ManagerUpdatePhase: String, Codable, Sendable {
    case prepared, applying, completed, abandoned
    public var isPending: Bool { self == .prepared || self == .applying }
}
public struct ManagerUpdateRecord: Codable, Equatable, Sendable {
    public var schemaVersion: Int = 1
    public let id: UUID
    public let before: ManagerUpdateIdentity
    public let after: ManagerUpdateIdentity
    public let metadata: ManagerUpdateMetadata
    public var phase: ManagerUpdatePhase = .prepared
    public init(id: UUID = UUID(), before: ManagerUpdateIdentity, after: ManagerUpdateIdentity,
                metadata: ManagerUpdateMetadata) {
        self.id = id; self.before = before; self.after = after; self.metadata = metadata
    }
    public func validate() throws {
        guard schemaVersion == 1 else { throw ManagerUpdateFailure.unsupportedSchema }
        try before.validate(); try after.validate()
        guard before != after, before.bundleID == after.bundleID, before.teamID == after.teamID,
              ManagerUpdateIdentity.identifier(metadata.originalBundleID),
              ManagerUpdateIdentity.digest(metadata.cacheFingerprint),
              !metadata.certificateSerial.isEmpty, metadata.certificateSerial.utf8.count <= 128,
              metadata.certificateSerial.utf8.allSatisfy({ (48...57).contains($0) || (65...70).contains($0) || (97...102).contains($0) }),
              metadata.storeBuild.map(ManagerUpdateIdentity.shortString) ?? true,
              Set(metadata.extensionOriginalIDs.keys) == Set(after.components.map(\.bundleID)).subtracting([after.bundleID]),
              Set(metadata.extensionOriginalIDs.values).count == metadata.extensionOriginalIDs.count,
              metadata.extensionOriginalIDs.values.allSatisfy({ ManagerUpdateIdentity.identifier($0) && $0.hasPrefix(metadata.originalBundleID + ".") }) else {
            throw ManagerUpdateFailure.invalidRecord
        }
    }
}

public protocol ManagerUpdateRecordStorage: Sendable {
    func read() throws -> Data?
    func write(_ data: Data) throws
}
public struct FileManagerUpdateStorage: ManagerUpdateRecordStorage {
    private let files: PrivateFileStore
    public init(root: URL) throws { files = try PrivateFileStore(root: root, maximumBytes: 131_072) }
    public func read() throws -> Data? { try files.prepare(); return try files.read("manager-update.json") }
    public func write(_ data: Data) throws { try files.write(data, named: "manager-update.json") }
}
/// Callers hold the common native mutation lease across journal AND database IO.
public struct ManagerUpdateJournal: Sendable {
    private let storage: any ManagerUpdateRecordStorage
    public init(storage: any ManagerUpdateRecordStorage) { self.storage = storage }
    public func read() throws -> ManagerUpdateRecord? {
        guard let bytes = try storage.read() else { return nil }
        guard !bytes.isEmpty, bytes.count <= 131_072 else { throw ManagerUpdateFailure.invalidRecord }
        let record: ManagerUpdateRecord
        do { record = try JSONDecoder().decode(ManagerUpdateRecord.self, from: bytes) }
        catch { throw ManagerUpdateFailure.invalidRecord }
        try record.validate()
        return record
    }
    private func save(_ record: ManagerUpdateRecord) throws {
        try record.validate()
        let bytes = try JSONEncoder().encode(record)
        guard bytes.count <= 131_072 else { throw ManagerUpdateFailure.invalidRecord }
        try storage.write(bytes)
        guard try read() == record else { throw ManagerUpdateFailure.storageMismatch }
    }
    public func stage(_ record: ManagerUpdateRecord, running: ManagerUpdateIdentity) throws {
        try record.validate(); try running.validate()
        guard record.phase == .prepared, running == record.before else { throw ManagerUpdateFailure.identityMismatch }
        if let previous = try read(), previous.phase.isPending { throw ManagerUpdateFailure.pendingUpdate }
        try save(record)
    }
    public func beginApplying(id: UUID) throws {
        guard var record = try read(), record.id == id else { throw ManagerUpdateFailure.wrongGeneration }
        guard record.phase == .prepared else { throw ManagerUpdateFailure.invalidRecord }
        record.phase = .applying
        try save(record) // This must succeed BEFORE calling the device installer.
    }
    /// The native callback must save AND read back only the manager's database
    /// fields. Any error preserves the applying record for idempotent retry.
    @discardableResult
    public func reconcile(running: ManagerUpdateIdentity, persist: (ManagerUpdateRecord) throws -> Void) throws -> Bool {
        try running.validate()
        guard var record = try read(), record.phase.isPending else { return false }
        if running == record.before { throw ManagerUpdateFailure.notInstalled }
        guard record.phase == .applying, running == record.after else { throw ManagerUpdateFailure.identityMismatch }
        try persist(record)
        guard try read() == record else { throw ManagerUpdateFailure.wrongGeneration }
        record.phase = .completed
        try save(record)
        return true
    }
    /// Explicit foreground abandonment only. It cannot discard a successful,
    /// changed, or unidentified installation and never changes app/database data.
    public func abandonUnapplied(running: ManagerUpdateIdentity) throws {
        try running.validate()
        guard var record = try read(), record.phase.isPending else { return }
        guard running == record.before else { throw ManagerUpdateFailure.identityMismatch }
        record.phase = .abandoned
        try save(record)
    }
}
