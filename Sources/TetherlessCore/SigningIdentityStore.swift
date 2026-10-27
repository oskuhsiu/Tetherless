// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// Storage consistency only. The native caller parses and checks the P12 and
/// certificate serial before constructing this record; these bytes are secrets.
public struct StoredSigningIdentity: Codable, Equatable, Sendable {
    public let serial: String
    public let p12: Data
    public let password: String?
    public init(serial: String, p12: Data, password: String?) throws {
        self.serial = serial; self.p12 = p12; self.password = password
        try validate()
    }
    public func validate() throws {
        guard !serial.isEmpty, serial.utf8.count <= 128,
              serial.utf8.allSatisfy({ (48...57).contains($0) || (65...70).contains($0) || (97...102).contains($0) }),
              !p12.isEmpty, p12.count <= 32_768,
              password.map({ $0.utf8.count <= 1_024 && !$0.contains("\0") }) ?? true else {
            throw AuthenticationStorageFailure.invalidRecord
        }
    }
}

public struct SigningIdentityEnvelope: Codable, Equatable, Sendable {
    public var schemaVersion = 1
    public let identity: StoredSigningIdentity?
    public init(identity: StoredSigningIdentity?) { self.identity = identity }
    public func validate() throws {
        guard schemaVersion == 1 else { throw AuthenticationStorageFailure.unsupportedVersion }
        try identity?.validate()
    }
}

/// One atomic Keychain item couples P12, its password and its expected serial.
/// An explicit empty envelope is authoritative and prevents legacy resurrection.
/// Caller serializes modifications with the shared native mutation lease.
public struct VerifiedSigningIdentityStore: Sendable {
    private let storage: any AuthenticationRecordStorage
    public init(storage: any AuthenticationRecordStorage) { self.storage = storage }
    public func read() throws -> SigningIdentityEnvelope? {
        guard let bytes = try storage.read() else { return nil }
        guard !bytes.isEmpty, bytes.count <= 65_536 else { throw AuthenticationStorageFailure.invalidRecord }
        let envelope: SigningIdentityEnvelope
        do { envelope = try JSONDecoder().decode(SigningIdentityEnvelope.self, from: bytes) }
        catch { throw AuthenticationStorageFailure.invalidRecord }
        try envelope.validate()
        return envelope
    }
    public func save(_ identity: StoredSigningIdentity?) throws {
        let envelope = SigningIdentityEnvelope(identity: identity)
        try envelope.validate()
        let bytes = try JSONEncoder().encode(envelope)
        guard bytes.count <= 65_536 else { throw AuthenticationStorageFailure.invalidRecord }
        try storage.write(bytes)
        guard try storage.read() == bytes else { throw AuthenticationStorageFailure.readbackMismatch }
    }
}
