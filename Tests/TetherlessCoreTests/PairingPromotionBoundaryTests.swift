// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import XCTest
@testable import TetherlessCore

/// Narrow target-readback and winner contracts. These are synthetic commit
/// closures, not all-files/defaults rollback or real-device acceptance proofs.
@MainActor final class PairingPromotionBoundaryTests: XCTestCase {
    private enum Failure: Error { case injected }
    private func record(_ name: String, keyBytes: Int = 32, format: PropertyListSerialization.PropertyListFormat = .xml) throws -> Data {
        try PropertyListSerialization.data(fromPropertyList: [
            "identifier": name, "private_key": Data(repeating: 1, count: keyBytes),
            "public_key": Data(repeating: 2, count: 32)
        ], format: format, options: 0)
    }

    func testBinaryCandidateUsesSameNormalizedBytesForValidationAndCommit() async throws {
        let candidate = try record("binary", format: .binary)
        XCTAssertTrue(candidate.starts(with: Data("bplist00".utf8)))
        var stored: Data?, validated: Data?
        let outcome = await PairingPromotion().validateAndPromote(candidate: candidate,
            validate: { validated = $0 }, readTarget: { stored }, commit: { value in
                XCTAssertEqual(value.kind, .remote)
                XCTAssertEqual(value.xml, validated)
                stored = value.xml
            })
        XCTAssertEqual(outcome, .committed)
        XCTAssertEqual(stored, validated)
        XCTAssertFalse(try XCTUnwrap(stored).starts(with: Data("bplist00".utf8)))
    }

    func testBinaryInputWhoseNormalizedOutputExceedsCapNeverReadsOrValidates() async throws {
        let candidate = try record("expanded", keyBytes: 2900, format: .binary)
        XCTAssertLessThanOrEqual(candidate.count, 4096)
        XCTAssertGreaterThan(try PairingRecord(data: candidate).xml.count, 4096)
        let outcome = await PairingPromotion().validateAndPromote(candidate: candidate,
            validate: { _ in XCTFail("validated oversized normalized bytes") },
            readTarget: { XCTFail("read target for rejected candidate"); return nil },
            commit: { _ in XCTFail("committed rejected candidate") })
        XCTAssertEqual(outcome, .unchangedFailure)
    }

    func testOriginalReadFailureDoesNotValidateOrCommit() async throws {
        let outcome = await PairingPromotion().validateAndPromote(candidate: try record("new"),
            validate: { _ in XCTFail("validated after unreadable original") },
            readTarget: { throw Failure.injected }, commit: { _ in XCTFail("committed") })
        XCTAssertEqual(outcome, .unchangedFailure)
    }

    func testPostCommitMissingOrDifferentReadbackRequiresRecoveryWithoutRetry() async throws {
        for missing in [false, true] {
            let old = try record("old"), foreign = try record("foreign")
            let promotion = PairingPromotion()
            var stored: Data? = old, writes = 0
            let outcome = await promotion.validateAndPromote(candidate: try record("new"),
                validate: { _ in }, readTarget: { stored }, commit: { _ in
                    writes += 1; stored = missing ? nil : foreign
                })
            XCTAssertEqual(outcome, .recoveryRequired)
            let retry = await promotion.validateAndPromote(candidate: try record("new"),
                validate: { _ in XCTFail("revalidated uncertain commit") }, readTarget: { stored },
                commit: { _ in XCTFail("retried uncertain commit") })
            XCTAssertEqual(retry, .alreadyUsed); XCTAssertEqual(writes, 1)
            XCTAssertEqual(stored, missing ? nil : foreign)
        }
    }

    func testUnreadablePostCommitAndReconciliationRequiresRecovery() async throws {
        let old = try record("old")
        var reads = 0, writes = 0
        let outcome = await PairingPromotion().validateAndPromote(candidate: try record("new"),
            validate: { _ in }, readTarget: {
                reads += 1
                guard reads <= 2 else { throw Failure.injected }
                return old
            }, commit: { _ in writes += 1 })
        XCTAssertEqual(outcome, .recoveryRequired)
        XCTAssertEqual(writes, 1); XCTAssertEqual(reads, 4)
    }

    func testPrecommitReadFailureReconcilesOnlyWhenOldTargetIsReadableAgain() async throws {
        for readableAgain in [false, true] {
            let old = try record("old")
            var reads = 0
            let outcome = await PairingPromotion().validateAndPromote(candidate: try record("new"),
                validate: { _ in }, readTarget: {
                    reads += 1
                    if reads == 2 || (reads > 2 && !readableAgain) { throw Failure.injected }
                    return old
                }, commit: { _ in XCTFail("committed after failed precommit read") })
            XCTAssertEqual(outcome, readableAgain ? .unchangedFailure : .recoveryRequired)
        }
    }

    func testPostWriteMetadataFailureDoesNotPromiseRollback() async throws {
        let old = try record("old")
        var stored: Data? = old, selected = "old", validated: Data?
        let outcome = await PairingPromotion().validateAndPromote(candidate: try record("new"),
            validate: { validated = $0 }, readTarget: { stored }, commit: { value in
                stored = value.xml
                selected = "partially updated"
                throw Failure.injected
            })
        XCTAssertEqual(outcome, .recoveryRequired)
        XCTAssertEqual(stored, validated)
        XCTAssertEqual(selected, "partially updated")
    }

    func testExpirationWinnerAtFinalReadPreventsMutationEvenWithoutActorCancel() async throws {
        let old = try record("old"), cancellation = PairingCancellationController()
        var reads = 0, writes = 0
        let outcome = await PairingPromotion().validateAndPromote(candidate: try record("new"),
            validate: { _ in }, readTarget: {
                reads += 1
                if reads == 2 { XCTAssertTrue(cancellation.cancel()) }
                return old
            }, commit: { _ in
                guard cancellation.beginPromotion() else { throw CancellationError() }
                writes += 1
            })
        // The app maps the thread-safe cancellation winner to .cancelled; the
        // storage reconciler itself reports the unchanged target precisely.
        XCTAssertEqual(outcome, .unchangedFailure)
        XCTAssertTrue(cancellation.isCancelled); XCTAssertEqual(writes, 0)
        cancellation.finish()
    }
}
