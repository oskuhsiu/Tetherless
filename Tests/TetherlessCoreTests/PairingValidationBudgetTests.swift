import XCTest
@testable import TetherlessCore

final class PairingValidationBudgetTests: XCTestCase {
    func testStaleFirstEndpointCannotConsumeTheSecondEndpointsShare() throws {
        let first = try XCTUnwrap(PairingValidationBudget.timeoutMilliseconds(
            remainingMilliseconds: 8_000, endpointsRemaining: 2))
        XCTAssertEqual(first, 4_000)
        // Synthetic elapsed time: the first attempt times out, then its actual
        // close consumes 100 ms. The next attempt keeps a useful bounded share.
        let second = try XCTUnwrap(PairingValidationBudget.timeoutMilliseconds(
            remainingMilliseconds: 8_000 - first - 100, endpointsRemaining: 1))
        XCTAssertEqual(second, 3_900)
        XCTAssertLessThanOrEqual(first + 100 + second, 8_000)
    }

    func testEveryAllowedEndpointGetsAnEqualShareWithoutCleanupOverhead() throws {
        for count in 1...4 {
            var remaining: UInt32 = 10_000
            var attempts: [UInt32] = []
            for outstanding in stride(from: count, through: 1, by: -1) {
                let share = try XCTUnwrap(PairingValidationBudget.timeoutMilliseconds(
                    remainingMilliseconds: remaining, endpointsRemaining: outstanding))
                attempts.append(share)
                remaining -= share
            }
            XCTAssertEqual(attempts.count, count)
            XCTAssertEqual(remaining, 0)
            let largest = try XCTUnwrap(attempts.max())
            let smallest = try XCTUnwrap(attempts.min())
            XCTAssertLessThanOrEqual(largest - smallest, 1)
        }
    }

    func testFastFailureRedistributesUnusedTimeWithinTheSameRemainder() {
        XCTAssertEqual(PairingValidationBudget.timeoutMilliseconds(
            remainingMilliseconds: 9_000, endpointsRemaining: 3), 3_000)
        XCTAssertEqual(PairingValidationBudget.timeoutMilliseconds(
            remainingMilliseconds: 8_900, endpointsRemaining: 2), 4_450)
    }

    func testSessionDeadlineCanShortenEveryShare() {
        XCTAssertEqual(PairingValidationBudget.timeoutMilliseconds(
            remainingMilliseconds: 121, endpointsRemaining: 4), 30)
        XCTAssertEqual(PairingValidationBudget.timeoutMilliseconds(
            remainingMilliseconds: 29, endpointsRemaining: 3), 9)
    }

    func testNoUsableShareFailsClosed() {
        XCTAssertNil(PairingValidationBudget.timeoutMilliseconds(
            remainingMilliseconds: 0, endpointsRemaining: 1))
        XCTAssertNil(PairingValidationBudget.timeoutMilliseconds(
            remainingMilliseconds: 3, endpointsRemaining: 4))
        XCTAssertEqual(PairingValidationBudget.timeoutMilliseconds(
            remainingMilliseconds: 4, endpointsRemaining: 4), 1)
    }

    func testInvalidEndpointCountsFailClosedBeforeIntegerConversion() {
        for count in [Int.min, -1, 0, 5, Int.max] {
            XCTAssertNil(PairingValidationBudget.timeoutMilliseconds(
                remainingMilliseconds: 10_000, endpointsRemaining: count))
        }
    }

    func testEvenAnOversizedCallerBudgetCannotExpandTheValidationWindow() {
        XCTAssertEqual(PairingValidationBudget.timeoutMilliseconds(
            remainingMilliseconds: .max, endpointsRemaining: 1), 10_000)
        XCTAssertEqual(PairingValidationBudget.timeoutMilliseconds(
            remainingMilliseconds: .max, endpointsRemaining: 4), 2_500)
    }
}
