// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

public enum IPAInputFailure: String, Error, LocalizedError, Sendable {
    case invalidLimit, unsafeFile, unavailable, tooLarge, sourceChanged, destinationExists, destinationChanged
    public var errorDescription: String? { "IPA input: \(rawValue)." }
}

/// One bounded, private copy is the input to both extraction and later caching.
/// The caller owns the destination directory and keeps external read permission
/// while this executes. This is not ZIP validation or signature verification.
public enum IPAInputSnapshot {
    public static func create(from source: URL, at destination: URL,
                              maximumBytes: UInt64 = 1_073_741_824,
                              check: () throws -> Void = { try Task.checkCancellation() }) throws {
        do { try copy(source, destination, maximumBytes, check) }
        catch is CancellationError { throw CancellationError() }
        catch let error as IPAInputFailure { throw error }
        catch { throw IPAInputFailure.unavailable }
    }

    private static func copy(_ source: URL, _ destination: URL, _ limit: UInt64,
                             _ check: () throws -> Void) throws {
        guard limit > 0, limit <= 1_073_741_824 else { throw IPAInputFailure.invalidLimit }
        guard source.isFileURL, destination.isFileURL,
              PrivateFileStore.validName(destination.lastPathComponent) else { throw IPAInputFailure.unsafeFile }
        try check()
        let input = open(source.path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC)
        guard input >= 0 else { throw IPAInputFailure.unsafeFile }
        defer { _ = close(input) }
        var before = stat()
        guard fstat(input, &before) == 0, before.st_mode & S_IFMT == S_IFREG,
              before.st_nlink == 1, before.st_size > 0 else { throw IPAInputFailure.unsafeFile }
        guard UInt64(before.st_size) <= limit else { throw IPAInputFailure.tooLarge }
        let parent = open(destination.deletingLastPathComponent().path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard parent >= 0 else { throw IPAInputFailure.unsafeFile }
        defer { _ = close(parent) }
        let name = destination.lastPathComponent
        let output = openat(parent, name, O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW | O_CLOEXEC, mode_t(0o600))
        guard output >= 0 else {
            if errno == EEXIST { throw IPAInputFailure.destinationExists }
            throw IPAInputFailure.unavailable
        }
        var complete = false
        defer {
            if !complete {
                // Delete only the partial output created by this invocation,
                // not a replacement someone else put at the same path.
                var opened = stat(), linked = stat()
                if fstat(output, &opened) == 0,
                   fstatat(parent, name, &linked, AT_SYMLINK_NOFOLLOW) == 0,
                   opened.st_dev == linked.st_dev, opened.st_ino == linked.st_ino {
                    _ = unlinkat(parent, name, 0)
                }
            }
            _ = close(output)
        }
        #if os(iOS) || os(tvOS)
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication],
                                             ofItemAtPath: destination.path)
        #endif
        #if canImport(Darwin)
        var privateURL = destination
        var flags = URLResourceValues(); flags.isExcludedFromBackup = true
        try privateURL.setResourceValues(flags)
        #endif
        let reader = FileHandle(fileDescriptor: input, closeOnDealloc: false)
        let writer = FileHandle(fileDescriptor: output, closeOnDealloc: false)
        var copied: UInt64 = 0
        while true {
            try check()
            let chunk = try reader.read(upToCount: 65_536) ?? Data()
            if chunk.isEmpty { break }
            guard UInt64(chunk.count) <= limit - copied else { throw IPAInputFailure.tooLarge }
            try writer.write(contentsOf: chunk)
            copied += UInt64(chunk.count)
        }
        try check()
        var after = stat()
        guard fstat(input, &after) == 0, after.st_nlink == 1,
              after.st_size == before.st_size, copied == UInt64(before.st_size),
              unchanged(before, after) else { throw IPAInputFailure.sourceChanged }
        var written = stat(), published = stat()
        guard fstat(output, &written) == 0,
              fstatat(parent, name, &published, AT_SYMLINK_NOFOLLOW) == 0,
              written.st_dev == published.st_dev, written.st_ino == published.st_ino,
              written.st_nlink == 1, written.st_size >= 0,
              UInt64(written.st_size) == copied else { throw IPAInputFailure.destinationChanged }
        guard fsync(output) == 0, fsync(parent) == 0 else { throw IPAInputFailure.unavailable }
        complete = true
    }

    private static func unchanged(_ a: stat, _ b: stat) -> Bool {
        #if canImport(Darwin)
        a.st_mtimespec.tv_sec == b.st_mtimespec.tv_sec && a.st_mtimespec.tv_nsec == b.st_mtimespec.tv_nsec &&
        a.st_ctimespec.tv_sec == b.st_ctimespec.tv_sec && a.st_ctimespec.tv_nsec == b.st_ctimespec.tv_nsec
        #else
        a.st_mtim.tv_sec == b.st_mtim.tv_sec && a.st_mtim.tv_nsec == b.st_mtim.tv_nsec &&
        a.st_ctim.tv_sec == b.st_ctim.tv_sec && a.st_ctim.tv_nsec == b.st_ctim.tv_nsec
        #endif
    }
}
