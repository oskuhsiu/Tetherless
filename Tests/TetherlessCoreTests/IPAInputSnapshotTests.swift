// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif
@testable import TetherlessCore

@Suite("IPA input: one real bounded snapshot, not ZIP/signature validation")
struct IPAInputSnapshotTests {
    let fm = FileManager.default
    private func fixture(_ body: (URL, URL) throws -> Void) throws {
        let root = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try fm.createDirectory(at: root, withIntermediateDirectories: false)
        defer { try? fm.removeItem(at: root) }
        let source = root.appendingPathComponent("selected.ipa")
        try Data(repeating: 0x5A, count: 150_000).write(to: source)
        try body(source, root.appendingPathComponent("App.ipa"))
    }
    @Test func originalCanChangeAfterSnapshotWithoutChangingAcceptedBytes() throws {
        try fixture { (source: URL, output: URL) throws -> Void in
            try IPAInputSnapshot.create(from: source, at: output)
            try Data("replacement".utf8).write(to: source)
            #expect(try Data(contentsOf: output) == Data(repeating: 0x5A, count: 150_000))
            let attrs = try fm.attributesOfItem(atPath: output.path)
            #expect((attrs[.posixPermissions] as? NSNumber)?.intValue == 0o600)
            #if canImport(Darwin)
            #expect(try output.resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup == true)
            #endif
        }
    }
    @Test func sizeAndParameterRejectionsDoNotCreateOutput() throws {
        try fixture { (source: URL, output: URL) throws -> Void in
            #expect(throws: IPAInputFailure.tooLarge) {
                try IPAInputSnapshot.create(from: source, at: output, maximumBytes: 149_999)
            }
            for maximum: UInt64 in [0, 1_073_741_825, .max] {
                #expect(throws: IPAInputFailure.invalidLimit) {
                    try IPAInputSnapshot.create(from: source, at: output, maximumBytes: maximum)
                }
            }
            #expect(!fm.fileExists(atPath: output.path))
        }
    }
    @Test func existingDestinationIsNotOverwritten() throws {
        try fixture { (source: URL, output: URL) throws -> Void in
            try Data("keep".utf8).write(to: output)
            #expect(throws: IPAInputFailure.destinationExists) {
                try IPAInputSnapshot.create(from: source, at: output)
            }
            #expect(try Data(contentsOf: output) == Data("keep".utf8))
        }
    }
    @Test func symlinksHardlinksDirectoriesAndFIFOAreRefused() throws {
        for kind in 0..<4 {
            try fixture { (source: URL, output: URL) throws -> Void in
                let invalid = source.deletingLastPathComponent().appendingPathComponent("invalid")
                switch kind {
                case 0: try fm.createSymbolicLink(at: invalid, withDestinationURL: source)
                case 1: try fm.linkItem(at: source, to: invalid)
                case 2: try fm.createDirectory(at: invalid, withIntermediateDirectories: false)
                default: #expect(mkfifo(invalid.path, 0o600) == 0)
                }
                #expect(throws: IPAInputFailure.unsafeFile) {
                    try IPAInputSnapshot.create(from: invalid, at: output)
                }
                #expect(!fm.fileExists(atPath: output.path))
            }
        }
    }
    @Test func cancellationBeforeAndDuringCopyLeavesOriginalIntact() throws {
        for stop in [1,3] {
            try fixture { (source: URL, output: URL) throws -> Void in
                var calls = 0
                #expect(throws: CancellationError.self) {
                    try IPAInputSnapshot.create(from: source, at: output, check: {
                        calls += 1
                        if calls == stop { throw CancellationError() }
                    })
                }
                #expect(calls == stop)
                #expect(!fm.fileExists(atPath: output.path))
                #expect(try Data(contentsOf: source) == Data(repeating: 0x5A, count: 150_000))
            }
        }
    }
    @Test func inPlaceMutationOfSameLengthIsNotAccepted() throws {
        try fixture { (source: URL, output: URL) throws -> Void in
            var calls = 0
            #expect(throws: IPAInputFailure.sourceChanged) {
                try IPAInputSnapshot.create(from: source, at: output, check: {
                    calls += 1
                    if calls == 3 {
                        let writer = try FileHandle(forWritingTo: source)
                        defer { try? writer.close() }
                        try writer.seek(toOffset: 0)
                        try writer.write(contentsOf: Data([0x2A]))
                        try writer.synchronize()
                    }
                })
            }
            #expect(!fm.fileExists(atPath: output.path))
        }
    }
    @Test func growthDuringCopyCannotExceedLimit() throws {
        try fixture { (source: URL, output: URL) throws -> Void in
            var calls = 0
            #expect(throws: IPAInputFailure.tooLarge) {
                try IPAInputSnapshot.create(from: source, at: output, maximumBytes: 150_000, check: {
                    calls += 1
                    if calls == 3 {
                        let writer = try FileHandle(forWritingTo: source)
                        defer { try? writer.close() }
                        _ = try writer.seekToEnd()
                        try writer.write(contentsOf: Data(repeating: 1, count: 100_000))
                    }
                })
            }
            #expect(!fm.fileExists(atPath: output.path))
        }
    }
    @Test func errorCleanupDoesNotDeleteReplacedDestination() throws {
        try fixture { (source: URL, output: URL) throws -> Void in
            var calls = 0
            #expect(throws: CancellationError.self) {
                try IPAInputSnapshot.create(from: source, at: output, check: {
                    calls += 1
                    if calls == 3 {
                        try fm.removeItem(at: output)
                        try Data("other-owner".utf8).write(to: output)
                        throw CancellationError()
                    }
                })
            }
            #expect(try Data(contentsOf: output) == Data("other-owner".utf8))
        }
    }
    @Test func replacingOutputDuringCopyIsNotAcceptedOrDeleted() throws {
        try fixture { (source: URL, output: URL) throws -> Void in
            var calls = 0
            #expect(throws: IPAInputFailure.destinationChanged) {
                try IPAInputSnapshot.create(from: source, at: output, check: {
                    calls += 1
                    if calls == 3 {
                        try fm.removeItem(at: output)
                        try Data("other-owner".utf8).write(to: output)
                    }
                })
            }
            let replacement = try Data(contentsOf: output)
            #expect(replacement == Data("other-owner".utf8))
        }
    }
    @Test func reflectedFailureContainsNoUntrustedSourcePath() throws {
        try fixture { (source: URL, output: URL) throws -> Void in
            let secret = "SYNTHETIC_PRIVATE_DOCUMENT_TOKEN"
            let invalid = source.deletingLastPathComponent().appendingPathComponent(secret)
            do {
                try IPAInputSnapshot.create(from: invalid, at: output)
                Issue.record("Missing input accepted")
            } catch {
                #expect(error as? IPAInputFailure == .unsafeFile)
                #expect(!String(reflecting: error).contains(secret))
                #expect(!(error as NSError).userInfo.description.contains(secret))
            }
        }
    }
}
