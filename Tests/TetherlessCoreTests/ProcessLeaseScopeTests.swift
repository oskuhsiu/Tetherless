// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Dispatch // ASSERTION_BOUNDARY_TIMING
import Testing
@testable import TetherlessCore

private actor LeaseSignal {
    private var ready = false
    private var waiters: [CheckedContinuation<Void, Never>] = []
    func wait() async { if ready { return }; await withCheckedContinuation { waiters.append($0) } }
    func send() { ready = true; let values = waiters; waiters.removeAll(); values.forEach { $0.resume() } }
}

// BEGIN ASSERTION_BOUNDARY_TIMING_DECLARATIONS
private enum LeaseAssertionTimingEvent: String {
    case busyExpectBefore, busyBodyBefore, busyBodyAfter, busyExpectAfter
}
private enum LeaseAssertionTimingTrace {
    static func emit(_ event: LeaseAssertionTimingEvent) {
        let monotonic = DispatchTime.now().uptimeNanoseconds
        let utc = Date().timeIntervalSince1970
        print("process_lease_scope_timing event=\(event.rawValue) monotonic_ns=\(monotonic) utc_unix_s=\(utc)")
    }
}
// END ASSERTION_BOUNDARY_TIMING_DECLARATIONS
@Suite("Real process lease transfer into nested native mutation ownership", .timeLimit(.minutes(1)))
struct ProcessLeaseScopeTests {
    private func use(_ body: (URL) async throws -> Void) async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try await body(root.appendingPathComponent("lock").resolvingSymlinksInPath())
    }
    @Test func nestedScopeBorrowsRealDescriptorAndExternalHandleStaysExcluded() async throws {
        try await use { url in
            let lease = try ProcessLease.acquire(at: url)
            try await lease.withMutationScope {
                lease.release() // Ownership has moved; this must not unlock it.
                #expect(throws: RenewalFailure.busy) { try ProcessLease.acquire(at: url) }
                try await MutationScope.withLease(identity: url.path, acquire: {
                    Issue.record("Tried to reacquire already owned native lease")
                    let other = try ProcessLease.acquire(at: url); return { other.release() }
                }) {
                    #expect(throws: RenewalFailure.busy) { try ProcessLease.acquire(at: url) }
                }
            }
            let next = try ProcessLease.acquire(at: url); next.release()
            await #expect(throws: RenewalFailure.lockUnavailable) { try await lease.withMutationScope {} }
        }
    }
    @Test func admittedChildRetainsTransferredDescriptorUntilItFinishes() async throws {
        try await use { url in
            let admitted = LeaseSignal(), finish = LeaseSignal()
            let lease = try ProcessLease.acquire(at: url)
            let child = try await lease.withMutationScope {
                let task = Task {
                    try await MutationScope.withLease(identity: url.path, acquire: {
                        Issue.record("Child unexpectedly reacquired lease")
                        let other = try ProcessLease.acquire(at: url); return { other.release() }
                    }) { await admitted.send(); await finish.wait() }
                }
                await admitted.wait()
                return task
            }
            LeaseAssertionTimingTrace.emit(.busyExpectBefore) // ASSERTION_BOUNDARY_TIMING
            #expect(throws: RenewalFailure.busy) {
                LeaseAssertionTimingTrace.emit(.busyBodyBefore) // ASSERTION_BOUNDARY_TIMING
                defer { LeaseAssertionTimingTrace.emit(.busyBodyAfter) } // ASSERTION_BOUNDARY_TIMING
                return try ProcessLease.acquire(at: url) // ASSERTION_BOUNDARY_RETURN
            }
            LeaseAssertionTimingTrace.emit(.busyExpectAfter) // ASSERTION_BOUNDARY_TIMING
            await finish.send(); try await child.value
            let next = try ProcessLease.acquire(at: url); next.release()
        }
    }
    @Test func thrownScopedBodyReleasesExactlyOnce() async throws {
        try await use { url in
            let lease = try ProcessLease.acquire(at: url)
            await #expect(throws: CancellationError.self) {
                try await lease.withMutationScope { throw CancellationError() }
            }
            let next = try ProcessLease.acquire(at: url)
            lease.release() // Must not close a reused OS descriptor.
            #expect(throws: RenewalFailure.busy) { try ProcessLease.acquire(at: url) }
            next.release()
        }
    }
    @Test func actualRenewalEngineSnapshotCanEnterNativeStyleLease() async throws {
        struct Backend: RenewalBackend {
            let url: URL
            func snapshot() async throws -> RenewalSnapshot {
                try await MutationScope.withLease(identity: url.path, acquire: {
                    Issue.record("Renewal engine did not convey mutation ownership")
                    let lease = try ProcessLease.acquire(at: url); return { lease.release() }
                }) { RenewalSnapshot(apps: []) }
            }
            func refresh(_ app: AppLease) async throws -> RenewalEvidence { throw RenewalFailure.unavailable }
            func reconcile(_ pending: PendingRenewal) async throws -> RenewalEvidence? { throw RenewalFailure.unavailable }
        }
        try await use { url in
            let engine = RenewalEngine(backend: Backend(url: url),
                journal: FileRenewalJournal(url: url.deletingLastPathComponent().appendingPathComponent("journal")),
                policy: try RenewalPolicy(), acquire: { try ProcessLease.acquire(at: url) })
            let result = try await engine.run(trigger: .background)
            #expect(result.globalFailure == nil)
            let next = try ProcessLease.acquire(at: url); next.release()
        }
    }
}
