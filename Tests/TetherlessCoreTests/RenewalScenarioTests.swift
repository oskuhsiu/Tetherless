// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore

private let epoch = Date(timeIntervalSince1970: 1_800_000_000)
private let day: TimeInterval = 86_400
private let identity = String(repeating: "a", count: 64)

private final class ScenarioJournal: RenewalJournal, @unchecked Sendable {
    let file: FileRenewalJournal
    private let lock = NSLock()
    private var writes = 0
    private var failAt: Int?
    init(_ url: URL, failAt: Int? = nil) { file = FileRenewalJournal(url: url); self.failAt = failAt }
    func load() throws -> RenewalState { try file.load() }
    func save(_ state: RenewalState) throws {
        try lock.withLock {
            writes += 1
            if writes == failAt { throw RenewalFailure.storageUnavailable }
            try file.save(state)
        }
    }
}
private actor ScenarioBackend: RenewalBackend {
    private var apps: [AppLease]
    private let stop: RenewalFailure?
    private let level: EvidenceLevel
    private var applied = [String: RenewalEvidence]()
    private(set) var fresh: [String] = []
    private(set) var reconciled: [String] = []
    init(apps: [AppLease], stop: RenewalFailure? = nil, level: EvidenceLevel = .deviceReadback) {
        self.apps = apps; self.stop = stop; self.level = level
    }
    func snapshot() -> RenewalSnapshot { RenewalSnapshot(apps: apps) }
    func refresh(_ app: AppLease) throws -> RenewalEvidence {
        fresh.append(app.bundleID)
        if !app.isManager, let stop {
            if stop == .cancelled { throw CancellationError() }
            throw stop
        }
        let evidence = RenewalEvidence(bundleID: app.bundleID, previousExpiry: app.effectiveExpiry,
            newExpiry: app.effectiveExpiry.addingTimeInterval(day), level: level, sameSigningIdentity: true)
        applied[app.bundleID] = evidence
        if level == .deviceReadback {
            let updated = try AppLease(bundleID: app.bundleID, isManager: app.isManager,
                effectiveExpiry: evidence.newExpiry, identityDigest: app.identityDigest)
            apps = apps.map { $0.bundleID == app.bundleID ? updated : $0 }
        }
        return evidence
    }
    func reconcile(_ pending: PendingRenewal) -> RenewalEvidence? {
        reconciled.append(pending.app.bundleID)
        return applied[pending.app.bundleID]
    }
}
private struct Scenario {
    let directory: URL
    let journal: ScenarioJournal
    let apps: [AppLease]
    let backend: ScenarioBackend
    init(stop: RenewalFailure? = nil, failSave: Int? = nil,
         level: EvidenceLevel = .deviceReadback) throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
        journal = ScenarioJournal(directory.appendingPathComponent("state.json"), failAt: failSave)
        apps = try [("test.user", false), ("test.manager", true), ("test.z", false)].map {
            try AppLease(bundleID: $0.0, isManager: $0.1,
                effectiveExpiry: epoch.addingTimeInterval(7 * day), identityDigest: identity)
        }
        backend = ScenarioBackend(apps: apps, stop: stop, level: level)
    }
    func engine(_ capture: RenewalRunCapture, at time: Date = epoch) throws -> RenewalEngine {
        let lock = directory.appendingPathComponent("device-mutation.lock")
        return RenewalEngine(backend: backend, journal: journal, policy: try RenewalPolicy(), now: { time },
            acquire: { try ProcessLease.acquire(at: lock) }, reportOnExit: { capture.record($0) })
    }
    func cleanup() { try? FileManager.default.removeItem(at: directory) }
}

@Suite("Daily renewal scenarios: real journal/lock, scripted device, no Apple/device claim")
struct RenewalScenarioTests {
    @Test func cancellationRetainsCommittedManagerAndNewExpiryForWarnings() async throws {
        let s = try Scenario(stop: .cancelled); defer { s.cleanup() }
        let capture = RenewalRunCapture()
        let engine = try s.engine(capture)
        await #expect(throws: CancellationError.self) { try await engine.run(trigger: .shortcut) }
        let report = capture.interrupted(by: .cancelled)
        #expect(report.verified == ["test.manager"])
        #expect(report.attempted == ["test.manager", "test.user"])
        #expect(report.deferred == ["test.z"])
        #expect(report.globalFailure == .cancelled)
        let state = try s.journal.load()
        #expect(state.records["test.manager"]?.lastKnownExpiry == epoch.addingTimeInterval(8 * day))
        #expect(state.records["test.user"]?.pending != nil)
        let summary = RenewalSummary(startedAt: epoch, finishedAt: epoch.addingTimeInterval(2),
            trigger: .shortcut, managerWasForeground: false, result: report)
        #expect(summary.verified == 1)
        #expect(!summary.managerRenewedOutsideForeground, "An interrupted batch is not full unattended acceptance")
        var timeline = RenewalTimeline(); try timeline.record(summary)
        #expect(timeline.lastObservedLeases.first(where: \.isManager)?.effectiveExpiry == epoch.addingTimeInterval(8 * day))
        // The failed/unattempted apps keep their earlier deadline, so the alarm
        // still protects them rather than moving every app's expiry forward.
        let warnings = try RenewalAlertPolicy.plan(leases: timeline.lastObservedLeases, now: epoch)
        #expect(warnings.first?.deliverAt == epoch.addingTimeInterval(5 * day))
        // The real descriptor is released despite cancellation.
        let lease = try ProcessLease.acquire(at: s.directory.appendingPathComponent("device-mutation.lock")); lease.release()
    }

