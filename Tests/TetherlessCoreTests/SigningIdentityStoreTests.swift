// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore

@Suite("Signing envelope persistence; synthetic bytes are not P12 validation")
struct SigningIdentityStoreTests {
    struct Files: AuthenticationRecordStorage {
        let files: PrivateFileStore
        init(_ root: URL) throws { files = try PrivateFileStore(root: root, maximumBytes: 65_536); try files.prepare() }
        func read() throws -> Data? { try files.read("signer") }
        func write(_ data: Data) throws { try files.write(data, named: "signer") }
    }
    func use(_ test: (VerifiedSigningIdentityStore, Files) throws -> Void) throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let files = try Files(root)
        try test(VerifiedSigningIdentityStore(storage: files), files)
    }
    func identity(_ serial: String = "a1") throws -> StoredSigningIdentity {
        try .init(serial: serial, p12: Data("synthetic-test-only".utf8), password: "p12-secret-test-only")
    }
    @Test func replacementKeepsPasswordAndSerialTogether() throws {
        try use { store, _ in
            #expect(try store.read() == nil)
            try store.save(identity())
            #expect(try store.read()?.identity == identity())
            try store.save(identity("b2"))
            #expect(try store.read()?.identity == identity("b2"))
        }
    }
    @Test func explicitDeactivationHasNoSecretAndIsNotMissing() throws {
        try use { store, files in
            try store.save(identity()); try store.save(nil)
            #expect(try store.read() != nil)
            #expect(try store.read()?.identity == nil)
            let saved = try files.read()
            let bytes = try #require(saved)
            let value = String(decoding: bytes, as: UTF8.self)
            #expect(!value.contains("p12-secret-test-only"))
            #expect(!value.contains("p12"))
        }
    }
    @Test func writeFailurePreservesOldIdentity() throws {
        struct Failing: AuthenticationRecordStorage {
            let files: Files
            func read() throws -> Data? { try files.read() }
            func write(_ data: Data) throws { throw AuthenticationStorageFailure.unavailable }
        }
        try use { store, files in
            try store.save(identity())
            let failing = VerifiedSigningIdentityStore(storage: Failing(files: files))
            #expect(throws: AuthenticationStorageFailure.unavailable) { try failing.save(identity("b2")) }
            #expect(try store.read()?.identity == identity())
        }
    }
    @Test func droppedWriteIsNotSuccessful() throws {
        struct Dropped: AuthenticationRecordStorage {
            func read() throws -> Data? { nil }
            func write(_ data: Data) throws {}
        }
        let store = VerifiedSigningIdentityStore(storage: Dropped())
        #expect(throws: AuthenticationStorageFailure.readbackMismatch) { try store.save(identity()) }
    }
    @Test func invalidIdentityCannotBeConstructed() throws {
        for serial in ["", "../key", String(repeating: "a", count: 129)] {
            #expect(throws: AuthenticationStorageFailure.invalidRecord) {
                try StoredSigningIdentity(serial: serial, p12: Data([1]), password: nil)
            }
        }
        #expect(throws: AuthenticationStorageFailure.invalidRecord) {
            try StoredSigningIdentity(serial: "a1", p12: Data(repeating: 1, count: 32_769), password: nil)
        }
    }
    @Test func corruptAndFutureReadDoesNotMeanNoCertificate() throws {
        try use { store, files in
            try files.write(Data("broken".utf8))
            #expect(throws: AuthenticationStorageFailure.invalidRecord) { try store.read() }
            var envelope = SigningIdentityEnvelope(identity: try identity()); envelope.schemaVersion = 100
            try files.write(JSONEncoder().encode(envelope))
            #expect(throws: AuthenticationStorageFailure.unsupportedVersion) { try store.read() }
        }
    }
}

#if os(macOS) && canImport(Security)
@Suite("Signing envelope on actual system Keychain; synthetic bytes, not a signing test")
struct SigningKeychainTests {
    @Test func coherentCacheAndPublicItemsAreIndependent() throws {
        let service = "org.tetherless.tests.signer." + UUID().uuidString
        let privateItem = try KeychainAuthenticationStorage(service: service, account: "private-test")
        let publicItem = try KeychainAuthenticationStorage(service: service, account: "public-test")
        defer { try? privateItem.remove(); try? publicItem.remove() }
        let vault = VerifiedSigningIdentityStore(storage: privateItem)
        let record = try StoredSigningIdentity(serial: "abc123", p12: Data("synthetic-secret".utf8), password: "test")
        try vault.save(record)
        try publicItem.write(Data("synthetic-public".utf8))
        #expect(try vault.read()?.identity == record)
        try vault.save(nil)
        #expect(try vault.read()?.identity == nil)
        #expect(try publicItem.read() == Data("synthetic-public".utf8))
    }
}
#endif
