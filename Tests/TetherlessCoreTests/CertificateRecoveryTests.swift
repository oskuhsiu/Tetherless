// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore

@Suite("Explicit certificate recovery: read-only checks, real durable journal, scripted portal")
struct CertificateRecoveryTests {
    let fixtures = CertificateIssuanceTests()
    func pending(_ store: CertificateIssuanceStore, _ backend: CertificateIssuanceTests.Backend,
                 phase: CertificateIssuanceRecord.Phase) throws -> CertificateIssuanceRecord {
        var record = CertificateIssuanceRecord(owner: try fixtures.owner(), material: try backend.prepare())
        try store.stage(record)
        if phase != .prepared {
            let old = record; record.phase = phase
            if phase == .issued { record.certificate = try backend.certificate() }
            try store.replace(expected: old, with: record)
        }
        return record
    }
    @Test func noPendingLocalReadDoesNotCreateAnything() async throws {
        try await fixtures.fixture { store, backend, storage in
            let observation = try CertificateRecoveryCoordinator(store: store).local(owner: fixtures.owner())
            #expect(observation.state == .none && observation.requestID == nil)
            #expect(try storage.read() == nil)
            #expect(backend.prepareCount == 0 && backend.submitCount == 0 && backend.fetchCount == 0)
        }
    }
    @Test(arguments: [CertificateIssuanceRecord.Phase.prepared, .submitted, .issued])
    func checkIsByteForByteReadOnly(_ phase: CertificateIssuanceRecord.Phase) async throws {
        try await fixtures.fixture { store, backend, storage in
            let record = try pending(store, backend, phase: phase)
            let before = try storage.read()
            backend.remote = [try backend.certificate()]
            let value = try await CertificateRecoveryCoordinator(store: store)
                .check(owner: fixtures.owner(), expectedID: record.id, backend: backend)
            #expect(value.requestID == record.id)
            #expect(value.state == (phase == .prepared ? .prepared : phase == .issued ? .issued : .available))
            #expect(try storage.read() == before)
            #expect(backend.prepareCount == 1 && backend.submitCount == 0 && backend.persistCount == 0)
            #expect(backend.fetchCount == (phase == .submitted ? 1 : 0))
        }
    }
    @Test func repeatedAbsentChecksNeverAuthorizeDiscardOrSubmission() async throws {
        try await fixtures.fixture { store, backend, storage in
            let record = try pending(store, backend, phase: .submitted)
            let before = try storage.read()
            let coordinator = CertificateRecoveryCoordinator(store: store)
            for _ in 0..<3 {
                let value = try await coordinator.check(owner: fixtures.owner(), expectedID: record.id, backend: backend)
                #expect(value.state == .awaitingPortal && !value.canDiscard && !value.canSubmit && !value.canSave)
            }
            #expect(throws: CertificateIssuanceFailure.staleAttempt) {
                try coordinator.discardPrepared(owner: fixtures.owner(), expectedID: record.id)
            }
            await #expect(throws: CertificateIssuanceFailure.staleAttempt) {
                try await coordinator.resolve(owner: fixtures.owner(), expectedID: record.id, action: .submitPrepared, backend: backend)
            }
            #expect(try storage.read() == before && backend.submitCount == 0 && backend.persistCount == 0)
        }
    }
    @Test func explicitPreparedSubmissionUsesTheSavedKeyOnce() async throws {
        try await fixtures.fixture { store, backend, _ in
            let record = try pending(store, backend, phase: .prepared)
            let coordinator = CertificateRecoveryCoordinator(store: store)
            await #expect(throws: CertificateIssuanceFailure.staleAttempt) {
                try await coordinator.resolve(owner: fixtures.owner(), expectedID: record.id, action: .saveExisting, backend: backend)
            }
            let cert = try await coordinator.resolve(owner: fixtures.owner(), expectedID: record.id, action: .submitPrepared, backend: backend)
            #expect(cert == backend.persisted && backend.prepareCount == 1 && backend.submitCount == 1)
            #expect(try store.read() == nil)
            await #expect(throws: CertificateIssuanceFailure.staleAttempt) {
                try await coordinator.resolve(owner: fixtures.owner(), expectedID: record.id, action: .submitPrepared, backend: backend)
            }
            #expect(backend.submitCount == 1)
        }
    }
    @Test func checkingAMatchDoesNotSaveUntilExplicitResolution() async throws {
        try await fixtures.fixture { store, backend, _ in
            let record = try pending(store, backend, phase: .submitted)
            backend.remote = [try backend.certificate()]
            let coordinator = CertificateRecoveryCoordinator(store: store)
            let check = try await coordinator.check(owner: fixtures.owner(), expectedID: record.id, backend: backend)
            #expect(check.canSave && backend.persisted == nil)
            #expect(try store.read() == record)
            _ = try await coordinator.resolve(owner: fixtures.owner(), expectedID: record.id, action: .saveExisting, backend: backend)
            #expect(backend.persistCount == 1 && backend.submitCount == 0 && backend.fetchCount == 2)
            #expect(try store.read() == nil)
        }
    }
    @Test func explicitDiscardOnlyRemovesAnUndispatchedRequest() async throws {
        try await fixtures.fixture { store, backend, _ in
            let record = try pending(store, backend, phase: .prepared)
            try CertificateRecoveryCoordinator(store: store).discardPrepared(owner: fixtures.owner(), expectedID: record.id)
            #expect(try store.read() == nil)
            #expect(backend.fetchCount == 0 && backend.submitCount == 0 && backend.persistCount == 0)
        }
    }
    @Test func checkErrorsRetainJournalAndKeys() async throws {
        try await fixtures.fixture { store, backend, storage in
            let record = try pending(store, backend, phase: .submitted)
            let before = try storage.read()
            let coordinator = CertificateRecoveryCoordinator(store: store)
            backend.fetchError = URLError(.timedOut)
            await #expect(throws: URLError.self) {
                try await coordinator.check(owner: fixtures.owner(), expectedID: record.id, backend: backend)
            }
            backend.fetchError = nil
            backend.remote = [try backend.certificate(), try backend.certificate(serial: "cd34")]
            await #expect(throws: CertificateIssuanceFailure.ambiguousMatch) {
                try await coordinator.check(owner: fixtures.owner(), expectedID: record.id, backend: backend)
            }
            #expect(try storage.read() == before && backend.persistCount == 0 && backend.submitCount == 0)
        }
    }
    @Test func wrongOwnerAndStaleConfirmationNeverCallPortal() async throws {
        try await fixtures.fixture { store, backend, storage in
            let record = try pending(store, backend, phase: .prepared)
            let before = try storage.read()
            let coordinator = CertificateRecoveryCoordinator(store: store)
            for owner in [try fixtures.owner("other"), try fixtures.owner(team: "OTHER"), try fixtures.owner(type: "distribution")] {
                await #expect(throws: CertificateIssuanceFailure.staleAttempt) {
                    try await coordinator.check(owner: owner, expectedID: record.id, backend: backend)
                }
                #expect(throws: CertificateIssuanceFailure.staleAttempt) { try coordinator.discardPrepared(owner: owner, expectedID: record.id) }
            }
            await #expect(throws: CertificateIssuanceFailure.staleAttempt) {
                try await coordinator.resolve(owner: fixtures.owner(), expectedID: UUID(), action: .submitPrepared, backend: backend)
            }
            #expect(try storage.read() == before && backend.fetchCount == 0 && backend.submitCount == 0)
        }
    }
    @Test func corruptRecordCannotBeCheckedOrDiscardedAsMissing() async throws {
        try await fixtures.fixture { store, backend, storage in
            let bytes = Data("corrupt".utf8); try storage.write(bytes)
            let coordinator = CertificateRecoveryCoordinator(store: store)
            #expect(throws: CertificateIssuanceFailure.invalidRecord) { try coordinator.local(owner: fixtures.owner()) }
            await #expect(throws: CertificateIssuanceFailure.invalidRecord) {
                try await coordinator.check(owner: fixtures.owner(), expectedID: UUID(), backend: backend)
            }
            #expect(try storage.read() == bytes && backend.fetchCount == 0)
        }
    }
}

