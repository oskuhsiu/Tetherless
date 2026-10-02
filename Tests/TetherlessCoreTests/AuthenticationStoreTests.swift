// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore

private final class AuthFixtureStore: AuthenticationRecordStorage, @unchecked Sendable {
    var data: Data?
    var failWrite = false
    var ignoreWrite = false
    var failRead = false
    func read() throws -> Data? {
        if failRead { throw AuthenticationStorageFailure.unavailable }
        return data
    }
    func write(_ data: Data) throws {
        if failWrite { throw AuthenticationStorageFailure.unavailable }
        if !ignoreWrite { self.data = data }
    }
}
@Suite("Coherent account storage; fixtures are not real credentials")
struct AuthenticationStoreTests {
    private func credentials(_ id: String = "fixture") throws -> AuthenticationCredentials {
        try AuthenticationCredentials(email: id + "@example.invalid", password: "synthetic", dsid: "12345", token: id + "-token")
    }
    @Test func stagedCredentialsNeverEnableBackgroundRenewal() throws {
        let storage = AuthFixtureStore(), store = VerifiedAuthenticationStore(storage: AuthFixtureStore())
        #expect(throws: AuthenticationStorageFailure.notReady) { try store.requireReady() }
        let subject = VerifiedAuthenticationStore(storage: storage)
        let generation = try subject.stage(credentials())
        #expect(throws: AuthenticationStorageFailure.notReady) { try subject.requireReady() }
        // Reconstruct the store, as if the process died after Apple login.
        let reopened = VerifiedAuthenticationStore(storage: storage)
        #expect(throws: AuthenticationStorageFailure.notReady) { try reopened.requireReady() }
        try reopened.activate(generation: generation, teamID: "TEAM123")
        #expect(try reopened.requireReady().teamID == "TEAM123")
    }
    @Test func staleLoginCannotActivateANewerAccount() throws {
        let store = VerifiedAuthenticationStore(storage: AuthFixtureStore())
        let old = try store.stage(credentials("first"))
        let new = try store.stage(credentials("second"))
        #expect(throws: AuthenticationStorageFailure.staleAttempt) { try store.activate(generation: old, teamID: "OLD") }
        try store.activate(generation: new, teamID: "NEW")
        #expect(try store.requireReady().credentials?.email == "second@example.invalid")
        #expect(try store.requireReady().credentials?.token == "second-token")
    }
    @Test func ignoredOrFailedKeychainWriteIsNotSuccess() throws {
        let storage = AuthFixtureStore(); let store = VerifiedAuthenticationStore(storage: storage)
        storage.ignoreWrite = true
        #expect(throws: AuthenticationStorageFailure.readbackMismatch) { try store.stage(credentials()) }
        storage.ignoreWrite = false; storage.failWrite = true
        #expect(throws: AuthenticationStorageFailure.unavailable) { try store.stage(credentials()) }
    }
    @Test func failedActivationLeavesStagedRecord() throws {
        let storage = AuthFixtureStore(); let store = VerifiedAuthenticationStore(storage: storage)
        let generation = try store.stage(credentials())
        storage.failWrite = true
        #expect(throws: AuthenticationStorageFailure.unavailable) { try store.activate(generation: generation, teamID: "TEAM") }
        #expect(throws: AuthenticationStorageFailure.notReady) { try store.requireReady() }
    }
    @Test func signOutTombstoneContainsNoSecrets() throws {
        let storage = AuthFixtureStore(); let store = VerifiedAuthenticationStore(storage: storage)
        try store.activate(generation: store.stage(credentials()), teamID: "TEAM")
        try store.signOut()
        #expect(try store.read()?.phase == .signedOut)
        #expect(throws: AuthenticationStorageFailure.notReady) { try VerifiedAuthenticationStore(storage: storage).requireReady() }
        let text = String(decoding: storage.data!, as: UTF8.self)
        #expect(!text.contains("synthetic")); #expect(!text.contains("fixture-token")); #expect(!text.contains("example.invalid"))
    }
    @Test func failedSignOutIsReportedAndDoesNotPretendDeletion() throws {
        let storage = AuthFixtureStore(); let store = VerifiedAuthenticationStore(storage: storage)
        try store.activate(generation: store.stage(credentials()), teamID: "TEAM")
        storage.failWrite = true
        #expect(throws: AuthenticationStorageFailure.unavailable) { try store.signOut() }
        #expect(try store.read()?.phase == .ready)
    }
    @Test func corruptOrFutureRecordIsNeverSilentlyReset() throws {
        let storage = AuthFixtureStore(); let store = VerifiedAuthenticationStore(storage: storage)
        storage.data = Data("broken".utf8)
        #expect(throws: AuthenticationStorageFailure.invalidRecord) { try store.read() }
        try store.signOut()
        var object = try JSONSerialization.jsonObject(with: storage.data!) as! [String: Any]
        object["schemaVersion"] = 99
        storage.data = try JSONSerialization.data(withJSONObject: object)
        #expect(throws: AuthenticationStorageFailure.unsupportedVersion) { try store.read() }
        storage.failRead = true
        #expect(throws: AuthenticationStorageFailure.unavailable) { try store.read() }
    }
    @Test func enteredPasswordIsNeverRetainedByANewSession() throws {
        let storage = AuthFixtureStore(); let store = VerifiedAuthenticationStore(storage: storage)
        let generation = try store.stage(credentials())
        #expect(try store.read()?.credentials?.password == nil)
        #expect(!String(decoding: storage.data!, as: UTF8.self).contains("synthetic"))
        try store.activate(generation: generation, teamID: "TEAM")
        #expect(try store.requireReady().credentials?.password == nil)
        #expect(try store.requireReady().credentials?.token == "fixture-token")
    }
    @Test func oldPasswordRemovalRetainsTheExistingReadySession() throws {
        let storage = AuthFixtureStore(); let store = VerifiedAuthenticationStore(storage: storage)
        let old = AuthenticationRecord(phase: .ready, credentials: try credentials(), teamID: "TEAM")
        storage.data = try JSONEncoder().encode(old)
        storage.failWrite = true
        #expect(throws: AuthenticationStorageFailure.unavailable) { try store.discardRetainedPassword() }
        #expect(try store.requireReady().credentials?.password == "synthetic")
        storage.failWrite = false
        try store.discardRetainedPassword()
        let after = try store.requireReady()
        #expect(after.generation == old.generation)
        #expect(after.teamID == old.teamID)
        #expect(after.credentials?.password == nil)
        #expect(after.credentials?.token == old.credentials?.token)
        let bytes = storage.data
        try store.discardRetainedPassword()
        #expect(storage.data == bytes)
    }
    @Test func invalidInputCannotReplaceAValidSession() throws {
        let storage = AuthFixtureStore(); let store = VerifiedAuthenticationStore(storage: storage)
        try store.activate(generation: store.stage(credentials()), teamID: "TEAM")
        let before = storage.data
        #expect(throws: AuthenticationStorageFailure.invalidRecord) {
            try store.stage(AuthenticationCredentials(email: "", password: nil, dsid: "123", token: "x"))
        }
        #expect(storage.data == before)
    }
}

#if canImport(Security) && os(macOS)
@Suite("Real system Keychain, isolated synthetic item")
struct KeychainAuthenticationTests {
    @Test func roundtripReplacementAndSignOut() throws {
        let adapter = try KeychainAuthenticationStorage(service: "org.tetherless.tests." + UUID().uuidString)
        defer { try? adapter.remove() }
        let store = VerifiedAuthenticationStore(storage: adapter)
        let generation = try store.stage(AuthenticationCredentials(email: "test@example.invalid", password: nil, dsid: "42", token: "synthetic-token"))
        try store.activate(generation: generation, teamID: "SYNTHETIC")
        #expect(try store.requireReady().credentials?.token == "synthetic-token")
        try store.signOut()
        #expect(throws: AuthenticationStorageFailure.notReady) { try store.requireReady() }
        try adapter.remove()
        #expect(try adapter.read() == nil)
    }
}
#endif
