// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
import ZIPFoundation
@testable import TetherlessArchive

private struct RawEntry {
    var name: String
    var bytes = Data([1,2,3])
    var flags: UInt16 = 0x800
    var mode: UInt32 = 0x81a4
    var crc: UInt32?
    var localName: String?
    var declaredSize: UInt32?
    var descriptor = false
}
private func crc32(_ bytes: Data) -> UInt32 {
    var crc: UInt32 = 0xffff_ffff
    for byte in bytes {
        crc ^= UInt32(byte)
        for _ in 0..<8 { crc = crc & 1 == 1 ? (crc >> 1) ^ 0xedb88320 : crc >> 1 }
    }
    return ~crc
}
private extension Data {
    mutating func word(_ x: UInt16) { append(UInt8(truncatingIfNeeded: x)); append(UInt8(truncatingIfNeeded: x >> 8)) }
    mutating func dword(_ x: UInt32) { word(UInt16(truncatingIfNeeded: x)); word(UInt16(truncatingIfNeeded: x >> 16)) }
}
/// Builds real ZIP bytes without using the implementation's parser/decompressor.
/// Corruption fields let each test cross the actual ZIPFoundation boundary.
private func zipBytes(_ entries: [RawEntry]) -> Data {
    var bytes = Data(), directory = Data()
    for e in entries {
        let offset = UInt32(bytes.count)
        let name = Data(e.name.utf8), local = Data((e.localName ?? e.name).utf8)
        let checksum = e.crc ?? crc32(e.bytes), size = e.declaredSize ?? UInt32(e.bytes.count)
        let flags = e.flags | (e.descriptor ? 8 : 0)
        bytes.dword(0x04034b50); bytes.word(20); bytes.word(flags); bytes.word(0); bytes.word(0); bytes.word(0)
        bytes.dword(e.descriptor ? 0 : checksum); bytes.dword(e.descriptor ? 0 : UInt32(e.bytes.count)); bytes.dword(e.descriptor ? 0 : size)
        bytes.word(UInt16(local.count)); bytes.word(0); bytes.append(local); bytes.append(e.bytes)
        if e.descriptor { bytes.dword(0x08074b50); bytes.dword(checksum); bytes.dword(UInt32(e.bytes.count)); bytes.dword(size) }
        directory.dword(0x02014b50); directory.word(0x0314); directory.word(20); directory.word(flags); directory.word(0)
        directory.word(0); directory.word(0); directory.dword(checksum); directory.dword(UInt32(e.bytes.count)); directory.dword(size)
        directory.word(UInt16(name.count)); directory.word(0); directory.word(0); directory.word(0); directory.word(0)
        directory.dword(e.mode << 16); directory.dword(offset); directory.append(name)
    }
    let offset = UInt32(bytes.count)
    bytes.append(directory)
    bytes.dword(0x06054b50); bytes.word(0); bytes.word(0); bytes.word(UInt16(entries.count)); bytes.word(UInt16(entries.count))
    bytes.dword(UInt32(directory.count)); bytes.dword(offset); bytes.word(0)
    return bytes
}