extension CertificateRecoveryTests {
    /// Conforms to the read-only capability alone; cannot submit or persist.
    struct Lookup: CertificateIssuanceLookup {
        let backend: CertificateIssuanceTests.Backend
        let duringFetch: @Sendable () throws -> Void
        func validate(_ material: CertificateRequestMaterial) throws { try backend.validate(material) }
        func validate(_ certificate: IssuedCertificate, for material: CertificateRequestMaterial) throws {
            try backend.validate(certificate, for: material)
        }
        func fetchCertificates() async throws -> [IssuedCertificate] {
            try duringFetch()
            return try await backend.fetchCertificates()
        }
    }
    @Test func staleLookupCannotPublishAnObservationForAReplacedRequest() async throws {
        try await fixtures.fixture { store, backend, _ in
            let record = try pending(store, backend, phase: .submitted)
            let replacement = CertificateIssuanceRecord(owner: record.owner, material: record.material)
            let lookup = Lookup(backend: backend) { try store.replace(expected: record, with: replacement) }
            await #expect(throws: CertificateIssuanceFailure.staleAttempt) {
                try await CertificateRecoveryCoordinator(store: store).check(owner: record.owner, expectedID: record.id, backend: lookup)
            }
            #expect(try store.read() == replacement && backend.persistCount == 0 && backend.submitCount == 0)
        }
    }
    @Test func cancellationDuringCheckLeavesOriginalJournalUnchanged() async throws {
        try await fixtures.fixture { store, backend, storage in
            let record = try pending(store, backend, phase: .submitted)
            let before = try storage.read()
            let lookup = Lookup(backend: backend) { withUnsafeCurrentTask { $0?.cancel() } }
            let task = Task {
                try await CertificateRecoveryCoordinator(store: store).check(owner: record.owner, expectedID: record.id, backend: lookup)
            }
            await #expect(throws: CancellationError.self) { try await task.value }
            #expect(try storage.read() == before && backend.persistCount == 0 && backend.submitCount == 0)
        }
    }
    @Test func explicitSaveFailureKeepsIssuedRequestForRetry() async throws {
        try await fixtures.fixture { store, backend, storage in
            let record = try pending(store, backend, phase: .issued)
            let before = try storage.read()
            backend.persistError = AuthenticationStorageFailure.unavailable
            await #expect(throws: AuthenticationStorageFailure.unavailable) {
                try await CertificateRecoveryCoordinator(store: store)
                    .resolve(owner: record.owner, expectedID: record.id, action: .saveExisting, backend: backend)
            }
            #expect(try storage.read() == before && backend.submitCount == 0 && backend.fetchCount == 0)
        }
    }
    @Test func failedDiscardReadbackIsNotReportedAsSuccess() async throws {
        try await fixtures.fixture { store, backend, _ in
            let record = try pending(store, backend, phase: .prepared)
            backend.storage.dropPhase = "empty"
            #expect(throws: AuthenticationStorageFailure.readbackMismatch) {
                try CertificateRecoveryCoordinator(store: store).discardPrepared(owner: record.owner, expectedID: record.id)
            }
            #expect(try store.read() == record && backend.submitCount == 0)
        }
    }
}

extension CertificateIssuanceTests.Backend: CertificateIssuanceLookup {}
