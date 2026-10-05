import Foundation
import XCTest
@testable import TetherlessCore

final class NativeCallLifetimeTests: XCTestCase {
    private final class Counter: @unchecked Sendable {
        private let lock = NSLock()
        private var stored = 0
        var value: Int { lock.lock(); defer { lock.unlock() }; return stored }
        func increment() { lock.lock(); stored += 1; lock.unlock() }
    }

    func testQueuedHandshakeAndConcurrentCancellationBothJoinBeforeCleanup() {
        let lifetime = NativeCallLifetime(), counter = Counter()
        let handshake = lifetime.admit()!
        let cancel = lifetime.admit()!
        XCTAssertTrue(lifetime.retire { counter.increment() })
        XCTAssertNil(lifetime.admit())
        XCTAssertEqual(counter.value, 0)
        handshake.returned()
        XCTAssertEqual(counter.value, 0)
        cancel.returned()
        XCTAssertEqual(counter.value, 1)
        cancel.returned()
        XCTAssertFalse(lifetime.retire { counter.increment() })
        XCTAssertEqual(counter.value, 1)
    }

    func testClaimOwnsLifetimeUntilActualReturn() {
        let counter = Counter()
        var lifetime: NativeCallLifetime? = NativeCallLifetime()
        var call = lifetime!.admit()
        weak var observed = lifetime
        lifetime!.retire { counter.increment() }
        lifetime = nil
        XCTAssertNotNil(observed)
        XCTAssertEqual(counter.value, 0)
        call?.returned()
        call = nil
        XCTAssertNil(observed)
        XCTAssertEqual(counter.value, 1)
    }

    func testConcurrentReturnsRunCleanupExactlyOnceOutsideLock() {
        let lifetime = NativeCallLifetime(), counter = Counter()
        let calls = (0..<64).map { _ in lifetime.admit()! }
        lifetime.retire { counter.increment(); XCTAssertNil(lifetime.admit()) }
        DispatchQueue.concurrentPerform(iterations: calls.count) { calls[$0].returned() }
        XCTAssertEqual(counter.value, 1)
    }
}
