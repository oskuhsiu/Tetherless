// SPDX-License-Identifier: AGPL-3.0-only
#if canImport(CryptoKit) && canImport(Darwin)
import Foundation
import CryptoKit
import Darwin

public enum AnisetteLibraryCacheFailure: String, Error, LocalizedError, Sendable {
    case invalidReceipt, changedContent, missingLibraries, unsafeFile, capacity, unavailable
    public var errorDescription: String? { "Anisette library cache: \(rawValue)." }
}

/// Locally sealed integrity, NOT publisher authentication. The caller owns the
/// process-wide mutation lease and a trusted sandbox parent. Completed versions
/// are immutable and retained: an existing provider may still hold their URL.
public struct AnisetteLibraryCache: Sendable {
    public let directory: URL
    public let requiredLibraries: [String]
    private let records: PrivateFileStore
    private static let maximumEntries = 4096
    private static let maximumFile: Int64 = 128 * 1024 * 1024
    private static let maximumTotal: Int64 = 256 * 1024 * 1024

    private struct Entry: Codable, Equatable {
        let path: String
        let size: Int64
        let sha256: String
    }
    private struct Snapshot: Codable, Equatable {
        let files: [Entry]
        let directories: [String]
    }
    private struct Receipt: Codable {
        let version: Int
        let generation: UUID
        let archiveSHA256: String
        let requiredLibraries: [String]
        let snapshot: Snapshot
    }
    public init(directory: URL, requiredLibraries: [String]) throws {
        guard directory.isFileURL, !requiredLibraries.isEmpty, requiredLibraries.count <= 32,
              Set(requiredLibraries).count == requiredLibraries.count,
              requiredLibraries.allSatisfy(PrivateFileStore.validName) else {
            throw AnisetteLibraryCacheFailure.invalidReceipt
        }
        self.directory = directory
        self.requiredLibraries = requiredLibraries.sorted()
        records = try PrivateFileStore(root: directory.appendingPathComponent(".tetherless-cache-v1"))
    }

    /// A provider owns this object, not merely its directory URL. The shared
    /// descriptor prevents cleanup until all in-flight uses release ownership.
    public final class PinnedGeneration: Sendable {
        public let directory: URL
        private let usage: LibraryCacheUsage
        fileprivate init(directory: URL, usage: LibraryCacheUsage) {
            self.directory = directory; self.usage = usage
        }
    }

    public func pinCurrent() throws -> PinnedGeneration? {
        guard try directoryExists(directory), try directoryExists(records.root) else { return nil }
        let usage = try LibraryCacheUsage.acquire(in: records.root)
        guard let url = try current() else { return nil }
        return PinnedGeneration(directory: url, usage: usage)
    }

    /// Call only through a native mutation owner. All provider clients additionally
    /// hold PinnedGeneration. Deferring while busy is safe; deleting is not.
    @discardableResult
    public func pruneUnused() throws -> Bool {
        guard try directoryExists(directory), try directoryExists(records.root) else { return true }
        return try LibraryCacheMaintenance.reclaim(in: records.root) { try current()?.lastPathComponent }
    }

    /// No receipt means an old/untracked directory, never an implicitly trusted
    /// one. Malformed/unreadable/tampered receipts throw, not a cache miss.
    public func current() throws -> URL? {
        guard try directoryExists(directory), try directoryExists(records.root) else { return nil }
        guard let bytes = try records.read("current.json") else { return nil }
        let receipt: Receipt
        do { receipt = try JSONDecoder().decode(Receipt.self, from: bytes) }
        catch { throw AnisetteLibraryCacheFailure.invalidReceipt }
        guard receipt.version == 1, receipt.requiredLibraries == requiredLibraries,
              Self.validDigest(receipt.archiveSHA256) else { throw AnisetteLibraryCacheFailure.invalidReceipt }
        let url = generationURL(receipt.generation)
        let actual = try snapshot(url)
        guard actual == receipt.snapshot else { throw AnisetteLibraryCacheFailure.changedContent }
        return url
    }

