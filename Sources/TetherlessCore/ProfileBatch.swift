// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// Validates identifiers before they are used as a relative file component.
public enum ManagedBundleIdentifier {
    public static func isSafe(_ value: String) -> Bool {
        !value.isEmpty && value.utf8.count <= 255 &&
        value.split(separator: ".", omittingEmptySubsequences: false).allSatisfy { !$0.isEmpty } &&
        value.unicodeScalars.allSatisfy {
            CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_").contains($0)
        }
    }
}

public enum ProfileBatchFailure: String, Error, Sendable {
    case invalidPlan, expiredPlan, identityChanged, readbackMismatch
}

/// Sensitive, device-bound material. Store only in protected, non-backed-up
/// application support storage, never in the public RenewalJournal or diagnostics.
/// Parsing and identity validation of the signed bytes is the native adapter's job.
public struct ProfileBatchPart: Codable, Equatable, Sendable {
    public let componentID: String
    public let profileID: String
    public let bytes: Data
    public let expiry: Date
    public init(componentID: String, profileID: String, bytes: Data, expiry: Date) {
        self.componentID = componentID
        self.profileID = profileID
        self.bytes = bytes
        self.expiry = expiry
    }
}

public struct ProfileBatch: Codable, Equatable, Sendable {
    public let schema: Int
    public let bundleID: String
    public let identityDigest: String
    public let previousExpiry: Date
    public let certificateExpiry: Date
    public let parts: [ProfileBatchPart]

    public init(bundleID: String, identityDigest: String, previousExpiry: Date,
                certificateExpiry: Date, parts: [ProfileBatchPart]) {
        schema = 1
        self.bundleID = bundleID
        self.identityDigest = identityDigest
        self.previousExpiry = previousExpiry
        self.certificateExpiry = certificateExpiry
        self.parts = parts
    }

    public var newExpiry: Date {
        parts.map(\.expiry).reduce(certificateExpiry, min)
    }

    /// Validate the ENTIRE batch before the first device write. UUID and byte
    /// equality are both checked; a different profile with a reused UUID is not proof.
    public func validate(requiredComponents: Set<String>, identityDigest expected: String,
                         now: Date) throws {
        guard schema == 1, ManagedBundleIdentifier.isSafe(bundleID),
              requiredComponents.contains(bundleID),
              requiredComponents.allSatisfy(ManagedBundleIdentifier.isSafe),
              identityDigest.count == 64,
              identityDigest.allSatisfy({ "0123456789abcdef".contains($0) }),
              !parts.isEmpty, parts.count <= 32,
              Set(parts.map(\.componentID)) == requiredComponents,
              parts.count == requiredComponents.count,
              Set(parts.map(\.profileID)).count == parts.count,
              Set(parts.map(\.bytes)).count == parts.count,
              parts.allSatisfy({ !$0.componentID.isEmpty && UUID(uuidString: $0.profileID) != nil &&
                  !$0.bytes.isEmpty && $0.bytes.count <= 1_048_576 &&
                  $0.expiry.timeIntervalSince1970.isFinite }),
              parts.reduce(0, { $0 + $1.bytes.count }) <= 8_388_608,
              previousExpiry.timeIntervalSince1970.isFinite,
              certificateExpiry.timeIntervalSince1970.isFinite,
              now.timeIntervalSince1970.isFinite else { throw ProfileBatchFailure.invalidPlan }
        guard identityDigest == expected else { throw ProfileBatchFailure.identityChanged }
        guard newExpiry > now, newExpiry > previousExpiry else { throw ProfileBatchFailure.expiredPlan }
    }
}

public protocol ProfileBatchTransport: Sendable {
    /// Must use a live, authenticated device channel, not a cache or the input IPA.
    func readInstalledProfileBytes() async throws -> [Data]
    func installProfileBytes(_ bytes: Data) async throws
}

/// Caller holds the shared device mutation lease and has durably persisted the
/// validated batch. Recovery uses the SAME batch: no new certificate/profile request.
public struct ProfileBatchReadback: Sendable {
    public let newExpiry: Date
    /// Exactly the final transport snapshot used to verify all submitted parts.
    /// Sensitive bytes: never put this object in public summaries or diagnostics.
    public let installedProfiles: [Data]
}

public enum ProfileBatchExecutor {
    public static func applyMissing(_ batch: ProfileBatch, requiredComponents: Set<String>,
                                    identityDigest: String, transport: any ProfileBatchTransport,
                                    now: @Sendable () -> Date = { Date() }) async throws -> Date {
        try await applyMissingAndReadback(batch, requiredComponents: requiredComponents,
            identityDigest: identityDigest, transport: transport, now: now).newExpiry
    }

    public static func applyMissingAndReadback(_ batch: ProfileBatch, requiredComponents: Set<String>,
                                    identityDigest: String, transport: any ProfileBatchTransport,
                                    now: @Sendable () -> Date = { Date() }) async throws -> ProfileBatchReadback {
        try batch.validate(requiredComponents: requiredComponents, identityDigest: identityDigest, now: now())
        try Task.checkCancellation()
        let installed = Set(try await transport.readInstalledProfileBytes())
        let ordered = batch.parts.sorted {
            if ($0.componentID == batch.bundleID) != ($1.componentID == batch.bundleID) {
                return $0.componentID == batch.bundleID
            }
            return $0.componentID < $1.componentID
        }
        for part in ordered where !installed.contains(part.bytes) {
            try Task.checkCancellation()
            try batch.validate(requiredComponents: requiredComponents, identityDigest: identityDigest, now: now())
            try await transport.installProfileBytes(part.bytes)
        }
        try Task.checkCancellation()
        let finalProfiles = try await transport.readInstalledProfileBytes()
        try Task.checkCancellation()
        let readback = Set(finalProfiles)
        guard batch.parts.allSatisfy({ readback.contains($0.bytes) }) else {
            throw ProfileBatchFailure.readbackMismatch
        }
        try batch.validate(requiredComponents: requiredComponents, identityDigest: identityDigest, now: now())
        return ProfileBatchReadback(newExpiry: batch.newExpiry, installedProfiles: finalProfiles)
    }
}
