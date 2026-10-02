// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore

@Suite("Certificate issuance: production state machine, scripted server, real durable files")
struct CertificateIssuanceTests {
    final class Storage: AuthenticationRecordStorage, @unchecked Sendable {
        let files: PrivateFileStore
        var failPhase: String?
        var dropPhase: String?
        init(root: URL) throws { files = try PrivateFileStore(root: root, maximumBytes: 65_536); try files.prepare() }
        func read() throws -> Data? { try files.read("request") }
        func write(_ data: Data) throws {
            // Select a semantic phase, never a substring sensitive to JSON key
            // ordering. Malformed bytes remain writable for corruption tests.
            let envelope = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            let pending = envelope?["pending"] as? [String: Any]
            let phase = pending?["phase"] as? String ?? (envelope != nil ? "empty" : "malformed")
            if failPhase == phase { throw AuthenticationStorageFailure.unavailable }
            if dropPhase == phase { return }
            try files.write(data, named: "request")
        }
    }
    final class Backend: CertificateIssuanceBackend, @unchecked Sendable {
        let storage: Storage
        var prepareCount = 0, submitCount = 0, fetchCount = 0, persistCount = 0
        var remote: [IssuedCertificate] = []
        var persisted: IssuedCertificate?
        var submissionError: Error?
        var fetchError: Error?
        var persistError: Error?
        var acceptBeforeError = false
        var badResponse = false
        init(_ storage: Storage) { self.storage = storage }
        func prepare() throws -> CertificateRequestMaterial {
            prepareCount += 1
            return try .init(machineName: "Tetherless synthetic", privateKeyPEM: Data("not-a-real-private-key".utf8),
                             csrPEM: Data("not-a-real-csr".utf8), publicKey: Data([1,2,3]))
        }
        func validate(_ material: CertificateRequestMaterial) throws { try material.validate() }
        func certificate(_ key: Data = Data([1,2,3]), serial: String = "ab12") throws -> IssuedCertificate {
            try .init(serial: serial, der: Data("synthetic-public-certificate".utf8), publicKey: key)
        }
        func submit(_ record: CertificateIssuanceRecord) async throws -> IssuedCertificate {
            submitCount += 1
            // This asserts the actual durable bytes at the mutation boundary.
            let readback = try CertificateIssuanceStore(storage: storage).read()
            #expect(readback == record)
            #expect(readback?.phase == .submitted)
            if let submissionError {
                if acceptBeforeError { remote.append(try certificate()) }
                throw submissionError
            }
            let cert = try certificate(badResponse ? Data([9]) : Data([1,2,3]))
            remote.append(cert); return cert
        }
        func fetchCertificates() async throws -> [IssuedCertificate] {
            fetchCount += 1
            if let fetchError { throw fetchError }
            return remote
        }
        func validate(_ certificate: IssuedCertificate, for material: CertificateRequestMaterial) throws {
            try certificate.validate()
            guard certificate.publicKey == material.publicKey else { throw CertificateIssuanceFailure.keyMismatch }
        }
        func persist(_ certificate: IssuedCertificate, material: CertificateRequestMaterial) throws {
            persistCount += 1
            if let persistError { throw persistError }
            persisted = certificate
        }
    }
    func owner(_ account: String = "123", team: String = "TEAM123", type: String = "development") throws -> CertificateIssuanceOwner {
        try .init(accountID: account, teamID: team, certificateType: type)
    }
    func fixture(_ body: (CertificateIssuanceStore, Backend, Storage) async throws -> Void) async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let storage = try Storage(root: root)
        try await body(CertificateIssuanceStore(storage: storage), Backend(storage), storage)
    }
    @Test func faultInjectionUsesSemanticPhaseRegardlessOfJSONKeyOrder() async throws {
        try await fixture { (_, _, storage) async throws in
            storage.failPhase = "empty"
            // These are testing the fault injector, not a valid production record.
            let first = Data(#"{"schemaVersion":1,"pending":{"phase":"issued"}}"#.utf8)
            let reordered = Data(#"{"pending":{"phase":"issued"},"schemaVersion":1}"#.utf8)
            try storage.write(first)
            try storage.write(reordered)
            #expect(throws: AuthenticationStorageFailure.unavailable) {
                try storage.write(Data(#"{"schemaVersion":1}"#.utf8))
            }
            #expect(try storage.read() == reordered)
        }
    }
    @Test func keyAndRequestAreDurableBeforeRemoteMutationAndClearedOnlyAfterSave() async throws {
        try await fixture { (store, backend, storage) async throws in
            let result = try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend)
            #expect(result == backend.persisted)
            #expect(backend.submitCount == 1 && backend.persistCount == 1)
            #expect(try store.read() == nil)
            let saved = try storage.read()
            let bytes = try #require(saved)
            #expect(!String(decoding: bytes, as: UTF8.self).contains("privateKeyPEM"))
        }
    }
    @Test func lostAcceptedResponseIsRecoveredWithoutAnotherCreateOrKey() async throws {
        try await fixture { (store, backend, _) async throws in
            backend.submissionError = URLError(.timedOut); backend.acceptBeforeError = true
            await #expect(throws: URLError.self) {
                try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend)
            }
            #expect(try store.read()?.phase == .submitted)
            backend.submissionError = nil
            let result = try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend)
            #expect(result == backend.persisted)
            #expect(backend.prepareCount == 1 && backend.submitCount == 1 && backend.fetchCount == 1)
        }
    }
    @Test func uncertainButAbsentResultNeverAutomaticallySubmitsAgain() async throws {
        try await fixture { (store, backend, _) async throws in
            backend.submissionError = URLError(.networkConnectionLost)
            await #expect(throws: URLError.self) {
                try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend)
            }
            for _ in 0..<3 {
                await #expect(throws: CertificateIssuanceFailure.awaitingPortalVisibility) {
                    try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend)
                }
            }
            #expect(backend.submitCount == 1 && backend.prepareCount == 1)
            #expect(try store.read()?.phase == .submitted)
        }
    }
    @Test(arguments: [CertificateIssuanceFailure.capacityReached, .requestRejected])
    func onlyDefinitiveServerRejectionClearsRequest(_ error: CertificateIssuanceFailure) async throws {
        try await fixture { (store, backend, _) async throws in
            backend.submissionError = error
            await #expect(throws: error) { try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend) }
            #expect(try store.read() == nil)
            #expect(backend.persistCount == 0)
        }
    }
    @Test func failedPersistKeepsIssuedKeyAndRecoveryDoesNotNeedAnotherServerCall() async throws {
        try await fixture { (store, backend, _) async throws in
            backend.persistError = AuthenticationStorageFailure.unavailable
            await #expect(throws: AuthenticationStorageFailure.unavailable) {
                try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend)
            }
            #expect(try store.read()?.phase == .issued)
            backend.persistError = nil
            _ = try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend, allowNew: false)
            #expect(backend.submitCount == 1 && backend.fetchCount == 0 && backend.persistCount == 2)
        }
    }
    @Test func mismatchingReturnedPublicKeyRetainsUncertainRequest() async throws {
        try await fixture { (store, backend, _) async throws in
            backend.badResponse = true
            await #expect(throws: CertificateIssuanceFailure.keyMismatch) {
                try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend)
            }
            #expect(try store.read()?.phase == .submitted)
            #expect(backend.persistCount == 0)
        }
    }
    @Test func multipleMatchingCertificatesNeverPickFirst() async throws {
        try await fixture { (store, backend, _) async throws in
            var record = CertificateIssuanceRecord(owner: try owner(), material: try backend.prepare())
            try store.stage(record); let previous = record; record.phase = .submitted
            try store.replace(expected: previous, with: record)
            backend.remote = [try backend.certificate(), try backend.certificate(serial: "cd34")]
            await #expect(throws: CertificateIssuanceFailure.ambiguousMatch) {
                try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend)
            }
            #expect(backend.submitCount == 0 && backend.persistCount == 0)
        }
    }
    @Test func stageAndPreSubmitWriteFailuresNeverSendAnything() async throws {
        for phase in ["prepared", "submitted"] {
            try await fixture { (store, backend, storage) async throws in
                storage.failPhase = phase
                await #expect(throws: AuthenticationStorageFailure.unavailable) {
                    try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend)
                }
                #expect(backend.submitCount == 0)
            }
        }
    }
    @Test func ignoredStageWriteCannotReachRemoteMutation() async throws {
        try await fixture { (store, backend, storage) async throws in
            storage.dropPhase = "prepared"
            await #expect(throws: AuthenticationStorageFailure.readbackMismatch) {
                try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend)
            }
            #expect(backend.submitCount == 0)
        }
    }
    @Test func issuedJournalWriteFailureRecoversByQueryInsteadOfCreatingAgain() async throws {
        try await fixture { (store, backend, storage) async throws in
            storage.failPhase = "issued"
            await #expect(throws: AuthenticationStorageFailure.unavailable) {
                try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend)
            }
            storage.failPhase = nil
            _ = try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend)
            #expect(backend.submitCount == 1 && backend.fetchCount == 1)
        }
    }
    @Test func completionWriteFailureRetainsIssuedRequest() async throws {
        try await fixture { (store, backend, storage) async throws in
            storage.failPhase = "empty"
            await #expect(throws: AuthenticationStorageFailure.unavailable) {
                try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend)
            }
            #expect(try store.read()?.phase == .issued)
            storage.failPhase = nil
            _ = try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend)
            #expect(backend.submitCount == 1)
        }
    }
    @Test func recoverOnlyWithNoPendingIsReadOnly() async throws {
        try await fixture { (store, backend, storage) async throws in
            let result = try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend, allowNew: false)
            #expect(result == nil && backend.prepareCount == 0 && backend.submitCount == 0)
            #expect(try storage.read() == nil)
        }
    }
    @Test func wrongAccountTeamOrTypeCannotResumeRequest() async throws {
        try await fixture { (store, backend, _) async throws in
            let record = CertificateIssuanceRecord(owner: try owner(), material: try backend.prepare()); try store.stage(record)
            for other in [try owner("456"), try owner(team: "OTHER"), try owner(type: "distribution")] {
                await #expect(throws: CertificateIssuanceFailure.staleAttempt) {
                    try await CertificateIssuanceCoordinator(store: store).issue(owner: other, backend: backend)
                }
            }
            #expect(backend.submitCount == 0 && backend.fetchCount == 0)
            #expect(try store.read() == record)
        }
    }
    @Test func corruptedOrFutureEnvelopeIsNotReplaced() async throws {
        for text in ["corrupt", "{\"schemaVersion\":99}", "{\"schemaVersion\":1,\"pending\":{}}"] {
            try await fixture { (store, backend, storage) async throws in
                try storage.write(Data(text.utf8))
                await #expect(throws: CertificateIssuanceFailure.self) {
                    try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend)
                }
                #expect(try storage.read() == Data(text.utf8))
                #expect(backend.prepareCount == 0)
            }
        }
    }
    @Test func staleCompletionCannotEraseAnotherGeneration() async throws {
        try await fixture { (store, backend, _) async throws in
            let first = CertificateIssuanceRecord(owner: try owner(), material: try backend.prepare())
            try store.stage(first)
            let second = CertificateIssuanceRecord(owner: try owner(), material: try backend.prepare())
            try store.replace(expected: first, with: second)
            #expect(throws: CertificateIssuanceFailure.staleAttempt) { try store.replace(expected: first, with: nil) }
            #expect(try store.read() == second)
        }
    }
    @Test func cancelledBeforeStartCreatesNothing() async throws {
        try await fixture { (store, backend, _) async throws in
            let task = Task {
                withUnsafeCurrentTask { $0?.cancel() }
                return try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend)
            }
            await #expect(throws: CancellationError.self) { try await task.value }
            #expect(try store.read() == nil && backend.submitCount == 0)
        }
    }
    @Test func failedLookupPreservesPendingKey() async throws {
        try await fixture { (store, backend, _) async throws in
            backend.submissionError = URLError(.timedOut)
            await #expect(throws: URLError.self) { try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend) }
            let previous = try store.read()
            backend.fetchError = AuthenticationStorageFailure.notReady
            await #expect(throws: AuthenticationStorageFailure.notReady) { try await CertificateIssuanceCoordinator(store: store).issue(owner: owner(), backend: backend) }
            #expect(try store.read() == previous && backend.submitCount == 1)
        }
    }
}
