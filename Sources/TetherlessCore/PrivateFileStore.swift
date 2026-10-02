// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

public enum PrivateFileError: String, Error, LocalizedError, Sendable {
    case invalidName, unavailable, unsafeFile, tooLarge, changedDuringRead, conflict, invalidContent
    public var errorDescription: String? { "Protected file operation failed: \(rawValue)." }
}

/// A bounded, flat store in a caller-owned directory. No symlink/hard-link files,
/// no delete-before-write, no path-derived filenames. Callers serialize mutations.
/// The root's parent must be a trusted, already-created sandbox directory.
public struct PrivateFileStore: Sendable {
    public let root: URL
    public let maximumBytes: Int
    public init(root: URL, maximumBytes: Int = 1_048_576) throws {
        guard root.isFileURL, maximumBytes > 0, maximumBytes <= 16_777_216 else {
            throw PrivateFileError.invalidName
        }
        self.root = root
        self.maximumBytes = maximumBytes
    }
    public static func validName(_ name: String) -> Bool {
        !name.isEmpty && name.utf8.count <= 128 && name != "." && name != ".." &&
        name.utf8.allSatisfy { (48...57).contains($0) || (65...90).contains($0) ||
            (97...122).contains($0) || $0 == 45 || $0 == 46 || $0 == 95 }
    }
    public func prepare() throws {
        let fd = try openRoot(create: true)
        defer { _ = close(fd) }
        guard fchmod(fd, mode_t(0o700)) == 0 else { throw PrivateFileError.unavailable }
        #if os(iOS) || os(tvOS)
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: root.path)
        #endif
        #if canImport(Darwin)
        var url = root
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try url.setResourceValues(values)
        #endif
    }
    private func openRoot(create: Bool) throws -> Int32 {
        if create && mkdir(root.path, mode_t(0o700)) != 0 && errno != EEXIST {
            throw PrivateFileError.unavailable
        }
        let fd = open(root.path, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW)
        guard fd >= 0 else { throw PrivateFileError.unavailable }
        return fd
    }
    public func read(_ name: String) throws -> Data? {
        guard Self.validName(name) else { throw PrivateFileError.invalidName }
        let dir = try openRoot(create: false)
        defer { _ = close(dir) }
        let fd = openat(dir, name, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK)
        guard fd >= 0 else {
            if errno == ENOENT { return nil }
            throw PrivateFileError.unsafeFile
        }
        defer { _ = close(fd) }
        return try Self.readDescriptor(fd, maximum: maximumBytes)
    }
    /// Security-scoped access, when needed, is owned by the native caller.
    public static func readExternal(_ url: URL, maximum: Int = 1_048_576) throws -> Data? {
        guard url.isFileURL, maximum > 0, maximum <= 16_777_216 else { throw PrivateFileError.invalidName }
        let fd = open(url.path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK)
        guard fd >= 0 else {
            if errno == ENOENT { return nil }
            throw PrivateFileError.unsafeFile
        }
        defer { _ = close(fd) }
        return try readDescriptor(fd, maximum: maximum)
    }
    private static func readDescriptor(_ fd: Int32, maximum: Int) throws -> Data {
        var before = stat()
        guard fstat(fd, &before) == 0, (before.st_mode & S_IFMT) == S_IFREG,
              before.st_nlink == 1, before.st_size >= 0 else { throw PrivateFileError.unsafeFile }
        guard before.st_size <= maximum else { throw PrivateFileError.tooLarge }
        let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: false)
        var bytes = Data()
        while bytes.count <= maximum {
            let chunk = try handle.read(upToCount: min(65_536, maximum + 1 - bytes.count)) ?? Data()
            if chunk.isEmpty { break }
            bytes.append(chunk)
        }
        guard bytes.count <= maximum else { throw PrivateFileError.tooLarge }
        var after = stat()
        guard fstat(fd, &after) == 0, before.st_size == after.st_size,
              after.st_size == bytes.count else { throw PrivateFileError.changedDuringRead }
        #if canImport(Darwin)
        guard before.st_mtimespec.tv_sec == after.st_mtimespec.tv_sec,
              before.st_mtimespec.tv_nsec == after.st_mtimespec.tv_nsec,
              before.st_ctimespec.tv_sec == after.st_ctimespec.tv_sec,
              before.st_ctimespec.tv_nsec == after.st_ctimespec.tv_nsec else { throw PrivateFileError.changedDuringRead }
        #else
        guard before.st_mtim.tv_sec == after.st_mtim.tv_sec,
              before.st_mtim.tv_nsec == after.st_mtim.tv_nsec,
              before.st_ctim.tv_sec == after.st_ctim.tv_sec,
              before.st_ctim.tv_nsec == after.st_ctim.tv_nsec else { throw PrivateFileError.changedDuringRead }
        #endif
        return bytes
    }
    public func write(_ bytes: Data, named name: String,
                      beforePromote: (URL) throws -> Void = { _ in }) throws {
        guard Self.validName(name) else { throw PrivateFileError.invalidName }
        guard !bytes.isEmpty, bytes.count <= maximumBytes else { throw PrivateFileError.tooLarge }
        try prepare()
        let dir = try openRoot(create: false)
        defer { _ = close(dir) }
        try checkRegularOrAbsent(dir, name: name)
        let temporaryName = ".staging-" + UUID().uuidString
        let fd = openat(dir, temporaryName, O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC | O_NOFOLLOW, mode_t(0o600))
        guard fd >= 0 else { throw PrivateFileError.unavailable }
        defer { _ = close(fd); _ = unlinkat(dir, temporaryName, 0) }
        let temporaryURL = root.appendingPathComponent(temporaryName)
        #if os(iOS) || os(tvOS)
        // Set protection before writing any secret bytes.
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: temporaryURL.path)
        #endif
        let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: false)
        try handle.write(contentsOf: bytes)
        guard fsync(fd) == 0 else { throw PrivateFileError.unavailable }
        try beforePromote(temporaryURL)
        try checkRegularOrAbsent(dir, name: name)
        guard renameat(dir, temporaryName, dir, name) == 0 else { throw PrivateFileError.unavailable }
        // A failed directory flush is ambiguous, not permission to delete a source.
        guard fsync(dir) == 0 else { throw PrivateFileError.unavailable }
    }
    private func checkRegularOrAbsent(_ dir: Int32, name: String) throws {
        var info = stat()
        if fstatat(dir, name, &info, AT_SYMLINK_NOFOLLOW) != 0 {
            if errno == ENOENT { return }
            throw PrivateFileError.unavailable
        }
        guard (info.st_mode & S_IFMT) == S_IFREG, info.st_nlink == 1 else { throw PrivateFileError.unsafeFile }
    }
    public func remove(_ name: String) throws {
        guard Self.validName(name) else { throw PrivateFileError.invalidName }
        let dir = try openRoot(create: false)
        defer { _ = close(dir) }
        try checkRegularOrAbsent(dir, name: name)
        if unlinkat(dir, name, 0) != 0 && errno != ENOENT { throw PrivateFileError.unavailable }
        guard fsync(dir) == 0 else { throw PrivateFileError.unavailable }
    }
    /// Never overwrites a different protected file and only removes legacy data
    /// after independently reading back the normalized destination. Caller owns
    /// the source directory and holds the same mutation lease as all importers.
    @discardableResult
    public func migrate(_ source: URL, to name: String,
                        normalize: (Data) throws -> Data) throws -> Bool {
        guard source.standardizedFileURL != root.appendingPathComponent(name).standardizedFileURL else {
            throw PrivateFileError.conflict
        }
        guard let original = try Self.readExternal(source, maximum: maximumBytes) else { return false }
        let normalized = try normalize(original)
        try prepare()
        if let current = try read(name) {
            guard try normalize(current) == normalized else { throw PrivateFileError.conflict }
        } else {
            try write(normalized, named: name)
        }
        guard try read(name) == normalized else { throw PrivateFileError.changedDuringRead }
        guard try Self.readExternal(source, maximum: maximumBytes) == original else {
            throw PrivateFileError.changedDuringRead
        }
        try FileManager.default.removeItem(at: source)
        return true
    }
}
