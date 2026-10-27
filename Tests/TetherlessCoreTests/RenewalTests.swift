import Foundation
import Testing
@testable import TetherlessCore

private let epoch = Date(timeIntervalSince1970: 1_800_000_000)
private func app(_ id: String = "test.app", manager: Bool = false, days: Double = 7) throws -> AppLease {
    try AppLease(bundleID: id, isManager: manager, effectiveExpiry: epoch.addingTimeInterval(days * 86_400))
}

@Suite("Renewal policy")
struct PolicyTests {
    @Test func dayOneIsDueWithSixDaysRemaining() throws {
        let policy = try RenewalPolicy()
        var record = RenewalRecord()
        record.lastAppliedAt = epoch
        #expect(!policy.isDue(app: try app(), record: record, now: epoch.addingTimeInterval(86_399)))
        #expect(policy.isDue(app: try app(), record: record, now: epoch.addingTimeInterval(86_400)))
    }
    @Test func acceleratedCadenceDoesNotChangeSignedExpiry() throws {
        let policy = try RenewalPolicy(interval: 7_200)
        let original = try app()
        var record = RenewalRecord()
        record.lastAppliedAt = epoch
        #expect(policy.isDue(app: original, record: record, now: epoch.addingTimeInterval(7_200)))
        #expect(original.effectiveExpiry == epoch.addingTimeInterval(7 * 86_400))
    }
    @Test func urgentDoesNotIgnoreRetryAfter() throws {
        var record = RenewalRecord()
        record.retryAfter = epoch.addingTimeInterval(900)
        #expect(try !RenewalPolicy().isDue(app: app(days: 0.1), record: record, now: epoch))
    }
    @Test func urgentDoesNotIgnoreInteraction() throws {
        var record = RenewalRecord()
        record.requiresInteraction = true
        #expect(try !RenewalPolicy().isDue(app: app(days: 0.1), record: record, now: epoch))
    }
    @Test func urgentThrottlesRepeatedTriggers() throws {
        var record = RenewalRecord()
        record.lastAttemptAt = epoch
        let policy = try RenewalPolicy()
        #expect(!policy.isDue(app: try app(days: 2), record: record, now: epoch.addingTimeInterval(60)))
        #expect(policy.isDue(app: try app(days: 2), record: record, now: epoch.addingTimeInterval(3_600)))
    }
    @Test func managerFirstThenEarliestExpiry() throws {
        let ordered = try RenewalPolicy().ordered([
            app("test.b", days: 1), app("test.manager", manager: true), app("test.a", days: 1)
        ])
        #expect(ordered.map(\.bundleID) == ["test.manager", "test.a", "test.b"])
    }
    @Test func duplicateIDsAreRejected() throws {
        #expect(throws: RenewalFailure.invalidInput) { try RenewalPolicy().ordered([app(), app()]) }
    }
    @Test func multipleManagersRejected() throws {
        #expect(throws: RenewalFailure.invalidInput) {
            try RenewalPolicy().ordered([app("test.a", manager: true), app("test.b", manager: true)])
        }
    }
    @Test(arguments: [0.0, -1, .nan, .infinity, 59]) func rejectsInvalidIntervals(_ value: Double) {
        #expect(throws: RenewalFailure.invalidInput) { try RenewalPolicy(interval: value) }
    }
    @Test func retryBackoffIsBounded() throws {
        let policy = try RenewalPolicy()
        #expect(policy.retryDate(failures: 0, now: epoch) == epoch.addingTimeInterval(900))
        #expect(policy.retryDate(failures: Int.max, now: epoch) == epoch.addingTimeInterval(43_200))
    }
    @Test func rollbackReevaluatesButDoesNotBypassRateLimit() throws {
        var record = RenewalRecord()
        record.lastAppliedAt = epoch.addingTimeInterval(86_400)
        #expect(try RenewalPolicy().isDue(app: app(), record: record, now: epoch))
        record.retryAfter = epoch.addingTimeInterval(900)
        #expect(try !RenewalPolicy().isDue(app: app(), record: record, now: epoch))
    }
}

