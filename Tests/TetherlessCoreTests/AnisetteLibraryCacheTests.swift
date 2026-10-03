// SPDX-License-Identifier: AGPL-3.0-only
#if canImport(CryptoKit) && canImport(Darwin)
import Foundation
import CryptoKit
import Darwin
import Testing
@testable import TetherlessCore

@Suite("Immutable ODA generations: real files and SHA-256, synthetic extractor; not publisher trust")
struct AnisetteLibraryCacheTests {
    let fm = FileManager.default
    enum Injected: Error { case crash }
    func root(_ body: (URL, AnisetteLibraryCache) throws -> Void) throws {
        let parent = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try fm.createDirectory(at: parent, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: parent) }
        try body(parent, AnisetteLibraryCache(directory: parent.appendingPathComponent("slot"), requiredLibraries: ["libadi.so", "libstore.so"]))
    }
    func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    func install(_ cache: AnisetteLibraryCache, value: String = "first",
                 before: () throws -> Void = {}, after: () throws -> Void = {}) throws -> URL {
        let archive = Data(value.utf8)
        return try cache.install(archive: archive, expectedSHA256: digest(archive), extract: { zip, output in
            // Real receipt/generation persistence with an explicitly synthetic
            // extractor. Native SafeArchive integration has separate tests.
            #expect(try Data(contentsOf: zip) == archive)
            try archive.write(to: output.appendingPathComponent("libadi.so"))
            try Data("library two".utf8).write(to: output.appendingPathComponent("libstore.so"))
        }, beforePublish: before, afterPublish: after)
    }
    @Test func trackedGenerationSurvivesNewStoreAndRetainsPreviousVersion() throws {
        try root { _, cache in
            #expect(try cache.current() == nil)
            let one = try install(cache)
            let two = try install(cache, value: "second")
            #expect(one != two)
            #expect(try Data(contentsOf: one.appendingPathComponent("libadi.so")) == Data("first".utf8))
            let reopened = try AnisetteLibraryCache(directory: cache.directory, requiredLibraries: ["libstore.so", "libadi.so"])
            #expect(try reopened.current() == two)
        }
    }
    @Test func sameSizeChangedLibraryFailsBeforeUse() throws {
        try root { _, cache in
            let current = try install(cache)
            try Data("other".utf8).write(to: current.appendingPathComponent("libadi.so"))
            #expect(throws: AnisetteLibraryCacheFailure.changedContent) { try cache.current() }
        }
    }
    @Test func extraHiddenFileAndMissingRequiredLibraryAreRejected() throws {
        try root { _, cache in
            let current = try install(cache)
            let hidden = current.appendingPathComponent(".extra")
            try Data([1]).write(to: hidden)
            #expect(throws: AnisetteLibraryCacheFailure.changedContent) { try cache.current() }
            try fm.removeItem(at: hidden)
            try fm.removeItem(at: current.appendingPathComponent("libstore.so"))
            #expect(throws: AnisetteLibraryCacheFailure.missingLibraries) { try cache.current() }
        }
    }
    @Test func symlinkHardlinkAndSpecialFilesAreNeverLibraries() throws {
        try root { parent, cache in
            let current = try install(cache)
            let target = current.appendingPathComponent("libadi.so")
            let outside = parent.appendingPathComponent("outside")
            try Data("first".utf8).write(to: outside)
            try fm.removeItem(at: target)
            try fm.createSymbolicLink(at: target, withDestinationURL: outside)
            #expect(throws: AnisetteLibraryCacheFailure.unsafeFile) { try cache.current() }
            try fm.removeItem(at: target)
            try fm.linkItem(at: outside, to: target)
            #expect(throws: AnisetteLibraryCacheFailure.unsafeFile) { try cache.current() }
            try fm.removeItem(at: target)
            #expect(mkfifo(target.path, 0o600) == 0)
            #expect(throws: AnisetteLibraryCacheFailure.unsafeFile) { try cache.current() }
        }
    }
    @Test func badDigestNeverCreatesTheSlot() throws {
        try root { _, cache in
            #expect(throws: AnisetteLibraryCacheFailure.changedContent) {
                try cache.install(archive: Data([1]), expectedSHA256: String(repeating: "0", count: 64), extract: { _, _ in Issue.record("Extractor called") })
            }
            #expect(!fm.fileExists(atPath: cache.directory.path))
        }
    }
    @Test func extractionFailureLeavesActivePointerByteIdentical() throws {
        try root { _, cache in
            let current = try install(cache)
            let pointer = cache.directory.appendingPathComponent(".tetherless-cache-v1/current.json")
            let before = try Data(contentsOf: pointer)
            let archive = Data("broken".utf8)
            #expect(throws: Injected.crash) {
                try cache.install(archive: archive, expectedSHA256: digest(archive), extract: { _, _ in throw Injected.crash })
            }
            #expect(try Data(contentsOf: pointer) == before)
            #expect(try cache.current() == current)
        }
    }
    @Test func interruptionsBeforeAndAfterPointerPublicationRecoverDeterministically() throws {
        try root { _, cache in
            let first = try install(cache)
            #expect(throws: Injected.crash) { try install(cache, value: "next", before: { throw Injected.crash }) }
            #expect(try cache.current() == first)
            #expect(throws: Injected.crash) { try install(cache, value: "next", after: { throw Injected.crash }) }
            let reopened = try AnisetteLibraryCache(directory: cache.directory, requiredLibraries: cache.requiredLibraries)
            let restored = try reopened.current()
            let second = try #require(restored)
            #expect(second != first)
            #expect(try Data(contentsOf: second.appendingPathComponent("libadi.so")) == Data("next".utf8))
        }
    }
    @Test func unreceiptedDirectoriesAndOrphansAreNeverSelected() throws {
        try root { _, cache in
            try fm.createDirectory(at: cache.directory, withIntermediateDirectories: true)
            try Data([1]).write(to: cache.directory.appendingPathComponent("libadi.so"))
            try Data([2]).write(to: cache.directory.appendingPathComponent("libstore.so"))
            #expect(try cache.current() == nil)
            _ = try install(cache)
            try fm.removeItem(at: cache.directory.appendingPathComponent(".tetherless-cache-v1/current.json"))
            #expect(try cache.current() == nil)
        }
    }
    @Test func corruptedAndFutureReceiptNeverBecomeMiss() throws {
        try root { _, cache in
            _ = try install(cache)
            let pointer = cache.directory.appendingPathComponent(".tetherless-cache-v1/current.json")
            let valid = try Data(contentsOf: pointer)
            let decoded = try JSONSerialization.jsonObject(with: valid)
            var json = try #require(decoded as? [String: Any])
            json["version"] = 999
            try JSONSerialization.data(withJSONObject: json).write(to: pointer)
            #expect(throws: AnisetteLibraryCacheFailure.invalidReceipt) { try cache.current() }
            try Data("bad".utf8).write(to: pointer)
            #expect(throws: AnisetteLibraryCacheFailure.invalidReceipt) { try cache.current() }
        }
    }
    @Test func pointerWriteFailureDoesNotDeleteAnyExistingVersion() throws {
        try root { _, cache in
            let first = try install(cache)
            let pointer = cache.directory.appendingPathComponent(".tetherless-cache-v1/current.json")
            let saved = try Data(contentsOf: pointer)
            #expect(throws: PrivateFileError.unsafeFile) {
                try install(cache, value: "next", before: {
                    try fm.removeItem(at: pointer)
                    try fm.createDirectory(at: pointer, withIntermediateDirectories: false)
                })
            }
            try fm.removeItem(at: pointer)
            try saved.write(to: pointer)
            #expect(try cache.current() == first)
        }
    }
    @Test func retentionBoundStopsUpdatesWithoutEvictingCurrentProvider() throws {
        try root { _, cache in
            for index in 0..<4 { _ = try install(cache, value: "v\(index)") }
            let current = try cache.current()
            #expect(throws: AnisetteLibraryCacheFailure.capacity) { try install(cache, value: "overflow") }
            #expect(try cache.current() == current)
        }
    }
    @Test func slotSymlinkAndChangedLibraryContractAreRejected() throws {
        try root { parent, cache in
            try fm.createSymbolicLink(at: cache.directory, withDestinationURL: parent)
            #expect(throws: AnisetteLibraryCacheFailure.unsafeFile) { try cache.current() }
            try fm.removeItem(at: cache.directory)
            _ = try install(cache)
            let changed = try AnisetteLibraryCache(directory: cache.directory, requiredLibraries: ["unexpected.so"])
            #expect(throws: AnisetteLibraryCacheFailure.invalidReceipt) { try changed.current() }
        }
    }
}
#endif