    /// Build a new generation without touching the active version. `extract`
    /// must be the bounded safe extractor; it receives only private staging.
    /// Fault hooks exercise actual durable boundaries and do not bypass checks.
    @discardableResult
    public func install(archive: Data, expectedSHA256: String,
                        extract: (URL, URL) throws -> Void,
                        beforePublish: () throws -> Void = {},
                        afterPublish: () throws -> Void = {}) throws -> URL {
        guard archive.count > 0, archive.count <= 64 * 1024 * 1024,
              Self.validDigest(expectedSHA256) else { throw AnisetteLibraryCacheFailure.invalidReceipt }
        guard Self.digest(archive) == expectedSHA256.lowercased() else {
            throw AnisetteLibraryCacheFailure.changedContent
        }
        // Verify before creating even a staging directory.
        try prepareDirectory(directory)
        try records.prepare()
        // Reclaim before taking our shared in-flight install pin. A live provider
        // defers reclamation; the capacity guard still bounds retained versions.
        try pruneUnused()
        let installUsage = try LibraryCacheUsage.acquire(in: records.root)
        defer { withExtendedLifetime(installUsage) {} }
        let entries = try FileManager.default.contentsOfDirectory(atPath: records.root.path)
        // Bound abandoned versions as well. Never delete files held by a client.
        guard entries.filter({ $0.hasPrefix("version-") || $0.hasPrefix("stage-") }).count < 4 else {
            throw AnisetteLibraryCacheFailure.capacity
        }
        let id = UUID()
        let stage = records.root.appendingPathComponent("stage-" + id.uuidString)
        let payload = stage.appendingPathComponent("payload")
        let zip = stage.appendingPathComponent("package.zip")
        let final = generationURL(id)
        try prepareDirectory(stage)
        defer { try? FileManager.default.removeItem(at: stage) }
        // Old versions stay usable on extraction, hashing or journal failure.
        try archive.write(to: zip, options: .withoutOverwriting)
        try prepareDirectory(payload)
        try extract(zip, payload)
        let observed = try snapshot(payload)
        try syncTree(payload)
        try beforePublish()
        guard try snapshot(payload) == observed else { throw AnisetteLibraryCacheFailure.changedContent }
        guard rename(payload.path, final.path) == 0 else { throw AnisetteLibraryCacheFailure.unavailable }
        // Keep an unreferenced final version if publishing is interrupted. It is
        // never selected by scanning directories or timestamps after restart.
        try syncDirectory(records.root)
        let receipt = Receipt(version: 1, generation: id, archiveSHA256: expectedSHA256.lowercased(),
                              requiredLibraries: requiredLibraries, snapshot: observed)
        let bytes = try JSONEncoder().encode(receipt)
        try records.write(bytes, named: "current.json")
        try afterPublish()
        guard try records.read("current.json") == bytes,
              try current() == final else { throw AnisetteLibraryCacheFailure.changedContent }
        return final
    }