@Suite("Real ZIP extraction, adversarial bytes and filesystem isolation")
struct ArchiveTests {
    private func fixture(_ body: (URL, URL, URL) throws -> Void) throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try body(root, root.appendingPathComponent("input.ipa"), root.appendingPathComponent("output"))
    }
    private func ipaEntries() throws -> [RawEntry] {
        let info = try PropertyListSerialization.data(fromPropertyList: ["CFBundleIdentifier":"example.test", "CFBundleExecutable":"Test"], format: .binary, options: 0)
        return [RawEntry(name: "Payload/Test.app/Info.plist", bytes: info), RawEntry(name: "Payload/Test.app/Test", bytes: Data([1,2,3,4]))]
    }
    @Test func validIPAExtractsSingleAppAndCleansStaging() throws {
        try fixture { _, source, output in
            try zipBytes(ipaEntries()).write(to: source)
            let app = try SafeArchive.extractIPA(at: source, toDirectory: output)
            #expect(app.lastPathComponent == "Test.app")
            #expect(try Data(contentsOf: app.appendingPathComponent("Test")) == Data([1,2,3,4]))
            #expect(try FileManager.default.contentsOfDirectory(atPath: output.path) == ["Test.app"])
        }
    }
    @Test func actualDeflatedChunksAndDescriptorArchivesExtract() throws {
        try fixture { _, source, output in
            let input = Data(repeating: 42, count: 150_000)
            do {
                let zip = try ZIPFoundation.Archive(url: source, accessMode: .create)
                try zip.addEntry(with: "folder/file", type: .file, uncompressedSize: Int64(input.count), compressionMethod: .deflate) { pos, count in
                    input.subdata(in: Int(pos)..<Int(pos)+count)
                }
            }
            try SafeArchive.extract(at: source, toDirectory: output)
            #expect(try Data(contentsOf: output.appendingPathComponent("folder/file")) == input)
            try FileManager.default.removeItem(at: output)
            var entry = RawEntry(name: "descriptor"); entry.descriptor = true
            try zipBytes([entry]).write(to: source)
            try SafeArchive.extract(at: source, toDirectory: output)
            #expect(try Data(contentsOf: output.appendingPathComponent("descriptor")) == entry.bytes)
        }
    }
    @Test(arguments: ["../escape", "/absolute", "a/../../escape", "a\\escape", "a/./file", "a//file", "a\u{0000}b", "C:drive"])
    func traversalNeverPublishes(_ name: String) throws {
        try fixture { root, source, output in
            try zipBytes([RawEntry(name: "good"), RawEntry(name: name)]).write(to: source)
            #expect(throws: (any Error).self) { try SafeArchive.extract(at: source, toDirectory: output) }
            #expect(!FileManager.default.fileExists(atPath: output.path))
            #expect(!FileManager.default.fileExists(atPath: root.appendingPathComponent("escape").path))
        }
    }
    @Test(arguments: [["a", "a"], ["Folder/a", "folder/b"], ["é", "e\u{0301}"], ["a/b", "a"], ["a", "a/b"]])
    func collisionsFailBeforeWriting(_ paths: [String]) throws {
        try fixture { _, source, output in
            try zipBytes(paths.map { RawEntry(name: $0) }).write(to: source)
            #expect(throws: SafeArchiveError.unsafePath) { try SafeArchive.extract(at: source, toDirectory: output) }
            #expect(!FileManager.default.fileExists(atPath: output.path))
        }
    }
    @Test(arguments: [UInt32(0xa1ff), UInt32(0x11ff), UInt32(0x61ff)])
    func symlinksAndSpecialFilesAreNotMaterialized(_ mode: UInt32) throws {
        try fixture { _, source, output in
            var entry = RawEntry(name: "special"); entry.mode = mode
            try zipBytes([entry]).write(to: source)
            #expect(throws: SafeArchiveError.unsupportedFormat) { try SafeArchive.extract(at: source, toDirectory: output) }
        }
    }
    @Test func encryptedTrailingEntryCannotBecomeValidPrefix() throws {
        try fixture { _, source, output in
            var encrypted = RawEntry(name: "encrypted"); encrypted.flags |= 1
            try zipBytes([RawEntry(name: "first"), encrypted]).write(to: source)
            #expect(throws: SafeArchiveError.unsupportedFormat) { try SafeArchive.extract(at: source, toDirectory: output) }
        }
    }
    @Test func localAndCentralNamesMustAgree() throws {
        try fixture { _, source, output in
            var entry = RawEntry(name: "safe"); entry.localName = "evil"
            try zipBytes([entry]).write(to: source)
            #expect(throws: SafeArchiveError.invalidArchive) { try SafeArchive.extract(at: source, toDirectory: output) }
        }
    }
    @Test func zeroCRCIsVerifiedRatherThanSkipped() throws {
        try fixture { _, source, output in
            var entry = RawEntry(name: "bad"); entry.crc = 0
            try zipBytes([entry]).write(to: source)
            #expect(throws: SafeArchiveError.checksumMismatch) { try SafeArchive.extract(at: source, toDirectory: output) }
            #expect(!FileManager.default.fileExists(atPath: output.path))
        }
    }
    @Test func lyingUncompressedSizeIsRejectedByStreamingCounter() throws {
        try fixture { _, source, output in
            var entry = RawEntry(name: "too-big"); entry.declaredSize = 1
            try zipBytes([entry]).write(to: source)
            #expect(throws: (any Error).self) { try SafeArchive.extract(at: source, toDirectory: output) }
            #expect(!FileManager.default.fileExists(atPath: output.path))
        }
    }
    @Test func limitAndCancelledExtractionDoNotPublish() throws {
        try fixture { _, source, output in
            try zipBytes([RawEntry(name: "file")]).write(to: source)
            var limits = ArchiveLimits(); limits.maximumExpandedBytes = 2; limits.maximumFileBytes = 2
            #expect(throws: SafeArchiveError.limitExceeded) { try SafeArchive.extract(at: source, toDirectory: output, limits: limits) }
            let progress = Progress(totalUnitCount: 100); progress.cancel()
            #expect(throws: CancellationError.self) { try SafeArchive.extract(at: source, toDirectory: output, progress: progress) }
            #expect(!FileManager.default.fileExists(atPath: output.path))
        }
    }
    @Test func destinationCollisionPreservesUnrelatedFiles() throws {
        try fixture { _, source, output in
            try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
            let sentinel = output.appendingPathComponent("keep")
            try Data([9]).write(to: sentinel)
            try zipBytes([RawEntry(name: "keep"), RawEntry(name: "new")]).write(to: source)
            #expect(throws: SafeArchiveError.destinationConflict) { try SafeArchive.extract(at: source, toDirectory: output) }
            #expect(try Data(contentsOf: sentinel) == Data([9]))
            #expect(try FileManager.default.contentsOfDirectory(atPath: output.path) == ["keep"])
        }
    }
    @Test func invalidAndMultiAppIPAsNeverPublish() throws {
        try fixture { _, source, output in
            let entries = try ipaEntries()
            try zipBytes(entries + [RawEntry(name: "Payload/Second.app/file")]).write(to: source)
            #expect(throws: SafeArchiveError.invalidApp) { try SafeArchive.extractIPA(at: source, toDirectory: output) }
            try zipBytes([RawEntry(name: "Payload/Test.app/file")]).write(to: source)
            #expect(throws: (any Error).self) { try SafeArchive.extractIPA(at: source, toDirectory: output) }
            #expect(!FileManager.default.fileExists(atPath: output.path))
        }
    }
    @Test func symlinkSourceOrDestinationIsRejected() throws {
        try fixture { root, source, output in
            let actual = root.appendingPathComponent("actual")
            try zipBytes([RawEntry(name: "good")]).write(to: actual)
            try FileManager.default.createSymbolicLink(at: source, withDestinationURL: actual)
            #expect(throws: SafeArchiveError.unsafePath) { try SafeArchive.extract(at: source, toDirectory: output) }
            try FileManager.default.removeItem(at: source)
            try FileManager.default.moveItem(at: actual, to: source)
            try FileManager.default.createSymbolicLink(at: output, withDestinationURL: root)
            #expect(throws: SafeArchiveError.unsafePath) { try SafeArchive.extract(at: source, toDirectory: output) }
        }
    }
    @Test func truncatedEOCDAndZIP64MarkerAreRejected() throws {
        try fixture { _, source, output in
            var bytes = zipBytes([RawEntry(name: "good")]); bytes.removeLast()
            try bytes.write(to: source)
            #expect(throws: (any Error).self) { try SafeArchive.extract(at: source, toDirectory: output) }
            bytes = zipBytes([RawEntry(name: "good")]); bytes[bytes.count-12] = 255; bytes[bytes.count-11] = 255
            try bytes.write(to: source)
            #expect(throws: SafeArchiveError.unsupportedFormat) { try SafeArchive.extract(at: source, toDirectory: output) }
        }
    }
}