    @Test func failedSecondCommitNeverBecomesVerifiedAndResumesWithoutDuplicateWrite() async throws {
        let s = try Scenario(failSave: 4); defer { s.cleanup() }
        let capture = RenewalRunCapture()
        let engine = try s.engine(capture)
        await #expect(throws: RenewalFailure.storageUnavailable) { try await engine.run(trigger: .background) }
        let result = capture.interrupted(by: .storageUnavailable)
        #expect(result.verified == ["test.manager"])
        #expect(result.globalFailure == .storageUnavailable)
        #expect(try s.journal.load().records["test.user"]?.pending != nil)
        // A new invocation uses durable state, not capture history. It reconciles
        // the applied user's profile and doesn't call refresh a second time.
        let second = try s.engine(RenewalRunCapture())
        let recovered = try await second.run(trigger: .background)
        #expect(recovered.verified == ["test.z", "test.user"])
        #expect(await s.backend.fresh == ["test.manager", "test.user", "test.z"])
        #expect(await s.backend.reconciled == ["test.user"])
    }

    @Test func writeAheadFailureReportsNoSuccessfulOrAttemptedMutation() async throws {
        let s = try Scenario(failSave: 1); defer { s.cleanup() }
        let capture = RenewalRunCapture(); let engine = try s.engine(capture)
        await #expect(throws: RenewalFailure.storageUnavailable) { try await engine.run(trigger: .shortcut) }
        let report = capture.interrupted(by: .storageUnavailable)
        #expect(report.verified.isEmpty && report.attempted.isEmpty)
        #expect(report.deferred.count == 3)
        #expect(await s.backend.fresh.isEmpty)
    }

    @Test func appliedOnlyNeverAdvancesObservedExpiryOrClaimsReadback() async throws {
        let s = try Scenario(stop: .cancelled, level: .applied); defer { s.cleanup() }
        let capture = RenewalRunCapture(); let engine = try s.engine(capture)
        await #expect(throws: CancellationError.self) { try await engine.run(trigger: .shortcut) }
        let report = capture.interrupted(by: .cancelled)
        #expect(report.verified.isEmpty)
        #expect(report.appliedUnverified == ["test.manager"])
        #expect(report.observed.allSatisfy { $0.effectiveExpiry == epoch.addingTimeInterval(7 * day) })
    }

    @Test func nextDayRenewsAllAppsAndSameDayDuplicateDoesNotRepeat() async throws {
        let s = try Scenario(); defer { s.cleanup() }
        let first = try s.engine(RenewalRunCapture())
        let initial = try await first.run(trigger: .shortcut)
        #expect(initial.verified == ["test.manager", "test.user", "test.z"])
        let duplicate = try s.engine(RenewalRunCapture(), at: epoch.addingTimeInterval(60))
        #expect(try await duplicate.run(trigger: .background).attempted.isEmpty)
        let nextDay = try s.engine(RenewalRunCapture(), at: epoch.addingTimeInterval(day))
        let next = try await nextDay.run(trigger: .shortcut)
        #expect(next.verified == initial.verified)
        #expect(next.observed.allSatisfy { $0.effectiveExpiry == epoch.addingTimeInterval(9 * day) })
        let stored = try FileRenewalJournal(url: s.journal.file.url).load()
        #expect(stored.records.values.allSatisfy { $0.lastVerifiedAt == epoch.addingTimeInterval(day) && $0.pending == nil })
        #expect(await s.backend.fresh.count == 6)
    }

    @Test func captureIsInvocationLocalAndCannotInventPreviousSuccess() {
        let capture = RenewalRunCapture()
        let report = capture.interrupted(by: .needsAuthentication)
        #expect(report.verified.isEmpty && report.managedIDs == nil)
        #expect(report.globalFailure == .needsAuthentication)
    }
}