@Suite("Profile evidence, not countdown UI")
struct EvidenceTests {
    @Test func rejectsUnchangedExpiry() throws {
        let a = try app()
        let evidence = RenewalEvidence(bundleID: a.bundleID, previousExpiry: a.effectiveExpiry,
            newExpiry: a.effectiveExpiry, level: .deviceReadback, sameSigningIdentity: true)
        #expect(throws: RenewalFailure.noExtension) { try evidence.validate(for: a, now: epoch) }
    }
    @Test func wrongAppCannotBeSuccess() throws {
        let a = try app()
        let e = RenewalEvidence(bundleID: "wrong.app", previousExpiry: a.effectiveExpiry,
            newExpiry: a.effectiveExpiry.addingTimeInterval(86_400), level: .applied, sameSigningIdentity: true)
        #expect(throws: RenewalFailure.invalidEvidence) { try e.validate(for: a, now: epoch) }
    }
    @Test func identityRotationIsNotNormalRefresh() throws {
        let a = try app()
        let e = RenewalEvidence(bundleID: a.bundleID, previousExpiry: a.effectiveExpiry,
            newExpiry: a.effectiveExpiry.addingTimeInterval(86_400), level: .applied, sameSigningIdentity: false)
        #expect(throws: RenewalFailure.identityChanged) { try e.validate(for: a, now: epoch) }
    }
    @Test func staleBeforeSnapshotRejected() throws {
        let a = try app()
        let e = RenewalEvidence(bundleID: a.bundleID, previousExpiry: epoch,
            newExpiry: a.effectiveExpiry.addingTimeInterval(86_400), level: .deviceReadback, sameSigningIdentity: true)
        #expect(throws: RenewalFailure.invalidEvidence) { try e.validate(for: a, now: epoch) }
    }
    @Test func mainProfileMustNotBeDictionaryFirst() throws {
        #expect(try ProfileSelection.requireMainProfile(in: ["ext": 1, "main": 2], bundleID: "main") == 2)
        #expect(throws: RenewalFailure.invalidEvidence) {
            try ProfileSelection.requireMainProfile(in: ["ext": 1], bundleID: "main")
        }
    }
    private func profile(_ id: String, component: String, days: Double,
                         team: String = "TEAM", cert: String = "CERT", validated: Bool = true) -> ProfileCandidate {
        ProfileCandidate(id: id, componentID: component, teamID: team, certificateID: cert,
            notBefore: epoch, expiry: epoch.addingTimeInterval(days * 86_400),
            validatedForInstalledBinary: validated)
    }
    @Test func latestApplicableProfilePerComponentThenMinimum() throws {
        let expiry = try ProfileSelection.effectiveExpiry(requiredComponents: ["main", "ext"], teamID: "TEAM",
            certificateID: "CERT", certificateExpiry: epoch.addingTimeInterval(365 * 86_400),
            candidates: [profile("old", component: "main", days: 1), profile("new", component: "main", days: 7),
                         profile("extension", component: "ext", days: 6)], now: epoch)
        #expect(expiry == epoch.addingTimeInterval(6 * 86_400))
    }
    @Test func certificateDeadlineCapsProfileDeadline() throws {
        let expiry = try ProfileSelection.effectiveExpiry(requiredComponents: ["main"], teamID: "TEAM",
            certificateID: "CERT", certificateExpiry: epoch.addingTimeInterval(2 * 86_400),
            candidates: [profile("p", component: "main", days: 7)], now: epoch)
        #expect(expiry == epoch.addingTimeInterval(2 * 86_400))
    }
    @Test func cannotIgnoreMissingExtension() {
        #expect(throws: RenewalFailure.invalidEvidence) {
            try ProfileSelection.effectiveExpiry(requiredComponents: ["main", "ext"], teamID: "TEAM",
                certificateID: "CERT", certificateExpiry: epoch.addingTimeInterval(365 * 86_400),
                candidates: [profile("p", component: "main", days: 7)], now: epoch)
        }
    }
    @Test func wrongTeamAndUnvalidatedProfilesAreNotEligible() {
        #expect(throws: RenewalFailure.invalidEvidence) {
            try ProfileSelection.effectiveExpiry(requiredComponents: ["main"], teamID: "TEAM",
                certificateID: "CERT", certificateExpiry: epoch.addingTimeInterval(365 * 86_400),
                candidates: [profile("p", component: "main", days: 7, team: "OTHER"),
                             profile("q", component: "main", days: 7, validated: false)], now: epoch)
        }
    }
}

