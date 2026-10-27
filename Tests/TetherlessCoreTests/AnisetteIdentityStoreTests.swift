// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore

private struct IdentityFiles: AuthenticationRecordStorage {
    let files: PrivateFileStore
    init(_ root: URL) throws { files = try PrivateFileStore(root: root, maximumBytes: 65_536); try files.prepare() }
    func read() throws -> Data? { try files.read("anisette") }
    func write(_ data: Data) throws { try files.write(data, named: "anisette") }
}
private struct IdentityWriteFault: AuthenticationRecordStorage {
    let files: IdentityFiles
    let drop: Bool
    func read() throws -> Data? { try files.read() }
    func write(_ data: Data) throws {
        if !drop { throw NSError(domain: "SYNTHETIC_PRIVATE_DETAIL", code: 1) }
    }
}
private let syntheticIdentity = UUID(uuidString: "00112233-4455-6677-8899-AABBCCDDEEFF")!
private let syntheticBlob = Data("SYNTHETIC_ADI_BLOB_ONLY".utf8)
private func legacyIdentity() -> LegacyAnisetteIdentity {
    .init(identifier: syntheticIdentity.uuidString, blob: syntheticBlob.base64EncodedString())
}
private func noLegacyIdentity() -> LegacyAnisetteIdentity { .init(identifier: nil, blob: nil) }

