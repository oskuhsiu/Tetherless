import Foundation
import XCTest
@testable import TetherlessCore

@MainActor final class PairingValidationChallengeTests: XCTestCase {
    private func library() throws -> URL {
        let root = FileManager.default.temporaryDirectory.resolvingSymlinksInPath()
            .appendingPathComponent("pairing-challenge-fixture-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false,
                                               attributes: [.posixPermissions: 0o700])
        return root
    }
    private func challenge(_ root: URL) throws -> PairingValidationChallenge {
        var calls = 0
        return try PairingValidationChallenge(libraryDirectory: root) { count in
            calls += 1
            return Data(repeating: calls == 1 ? 0x11 : 0x22, count: count)
        }
    }
    private func path(_ root: URL, _ challenge: PairingValidationChallenge) -> URL {
        root.appendingPathComponent(String(challenge.relativePath.dropFirst("Library/".count)))
    }
    func testIndependentFilenameAndContentAreProtectedAndRemovedAfterJoin() async throws {
        let root = try library(); defer { try? FileManager.default.removeItem(at: root) }
        let value = try challenge(root)
        let owned = path(root, value)
        XCTAssertEqual(try Data(contentsOf: owned), Data(repeating: 0x22, count: 32))
        XCTAssertEqual(owned.lastPathComponent, String(repeating: "11", count: 32) + ".challenge")
        let attributes = try FileManager.default.attributesOfItem(atPath: owned.path)
        XCTAssertEqual((attributes[.posixPermissions] as? NSNumber)?.intValue, 0o600)
        let borrow = try value.borrowForNative()
        XCTAssertEqual(borrow.withExpectedBytes { Data($0) }, Data(repeating: 0x22, count: 32))
        var finished = false
        let closing = Task { @MainActor in try await value.closeAfterValidation(); finished = true }
        await Task.yield()
        XCTAssertFalse(finished); XCTAssertTrue(FileManager.default.fileExists(atPath: owned.path))
        borrow.returned()
        try await closing.value
        XCTAssertTrue(finished); XCTAssertFalse(FileManager.default.fileExists(atPath: owned.path))
        XCTAssertThrowsError(try value.borrowForNative())
    }
    func testReplacementBeforeCleanupIsPreserved() async throws {
        let root = try library(); defer { try? FileManager.default.removeItem(at: root) }
        let value = try challenge(root), owned = path(root, value)
        let moved = root.appendingPathComponent("owned-original")
        try FileManager.default.moveItem(at: owned, to: moved)
        let replacement = Data("unrelated fixture".utf8)
        try replacement.write(to: owned)
        do { try await value.closeAfterValidation(); XCTFail("replacement was treated as ours") }
        catch { XCTAssertEqual(error as? PairingChallengeError, .changedFile) }
        XCTAssertEqual(try Data(contentsOf: owned), replacement)
    }
    func testWrongRandomLengthDoesNotCreateChallengeDirectory() throws {
        let root = try library(); defer { try? FileManager.default.removeItem(at: root) }
        XCTAssertThrowsError(try PairingValidationChallenge(libraryDirectory: root, random: { _ in Data([1]) }))
        XCTAssertFalse(FileManager.default.fileExists(atPath: root.appendingPathComponent("TetherlessPairingValidation").path))
    }
}