private final class MemoryJournal: RenewalJournal, @unchecked Sendable {
    private let lock = NSLock()
    private var value = RenewalState()
    private var saves = 0
    var failingSave: Int? // Set before running an engine, never during a run.
    func load() -> RenewalState { lock.withLock { value } }
    func save(_ state: RenewalState) throws {
        try lock.withLock {
            saves += 1
            if saves == failingSave { throw RenewalFailure.storageUnavailable }
            value = state
        }
    }
}

/// Scripted test double only. These results are NEVER real-device evidence.
private actor ScriptedBackend: RenewalBackend {
    let apps: [AppLease]
    var calls: [String] = []
    var recoveryCalls = 0
    var failure: RenewalFailure?
    var evidenceLevel: EvidenceLevel = .deviceReadback
    var advance: TimeInterval = 86_400
    var recoveryApplied = true
    var blocked = false
    var continuation: CheckedContinuation<Void, Never>?
    init(apps: [AppLease]) { self.apps = apps }
    func configure(failure: RenewalFailure? = nil, level: EvidenceLevel = .deviceReadback,
                   advance: TimeInterval = 86_400, blocked: Bool = false) {
        self.failure = failure; evidenceLevel = level; self.advance = advance; self.blocked = blocked
    }
    func snapshot() -> RenewalSnapshot { RenewalSnapshot(apps: apps) }
    func refresh(_ app: AppLease) async throws -> RenewalEvidence {
        calls.append(app.bundleID)
        if blocked { await withCheckedContinuation { continuation = $0 } }
        if let failure { throw failure }
        return RenewalEvidence(bundleID: app.bundleID, previousExpiry: app.effectiveExpiry,
            newExpiry: app.effectiveExpiry.addingTimeInterval(advance),
            level: evidenceLevel, sameSigningIdentity: true)
    }
    func reconcile(_ pending: PendingRenewal) -> RenewalEvidence? {
        recoveryCalls += 1
        guard recoveryApplied else { return nil }
        return RenewalEvidence(bundleID: pending.app.bundleID, previousExpiry: pending.app.effectiveExpiry,
            newExpiry: pending.app.effectiveExpiry.addingTimeInterval(advance),
            level: .deviceReadback, sameSigningIdentity: true)
    }
    func release() { continuation?.resume(); continuation = nil }
    func hasStarted() -> Bool { continuation != nil }
}

private struct Harness {
    let directory: URL
    let journal = MemoryJournal()
    let backend: ScriptedBackend
    let engine: RenewalEngine
    init(apps: [AppLease]) throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        backend = ScriptedBackend(apps: apps)
        let lockURL = directory.appendingPathComponent("renewal.lock")
        engine = RenewalEngine(backend: backend, journal: journal, policy: try RenewalPolicy(),
            now: { epoch }, acquire: { try ProcessLease.acquire(at: lockURL) })
    }
    func cleanup() { try? FileManager.default.removeItem(at: directory) }
}

