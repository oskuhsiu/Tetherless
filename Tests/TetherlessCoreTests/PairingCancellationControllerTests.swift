import Foundation
import XCTest
@testable import TetherlessCore

final class PairingCancellationControllerTests: XCTestCase {
    private final class Counter: @unchecked Sendable {
        let lock = NSLock(); var stored = 0
        var value: Int { lock.lock(); defer { lock.unlock() }; return stored }
        func increment() { lock.lock(); stored += 1; lock.unlock() }
    }
    func testCancelledRegistrationSignalsImmediatelyWithoutAdmittingWork() {
        let control = PairingCancellationController(), counter = Counter()
        XCTAssertTrue(control.cancel())
        XCTAssertNil(control.register { counter.increment() })
        XCTAssertEqual(counter.value, 1)
        XCTAssertFalse(control.beginPromotion())
    }
    func testCallbacksRunOutsideLockAndRemovalIsIdempotent() {
        let control = PairingCancellationController(), counter = Counter()
        let first = control.register { XCTAssertTrue(control.isCancelled); counter.increment() }
        let removed = control.register { XCTFail("removed cancellation callback ran") }
        removed?.remove(); removed?.remove()
        XCTAssertTrue(control.cancel()); XCTAssertTrue(control.cancel())
        XCTAssertEqual(counter.value, 1)
        first?.remove(); control.finish()
    }
    func testCancellationAndCommitHaveExactlyOneWinner() {
        for _ in 0..<64 {
            let control = PairingCancellationController()
            // Synchronize result storage separately from the state being tested.
            let output = RaceResults()
            DispatchQueue.concurrentPerform(iterations: 2) { index in
                output.set(index, index == 0 ? control.cancel() : control.beginPromotion())
            }
            let results = output.values
            XCTAssertNotEqual(results[0], results[1])
            control.finish()
        }
    }
    private final class ReentrantRelease: @unchecked Sendable {
        let control: PairingCancellationController
        let counter: Counter
        init(_ control: PairingCancellationController, _ counter: Counter) { self.control = control; self.counter = counter }
        deinit { _ = control.isCancelled; counter.increment() }
    }
    func testRemovedActionsReleaseCapturedObjectsOutsideControllerLock() {
        for finish in [false, true] {
            let control = PairingCancellationController(), counter = Counter()
            var capture: ReentrantRelease? = ReentrantRelease(control, counter)
            let registration = control.register { [value = capture!] in withExtendedLifetime(value) {} }
            capture = nil
            XCTAssertEqual(counter.value, 0)
            if finish { control.finish() } else { registration?.remove() }
            XCTAssertEqual(counter.value, 1)
        }
    }
    private final class RaceResults: @unchecked Sendable {
        private let lock = NSLock(); private var stored = [false, false]
        var values: [Bool] { lock.lock(); defer { lock.unlock() }; return stored }
        func set(_ index: Int, _ value: Bool) { lock.lock(); stored[index] = value; lock.unlock() }
    }
}
