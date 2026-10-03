// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

public enum AnisettePackageFailure: String, Error, LocalizedError, Sendable {
    case missingDigest, invalidDigest, checksumMismatch, alreadyInProgress
    case ambiguousPayload, payloadTooLarge, invalidPayload
    public var errorDescription: String? { "Anisette package rejected: \(rawValue)." }
}

/// Transport/integrity limits, not publisher authentication. A checksum from
/// mutable metadata does not establish independently reviewed provenance.
public enum AnisettePackageInput {
    public static let maximumArchiveBytes = 64 * 1024 * 1024
    public static let maximumEncodedBytes = ((maximumArchiveBytes + 2) / 3) * 4
    // Metadata may itself contain a complete Base64-encoded archive.
    public static let maximumMetadataBytes = maximumEncodedBytes + 1024 * 1024

    public static func digest(_ value: String?) throws -> String {
        guard let value else { throw AnisettePackageFailure.missingDigest }
        guard value.utf8.count == 64, value.utf8.allSatisfy({
            (48...57).contains($0) || (65...70).contains($0) || (97...102).contains($0)
        }) else { throw AnisettePackageFailure.invalidDigest }
        return value.lowercased()
    }
    public static func verify(expected: String?, actual: String) throws {
        guard try digest(expected) == digest(actual) else {
            throw AnisettePackageFailure.checksumMismatch
        }
    }
    public static func decodeBase64(_ input: String) throws -> Data {
        guard input.utf8.count <= maximumEncodedBytes else { throw AnisettePackageFailure.payloadTooLarge }
        // MIME line breaks are allowed; unknown characters never are.
        let compact = input.utf8.filter { $0 != 9 && $0 != 10 && $0 != 13 && $0 != 32 }
        guard let decoded = Data(base64Encoded: Data(compact)), !decoded.isEmpty,
              decoded.count <= maximumArchiveBytes else { throw AnisettePackageFailure.invalidPayload }
        return decoded
    }
    public static func archive(from body: Data) throws -> Data {
        guard body.count <= maximumEncodedBytes else { throw AnisettePackageFailure.payloadTooLarge }
        if body.starts(with: [0x50, 0x4b, 0x03, 0x04]) {
            guard body.count <= maximumArchiveBytes else { throw AnisettePackageFailure.payloadTooLarge }
            return body
        }
        guard let text = String(data: body, encoding: .utf8) else { throw AnisettePackageFailure.invalidPayload }
        return try decodeBase64(text)
    }
}

/// Admission is per manager and deliberately nonwaiting. A rejected concurrent
/// caller cannot mistake another caller's failed install for its own success.
/// This is not a substitute for the native process-wide mutation lease.
public final class AnisettePackageAdmission: @unchecked Sendable {
    private let lock = NSLock()
    private var active: UUID?
    public init() {}
    public func acquire() throws -> Lease {
        lock.lock(); defer { lock.unlock() }
        guard active == nil else { throw AnisettePackageFailure.alreadyInProgress }
        let id = UUID(); active = id
        return Lease(owner: self, id: id)
    }
    private func release(_ id: UUID) {
        lock.lock(); defer { lock.unlock() }
        if active == id { active = nil }
    }
    public final class Lease: @unchecked Sendable {
        private let owner: AnisettePackageAdmission
        private let id: UUID
        fileprivate init(owner: AnisettePackageAdmission, id: UUID) { self.owner = owner; self.id = id }
        public func release() { owner.release(id) }
        deinit { release() }
    }
}