    private func generationURL(_ id: UUID) -> URL {
        records.root.appendingPathComponent("version-" + id.uuidString, isDirectory: true)
    }
    private static func validDigest(_ value: String) -> Bool {
        value.utf8.count == 64 && value.utf8.allSatisfy {
            (48...57).contains($0) || (65...70).contains($0) || (97...102).contains($0)
        }
    }
    private static func digest(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
    private func directoryExists(_ url: URL) throws -> Bool {
        var info = stat()
        guard lstat(url.path, &info) == 0 else {
            if errno == ENOENT { return false }
            throw AnisetteLibraryCacheFailure.unavailable
        }
        guard info.st_mode & S_IFMT == S_IFDIR else { throw AnisetteLibraryCacheFailure.unsafeFile }
        return true
    }
    private func prepareDirectory(_ url: URL) throws {
        if !FileManager.default.fileExists(atPath: url.deletingLastPathComponent().path) {
            // Base sandbox parents are created by the native owner, not by an
            // untrusted receipt or a recursive path from an archive.
            throw AnisetteLibraryCacheFailure.unavailable
        }
        guard mkdir(url.path, 0o700) == 0 || errno == EEXIST else {
            throw AnisetteLibraryCacheFailure.unavailable
        }
        guard try directoryExists(url) else { throw AnisetteLibraryCacheFailure.unsafeFile }
        #if os(iOS) || os(tvOS)
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: url.path)
        #endif
    }
    private func snapshot(_ root: URL) throws -> Snapshot {
        let fd = open(root.path, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW)
        guard fd >= 0 else { throw AnisetteLibraryCacheFailure.unsafeFile }
        defer { _ = close(fd) }
        var files = [Entry](), directories = [String]()
        var total: Int64 = 0, count = 0
        func walk(_ dir: Int32, _ url: URL, _ prefix: String, depth: Int) throws {
            guard depth <= 16 else { throw AnisetteLibraryCacheFailure.capacity }
            var before = stat(); guard fstat(dir, &before) == 0 else { throw AnisetteLibraryCacheFailure.unavailable }
            let names = try FileManager.default.contentsOfDirectory(atPath: url.path).sorted()
            guard names.count <= Self.maximumEntries - count else { throw AnisetteLibraryCacheFailure.capacity }
            count += names.count
            for name in names {
                guard PrivateFileStore.validName(name) else { throw AnisetteLibraryCacheFailure.unsafeFile }
                let path = prefix + name
                let child = openat(dir, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK)
                guard child >= 0 else { throw AnisetteLibraryCacheFailure.unsafeFile }
                defer { _ = close(child) }
                var info = stat(); guard fstat(child, &info) == 0 else { throw AnisetteLibraryCacheFailure.unavailable }
                if info.st_mode & S_IFMT == S_IFDIR {
                    directories.append(path)
                    try walk(child, url.appendingPathComponent(name), path + "/", depth: depth + 1)
                } else {
                    guard info.st_mode & S_IFMT == S_IFREG, info.st_nlink == 1,
                          info.st_size >= 0, info.st_size <= Self.maximumFile,
                          info.st_size <= Self.maximumTotal - total else { throw AnisetteLibraryCacheFailure.unsafeFile }
                    let handle = FileHandle(fileDescriptor: child, closeOnDealloc: false)
                    var hash = SHA256(), size: Int64 = 0
                    while let chunk = try handle.read(upToCount: 65_536), !chunk.isEmpty {
                        guard Int64(chunk.count) <= Self.maximumFile - size,
                              Int64(chunk.count) <= Self.maximumTotal - total else { throw AnisetteLibraryCacheFailure.capacity }
                        size += Int64(chunk.count); total += Int64(chunk.count); hash.update(data: chunk)
                    }
                    var after = stat(); guard fstat(child, &after) == 0, unchanged(info, after), size == info.st_size else {
                        throw AnisetteLibraryCacheFailure.changedContent
                    }
                    files.append(Entry(path: path, size: size, sha256: hash.finalize().map { String(format: "%02x", $0) }.joined()))
                }
            }
            var after = stat(); guard fstat(dir, &after) == 0, unchanged(before, after) else { throw AnisetteLibraryCacheFailure.changedContent }
        }
        try walk(fd, root, "", depth: 0)
        guard requiredLibraries.allSatisfy({ name in files.contains { $0.path == name && $0.size > 0 } }) else {
            throw AnisetteLibraryCacheFailure.missingLibraries
        }
        return Snapshot(files: files.sorted { $0.path < $1.path }, directories: directories.sorted())
    }
    private func unchanged(_ a: stat, _ b: stat) -> Bool {
        a.st_dev == b.st_dev && a.st_ino == b.st_ino && a.st_size == b.st_size && a.st_nlink == b.st_nlink &&
        a.st_mtimespec.tv_sec == b.st_mtimespec.tv_sec && a.st_mtimespec.tv_nsec == b.st_mtimespec.tv_nsec &&
        a.st_ctimespec.tv_sec == b.st_ctimespec.tv_sec && a.st_ctimespec.tv_nsec == b.st_ctimespec.tv_nsec
    }
    private func syncDirectory(_ url: URL) throws {
        let fd = open(url.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw AnisetteLibraryCacheFailure.unavailable }
        defer { _ = close(fd) }
        guard fsync(fd) == 0 else { throw AnisetteLibraryCacheFailure.unavailable }
    }
    private func syncTree(_ url: URL) throws {
        for child in try FileManager.default.contentsOfDirectory(at: url, includingPropertiesForKeys: [.isDirectoryKey]) {
            if try directoryExistsOrFile(child) { try syncTree(child) }
            else {
                let fd = open(child.path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK)
                guard fd >= 0 else { throw AnisetteLibraryCacheFailure.unavailable }
                defer { _ = close(fd) }
                var s = stat()
                guard fstat(fd, &s) == 0, s.st_mode & S_IFMT == S_IFREG, s.st_nlink == 1, fsync(fd) == 0 else {
                    throw AnisetteLibraryCacheFailure.unsafeFile
                }
            }
        }
        try syncDirectory(url)
    }
    private func directoryExistsOrFile(_ url: URL) throws -> Bool {
        var s = stat(); guard lstat(url.path, &s) == 0 else { throw AnisetteLibraryCacheFailure.unavailable }
        if s.st_mode & S_IFMT == S_IFDIR { return true }
        guard s.st_mode & S_IFMT == S_IFREG, s.st_nlink == 1 else { throw AnisetteLibraryCacheFailure.unsafeFile }
        return false
    }
}
#endif
