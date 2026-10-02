// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
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
        let child = try await MutationScope.withLease(identity: "device", acquire: lock.acquire) {
            let child = Task {
                try await MutationScope.withLease(identity: "device", acquire: lock.acquire) {
                    await admitted.signal()
                    await resume.wait()
                }
            }
            await admitted.wait()
            return child
        }
        #expect(lock.counts.0 == 1)
        #expect(lock.counts.1 == 0)
        #expect(throws: ScopeTestError.busy) { _ = try lock.acquire() }
        await resume.signal()
        try await child.value
        #expect(lock.counts.1 == 1)
    }
    @Test func lateChildCannotBorrowClosedScope() async throws {
        let lock = ScopeTestLock()
        let resume = ScopeSignal()
        let child = try await MutationScope.withLease(identity: "device", acquire: lock.acquire) {
            Task {
                await resume.wait()
                try await MutationScope.withLease(identity: "device", acquire: lock.acquire) {}
            }
        }
        #expect(lock.counts.1 == 1)
        let otherOwnerRelease = try lock.acquire()
        await resume.signal()
        await #expect(throws: ScopeTestError.busy) { try await child.value }
        #expect(lock.counts.0 == 2)
        otherOwnerRelease()
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
