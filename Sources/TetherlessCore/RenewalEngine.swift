// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

public protocol RenewalBackend: Sendable {
    func snapshot() async throws -> RenewalSnapshot
    /// Must not silently revoke certificates, reinstall the manager or show UI.
    func refresh(_ app: AppLease) async throws -> RenewalEvidence
    /// Read back the device before retrying an interrupted transaction. Return nil
    /// only when readback proves that the previous transaction was not applied.
    /// Inability to read back must throw, not return nil and blindly mutate again.
    func reconcile(_ pending: PendingRenewal) async throws -> RenewalEvidence?
}

public protocol RenewalJournal: Sendable {
    func load() throws -> RenewalState
    /// Atomic replacement: a failure leaves the previous valid state readable.
    func save(_ state: RenewalState) throws
}

/// The file-lock closure is intentionally injected: iOS must use a lock located
/// in the same container as the journal; tests can use a real temporary file.
public actor RenewalEngine {
    private let backend: any RenewalBackend
    private let journal: any RenewalJournal
    private let policy: RenewalPolicy
    private let now: @Sendable () -> Date
    private let acquire: @Sendable () throws -> ProcessLease
    private let reportOnExit: @Sendable (RenewalRunResult) -> Void
    private var running = false

    public init(backend: any RenewalBackend, journal: any RenewalJournal,
                policy: RenewalPolicy, now: @escaping @Sendable () -> Date = { Date() },
                acquire: @escaping @Sendable () throws -> ProcessLease,
                reportOnExit: @escaping @Sendable (RenewalRunResult) -> Void = { _ in }) {
        self.backend = backend
        self.journal = journal
        self.policy = policy
        self.now = now
        self.acquire = acquire
        self.reportOnExit = reportOnExit
    }

    public func run(trigger: RenewalTrigger, force: Bool = false) async throws -> RenewalRunResult {
        guard now().timeIntervalSince1970.isFinite else { throw RenewalFailure.invalidInput }
        guard !running else { throw RenewalFailure.busy }
        running = true
        defer { running = false }
        let lease = try acquire()
        return try await lease.withMutationScope { try await self.runAcquired(trigger: trigger, force: force) }
    }

    private func runAcquired(trigger: RenewalTrigger, force: Bool) async throws -> RenewalRunResult {
        var report = RenewalRunResult()
        // Publish the actual in-memory outcome even when a later app is cancelled
        // or persistence fails. Only append() after a durable commit adds verified
        // work. The observer is synchronous/nonthrowing and cannot change control
        // flow, suppress an error, or replace the write-ahead journal.
        defer { reportOnExit(report) }
        var state = try loadState() // Always read AFTER acquiring the process lock.
        guard state.schemaVersion == 1 else { throw RenewalFailure.unsupportedJournal }
        // Do not contact Apple again until an explicit repair or retry window.
        if let gate = state.gate,
           gate.requiresInteraction || (gate.retryAfter.map { $0 > now() } ?? false) {
            report.globalFailure = gate.failure
            report.deferred = state.records.keys.sorted()
            return report
        }
        let snapshot: RenewalSnapshot
        do {
            snapshot = try await backend.snapshot()
            try snapshot.validate()
        } catch {
            if let failure = error as? RenewalFailure, failure.isStorageFailure { throw failure }
            if error is CancellationError { throw CancellationError() }
            let failure = error as? RenewalFailure ?? .unavailable
            let count = min(state.gate?.consecutiveFailures ?? 0, 999) + 1
            state.gate = RenewalGate(failure: failure,
                retryAfter: policy.retryDate(failures: count, now: now()), consecutiveFailures: count)
            try saveState(state)
            throw failure
        }
        state.gate = nil
        let apps = try policy.ordered(snapshot.apps)
        report.observed = apps
        report.managedIDs = (apps.map(\.bundleID) + snapshot.failures.keys).sorted()
        let activeIDs = Set(report.managedIDs ?? [])
        // Seed known state in memory; the first write-ahead save commits it. This
        // is observed expiry, not a fabricated renewal or lastVerifiedAt value.
        for app in apps {
            var record = state.records[app.bundleID] ?? RenewalRecord()
            record.lastKnownExpiry = app.effectiveExpiry
            state.records[app.bundleID] = record
        }
        for (id, failure) in snapshot.failures {
            var record = state.records[id] ?? RenewalRecord()
            record.failure = failure
            record.outcome = .failed
            record.requiresInteraction = failure.requiresInteraction
            record.consecutiveFailures = min(record.consecutiveFailures, 999) + 1
            record.retryAfter = policy.retryDate(failures: record.consecutiveFailures, now: now())
            state.records[id] = record // Keep any interrupted transaction intact.
            report.failures[id] = failure
        }
        if !snapshot.failures.isEmpty { try saveState(state) }
        // Only active account/device blockers are shared. Retain inactive records
        // for recovery/history, but do not let an uninstalled app poison this run.
        let blockers = state.records.filter {
            activeIDs.contains($0.key) && $0.value.requiresInteraction &&
            [.needsAuthentication, .needsPairing].contains($0.value.failure)
        }
        if !blockers.isEmpty {
            report.deferred = apps.map(\.bundleID)
            for (id, record) in blockers { report.failures[id] = record.failure }
            return report
        }

        for app in apps {
            try Task.checkCancellation()
            var record = state.records[app.bundleID] ?? RenewalRecord()
            if record.requiresInteraction || (record.retryAfter.map { $0 > now() } ?? false) {
                report.deferred.append(app.bundleID)
                if let failure = record.failure { report.failures[app.bundleID] = failure }
                continue
            }
            do {
                if let pending = record.pending {
                    guard pending.app.isManager == app.isManager,
                          pending.app.identityDigest == app.identityDigest else {
                        throw RenewalFailure.identityChanged
                    }
                    // Reconciliation remains mandatory even for a manual/force run.
                    if let evidence = try await backend.reconcile(pending) {
                        try evidence.validate(for: pending.app, now: now())
                        commit(evidence, record: &record)
                        state.records[app.bundleID] = record
                        try saveState(state)
                        append(evidence, app: app, to: &report)
                        continue
                    }
                    record.pending = nil
                    record.outcome = .interrupted
                    state.records[app.bundleID] = record
                    try saveState(state)
                }
                // Force bypasses the normal cadence, NOT interaction/rate limits.
                if record.requiresInteraction || (record.retryAfter.map { $0 > now() } ?? false) ||
                    (!force && !policy.isDue(app: app, record: state.records[app.bundleID], now: now())) {
                    report.deferred.append(app.bundleID)
                    continue
                }
                record.lastAttemptAt = now()
                record.pending = PendingRenewal(id: UUID(), app: app, startedAt: now())
                state.records[app.bundleID] = record
                try saveState(state) // Write-ahead record BEFORE the device can change.
                report.attempted.append(app.bundleID)
                let evidence = try await backend.refresh(app)
                try Task.checkCancellation()
                try evidence.validate(for: app, now: now())
                commit(evidence, record: &record)
                state.records[app.bundleID] = record
                try saveState(state)
                append(evidence, app: app, to: &report)
            } catch {
                // A storage failure must not be converted into a successful run.
                // Keep the on-disk write-ahead record for next-run reconciliation.
                if let failure = error as? RenewalFailure,
                   failure.isStorageFailure {
                    throw failure
                }
                let failure = error is CancellationError ? RenewalFailure.cancelled :
                    (error as? RenewalFailure ?? .unavailable)
                record.outcome = failure == .noExtension ? .checkedNotExtended : .failed
                record.failure = failure
                record.consecutiveFailures = min(max(record.consecutiveFailures, 0), 999) + 1
                record.retryAfter = policy.retryDate(failures: record.consecutiveFailures, now: now())
                record.requiresInteraction = failure.requiresInteraction
                // Failure after applying may be ambiguous. Do NOT discard pending:
                // the backend must read back or explicitly request interaction.
                if failure == .noExtension { record.pending = nil }
                state.records[app.bundleID] = record
                if [.needsAuthentication, .needsPairing].contains(failure) {
                    state.gate = RenewalGate(failure: failure, retryAfter: record.retryAfter,
                                            consecutiveFailures: record.consecutiveFailures)
                }
                try saveState(state)
                report.failures[app.bundleID] = failure
                if failure == .cancelled { throw CancellationError() }
                // Account/pairing faults affect the whole run. Do not amplify them.
                if failure.isRunWide {
                    report.globalFailure = failure
                    let visited = Set(report.attempted + report.verified + report.appliedUnverified + report.deferred + Array(report.failures.keys))
                    report.deferred += apps.filter { !visited.contains($0.bundleID) }.map(\.bundleID)
                    break
                }
            }
        }
        try saveState(state)
        return report
    }

    private func commit(_ evidence: RenewalEvidence, record: inout RenewalRecord) {
        record.lastAppliedAt = now()
        record.lastKnownExpiry = evidence.newExpiry
        record.retryAfter = nil
        record.consecutiveFailures = 0
        record.requiresInteraction = false
        record.failure = nil
        record.pending = nil
        if evidence.level == .deviceReadback {
            record.lastVerifiedAt = now()
            record.outcome = .verified
        } else {
            record.outcome = .appliedUnverified
        }
    }

    /// Call only after an explicit, successful foreground authentication/pairing
    /// repair. This does not bypass reconciliation of an interrupted mutation.
    public func resumeAfterInteraction(bundleID: String) throws {
        guard !running else { throw RenewalFailure.busy }
        let lease = try acquire()
        defer { lease.release() }
        var state = try loadState()
        guard var record = state.records[bundleID] else { return }
        record.requiresInteraction = false
        record.retryAfter = nil
        state.records[bundleID] = record
        try saveState(state)
    }

    private func append(_ evidence: RenewalEvidence, app: AppLease, to report: inout RenewalRunResult) {
        if evidence.level == .deviceReadback,
           let index = report.observed.firstIndex(where: { $0.bundleID == app.bundleID }),
           let updated = try? AppLease(bundleID: app.bundleID, isManager: app.isManager,
                                      effectiveExpiry: evidence.newExpiry, identityDigest: app.identityDigest) {
            report.observed[index] = updated
        }
        if evidence.level == .deviceReadback { report.verified.append(evidence.bundleID) }
        else { report.appliedUnverified.append(evidence.bundleID) }
    }

    private func loadState() throws -> RenewalState {
        do {
            let state = try journal.load()
            try state.validate()
            return state
        }
        catch let failure as RenewalFailure { throw failure }
        catch { throw RenewalFailure.storageUnavailable }
    }

    private func saveState(_ state: RenewalState) throws {
        do { try journal.save(state) }
        catch { throw RenewalFailure.storageUnavailable }
    }

}
