// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

public protocol RenewalBackend: Sendable {
    func snapshot() async throws -> [AppLease]
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
    private var running = false

    public init(backend: any RenewalBackend, journal: any RenewalJournal,
                policy: RenewalPolicy, now: @escaping @Sendable () -> Date = { Date() },
                acquire: @escaping @Sendable () throws -> ProcessLease) {
        self.backend = backend
        self.journal = journal
        self.policy = policy
        self.now = now
        self.acquire = acquire
    }

    public func run(trigger: RenewalTrigger, force: Bool = false) async throws -> RenewalRunResult {
        guard now().timeIntervalSince1970.isFinite else { throw RenewalFailure.invalidInput }
        guard !running else { throw RenewalFailure.busy }
        running = true
        defer { running = false }
        let lease = try acquire()
        defer { lease.release() }
        var state = try loadState() // Always read AFTER acquiring the process lock.
        guard state.schemaVersion == 1 else { throw RenewalFailure.unsupportedJournal }
        let apps = try policy.ordered(try await backend.snapshot())
        var report = RenewalRunResult()
        // Authentication/pairing repair is account/device-wide, not app-local.
        if state.records.values.contains(where: {
            $0.requiresInteraction && [.needsAuthentication, .needsPairing, .identityChanged].contains($0.failure)
        }) {
            report.deferred = apps.map(\.bundleID)
            return report
        }

        for app in apps {
            try Task.checkCancellation()
            var record = state.records[app.bundleID] ?? RenewalRecord()
            if record.requiresInteraction || (record.retryAfter.map { $0 > now() } ?? false) {
                report.deferred.append(app.bundleID)
                continue
            }
            do {
                if let pending = record.pending {
                    // Reconciliation remains mandatory even for a manual/force run.
                    if let evidence = try await backend.reconcile(pending) {
                        try evidence.validate(for: pending.app, now: now())
                        commit(evidence, record: &record)
                        state.records[app.bundleID] = record
                        try saveState(state)
                        append(evidence, to: &report)
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
                append(evidence, to: &report)
            } catch {
                // A storage failure must not be converted into a successful run.
                // Keep the on-disk write-ahead record for next-run reconciliation.
                if let failure = error as? RenewalFailure,
                   [.storageUnavailable, .corruptJournal, .unsupportedJournal].contains(failure) {
                    throw failure
                }
                let failure = error is CancellationError ? RenewalFailure.cancelled :
                    (error as? RenewalFailure ?? .unavailable)
                record.outcome = failure == .noExtension ? .checkedNotExtended : .failed
                record.failure = failure
                record.consecutiveFailures = min(max(record.consecutiveFailures, 0), 999) + 1
                record.retryAfter = policy.retryDate(failures: record.consecutiveFailures, now: now())
                record.requiresInteraction = [.needsAuthentication, .needsPairing, .needsForeground,
                                              .identityChanged].contains(failure)
                // Failure after applying may be ambiguous. Do NOT discard pending:
                // the backend must read back or explicitly request interaction.
                if failure == .noExtension { record.pending = nil }
                state.records[app.bundleID] = record
                try saveState(state)
                report.failures[app.bundleID] = failure
                if failure == .cancelled { throw CancellationError() }
                // Account/pairing faults affect the whole run. Do not amplify them.
                if [.needsAuthentication, .needsPairing, .identityChanged].contains(failure) { break }
            }
        }
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

    private func append(_ evidence: RenewalEvidence, to report: inout RenewalRunResult) {
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
