import Foundation
import XCTest
@testable import TetherlessCore

@MainActor final class PairingPromotionTests: XCTestCase {
    private enum TestFailure: Error { case expected }
    private func record(_ identifier: String) throws -> Data {
        try PropertyListSerialization.data(fromPropertyList: [
            "identifier": identifier, "private_key": Data(repeating: 1, count: 32),
            "public_key": Data(repeating: 2, count: 32), "alt_irk": Data(repeating: 3, count: 16)
        ], format: .xml, options: 0)
    }

    func testValidationFailurePreservesOldRecordAndNeverCommits() async throws {
        let promotion = PairingPromotion(), old = try record("old")
        var stored: Data? = old
        var commits = 0
        let outcome = await promotion.validateAndPromote(candidate: try record("new"),
            validate: { _ in throw TestFailure.expected }, readTarget: { stored },
            commit: { commits += 1; stored = $0.xml })
        XCTAssertEqual(outcome, .validationFailed)
        XCTAssertEqual(stored, old)
        XCTAssertEqual(commits, 0)
    }

    func testCancellationWaitsForValidatorReturnAndRejectsStalePIN() async throws {
        let promotion = PairingPromotion(), old = try record("old")
        let generation = promotion.generation
        var stored: Data? = old
        var validatorReturned = false
        let outcome = await promotion.validateAndPromote(candidate: try record("new"), validate: { _ in
            XCTAssertTrue(promotion.cancel())
            XCTAssertFalse(promotion.acceptsPIN(for: generation))
            await Task.yield()
            validatorReturned = true
        }, readTarget: { stored }, commit: { stored = $0.xml })
        XCTAssertTrue(validatorReturned)
        XCTAssertEqual(outcome, .cancelled)
        XCTAssertEqual(stored, old)
    }

    func testExactlyValidatedBytesAreCommittedOnceAndLateCancelCannotUndoCommit() async throws {
        let promotion = PairingPromotion()
        var stored: Data?
        var validated: Data?
        var commits = 0
        let candidate = try record("new")
        let outcome = await promotion.validateAndPromote(candidate: candidate,
            validate: { validated = $0 }, readTarget: { stored }, commit: {
                XCTAssertFalse(promotion.cancel())
                XCTAssertEqual($0.xml, validated)
                commits += 1; stored = $0.xml
            })
        XCTAssertEqual(outcome, .committed)
        XCTAssertEqual(stored, validated)
        let again = await promotion.validateAndPromote(candidate: candidate,
            validate: { _ in XCTFail("revalidated") }, readTarget: { stored },
            commit: { _ in XCTFail("recommitted") })
        XCTAssertEqual(again, .alreadyUsed)
        XCTAssertEqual(commits, 1)
    }

    func testPostRenameFailureRequiresRecoveryAndPreRenameFailurePreservesOld() async throws {
        for renamed in [false, true] {
            let promotion = PairingPromotion(), old = try record("old")
            var stored: Data? = old
            let outcome = await promotion.validateAndPromote(candidate: try record("new"),
                validate: { _ in }, readTarget: { stored }, commit: {
                    if renamed { stored = $0.xml }
                    throw TestFailure.expected
                })
            XCTAssertEqual(outcome, renamed ? .recoveryRequired : .unchangedFailure)
            if !renamed { XCTAssertEqual(stored, old) }
        }
    }

    func testUnreadableReconciliationAndChangedTargetNeverClaimRollback() async throws {
        let promotion = PairingPromotion(), old = try record("old")
        var reads = 0
        let outcome = await promotion.validateAndPromote(candidate: try record("new"), validate: { _ in },
            readTarget: { reads += 1; if reads > 2 { throw TestFailure.expected }; return old },
            commit: { _ in throw TestFailure.expected })
        XCTAssertEqual(outcome, .recoveryRequired)
        let changed = PairingPromotion()
        var stored: Data? = old
        let foreign = try record("other-writer")
        let conflict = await changed.validateAndPromote(candidate: try record("new"),
            validate: { _ in stored = foreign }, readTarget: { stored },
            commit: { _ in XCTFail("overwrote changed target") })
        XCTAssertEqual(conflict, .recoveryRequired)
        XCTAssertEqual(stored, foreign)
    }

    func testCancelledBeforeStartAndNewGenerationCannotReuseOldPIN() async throws {
        let old = PairingPromotion(), next = PairingPromotion()
        XCTAssertTrue(old.acceptsPIN(for: old.generation))
        XCTAssertFalse(next.acceptsPIN(for: old.generation))
        XCTAssertTrue(old.cancel())
        let result = await old.validateAndPromote(candidate: try record("new"),
            validate: { _ in XCTFail("validated cancelled session") },
            readTarget: { XCTFail("read cancelled session"); return nil },
            commit: { _ in XCTFail("committed cancelled session") })
        XCTAssertEqual(result, .cancelled)
    }
    func testProtectedStorePreservesOldBeforeRenameAndRequiresRecoveryAfterRename() async throws {
        for renamed in [false, true] {
            let root = FileManager.default.temporaryDirectory.resolvingSymlinksInPath()
                .appendingPathComponent("pairing-promotion-test-" + UUID().uuidString, isDirectory: true)
            let store = try PrivateFileStore(root: root)
            try store.prepare()
            defer { try? FileManager.default.removeItem(at: root) }
            let old = try PairingRecord(data: record("old")).xml
            let candidate = try record("new")
            let normalized = try PairingRecord(data: candidate).xml
            try store.write(old, named: "remote.plist")
            let promotion = PairingPromotion()
            let outcome = await promotion.validateAndPromote(candidate: candidate,
                validate: { bytes in XCTAssertEqual(bytes, normalized) },
                readTarget: { try store.read("remote.plist") }, commit: { record in
                    try store.write(record.xml, named: "remote.plist", beforePromote: { _ in
                        if !renamed { throw TestFailure.expected }
                    })
                    throw TestFailure.expected
                })
            XCTAssertEqual(outcome, renamed ? .recoveryRequired : .unchangedFailure)
            XCTAssertEqual(try store.read("remote.plist"), renamed ? normalized : old)
        }
    }

    func testSwiftTaskCancellationThrownByValidatorIsReportedAsCancelled() async throws {
        let promotion = PairingPromotion(), candidate = try record("new")
        let operation = Task { @MainActor in
            await promotion.validateAndPromote(candidate: candidate, validate: { _ in
                withUnsafeCurrentTask { $0?.cancel() }
                throw CancellationError()
            }, readTarget: { nil }, commit: { _ in XCTFail("committed cancelled validator") })
        }
        let outcome = await operation.value
        XCTAssertEqual(outcome, .cancelled)
    }

    func testCancellationWhileReadingOriginalDoesNotEnterValidator() async throws {
        let promotion = PairingPromotion()
        let outcome = await promotion.validateAndPromote(candidate: try record("new"),
            validate: { _ in XCTFail("entered cancelled validator") },
            readTarget: { promotion.cancel(); return nil },
            commit: { _ in XCTFail("committed cancelled session") })
        XCTAssertEqual(outcome, .cancelled)
    }

}