@Suite("Coordinator fault injection")
struct EngineTests {
    @Test func verifiedOnlyAfterDurableSave() async throws {
        let h = try Harness(apps: [app()]); defer { h.cleanup() }
        let r = try await h.engine.run(trigger: .shortcut)
        #expect(r.verified == ["test.app"])
        #expect(h.journal.load().records["test.app"]?.lastVerifiedAt == epoch)
        #expect(h.journal.load().records["test.app"]?.pending == nil)
    }
    @Test func appliedDoesNotBecomeVerified() async throws {
        let h = try Harness(apps: [app()]); defer { h.cleanup() }
        await h.backend.configure(level: .applied)
        let r = try await h.engine.run(trigger: .shortcut)
        #expect(r.verified.isEmpty)
        #expect(r.appliedUnverified == ["test.app"])
        #expect(h.journal.load().records["test.app"]?.lastVerifiedAt == nil)
    }
    @Test func unchangedProfileIsNotSuccessful() async throws {
        let h = try Harness(apps: [app()]); defer { h.cleanup() }
        await h.backend.configure(advance: 0)
        let r = try await h.engine.run(trigger: .shortcut)
        #expect(r.verified.isEmpty)
        #expect(r.failures["test.app"] == .noExtension)
        #expect(h.journal.load().records["test.app"]?.outcome == .checkedNotExtended)
    }
    @Test func writeAheadFailurePreventsDeviceMutation() async throws {
        let h = try Harness(apps: [app()]); defer { h.cleanup() }
        h.journal.failingSave = 1
        await #expect(throws: RenewalFailure.storageUnavailable) { try await h.engine.run(trigger: .shortcut) }
        #expect(await h.backend.calls.isEmpty)
    }
    @Test func commitFailureLeavesPendingAndNextRunReconcilesWithoutRefreshing() async throws {
        let h = try Harness(apps: [app()]); defer { h.cleanup() }
        h.journal.failingSave = 2
        await #expect(throws: RenewalFailure.storageUnavailable) { try await h.engine.run(trigger: .shortcut) }
        #expect(h.journal.load().records["test.app"]?.pending != nil)
        #expect(h.journal.load().records["test.app"]?.lastVerifiedAt == nil)
        let r = try await h.engine.run(trigger: .background)
        #expect(r.verified == ["test.app"])
        #expect(await h.backend.calls.count == 1)
        #expect(await h.backend.recoveryCalls == 1)
    }
    @Test func duplicateShortcutDoesNotRepeatWork() async throws {
        let h = try Harness(apps: [app()]); defer { h.cleanup() }
        _ = try await h.engine.run(trigger: .shortcut)
        let r = try await h.engine.run(trigger: .background)
        #expect(r.deferred == ["test.app"])
        #expect(await h.backend.calls.count == 1)
    }
    @Test func authenticationFailureStopsBatchAndRequiresExplicitRepair() async throws {
        let h = try Harness(apps: [app("test.user"), app("test.manager", manager: true)])
        defer { h.cleanup() }
        await h.backend.configure(failure: .needsAuthentication)
        let r = try await h.engine.run(trigger: .shortcut)
        #expect(r.failures["test.manager"] == .needsAuthentication)
        #expect(await h.backend.calls == ["test.manager"])
        #expect(h.journal.load().records["test.manager"]?.requiresInteraction == true)
        let second = try await h.engine.run(trigger: .shortcut, force: true)
        #expect(second.attempted.isEmpty)
        #expect(second.deferred.count == 2)
        #expect(await h.backend.calls == ["test.manager"])
    }
    @Test func reentrancyIsRejectedAndCancellationKeepsRecoveryRecord() async throws {
        let h = try Harness(apps: [app()]); defer { h.cleanup() }
        await h.backend.configure(blocked: true)
        let task = Task { try await h.engine.run(trigger: .shortcut) }
        for _ in 0..<10_000 {
            if await h.backend.hasStarted() { break }
            await Task.yield()
        }
        #expect(await h.backend.hasStarted())
        await #expect(throws: RenewalFailure.busy) { try await h.engine.run(trigger: .background) }
        task.cancel()
        await h.backend.release()
        await #expect(throws: CancellationError.self) { try await task.value }
        #expect(h.journal.load().records["test.app"]?.pending != nil)
        // Cancellation preserves pending, and backoff is not bypassed by force.
        let deferred = try await h.engine.run(trigger: .shortcut, force: true)
        #expect(deferred.deferred == ["test.app"])
        // Simulate arrival of the next retry window without changing a device clock.
        var state = h.journal.load()
        state.records["test.app"]?.retryAfter = nil
        try h.journal.save(state)
        let r = try await h.engine.run(trigger: .shortcut)
        #expect(r.verified == ["test.app"])
    }
}

