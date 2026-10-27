// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

public enum SafeArchiveError: String, Error, LocalizedError, Sendable {
    case unsafePath, unsupportedFormat, invalidArchive, limitExceeded, checksumMismatch, destinationConflict, invalidApp
    public var errorDescription: String? { "Archive rejected: \(rawValue)." }
}

public struct ArchiveLimits: Sendable {
    public var maximumArchiveBytes: UInt64 = 1_073_741_824
    public var maximumExpandedBytes: UInt64 = 4_294_967_296
    public var maximumFileBytes: UInt64 = 536_870_912
    public var maximumEntries: Int = 30_000
    public init() {}
    func validate() throws {
        guard maximumArchiveBytes > 0, maximumArchiveBytes <= 1_073_741_824,
              maximumExpandedBytes > 0, maximumExpandedBytes <= 4_294_967_296,
              maximumFileBytes > 0, maximumFileBytes <= maximumExpandedBytes,
              maximumEntries > 0, maximumEntries <= 30_000 else { throw SafeArchiveError.limitExceeded }
    }
}

/// Verify ZIP32 directory completeness before ZIPFoundation iteration. Its
/// iterator can stop on an unsupported entry; a valid prefix is not a valid ZIP.
/// This is structural checking, not a second decompressor. ZIP64/multidisk and
/// encryption intentionally fail closed in v1, with no unsafe fallback.
struct ArchivePreflight {
    struct Item {
        let compressed: UInt64
        let expanded: UInt64
        let crc: UInt32
    }
    let items: [Item]
    init(url: URL, limits: ArchiveLimits, check: () throws -> Void) throws {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        let size = try handle.seekToEnd()
        guard size >= 22, size <= limits.maximumArchiveBytes else { throw SafeArchiveError.limitExceeded }
        func read(_ offset: UInt64, _ count: Int) throws -> Data {
            guard count >= 0, UInt64(count) <= size, offset <= size - UInt64(count) else { throw SafeArchiveError.invalidArchive }
            try handle.seek(toOffset: offset)
            let data = try handle.read(upToCount: count) ?? Data()
            guard data.count == count else { throw SafeArchiveError.invalidArchive }
            return data
        }
        let tailSize = Int(min(size, 65_557))
        let tail = try read(size - UInt64(tailSize), tailSize)
        var end: Int?
        for i in stride(from: tail.count - 22, through: 0, by: -1) {
            if tail.u32(i) == 0x06054b50, i + 22 + Int(tail.u16(i + 20)) == tail.count { end = i; break }
        }
        guard let end else { throw SafeArchiveError.invalidArchive }
        let entries = Int(tail.u16(end + 10))
        let directorySize = UInt64(tail.u32(end + 12))
        let directoryOffset = UInt64(tail.u32(end + 16))
        guard tail.u16(end + 4) == 0, tail.u16(end + 6) == 0,
              Int(tail.u16(end + 8)) == entries,
              entries != 65_535, directorySize != 0xffff_ffff, directoryOffset != 0xffff_ffff else {
            throw SafeArchiveError.unsupportedFormat
        }
        guard entries > 0, entries <= limits.maximumEntries, directorySize <= 16_777_216,
              directoryOffset + directorySize == size - UInt64(tailSize) + UInt64(end) else {
            throw SafeArchiveError.invalidArchive
        }
        let directory = try read(directoryOffset, Int(directorySize))
        var result: [Item] = []
        var ranges: [Range<UInt64>] = []
        var cursor = 0
        var total: UInt64 = 0
        for _ in 0..<entries {
            try check()
            guard directory.count - cursor >= 46, directory.u32(cursor) == 0x02014b50 else { throw SafeArchiveError.invalidArchive }
            let flags = directory.u16(cursor + 8)
            let method = directory.u16(cursor + 10)
            let crc = directory.u32(cursor + 16)
            let compressed = UInt64(directory.u32(cursor + 20))
            let expanded = UInt64(directory.u32(cursor + 24))
            let nameLength = Int(directory.u16(cursor + 28))
            let extraLength = Int(directory.u16(cursor + 30))
            let commentLength = Int(directory.u16(cursor + 32))
            let localOffset = UInt64(directory.u32(cursor + 42))
            guard flags & ~UInt16(0x080e) == 0, method == 0 || method == 8,
                  directory.u16(cursor + 34) == 0,
                  compressed != 0xffff_ffff, expanded != 0xffff_ffff, localOffset != 0xffff_ffff else {
                throw SafeArchiveError.unsupportedFormat
            }
            let mode = directory.u32(cursor + 38) >> 16 & 0xf000
            guard mode == 0 || mode == 0x8000 || mode == 0x4000 else { throw SafeArchiveError.unsupportedFormat }
            guard nameLength > 0, nameLength <= 4096,
                  directory.count - cursor - 46 >= nameLength + extraLength + commentLength,
                  expanded <= limits.maximumFileBytes, total <= limits.maximumExpandedBytes - expanded,
                  compressed <= directoryOffset, localOffset <= directoryOffset - compressed,
                  localOffset + 30 <= directoryOffset else { throw SafeArchiveError.limitExceeded }
            total += expanded
            let name = directory.subdata(in: cursor+46..<cursor+46+nameLength)
            let local = try read(localOffset, 30)
            guard local.u32(0) == 0x04034b50, local.u16(6) == flags, local.u16(8) == method,
                  Int(local.u16(26)) == nameLength else { throw SafeArchiveError.invalidArchive }
            let start = localOffset + 30 + UInt64(nameLength) + UInt64(local.u16(28))
            var finish = start + compressed
            guard finish <= directoryOffset,
                  try read(localOffset + 30, nameLength) == name else { throw SafeArchiveError.invalidArchive }
            if flags & 8 == 0 {
                guard local.u32(14) == crc, UInt64(local.u32(18)) == compressed,
                      UInt64(local.u32(22)) == expanded else { throw SafeArchiveError.invalidArchive }
            } else {
                guard (local.u32(14) == 0 || local.u32(14) == crc),
                      (local.u32(18) == 0 || UInt64(local.u32(18)) == compressed),
                      (local.u32(22) == 0 || UInt64(local.u32(22)) == expanded),
                      finish + 12 <= directoryOffset else { throw SafeArchiveError.invalidArchive }
                let first = try read(finish, 4).u32(0)
                let descriptorSize = first == 0x08074b50 ? 16 : 12
                guard finish + UInt64(descriptorSize) <= directoryOffset else { throw SafeArchiveError.invalidArchive }
                let descriptor = try read(finish, descriptorSize)
                let skip = descriptorSize - 12
                guard descriptor.u32(skip) == crc, UInt64(descriptor.u32(skip+4)) == compressed,
                      UInt64(descriptor.u32(skip+8)) == expanded else { throw SafeArchiveError.invalidArchive }
                finish += UInt64(descriptorSize)
            }
            ranges.append(localOffset..<finish)
            result.append(Item(compressed: compressed, expanded: expanded, crc: crc))
            cursor += 46 + nameLength + extraLength + commentLength
        }
        guard cursor == directory.count else { throw SafeArchiveError.invalidArchive }
        ranges.sort { $0.lowerBound < $1.lowerBound }
        for i in ranges.indices.dropFirst() {
            guard ranges[i-1].upperBound <= ranges[i].lowerBound else { throw SafeArchiveError.invalidArchive }
        }
        items = result
    }
}

