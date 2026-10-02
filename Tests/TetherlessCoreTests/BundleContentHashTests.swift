// SPDX-License-Identifier: AGPL-3.0-only
#if canImport(CryptoKit) && canImport(Darwin)
import Foundation
import Testing
@testable import TetherlessCore

@Suite("Production content hash: actual file bytes, not names and lengths")
struct BundleContentHashTests {
    func withRoot(_ body: (URL) throws -> Void) throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try body(root)
    }
    @Test func sameLengthDifferentBytesChangeCacheIdentity() throws {
        try withRoot { root in
            let file = root.appendingPathComponent("Executable")
            try Data("ABCD".utf8).write(to: file)
            let before = try BundleContentHash.bundle(root)
            try Data("WXYZ".utf8).write(to: file)
            #expect(try BundleContentHash.bundle(root) != before)
        }
    }
    @Test func profileAndDetachedSignatureAreNotCachePayload() throws {
        try withRoot { root in
            try Data("payload".utf8).write(to: root.appendingPathComponent("Executable"))
            let before = try BundleContentHash.bundle(root)
            try Data("new profile".utf8).write(to: root.appendingPathComponent("embedded.mobileprovision"))
            #expect(try BundleContentHash.bundle(root) == before)
            try Data("hidden payload".utf8).write(to: root.appendingPathComponent(".hidden"))
            #expect(try BundleContentHash.bundle(root) != before)
        }
    }
    @Test func symlinkAndHardlinkRejected() throws {
        try withRoot { root in
            let file = root.appendingPathComponent("file")
            try Data("payload".utf8).write(to: file)
            let link = root.appendingPathComponent("link")
            try FileManager.default.createSymbolicLink(at: link, withDestinationURL: file)
            #expect(throws: PrivateFileError.unsafeFile) { try BundleContentHash.bundle(root) }
            try FileManager.default.removeItem(at: link)
            try FileManager.default.linkItem(at: file, to: link)
            #expect(throws: PrivateFileError.unsafeFile) { try BundleContentHash.file(file) }
        }
    }
    @Test func emptyAndOversizedFilesHaveExplicitBehavior() throws {
        try withRoot { root in
            let file = root.appendingPathComponent("file")
            try Data().write(to: file)
            #expect(try BundleContentHash.file(file) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
            try Data(repeating: 1, count: 101).write(to: file)
            #expect(throws: PrivateFileError.unsafeFile) { try BundleContentHash.file(file, maximum: 100) }
        }
    }
}
#endif
