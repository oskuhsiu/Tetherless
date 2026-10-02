// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

public enum AuthenticationStorageFailure: String, Error, LocalizedError, Sendable {
    case unavailable, invalidRecord, unsupportedVersion, readbackMismatch, staleAttempt, notReady
    public var errorDescription: String? { "Account storage needs attention: \(rawValue)." }
}

/// One backend item, never four independently readable credential fields.
/// Implementations atomically replace an existing item, without delete-first.
public protocol AuthenticationRecordStorage: Sendable {
    func read() throws -> Data?
    func write(_ data: Data) throws
}

public struct AuthenticationCredentials: Codable, Equatable, Sendable {
    public let email: String
    public let password: String?
    public let dsid: String
    public let token: String
    public init(email: String, password: String?, dsid: String, token: String) throws {
        self.email = email; self.password = password; self.dsid = dsid; self.token = token
        try validate()
    }
    public func validate() throws {
        for (value, maximum) in [(email, 1024), (dsid, 1024), (token, 32_768)] {
            guard !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  value.utf8.count <= maximum,
                  !value.unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 }) else {
                throw AuthenticationStorageFailure.invalidRecord
            }
        }
        if let password {
            guard !password.isEmpty, password.utf8.count <= 4096,
                  !password.contains("\0") else { throw AuthenticationStorageFailure.invalidRecord }
        }
    }
}

public struct AuthenticationRecord: Codable, Equatable, Sendable {
    public enum Phase: String, Codable, Sendable { case staged, ready, signedOut }
    public let schemaVersion: Int
    public let generation: UUID
    public let phase: Phase
    public let credentials: AuthenticationCredentials?
    public let teamID: String?
    public init(generation: UUID = UUID(), phase: Phase, credentials: AuthenticationCredentials? = nil, teamID: String? = nil) {
        self.schemaVersion = 1; self.generation = generation; self.phase = phase
        self.credentials = credentials; self.teamID = teamID
    }
    public func validate() throws {
        guard schemaVersion == 1 else { throw AuthenticationStorageFailure.unsupportedVersion }
        switch phase {
        case .signedOut:
            guard credentials == nil, teamID == nil else { throw AuthenticationStorageFailure.invalidRecord }
        case .staged, .ready:
            guard let credentials else { throw AuthenticationStorageFailure.invalidRecord }
            try credentials.validate()
            if phase == .staged {
                guard teamID == nil else { throw AuthenticationStorageFailure.invalidRecord }
            } else {
                guard let teamID, !teamID.isEmpty, teamID.utf8.count <= 64,
                      teamID.utf8.allSatisfy({ (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) }) else {
                    throw AuthenticationStorageFailure.invalidRecord
                }
            }
        }
    }
}

/// The caller holds the shared native mutation lease for writes. A valid Apple
/// login is staged, then activated only after the selected team is durable in DB.
/// A crash between those steps remains NOT ready on the next process launch.
public struct VerifiedAuthenticationStore: Sendable {
    private let storage: any AuthenticationRecordStorage
    public init(storage: any AuthenticationRecordStorage) { self.storage = storage }
    public func read() throws -> AuthenticationRecord? {
        guard let data = try storage.read() else { return nil }
        guard !data.isEmpty, data.count <= 65_536 else { throw AuthenticationStorageFailure.invalidRecord }
        let record: AuthenticationRecord
        do { record = try JSONDecoder().decode(AuthenticationRecord.self, from: data) }
        catch { throw AuthenticationStorageFailure.invalidRecord }
        try record.validate()
        return record
    }
    public func requireReady() throws -> AuthenticationRecord {
        guard let record = try read(), record.phase == .ready else { throw AuthenticationStorageFailure.notReady }
        return record
    }
    @discardableResult
    public func stage(_ credentials: AuthenticationCredentials) throws -> UUID {
        try credentials.validate()
        // Persist only the session needed for renewal, not the entered Apple
        // password. The optional field remains readable for old dev records.
        let session = try AuthenticationCredentials(email: credentials.email, password: nil,
            dsid: credentials.dsid, token: credentials.token)
        let record = AuthenticationRecord(phase: .staged, credentials: session)
        try commit(record)
        return record.generation
    }
    public func activate(generation: UUID, teamID: String) throws {
        guard let current = try read(), current.phase == .staged, current.generation == generation else {
            throw AuthenticationStorageFailure.staleAttempt
        }
        try commit(AuthenticationRecord(generation: generation, phase: .ready, credentials: current.credentials, teamID: teamID))
    }
    /// Called under the native mutation lease during startup/maintenance.
    /// Retain the valid token/team/generation while removing a password kept by
    /// an earlier development build. Failure is surfaced, never called success.
    public func discardRetainedPassword() throws {
        guard let record = try read(), let credentials = record.credentials,
              credentials.password != nil else { return }
        let session = try AuthenticationCredentials(email: credentials.email, password: nil,
            dsid: credentials.dsid, token: credentials.token)
        try commit(AuthenticationRecord(generation: record.generation, phase: record.phase,
            credentials: session, teamID: record.teamID))
    }
    public func signOut() throws {
        // A tombstone is authoritative: leftover legacy fields cannot resurrect
        // a session if later cleanup fails. A write failure is not sign-out success.
        try commit(AuthenticationRecord(phase: .signedOut))
    }
    private func commit(_ record: AuthenticationRecord) throws {
        try record.validate()
        let data = try JSONEncoder().encode(record)
        guard data.count <= 65_536 else { throw AuthenticationStorageFailure.invalidRecord }
        try storage.write(data)
        guard try storage.read() == data else { throw AuthenticationStorageFailure.readbackMismatch }
    }
}
