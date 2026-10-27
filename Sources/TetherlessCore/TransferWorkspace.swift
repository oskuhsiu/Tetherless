// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

public enum TransferWorkspaceFailure: String, Error, LocalizedError, Sendable {
    case invalidLimit, unsafeEntry, unavailable, capacity, closed, invalidOutput
    public var errorDescription: String? { "Transfer workspace: \(rawValue)." }
}

/// One in-flight transfer per caller-owned pool, including its final bounded
/// read. Shared processes must use the same root. This bounds retained download
/// files, not Data retained by callers after this workspace has been released.
/// The stable usage.lock is never unlinked. A process death releases ownership;
/// the next admission removes only recognized abandoned flat workspaces.
public final class TransferWorkspace: @unchecked Sendable {
    public static let maximumTransferBytes = 128 * 1024 * 1024
    public let directory: URL
    public let maximumBytes: Int
    private let mutex = NSLock()
    private let rootDescriptor: Int32
    private let name: String
    private let identity: stat
    private var usage: LibraryCacheUsage?

    private struct FileEntry {
        let name: String
        let identity: stat
    }
    private struct Stage {
        let name: String
        let identity: stat
        let files: [FileEntry]
    }

    public init(pool: URL, maximumBytes: Int) throws {
        guard maximumBytes > 0, maximumBytes <= Self.maximumTransferBytes else {
            throw TransferWorkspaceFailure.invalidLimit
        }
        // pool's parent is an existing trusted sandbox directory; no path from
        // metadata, a URL or a downloaded file is used to select this directory.
        try PrivateFileStore(root: pool).prepare()
        let usage = try LibraryCacheUsage.acquire(in: pool, exclusive: true)
        let fd = open(pool.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw TransferWorkspaceFailure.unavailable }
        var admitted = false
        defer { if !admitted { _ = close(fd) }; withExtendedLifetime(usage) {} }
        // Validate ALL candidates before deleting any. Unknown root entries are
        // preserved; an unexpected entry inside our stage aborts cleanup.
        let stages = try Self.children(fd, limit: 128).filter { Self.isStage($0) }
            .map { try Self.inspect(fd, name: $0) }
        for stage in stages { try Self.remove(stage, from: fd) }
        guard fsync(fd) == 0 else { throw TransferWorkspaceFailure.unavailable }
        let name = "transfer-" + UUID().uuidString
        guard mkdirat(fd, name, mode_t(0o700)) == 0 else { throw TransferWorkspaceFailure.unavailable }
        // Any error after this point leaves a recognizable abandoned stage; the
        // next admission can reclaim it under the same stable lock.
        let stage = try Self.inspect(fd, name: name)
        let directory = pool.appendingPathComponent(name, isDirectory: true)
        #if os(iOS) || os(tvOS)
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: directory.path)
        #endif
        self.directory = directory
        self.maximumBytes = maximumBytes
        self.rootDescriptor = fd
        self.name = name
        self.identity = stage.identity
        self.usage = usage
        admitted = true
    }

    /// Only the downloader's canonical output, in this exact workspace, may be
    /// read. No link-following FileHandle initializer or unbounded Data load.
    public func readOutput(_ url: URL) throws -> Data {
        mutex.lock(); defer { mutex.unlock() }
        guard usage != nil else { throw TransferWorkspaceFailure.closed }
        guard url.isFileURL, Self.isOutput(url.lastPathComponent),
              url.standardizedFileURL == directory.appendingPathComponent(url.lastPathComponent).standardizedFileURL else {
            throw TransferWorkspaceFailure.invalidOutput
        }
        let dir = try Self.openDirectory(rootDescriptor, name: name, expected: identity)
        defer { _ = close(dir) }
        let fd = openat(dir, url.lastPathComponent, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC)
        guard fd >= 0 else { throw TransferWorkspaceFailure.unsafeEntry }
        defer { _ = close(fd) }
        var before = stat()
        guard fstat(fd, &before) == 0, Self.regular(before), before.st_size > 0,
              before.st_size <= maximumBytes else { throw TransferWorkspaceFailure.invalidOutput }
        let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: false)
        var bytes = Data()
        while bytes.count <= maximumBytes {
            let chunk = try handle.read(upToCount: min(65_536, maximumBytes + 1 - bytes.count)) ?? Data()
            if chunk.isEmpty { break }
            bytes.append(chunk)
        }
        var after = stat()
        guard fstat(fd, &after) == 0, Self.regular(after), Self.same(before, after),
              bytes.count == before.st_size, bytes.count <= maximumBytes,
              Self.unchangedTimes(before, after) else { throw TransferWorkspaceFailure.invalidOutput }
        return bytes
    }

    /// Successful callers must observe cleanup failure. Error paths may keep
    /// their original error; leftover stages remain recoverable on next entry.
    public func finish() throws {
        mutex.lock(); defer { mutex.unlock() }
        guard usage != nil else { return }
        let stage = try Self.inspect(rootDescriptor, name: name)
        guard Self.same(stage.identity, identity) else { throw TransferWorkspaceFailure.unsafeEntry }
        try Self.remove(stage, from: rootDescriptor)
        guard fsync(rootDescriptor) == 0 else { throw TransferWorkspaceFailure.unavailable }
        usage = nil
    }
    deinit {
        // Best effort only: callers use explicit finish for a success result.
        // A failure must not retain the process lock after this owner disappears.
        try? finish()
        _ = close(rootDescriptor)
    }

    private static func isStage(_ name: String) -> Bool {
        guard name.hasPrefix("transfer-") else { return false }
        let id = String(name.dropFirst(9))
        return UUID(uuidString: id)?.uuidString == id
    }
    private static func isOutput(_ name: String) -> Bool {
        guard name.hasPrefix("download-"), name.hasSuffix(".part") else { return false }
        let id = String(name.dropFirst(9).dropLast(5))
        return UUID(uuidString: id)?.uuidString == id
    }
    private static func regular(_ s: stat) -> Bool {
        s.st_mode & S_IFMT == S_IFREG && s.st_nlink == 1 && s.st_size >= 0
    }
    private static func same(_ a: stat, _ b: stat) -> Bool {
        a.st_dev == b.st_dev && a.st_ino == b.st_ino && a.st_mode & S_IFMT == b.st_mode & S_IFMT
    }
    private static func unchangedTimes(_ a: stat, _ b: stat) -> Bool {
        #if canImport(Darwin)
        a.st_mtimespec.tv_sec == b.st_mtimespec.tv_sec && a.st_mtimespec.tv_nsec == b.st_mtimespec.tv_nsec &&
        a.st_ctimespec.tv_sec == b.st_ctimespec.tv_sec && a.st_ctimespec.tv_nsec == b.st_ctimespec.tv_nsec
        #else
        a.st_mtim.tv_sec == b.st_mtim.tv_sec && a.st_mtim.tv_nsec == b.st_mtim.tv_nsec &&
        a.st_ctim.tv_sec == b.st_ctim.tv_sec && a.st_ctim.tv_nsec == b.st_ctim.tv_nsec
        #endif
    }
    private static func openDirectory(_ parent: Int32, name: String, expected: stat) throws -> Int32 {
        let fd = openat(parent, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw TransferWorkspaceFailure.unsafeEntry }
        var opened = stat()
        guard fstat(fd, &opened) == 0, same(opened, expected) else {
            _ = close(fd); throw TransferWorkspaceFailure.unsafeEntry
        }
        return fd
    }
    private static func children(_ parent: Int32, limit: Int) throws -> [String] {
        let fd = openat(parent, ".", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw TransferWorkspaceFailure.unavailable }
        guard let stream = fdopendir(fd) else { _ = close(fd); throw TransferWorkspaceFailure.unavailable }
        defer { _ = closedir(stream) }
        var result: [String] = []
        while true {
            errno = 0
            guard let entry = readdir(stream) else {
                guard errno == 0 else { throw TransferWorkspaceFailure.unavailable }
                return result.sorted()
            }
            let name = withUnsafePointer(to: &entry.pointee.d_name) { pointer in
                pointer.withMemoryRebound(to: CChar.self, capacity: MemoryLayout.size(ofValue: entry.pointee.d_name)) { String(cString: $0) }
            }
            if name == "." || name == ".." { continue }
            guard result.count < limit else { throw TransferWorkspaceFailure.capacity }
            result.append(name)
        }
    }
    private static func inspect(_ parent: Int32, name: String) throws -> Stage {
        var identity = stat()
        guard fstatat(parent, name, &identity, AT_SYMLINK_NOFOLLOW) == 0,
              identity.st_mode & S_IFMT == S_IFDIR else { throw TransferWorkspaceFailure.unsafeEntry }
        let fd = try openDirectory(parent, name: name, expected: identity)
        defer { _ = close(fd) }
        let files = try children(fd, limit: 8).map { name -> FileEntry in
            var s = stat()
            guard isOutput(name), fstatat(fd, name, &s, AT_SYMLINK_NOFOLLOW) == 0,
                  regular(s), s.st_size <= maximumTransferBytes else { throw TransferWorkspaceFailure.unsafeEntry }
            return FileEntry(name: name, identity: s)
        }
        return Stage(name: name, identity: identity, files: files)
    }
    private static func remove(_ stage: Stage, from parent: Int32) throws {
        let dir = try openDirectory(parent, name: stage.name, expected: stage.identity)
        defer { _ = close(dir) }
        for file in stage.files {
            var s = stat()
            guard fstatat(dir, file.name, &s, AT_SYMLINK_NOFOLLOW) == 0, regular(s),
                  same(s, file.identity) else { throw TransferWorkspaceFailure.unsafeEntry }
            guard unlinkat(dir, file.name, 0) == 0 else { throw TransferWorkspaceFailure.unavailable }
        }
        guard fsync(dir) == 0 else { throw TransferWorkspaceFailure.unavailable }
        var current = stat()
        guard fstatat(parent, stage.name, &current, AT_SYMLINK_NOFOLLOW) == 0,
              same(current, stage.identity) else { throw TransferWorkspaceFailure.unsafeEntry }
        guard unlinkat(parent, stage.name, AT_REMOVEDIR) == 0 else { throw TransferWorkspaceFailure.unavailable }
    }
}