@Suite("Real filesystem, not mocks")
struct PersistenceTests {
    @Test func fileRoundtripAndCorruptionFailsClosed() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let j = FileRenewalJournal(url: dir.appendingPathComponent("state.json"))
        var state = RenewalState()
        state.records["test.app"] = RenewalRecord()
        try j.save(state)
        #expect(try j.load() == state)
        try Data("{broken".utf8).write(to: j.url)
        #expect(throws: RenewalFailure.corruptJournal) { try j.load() }
    }
    @Test func lockExcludesIndependentDescriptorsAndCanBeReacquired() throws {
        let path = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: path) }
        let first = try ProcessLease.acquire(at: path)
        #expect(throws: RenewalFailure.busy) { try ProcessLease.acquire(at: path) }
        first.release(); first.release()
        let second = try ProcessLease.acquire(at: path)
        second.release()
        #expect(FileManager.default.fileExists(atPath: path.path))
    }
    @Test func futureSchemaIsNotSilentlyReset() throws {
        let path = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: path) }
        try Data(#"{"schemaVersion":2,"records":{}}"#.utf8).write(to: path)
        #expect(throws: RenewalFailure.unsupportedJournal) { try FileRenewalJournal(url: path).load() }
    }
    #if os(Linux) || os(macOS)
    @Test func processLockReallyExcludesAnotherProcess() throws {
        let path = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: path) }
        let lease = try ProcessLease.acquire(at: path); defer { lease.release() }
        let child = Process()
        child.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        child.arguments = ["python3", "-c", "import sys,fcntl; f=open(sys.argv[1], 'a');\ntry: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\nexcept BlockingIOError: sys.exit(0)\nelse: sys.exit(19)", path.path]
        try child.run(); child.waitUntilExit()
        #expect(child.terminationStatus == 0)
    }
    #endif
}

@Suite("Journal validation")
struct JournalValidationTests {
    @Test func malformedDecodedBundleIDFailsClosed() throws {
        var state = RenewalState()
        state.records["../escape"] = RenewalRecord()
        #expect(throws: RenewalFailure.corruptJournal) { try state.validate() }
    }
    @Test func absurdFailureCountFailsClosed() throws {
        var state = RenewalState()
        var record = RenewalRecord()
        record.consecutiveFailures = Int.max
        state.records["test.app"] = record
        #expect(throws: RenewalFailure.corruptJournal) { try state.validate() }
    }
    @Test func pendingCannotBelongToAnotherApp() throws {
        var state = RenewalState()
        var record = RenewalRecord()
        record.pending = PendingRenewal(id: UUID(), app: try app("test.other"), startedAt: epoch)
        state.records["test.app"] = record
        #expect(throws: RenewalFailure.corruptJournal) { try state.validate() }
    }
    @Test func symlinkJournalIsNotFollowed() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let target = dir.appendingPathComponent("target.json")
        try FileRenewalJournal(url: target).save(RenewalState())
        let link = dir.appendingPathComponent("link.json")
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: target)
        #expect(throws: RenewalFailure.storageUnavailable) { try FileRenewalJournal(url: link).load() }
    }
}
