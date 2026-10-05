#if canImport(Darwin)
import Foundation
import Darwin
import XCTest
import IDevice
@testable import TetherlessCore

/// Executes the exact Swift bridge against the explicitly synthetic C spy.
/// No authenticated peer, native Rust ABI or device behavior is exercised.
@MainActor final class NativeStagedPairingValidatorTests: XCTestCase {
    private func root() throws -> URL {
        let value = FileManager.default.temporaryDirectory.resolvingSymlinksInPath()
            .appendingPathComponent("pairing-validator-spy-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: value, withIntermediateDirectories: false)
        return value
    }
    private func challenge(_ root: URL) throws -> PairingValidationChallenge {
        var draw = 0
        return try PairingValidationChallenge(libraryDirectory: root) { count in
            draw += 1; return Data(repeating: UInt8(draw), count: count)
        }
    }
    private func endpoint() throws -> PairingNumericEndpoint {
        var value = sockaddr_in()
        value.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        value.sin_family = sa_family_t(AF_INET); value.sin_port = UInt16(49152).bigEndian
        _ = "127.0.0.1".withCString { inet_pton(AF_INET, $0, &value.sin_addr) }
        return try withUnsafeBytes(of: &value) { try PairingNumericEndpoint(sockaddrBytes: Data($0)) }
    }
    private func entered() async -> Bool {
        let end = ProcessInfo.processInfo.systemUptime + 2
        while tetherless_spy_started() == 0, ProcessInfo.processInfo.systemUptime < end { await Task.yield() }
        return tetherless_spy_started() == 1
    }
    private func validate(_ subject: NativeStagedPairingValidator, _ document: PairingValidationChallenge) async throws {
        try await subject.validate(record: Data("synthetic record".utf8), endpoint: endpoint(),
            bundleIdentifier: "test.Tetherless", challenge: document, timeoutMilliseconds: 1000)
    }

    func testExactBridgeReturnsThenFreesTokenAndReleasesDocumentBorrow() async throws {
        tetherless_spy_reset(false)
        let root = try root(); defer { try? FileManager.default.removeItem(at: root) }
        let document = try challenge(root), subject = try NativeStagedPairingValidator()
        try await validate(subject, document)
        await subject.close()
        try await document.closeAfterValidation()
        XCTAssertEqual(tetherless_spy_started(), 1); XCTAssertEqual(tetherless_spy_invalid_input(), 0)
        XCTAssertEqual(tetherless_spy_active(), 0); XCTAssertEqual(tetherless_spy_frees(), 1)
        XCTAssertEqual(tetherless_spy_freed_while_active(), 0)
    }

    func testCancellationAndCloseWaitForActualFFIReturn() async throws {
        tetherless_spy_reset(true)
        let root = try root(); defer { try? FileManager.default.removeItem(at: root) }
        let document = try challenge(root), subject = try NativeStagedPairingValidator()
        let path = root.appendingPathComponent(String(document.relativePath.dropFirst("Library/".count)))
        let operation = Task { @MainActor in try await validate(subject, document) }
        let started = await entered(); XCTAssertTrue(started)
        subject.cancel()
        var closed = false, removed = false
        let closing = Task { @MainActor in await subject.close(); closed = true }
        let cleanup = Task { @MainActor in try await document.closeAfterValidation(); removed = true }
        await Task.yield()
        XCTAssertFalse(closed); XCTAssertFalse(removed)
        XCTAssertEqual(tetherless_spy_frees(), 0)
        XCTAssertTrue(FileManager.default.fileExists(atPath: path.path))
        tetherless_spy_release()
        do { try await operation.value; XCTFail("cancelled spy returned success") }
        catch { XCTAssertTrue(error is NativeStagedValidationError) }
        await closing.value; try await cleanup.value
        XCTAssertTrue(closed); XCTAssertTrue(removed)
        XCTAssertEqual(tetherless_spy_active(), 0); XCTAssertEqual(tetherless_spy_frees(), 1)
        XCTAssertEqual(tetherless_spy_freed_while_active(), 0)
        XCTAssertFalse(FileManager.default.fileExists(atPath: path.path))
    }

    func testPreCancelledTokenAndLateCancelNeverEnterFreedNativeHandle() async throws {
        tetherless_spy_reset(false)
        let root = try root(); defer { try? FileManager.default.removeItem(at: root) }
        let document = try challenge(root), subject = try NativeStagedPairingValidator()
        subject.cancel()
        do { try await validate(subject, document); XCTFail("pre-cancelled spy returned success") }
        catch { XCTAssertTrue(error is NativeStagedValidationError) }
        let cancellations = tetherless_spy_cancels()
        subject.cancel(); await subject.close()
        XCTAssertEqual(tetherless_spy_cancels(), cancellations)
        XCTAssertEqual(tetherless_spy_frees(), 1)
        try await document.closeAfterValidation()
    }

    func testSecondValidationAndRepeatedCloseDoNotReuseToken() async throws {
        tetherless_spy_reset(false)
        let root = try root(); defer { try? FileManager.default.removeItem(at: root) }
        let document = try challenge(root), subject = try NativeStagedPairingValidator()
        try await validate(subject, document)
        do { try await validate(subject, document); XCTFail("reused retired token") }
        catch { XCTAssertTrue(error is NativeStagedValidationError) }
        async let first: Void = subject.close()
        async let second: Void = subject.close()
        _ = await (first, second)
        XCTAssertEqual(tetherless_spy_started(), 1); XCTAssertEqual(tetherless_spy_frees(), 1)
        try await document.closeAfterValidation()
    }

    func testRejectedInputsAndClosedChallengeNeverDispatchNativeValidation() async throws {
        for closed in [true, false] {
            tetherless_spy_reset(false)
            let root = try root(); defer { try? FileManager.default.removeItem(at: root) }
            let document = try challenge(root), subject = try NativeStagedPairingValidator()
            if closed { try await document.closeAfterValidation() }
            do {
                try await subject.validate(record: Data([1]), endpoint: endpoint(),
                    bundleIdentifier: closed ? "test.Tetherless" : "invalid..bundle", challenge: document, timeoutMilliseconds: 1000)
                XCTFail("invalid request was accepted")
            } catch { /* Fixed local failure; no native payload or endpoint is printed. */ }
            await subject.close(); try await document.closeAfterValidation()
            XCTAssertEqual(tetherless_spy_started(), 0); XCTAssertEqual(tetherless_spy_frees(), 1)
        }
    }
}
#endif
