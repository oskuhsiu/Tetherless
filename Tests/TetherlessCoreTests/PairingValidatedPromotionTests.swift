import Foundation
import XCTest
@testable import TetherlessCore

/// Synthetic local ownership/composition fixtures. The injected validator does
/// not authenticate a device and cannot establish native ABI or identity proof.
@MainActor final class PairingValidatedPromotionTests: XCTestCase {
    private enum Failure: Error { case mismatch }
    private func record(_ name: String) throws -> Data {
        try PropertyListSerialization.data(fromPropertyList: [
            "identifier": name, "private_key": Data(repeating: 1, count: 32),
            "public_key": Data(repeating: 2, count: 32), "alt_irk": Data(repeating: 3, count: 16)
        ], format: .xml, options: 0)
    }
    private func root() throws -> URL {
        let value = FileManager.default.temporaryDirectory.resolvingSymlinksInPath()
            .appendingPathComponent("pairing-composition-fixture-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: value, withIntermediateDirectories: false)
        return value
    }
    private func challenge(_ root: URL) throws -> PairingValidationChallenge {
        var draw = 0
        return try PairingValidationChallenge(libraryDirectory: root) { count in
            draw += 1
            return Data(repeating: UInt8(draw), count: count)
        }
    }
    private func ownedFile(_ root: URL, _ challenge: PairingValidationChallenge) -> URL {
        root.appendingPathComponent(String(challenge.relativePath.dropFirst("Library/".count)))
    }

    func testPromotionFollowsExactValidationAndOwnedDocumentCleanup() async throws {
        let root = try root(); defer { try? FileManager.default.removeItem(at: root) }
        let store = try PrivateFileStore(root: root.appendingPathComponent("records")); try store.prepare()
        let old = try PairingRecord(data: record("old")).xml
        try store.write(old, named: "remote.plist")
        let document = try challenge(root), path = ownedFile(root, document)
        let controller = PairingCancellationController(), promotion = PairingPromotion()
        var validated: Data?
        let result = await promotion.validateAndPromote(candidate: try record("new"), validate: { bytes in
            validated = bytes
            XCTAssertEqual(try store.read("remote.plist"), old)
            let borrow = try document.borrowForNative()
            XCTAssertEqual(borrow.withExpectedBytes { Data($0) }, try Data(contentsOf: path))
            borrow.returned()
            try await document.closeAfterValidation()
        }, readTarget: { try store.read("remote.plist") }, commit: { value in
            XCTAssertFalse(FileManager.default.fileExists(atPath: path.path))
            XCTAssertEqual(value.xml, validated)
            guard controller.beginPromotion() else { throw CancellationError() }
            try store.write(value.xml, named: "remote.plist")
            XCTAssertFalse(controller.cancel())
        })
        XCTAssertEqual(result, .committed)
        XCTAssertEqual(try store.read("remote.plist"), validated)
        controller.finish()
    }

    func testExpirationWinnerBeforeCommitPreservesOldRecord() async throws {
        let old = try PairingRecord(data: record("old")).xml
        var stored: Data? = old
        let controller = PairingCancellationController(), promotion = PairingPromotion()
        var commits = 0
        let result = await promotion.validateAndPromote(candidate: try record("new"), validate: { _ in
            // Simulates an expiration callback whose decision does not depend
            // on scheduling a promotion.cancel() call on the UI actor.
            XCTAssertTrue(controller.cancel())
        }, readTarget: { stored }, commit: { value in
            guard controller.beginPromotion() else { throw CancellationError() }
            commits += 1; stored = value.xml
        })
        XCTAssertEqual(result, .unchangedFailure)
        XCTAssertTrue(controller.isCancelled)
        XCTAssertEqual(commits, 0); XCTAssertEqual(stored, old)
        controller.finish()
    }

    func testCancellationWaitsForBorrowedValidationBeforeFileCleanupAndReturn() async throws {
        let root = try root(); defer { try? FileManager.default.removeItem(at: root) }
        let document = try challenge(root), path = ownedFile(root, document)
        let promotion = PairingPromotion(), old = try record("old"), candidate = try record("new")
        let entered = AsyncStream<Void>.makeStream(), returned = AsyncStream<Void>.makeStream()
        var finished = false, stored: Data? = old
        let operation = Task { @MainActor in
            let result = await promotion.validateAndPromote(candidate: candidate, validate: { _ in
                let borrow = try document.borrowForNative()
                entered.continuation.yield(())
                var iterator = returned.stream.makeAsyncIterator()
                _ = await iterator.next() // synthetic native return, never a cancellation timeout
                borrow.returned()
                try await document.closeAfterValidation()
            }, readTarget: { stored }, commit: { stored = $0.xml })
            finished = true; return result
        }
        var iterator = entered.stream.makeAsyncIterator(); _ = await iterator.next()
        XCTAssertTrue(promotion.cancel())
        await Task.yield()
        XCTAssertFalse(finished); XCTAssertTrue(FileManager.default.fileExists(atPath: path.path))
        returned.continuation.yield(())
        let outcome = await operation.value
        XCTAssertEqual(outcome, .cancelled)
        XCTAssertFalse(FileManager.default.fileExists(atPath: path.path)); XCTAssertEqual(stored, old)
    }

    func testValidationAndCleanupFailuresBothPreserveOldRecord() async throws {
        for replaced in [false, true] {
            let root = try root(); defer { try? FileManager.default.removeItem(at: root) }
            let document = try challenge(root), path = ownedFile(root, document)
            let promotion = PairingPromotion(), old = try record("old")
            var stored: Data? = old
            let result = await promotion.validateAndPromote(candidate: try record("new"), validate: { _ in
                if replaced {
                    try FileManager.default.moveItem(at: path, to: root.appendingPathComponent("owned-original"))
                    try Data("unrelated fixture".utf8).write(to: path)
                    try await document.closeAfterValidation()
                } else {
                    try await document.closeAfterValidation()
                    throw Failure.mismatch
                }
            }, readTarget: { stored }, commit: { stored = $0.xml })
            XCTAssertEqual(result, .validationFailed); XCTAssertEqual(stored, old)
            if replaced { XCTAssertEqual(try Data(contentsOf: path), Data("unrelated fixture".utf8)) }
        }
    }
}
