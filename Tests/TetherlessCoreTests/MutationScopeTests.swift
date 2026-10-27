// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Dispatch // MUTATION_SCOPE_TIMING
import Testing
@testable import TetherlessCore

private enum ScopeTestError: Error { case busy, deliberate }
private final class ScopeTestLock: @unchecked Sendable {
    private let mutex = NSLock()
    private var held = false
    private var acquired = 0
    private var released = 0
    var counts: (Int, Int) { mutex.lock(); defer { mutex.unlock() }; return (acquired, released) }
    func acquire() throws -> (@Sendable () -> Void) {
        mutex.lock()
        defer { mutex.unlock() }
        guard !held else { throw ScopeTestError.busy }
        held = true; acquired += 1
        return { [self] in
            mutex.lock(); held = false; released += 1; mutex.unlock()
        }
    }
}
private actor ScopeSignal {
    var signalled = false
    var waiters: [CheckedContinuation<Void, Never>] = []
    func wait() async {
        if signalled { return }
        await withCheckedContinuation { waiters.append($0) }
    }
    func signal() {
        signalled = true
        let values = waiters; waiters.removeAll()
        for value in values { value.resume() }
    }
}

// BEGIN MUTATION_SCOPE_TIMING_DECLARATIONS
private enum ScopeTimingEvent: String {
    case admittedCountsAcquiredBefore // ASSERTION_BOUNDARY_TIMING
    case admittedCountsAcquiredAfter // ASSERTION_BOUNDARY_TIMING
    case admittedCountsReleasedBefore // ASSERTION_BOUNDARY_TIMING
    case admittedCountsReleasedAfter // ASSERTION_BOUNDARY_TIMING
    case admittedBusyExpectBefore // ASSERTION_BOUNDARY_TIMING
    case admittedBusyExpectAfter // ASSERTION_BOUNDARY_TIMING
    case admittedBusyBodyBefore // ASSERTION_BOUNDARY_TIMING
    case admittedBusyBodyAfter // ASSERTION_BOUNDARY_TIMING
    case lateAwaitBodyBefore // ASSERTION_BOUNDARY_TIMING
    case lateAwaitBodyAfter // ASSERTION_BOUNDARY_TIMING
    case admittedOuterBefore
    case admittedParentEnter
    case admittedChildEnter
    case admittedChildExit
    case admittedChildScopeBefore
    case admittedChildScopeEnter
    case admittedChildSignalBefore
    case admittedChildSignalAfter
    case admittedChildResumeWaitBefore
    case admittedChildResumeWaitAfter
    case admittedChildScopeAfter
    case admittedParentChildCreated
    case admittedParentWaitBefore
    case admittedParentWaitAfter
    case admittedParentReturning
    case admittedOuterAfter
    case admittedParentSignalBefore
    case admittedParentSignalAfter
    case admittedParentValueBefore
    case admittedParentValueAfter
    case admittedTestEnd
    case lateOuterBefore
    case lateChildEnter
    case lateChildExit
    case lateChildResumeWaitBefore
    case lateChildResumeWaitAfter
    case lateChildScopeBefore
    case lateChildScopeAfter
    case lateOuterAfter
    case lateParentOwnerAcquired
    case lateParentSignalBefore
    case lateParentSignalAfter
    case lateParentExpectBefore
    case lateParentExpectAfter
    case lateTestEnd
}
private enum ScopeTimingTrace {
    static func emit(_ event: ScopeTimingEvent) {
        let monotonic = DispatchTime.now().uptimeNanoseconds
        let utc = Date().timeIntervalSince1970
        print("mutation_scope_timing event=\(event.rawValue) monotonic_ns=\(monotonic) utc_unix_s=\(utc)")
    }
}
// END MUTATION_SCOPE_TIMING_DECLARATIONS
@Suite("Mutation scope lifetime (lock adapter tested separately)", .timeLimit(.minutes(1)))
struct MutationScopeTests {
    @Test func nestedScopeAcquiresOnce() async throws {
        let lock = ScopeTestLock()
        try await MutationScope.withLease(identity: "device", acquire: lock.acquire) {
            try await MutationScope.withLease(identity: "device", acquire: lock.acquire) {
                #expect(lock.counts.0 == 1)
                #expect(lock.counts.1 == 0)
            }
            #expect(lock.counts.1 == 0)
        }
        #expect(lock.counts.1 == 1)
    }
    @Test func thrownBodyReleasesLease() async {
        let lock = ScopeTestLock()
        await #expect(throws: ScopeTestError.deliberate) {
            try await MutationScope.withLease(identity: "device", acquire: lock.acquire) {
                throw ScopeTestError.deliberate
            }
        }
        #expect(lock.counts.1 == 1)
    }
    @Test func admittedChildKeepsLeaseAfterParentReturns() async throws {
        let lock = ScopeTestLock()
        let admitted = ScopeSignal(), resume = ScopeSignal()
        ScopeTimingTrace.emit(.admittedOuterBefore) // MUTATION_SCOPE_TIMING
        let child = try await MutationScope.withLease(identity: "device", acquire: lock.acquire) {
            ScopeTimingTrace.emit(.admittedParentEnter) // MUTATION_SCOPE_TIMING
            let child = Task {
                ScopeTimingTrace.emit(.admittedChildEnter) // MUTATION_SCOPE_TIMING
                defer { ScopeTimingTrace.emit(.admittedChildExit) } // MUTATION_SCOPE_TIMING
                ScopeTimingTrace.emit(.admittedChildScopeBefore) // MUTATION_SCOPE_TIMING
                try await MutationScope.withLease(identity: "device", acquire: lock.acquire) {
                    ScopeTimingTrace.emit(.admittedChildScopeEnter) // MUTATION_SCOPE_TIMING
                    ScopeTimingTrace.emit(.admittedChildSignalBefore) // MUTATION_SCOPE_TIMING
                    await admitted.signal()
                    ScopeTimingTrace.emit(.admittedChildSignalAfter) // MUTATION_SCOPE_TIMING
                    ScopeTimingTrace.emit(.admittedChildResumeWaitBefore) // MUTATION_SCOPE_TIMING
                    await resume.wait()
                    ScopeTimingTrace.emit(.admittedChildResumeWaitAfter) // MUTATION_SCOPE_TIMING
                }
                ScopeTimingTrace.emit(.admittedChildScopeAfter) // MUTATION_SCOPE_TIMING
            }
            ScopeTimingTrace.emit(.admittedParentChildCreated) // MUTATION_SCOPE_TIMING
            ScopeTimingTrace.emit(.admittedParentWaitBefore) // MUTATION_SCOPE_TIMING
            await admitted.wait()
            ScopeTimingTrace.emit(.admittedParentWaitAfter) // MUTATION_SCOPE_TIMING
            ScopeTimingTrace.emit(.admittedParentReturning) // MUTATION_SCOPE_TIMING
            return child
        }
        ScopeTimingTrace.emit(.admittedOuterAfter) // MUTATION_SCOPE_TIMING
        ScopeTimingTrace.emit(.admittedCountsAcquiredBefore) // ASSERTION_BOUNDARY_TIMING
        #expect(lock.counts.0 == 1)
        ScopeTimingTrace.emit(.admittedCountsAcquiredAfter) // ASSERTION_BOUNDARY_TIMING
        ScopeTimingTrace.emit(.admittedCountsReleasedBefore) // ASSERTION_BOUNDARY_TIMING
        #expect(lock.counts.1 == 0)
        ScopeTimingTrace.emit(.admittedCountsReleasedAfter) // ASSERTION_BOUNDARY_TIMING
        ScopeTimingTrace.emit(.admittedBusyExpectBefore) // ASSERTION_BOUNDARY_TIMING
        #expect(throws: ScopeTestError.busy) {
            ScopeTimingTrace.emit(.admittedBusyBodyBefore) // ASSERTION_BOUNDARY_TIMING
            defer { ScopeTimingTrace.emit(.admittedBusyBodyAfter) } // ASSERTION_BOUNDARY_TIMING
            _ = try lock.acquire()
        }
        ScopeTimingTrace.emit(.admittedBusyExpectAfter) // ASSERTION_BOUNDARY_TIMING
        ScopeTimingTrace.emit(.admittedParentSignalBefore) // MUTATION_SCOPE_TIMING
        await resume.signal()
        ScopeTimingTrace.emit(.admittedParentSignalAfter) // MUTATION_SCOPE_TIMING
        ScopeTimingTrace.emit(.admittedParentValueBefore) // MUTATION_SCOPE_TIMING
        try await child.value
        ScopeTimingTrace.emit(.admittedParentValueAfter) // MUTATION_SCOPE_TIMING
        #expect(lock.counts.1 == 1)
        ScopeTimingTrace.emit(.admittedTestEnd) // MUTATION_SCOPE_TIMING
    }
    @Test func lateChildCannotBorrowClosedScope() async throws {
        let lock = ScopeTestLock()
        let resume = ScopeSignal()
        ScopeTimingTrace.emit(.lateOuterBefore) // MUTATION_SCOPE_TIMING
        let child = try await MutationScope.withLease(identity: "device", acquire: lock.acquire) {
            Task {
                ScopeTimingTrace.emit(.lateChildEnter) // MUTATION_SCOPE_TIMING
                defer { ScopeTimingTrace.emit(.lateChildExit) } // MUTATION_SCOPE_TIMING
                ScopeTimingTrace.emit(.lateChildResumeWaitBefore) // MUTATION_SCOPE_TIMING
                await resume.wait()
                ScopeTimingTrace.emit(.lateChildResumeWaitAfter) // MUTATION_SCOPE_TIMING
                ScopeTimingTrace.emit(.lateChildScopeBefore) // MUTATION_SCOPE_TIMING
                try await MutationScope.withLease(identity: "device", acquire: lock.acquire) {}
                ScopeTimingTrace.emit(.lateChildScopeAfter) // MUTATION_SCOPE_TIMING
            }
        }
        ScopeTimingTrace.emit(.lateOuterAfter) // MUTATION_SCOPE_TIMING
        #expect(lock.counts.1 == 1)
        let otherOwnerRelease = try lock.acquire()
        ScopeTimingTrace.emit(.lateParentOwnerAcquired) // MUTATION_SCOPE_TIMING
        ScopeTimingTrace.emit(.lateParentSignalBefore) // MUTATION_SCOPE_TIMING
        await resume.signal()
        ScopeTimingTrace.emit(.lateParentSignalAfter) // MUTATION_SCOPE_TIMING
        ScopeTimingTrace.emit(.lateParentExpectBefore) // MUTATION_SCOPE_TIMING
        await #expect(throws: ScopeTestError.busy) {
            ScopeTimingTrace.emit(.lateAwaitBodyBefore) // ASSERTION_BOUNDARY_TIMING
            defer { ScopeTimingTrace.emit(.lateAwaitBodyAfter) } // ASSERTION_BOUNDARY_TIMING
            try await child.value
        }
        ScopeTimingTrace.emit(.lateParentExpectAfter) // MUTATION_SCOPE_TIMING
        #expect(lock.counts.0 == 2)
        otherOwnerRelease()
        ScopeTimingTrace.emit(.lateTestEnd) // MUTATION_SCOPE_TIMING
    }
    @Test func differentResourceCannotBorrowScope() async throws {
        let first = ScopeTestLock(), second = ScopeTestLock()
        try await MutationScope.withLease(identity: "first", acquire: first.acquire) {
            try await MutationScope.withLease(identity: "second", acquire: second.acquire) {}
        }
        #expect(first.counts.0 == 1)
        #expect(second.counts.0 == 1)
    }
}