@Suite("Anisette identity: production store, actual durable files, synthetic provisioning")
struct AnisetteIdentityStoreTests {
    private func use(_ body: (VerifiedAnisetteIdentityStore, IdentityFiles) async throws -> Void) async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let files = try IdentityFiles(root)
        try await body(VerifiedAnisetteIdentityStore(storage: files), files)
    }
    @Test func uuidAndBlobMigrateTogetherAndReopen() async throws {
        try await use { store, files async throws -> Void in
            var cleaned = false
            let record = try store.prepare(readLegacy: legacyIdentity, removeLegacy: { cleaned = true })
            #expect(cleaned); #expect(record.phase == .ready)
            #expect(record.identifier == syntheticIdentity); #expect(record.blob == syntheticBlob)
            let reopened = VerifiedAnisetteIdentityStore(storage: files)
            #expect(try reopened.read() == record)
            let bytes = try files.read()
            _ = try reopened.prepare(readLegacy: { Issue.record("Read authoritative legacy"); return noLegacyIdentity() }, removeLegacy: {})
            #expect(try files.read() == bytes)
        }
    }
    @Test func base64UUIDKeepsExactBytes() throws {
        let input = Data([0x00,0x11,0x22,0x33,0x44,0x55,0x66,0x77,0x88,0x99,0xaa,0xbb,0xcc,0xdd,0xee,0xff])
        let record = try LegacyAnisetteIdentity(identifier: input.base64EncodedString(), blob: syntheticBlob.base64EncodedString()).record()
        #expect(record.identifier == syntheticIdentity); #expect(record.blob == syntheticBlob)
    }
    @Test func invalidSplitRecordsDoNotGenerateOrClean() async throws {
        try await use { store, files async throws -> Void in
            for fields in [LegacyAnisetteIdentity(identifier: nil, blob: "AQ=="),
                           .init(identifier: "bad", blob: "AQ=="),
                           .init(identifier: syntheticIdentity.uuidString, blob: ""),
                           .init(identifier: syntheticIdentity.uuidString, blob: "AQ==\n"),
                           .init(identifier: syntheticIdentity.uuidString, blob: "AQ==garbage")] {
                #expect(throws: AnisetteIdentityFailure.invalidRecord) {
                    try store.prepare(readLegacy: { fields }, removeLegacy: { Issue.record("Invalid legacy removed") })
                }
                #expect(try files.read() == nil)
            }
        }
    }
    @Test func legacyReadFailureIsNotFirstUse() async throws {
        try await use { store, files async throws -> Void in
            #expect(throws: AnisetteIdentityFailure.unavailable) {
                try store.prepare(readLegacy: { throw NSError(domain: "SECRET", code: 1) }, removeLegacy: { Issue.record("Removed unreadable legacy") })
            }
            #expect(try files.read() == nil)
        }
    }
    @Test func migrationWriteFailureKeepsLegacy() async throws {
        try await use { _, files async throws -> Void in
            for drop in [false, true] {
                let store = VerifiedAnisetteIdentityStore(storage: IdentityWriteFault(files: files, drop: drop))
                #expect(throws: drop ? AnisetteIdentityFailure.readbackMismatch : .unavailable) {
                    try store.prepare(readLegacy: legacyIdentity, removeLegacy: { Issue.record("Removed only valid copy") })
                }
                #expect(try files.read() == nil)
            }
        }
    }
    @Test func migrationCleanupFailureKeepsAuthoritativeCopy() async throws {
        try await use { store, files async throws -> Void in
            #expect(throws: AnisetteIdentityFailure.unavailable) {
                try store.prepare(readLegacy: legacyIdentity, removeLegacy: { throw CocoaError(.fileWriteNoPermission) })
            }
            let original = try #require(try store.read())
            #expect(original.blob == syntheticBlob)
            var retried = false
            let reopened = VerifiedAnisetteIdentityStore(storage: files)
            let next = try reopened.prepare(readLegacy: { Issue.record("Read partly cleaned legacy"); return noLegacyIdentity() }, removeLegacy: { retried = true })
            #expect(retried); #expect(next == original)
        }
    }
    @Test func firstUsePersistsIdentifierBeforeProvider() async throws {
        try await use { store, files async throws -> Void in
            let value = try await store.use(readLegacy: noLegacyIdentity, removeLegacy: {}, fetch: { record async throws -> (String, Data?) in
                #expect(record.phase == .prepared); #expect(record.blob == nil)
                #expect(try VerifiedAnisetteIdentityStore(storage: files).read() == record)
                return ("headers", syntheticBlob)
            })
            #expect(value == "headers"); #expect(try store.read()?.phase == .ready)
            #expect(try store.read()?.blob == syntheticBlob)
        }
    }
    @Test func providerFailureKeepsOldPair() async throws {
        try await use { store, files async throws -> Void in
            _ = try store.prepare(readLegacy: legacyIdentity, removeLegacy: {})
            let before = try files.read()
            await #expect(throws: CancellationError.self) {
                let _: String = try await store.use(readLegacy: noLegacyIdentity, removeLegacy: {}, fetch: { _ in throw CancellationError() })
            }
            #expect(try files.read() == before)
        }
    }
    @Test func failedFreshSaveNeverReturnsHeadersOrDeletesOldBlob() async throws {
        try await use { store, files async throws -> Void in
            _ = try store.prepare(readLegacy: legacyIdentity, removeLegacy: {})
            let before = try files.read()
            for drop in [false, true] {
                let faulted = VerifiedAnisetteIdentityStore(storage: IdentityWriteFault(files: files, drop: drop))
                await #expect(throws: drop ? AnisetteIdentityFailure.readbackMismatch : .unavailable) {
                    let _: String = try await faulted.use(readLegacy: noLegacyIdentity, removeLegacy: {}, fetch: { _ in ("must-not-escape", Data([2])) })
                }
                #expect(try files.read() == before)
            }
        }
    }
    @Test func staleProviderCannotReplaceResetOrNewIdentity() async throws {
        try await use { store, _ async throws -> Void in
            await #expect(throws: AnisetteIdentityFailure.staleResult) {
                let _: String = try await store.use(readLegacy: legacyIdentity, removeLegacy: {}, fetch: { _ in
                    try store.reset(keepingIdentifier: false, removeLegacy: {})
                    _ = try store.prepare(readLegacy: { Issue.record("Read reset legacy"); return legacyIdentity() }, removeLegacy: {})
                    return ("must-not-escape", syntheticBlob)
                })
            }
            let after = try #require(try store.read())
            #expect(after.identifier != syntheticIdentity); #expect(after.blob == nil)
        }
    }
    @Test func cancellationAfterProviderPreservesReturnedMaterial() async throws {
        try await use { store, _ async throws -> Void in
            let task = Task {
                try await store.use(readLegacy: noLegacyIdentity, removeLegacy: {}, fetch: { _ in
                    withUnsafeCurrentTask { $0?.cancel() }
                    return ("cancelled-headers", syntheticBlob)
                })
            }
            await #expect(throws: CancellationError.self) { try await task.value }
            #expect(try store.read()?.blob == syntheticBlob)
        }
    }
    @Test func absentFreshBlobAndIdenticalBlobDoNotRewrite() async throws {
        try await use { store, files async throws -> Void in
            let record = try store.prepare(readLegacy: legacyIdentity, removeLegacy: {})
            let before = try files.read()
            try store.accept(nil, for: record); try store.accept(syntheticBlob, for: record)
            #expect(try files.read() == before)
        }
    }
    @Test func resetSurvivesCleanupFailureAndInvalidatesLateResults() async throws {
        try await use { store, files async throws -> Void in
            let old = try store.prepare(readLegacy: legacyIdentity, removeLegacy: {})
            #expect(throws: AnisetteIdentityFailure.unavailable) {
                try store.reset(keepingIdentifier: false, removeLegacy: { throw CocoaError(.fileWriteNoPermission) })
            }
            let tombstone = try #require(try store.read())
            #expect(tombstone.phase == .reset); #expect(tombstone.identifier == nil); #expect(tombstone.blob == nil)
            #expect(!String(decoding: try #require(try files.read()), as: UTF8.self).contains(syntheticBlob.base64EncodedString()))
            #expect(throws: AnisetteIdentityFailure.staleResult) { try store.accept(Data([2]), for: old) }
            let next = try store.prepare(readLegacy: { Issue.record("Old pair resurrected"); return legacyIdentity() }, removeLegacy: {})
            #expect(next.generation != old.generation); #expect(next.identifier != old.identifier)
        }
    }
    @Test func blobResetKeepsIdentifierButChangesGeneration() async throws {
        try await use { store, _ async throws -> Void in
            let old = try store.prepare(readLegacy: legacyIdentity, removeLegacy: {})
            try store.reset(keepingIdentifier: true, removeLegacy: {})
            let next = try #require(try store.read())
            #expect(next.identifier == old.identifier); #expect(next.phase == .prepared)
            #expect(next.generation != old.generation); #expect(next.blob == nil)
            #expect(throws: AnisetteIdentityFailure.staleResult) { try store.accept(syntheticBlob, for: old) }
        }
    }
    @Test func corruptFutureAndOversizeRecordsRemainErrors() async throws {
        try await use { store, files async throws -> Void in
            try files.write(Data("not-json".utf8))
            #expect(throws: AnisetteIdentityFailure.invalidRecord) { try store.prepare(readLegacy: noLegacyIdentity, removeLegacy: {}) }
            let valid = try legacyIdentity().record()
            var fields = try JSONSerialization.jsonObject(with: JSONEncoder().encode(valid)) as! [String: Any]
            fields["schemaVersion"] = 99
            try files.write(JSONSerialization.data(withJSONObject: fields))
            #expect(throws: AnisetteIdentityFailure.unsupportedVersion) { try store.read() }
            #expect(throws: AnisetteIdentityFailure.unsupportedVersion) { try store.reset(keepingIdentifier: false, removeLegacy: {}) }
            #expect(throws: AnisetteIdentityFailure.invalidRecord) {
                try AnisetteIdentityRecord(phase: .ready, identifier: syntheticIdentity, blob: Data(repeating: 1, count: 32_769))
            }
        }
    }
    @Test func maximumBlobRoundTripsWithoutEnvelopeOverflow() async throws {
        try await use { store, files async throws -> Void in
            let record = try store.prepare(readLegacy: noLegacyIdentity, removeLegacy: {})
            let data = Data(repeating: 0xa5, count: AnisetteIdentityRecord.maximumBlobBytes)
            try store.accept(data, for: record)
            #expect(try store.read()?.blob == data); #expect(try #require(try files.read()).count <= 65_536)
        }
    }
    @Test func errorDoesNotRetainMaliciousIdentityInput() throws {
        let secret = "SYNTHETIC_PRIVATE_MALFORMED_IDENTITY"
        do {
            _ = try LegacyAnisetteIdentity(identifier: secret, blob: secret).record()
            Issue.record("Invalid identity accepted")
        } catch {
            #expect(error as? AnisetteIdentityFailure == .invalidRecord)
            #expect(!String(reflecting: error).contains(secret))
            #expect(!String(reflecting: (error as NSError).userInfo).contains(secret))
        }
    }
}

#if os(macOS) && canImport(Security)
@Suite("Anisette envelope on real system Keychain; synthetic blob, not Apple provisioning")
struct AnisetteIdentityKeychainTests {
    @Test func coherentPairAndResetReadBackFromSystem() throws {
        let item = try KeychainAuthenticationStorage(service: "org.tetherless.tests.anisette." + UUID().uuidString)
        defer { try? item.remove() }
        let store = VerifiedAnisetteIdentityStore(storage: item)
        _ = try store.prepare(readLegacy: legacyIdentity, removeLegacy: {})
        let reopened = VerifiedAnisetteIdentityStore(storage: item)
        #expect(try reopened.read()?.blob == syntheticBlob)
        #expect(try reopened.read()?.identifier == syntheticIdentity)
        try reopened.reset(keepingIdentifier: false, removeLegacy: {})
        #expect(try store.read()?.phase == .reset)
    }
}
#endif