private extension Data {
    func u16(_ i: Int) -> UInt16 { UInt16(self[i]) | UInt16(self[i+1]) << 8 }
    func u32(_ i: Int) -> UInt32 { UInt32(u16(i)) | UInt32(u16(i+2)) << 16 }
}

struct ArchivePaths {
    private var explicit: Set<String> = []
    private var nodes: [String: (spelling: String, directory: Bool)] = [:]
    mutating func accept(_ path: String, directory: Bool) throws -> String {
        guard !path.isEmpty, path.utf8.count <= 4096, !path.hasPrefix("/"),
              !path.contains("\\"), !path.contains(":"),
              !path.unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 }) else { throw SafeArchiveError.unsafePath }
        var parts = path.split(separator: "/", omittingEmptySubsequences: false).map(String.init)
        if parts.last == "", directory { parts.removeLast() }
        guard !parts.isEmpty, parts.count <= 32,
              parts.allSatisfy({ !$0.isEmpty && $0 != "." && $0 != ".." && $0.utf8.count <= 255 }) else { throw SafeArchiveError.unsafePath }
        let clean = parts.joined(separator: "/")
        let key = canonical(clean)
        guard explicit.insert(key).inserted else { throw SafeArchiveError.unsafePath }
        for i in parts.indices {
            let prefix = parts[...i].joined(separator: "/")
            let prefixKey = canonical(prefix)
            let isDirectory = i < parts.count - 1 || directory
            if let prior = nodes[prefixKey] {
                guard prior.spelling == prefix, prior.directory, isDirectory else { throw SafeArchiveError.unsafePath }
            } else { nodes[prefixKey] = (prefix, isDirectory) }
        }
        return clean
    }
    private func canonical(_ s: String) -> String {
        s.precomposedStringWithCanonicalMapping.folding(options: [.caseInsensitive], locale: Locale(identifier: "en_US_POSIX"))
    }
}
