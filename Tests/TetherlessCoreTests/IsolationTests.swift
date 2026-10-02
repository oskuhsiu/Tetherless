import Foundation
import Testing
@testable import TetherlessCore

private let now = Date(timeIntervalSince1970: 1_800_000_000)
private let digest = String(repeating: "a", count: 64)
private func lease(_ id: String, manager: Bool = false, identity: String? = nil) throws -> AppLease {
    try AppLease(bundleID: id, isManager: manager, effectiveExpiry: now.addingTimeInterval(86_400 * 7), identityDigest: identity)
}
private actor IsolatedBackend: RenewalBackend {
    let value: RenewalSnapshot
    var preflightFailure: RenewalFailure?
    var faults: [String: RenewalFailure] = [:]
    var calls: [String] = []
    var snapshots = 0
    var reconciles = 0
    init(_ value: RenewalSnapshot) { self.value = value }
    func configure(preflight: RenewalFailure? = nil, faults: [String: RenewalFailure] = [:]) {
        preflightFailure = preflight; self.faults = faults
    }
    func snapshot() throws -> RenewalSnapshot {
        snapshots += 1
        if let preflightFailure { throw preflightFailure }
        return value
    }
    func refresh(_ app: AppLease) throws -> RenewalEvidence {
        calls.append(app.bundleID)
        if let fault = faults[app.bundleID] { throw fault }
        return RenewalEvidence(bundleID: app.bundleID, previousExpiry: app.effectiveExpiry,
            newExpiry: app.effectiveExpiry.addingTimeInterval(86_400), level: .deviceReadback, sameSigningIdentity: true)
    }
    func reconcile(_ pending: PendingRenewal) -> RenewalEvidence? { reconciles += 1; return nil }
}
private struct Fixture {
    let dir: URL
    let journal: FileRenewalJournal
    let backend: IsolatedBackend
    let engine: RenewalEngine
    init(_ snapshot: RenewalSnapshot) throws {
        dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        journal = FileRenewalJournal(url: dir.appendingPathComponent("state.json"))
        backend = IsolatedBackend(snapshot)
        let path = dir.appendingPathComponent("test.lock")
        engine = RenewalEngine(backend: backend, journal: journal, policy: try RenewalPolicy(), now: { now },
                               acquire: { try ProcessLease.acquire(at: path) })
    }
    func cleanup() { try? FileManager.default.removeItem(at: dir) }
}
@Suite("Fault isolation and durable preflight gates")
struct IsolationTests {
    @Test func brokenTargetDoesNotPreventManagerRenewal() async throws {
        let f = try Fixture(RenewalSnapshot(apps: [lease("test.manager", manager: true)],
                                           failures: ["test.broken": .needsForeground]))
        defer { f.cleanup() }
        let report = try await f.engine.run(trigger: .shortcut)
        #expect(report.verified == ["test.manager"])
        #expect(report.failures["test.broken"] == .needsForeground)
        #expect(try f.journal.load().records["test.broken"]?.requiresInteraction == true)
        #expect(report.observed[0].effectiveExpiry == now.addingTimeInterval(86_400 * 8))
    }
    @Test func changedTargetIdentityIsNotAnAccountBlocker() async throws {
        let f = try Fixture(RenewalSnapshot(apps: [lease("test.manager", manager: true), lease("test.a"), lease("test.b")]))
        defer { f.cleanup() }
        await f.backend.configure(faults: ["test.a": .identityChanged])
        let report = try await f.engine.run(trigger: .background)
        #expect(report.verified == ["test.manager", "test.b"])
        #expect(report.globalFailure == nil)
        let second = try await f.engine.run(trigger: .shortcut)
        #expect(second.failures["test.a"] == .identityChanged)
        #expect(second.deferred.count == 3)
    }
    @Test func preflightAuthFailureIsPersistedBeforeAnotherTrigger() async throws {
        let f = try Fixture(RenewalSnapshot(apps: [lease("test.manager", manager: true)]))
        defer { f.cleanup() }
        await f.backend.configure(preflight: .needsAuthentication)
        await #expect(throws: RenewalFailure.needsAuthentication) { try await f.engine.run(trigger: .shortcut) }
        let report = try await f.engine.run(trigger: .manual, force: true)
        #expect(report.globalFailure == .needsAuthentication)
        #expect(await f.backend.snapshots == 1)
        #expect(try f.journal.load().gate?.requiresInteraction == true)
    }
    @Test func preflightTemporaryFailureHonorsBackoff() async throws {
        let f = try Fixture(RenewalSnapshot(apps: [lease("test.manager", manager: true)]))
        defer { f.cleanup() }
        await f.backend.configure(preflight: .unavailable)
        await #expect(throws: RenewalFailure.unavailable) { try await f.engine.run(trigger: .shortcut) }
        _ = try await f.engine.run(trigger: .manual, force: true)
        #expect(await f.backend.snapshots == 1)
    }
    @Test func midRunAuthGatePreventsSubsequentPreflight() async throws {
        let f = try Fixture(RenewalSnapshot(apps: [lease("test.manager", manager: true), lease("test.b")]))
        defer { f.cleanup() }
        await f.backend.configure(faults: ["test.manager": .needsAuthentication])
        _ = try await f.engine.run(trigger: .shortcut)
        let second = try await f.engine.run(trigger: .manual, force: true)
        #expect(await f.backend.snapshots == 1)
        #expect(second.deferred.count == 2)
        #expect(second.globalFailure == .needsAuthentication)
    }
    @Test func changedPendingIdentityCannotBeReconciledAsSameBinary() async throws {
        let f = try Fixture(RenewalSnapshot(apps: [lease("test.app", identity: digest)]))
        defer { f.cleanup() }
        var state = RenewalState()
        var record = RenewalRecord()
        record.pending = PendingRenewal(id: UUID(), app: try lease("test.app", identity: String(repeating: "b", count: 64)), startedAt: now)
        state.records["test.app"] = record
        try f.journal.save(state)
        let report = try await f.engine.run(trigger: .shortcut)
        #expect(report.failures["test.app"] == .identityChanged)
        #expect(await f.backend.reconciles == 0)
        #expect(await f.backend.calls.isEmpty)
        #expect(try f.journal.load().records["test.app"]?.pending != nil)
    }
    @Test func budgetKeepsCompletedManagerAndReportsUnvisitedTargets() async throws {
        let f = try Fixture(RenewalSnapshot(apps: [lease("test.manager", manager: true), lease("test.a"), lease("test.b")]))
        defer { f.cleanup() }
        await f.backend.configure(faults: ["test.a": .budgetExhausted])
        let report = try await f.engine.run(trigger: .background)
        #expect(report.verified == ["test.manager"])
        #expect(report.globalFailure == .budgetExhausted)
        #expect(report.deferred == ["test.b"])
        #expect(try f.journal.load().records["test.manager"]?.outcome == .verified)
    }
    @Test func failureCannotAlsoBeAnEligibleLease() throws {
        #expect(throws: RenewalFailure.invalidEvidence) {
            try RenewalSnapshot(apps: [lease("test.app")], failures: ["test.app": .invalidEvidence]).validate()
        }
    }
    @Test func storageAndAccountFailuresCannotBeSilentlyDowngradedToOneApp() {
        for error in [RenewalFailure.storageUnavailable, .needsAuthentication, .needsPairing, .budgetExhausted] {
            #expect(throws: RenewalFailure.invalidEvidence) {
                try RenewalSnapshot(apps: [], failures: ["test.app": error]).validate()
            }
        }
    }
    @Test func oldJournalAndLeaseDecodeWithoutNewOptionalFields() throws {
        let state = try JSONDecoder().decode(RenewalState.self, from: Data(#"{"schemaVersion":1,"records":{}}"#.utf8))
        #expect(state.gate == nil)
        let old = try JSONDecoder().decode(AppLease.self, from: Data(#"{"bundleID":"test.app","isManager":false,"effectiveExpiry":0}"#.utf8))
        #expect(old.identityDigest == nil)
    }
    @Test func lockMustBeARegularFile() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        #expect(throws: RenewalFailure.lockUnavailable) { try ProcessLease.acquire(at: directory) }
    }
}
