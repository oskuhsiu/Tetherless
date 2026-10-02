// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import ZIPFoundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

/// Stream into a fresh private tree, then publish only validated output without
/// overwriting anything. Input archives are snapshotted to defeat TOCTOU during
/// extraction. This does not attest code signatures or make an IPA trustworthy.
public enum SafeArchive {
    public static func extractIPA(at source: URL, toDirectory destination: URL,
                                  limits: ArchiveLimits = .init(), progress: Progress? = nil) throws -> URL {
        try withStaging(source: source, destination: destination, limits: limits, progress: progress) { extracted in
            let payload = extracted.appendingPathComponent("Payload", isDirectory: true)
            let apps = try FileManager.default.contentsOfDirectory(at: payload, includingPropertiesForKeys: [.isDirectoryKey])
            guard apps.count == 1, let app = apps.first, app.pathExtension == "app",
                  try app.resourceValues(forKeys: [.isDirectoryKey]).isDirectory == true else { throw SafeArchiveError.invalidApp }
            try validateApp(at: app)
            let final = destination.appendingPathComponent(app.lastPathComponent, isDirectory: true)
            guard !exists(final) else { throw SafeArchiveError.destinationConflict }
            try FileManager.default.moveItem(at: app, to: final)
            return final
        }
    }

    public static func extract(at source: URL, toDirectory destination: URL,
                               limits: ArchiveLimits = .init(), progress: Progress? = nil) throws {
        try withStaging(source: source, destination: destination, limits: limits, progress: progress) { extracted in
            let children = try FileManager.default.contentsOfDirectory(at: extracted, includingPropertiesForKeys: nil)
            guard children.allSatisfy({ !exists(destination.appendingPathComponent($0.lastPathComponent)) }) else {
                throw SafeArchiveError.destinationConflict
            }
            var moved: [URL] = []
            do {
                for child in children {
                    try check(progress)
                    let final = destination.appendingPathComponent(child.lastPathComponent)
                    try FileManager.default.moveItem(at: child, to: final)
                    moved.append(final)
                }
            } catch {
                // Only this invocation's newly published children are removed.
                // A crash can leave partial new output, but never replaces old data.
                for path in moved { try? FileManager.default.removeItem(at: path) }
                throw error
            }
        }
    }

    private static func withStaging<T>(source: URL, destination: URL, limits: ArchiveLimits,
                    progress: Progress?, publish: (URL) throws -> T) throws -> T {
        try limits.validate()
        guard source.isFileURL, destination.isFileURL else { throw SafeArchiveError.unsafePath }
        let fm = FileManager.default
        let createdDestination = !exists(destination)
        if createdDestination { try fm.createDirectory(at: destination, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]) }
        let rootFD = open(destination.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard rootFD >= 0 else { throw SafeArchiveError.unsafePath }
        defer { _ = close(rootFD) }
        let staging = destination.appendingPathComponent(".tetherless-unpack-" + UUID().uuidString, isDirectory: true)
        try fm.createDirectory(at: staging, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        var complete = false
        defer {
            try? fm.removeItem(at: staging)
            if !complete && createdDestination { _ = rmdir(destination.path) }
        }
        #if os(iOS) || os(tvOS)
        try fm.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: staging.path)
        #endif
        #if canImport(Darwin)
        var protected = staging
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try protected.setResourceValues(values)
        #endif
        let snapshot = staging.appendingPathComponent("input.zip")
        try copySnapshot(source, to: snapshot, limit: limits.maximumArchiveBytes, progress: progress)
        let preflight = try ArchivePreflight(url: snapshot, limits: limits, check: { try check(progress) })
        let archive = try ZIPFoundation.Archive(url: snapshot, accessMode: .read)
        let entries = Array(archive)
        guard entries.count == preflight.items.count else { throw SafeArchiveError.invalidArchive }
        var paths = ArchivePaths()
        var targets: [(Entry, String)] = []
        for (entry, item) in zip(entries, preflight.items) {
            try check(progress)
            guard entry.type != .symlink, entry.compressedSize == item.compressed,
                  entry.uncompressedSize == item.expanded, entry.checksum == item.crc else { throw SafeArchiveError.invalidArchive }
            if entry.type == .directory {
                guard item.expanded == 0, item.crc == 0 else { throw SafeArchiveError.invalidArchive }
            }
            targets.append((entry, try paths.accept(entry.path, directory: entry.type == .directory)))
        }
        let extracted = staging.appendingPathComponent("contents", isDirectory: true)
        try fm.createDirectory(at: extracted, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        var total: UInt64 = 0
        for (entry, name) in targets {
            try check(progress)
            let output = extracted.appendingPathComponent(name, isDirectory: entry.type == .directory)
            if entry.type == .directory {
                try fm.createDirectory(at: output, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o755])
                continue
            }
            try fm.createDirectory(at: output.deletingLastPathComponent(), withIntermediateDirectories: true, attributes: [.posixPermissions: 0o755])
            let fd = open(output.path, O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW | O_CLOEXEC, mode_t(0o600))
            guard fd >= 0 else { throw SafeArchiveError.unsafePath }
            do {
                defer { _ = close(fd) }
                let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: false)
                var written: UInt64 = 0
                let checksum = try archive.extract(entry, bufferSize: 65_536, skipCRC32: false) { chunk in
                    try check(progress)
                    let count = UInt64(chunk.count)
                    guard count <= entry.uncompressedSize - written,
                          count <= limits.maximumExpandedBytes - total else { throw SafeArchiveError.limitExceeded }
                    try handle.write(contentsOf: chunk)
                    written += count; total += count
                }
                guard written == entry.uncompressedSize else { throw SafeArchiveError.invalidArchive }
                // CRC 0 is still a checksum, not a flag to skip verification.
                guard checksum == entry.checksum else { throw SafeArchiveError.checksumMismatch }
                let archived = (entry.fileAttributes[.posixPermissions] as? NSNumber)?.intValue ?? 0
                guard fchmod(fd, mode_t(archived & 0o111 == 0 ? 0o644 : 0o755)) == 0 else { throw SafeArchiveError.invalidArchive }
            }
        }
        try check(progress)
        let value = try publish(extracted)
        complete = true
        return value
    }

    private static func validateApp(at app: URL) throws {
        let infoURL = app.appendingPathComponent("Info.plist")
        let attrs = try FileManager.default.attributesOfItem(atPath: infoURL.path)
        guard let size = attrs[.size] as? NSNumber, size.uint64Value <= 1_048_576 else { throw SafeArchiveError.invalidApp }
        let bytes = try Data(contentsOf: infoURL)
        guard let dict = try PropertyListSerialization.propertyList(from: bytes, format: nil) as? [String: Any],
              let executable = dict["CFBundleExecutable"] as? String,
              let identifier = dict["CFBundleIdentifier"] as? String, !identifier.isEmpty else { throw SafeArchiveError.invalidApp }
        var paths = ArchivePaths()
        guard try paths.accept(executable, directory: false) == executable, !executable.contains("/") else { throw SafeArchiveError.invalidApp }
        let file = app.appendingPathComponent(executable)
        let values = try file.resourceValues(forKeys: [.isRegularFileKey])
        guard values.isRegularFile == true else { throw SafeArchiveError.invalidApp }
        // Preserve executable permission even for archives produced on Windows.
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: file.path)
    }

    private static func copySnapshot(_ source: URL, to destination: URL, limit: UInt64, progress: Progress?) throws {
        let fd = open(source.path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC)
        guard fd >= 0 else { throw SafeArchiveError.unsafePath }
        defer { _ = close(fd) }
        var before = stat()
        guard fstat(fd, &before) == 0, before.st_mode & S_IFMT == S_IFREG,
              before.st_nlink == 1, before.st_size >= 22, UInt64(before.st_size) <= limit else { throw SafeArchiveError.limitExceeded }
        let out = open(destination.path, O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW | O_CLOEXEC, mode_t(0o600))
        guard out >= 0 else { throw SafeArchiveError.unsafePath }
        defer { _ = close(out) }
        let input = FileHandle(fileDescriptor: fd, closeOnDealloc: false)
        let output = FileHandle(fileDescriptor: out, closeOnDealloc: false)
        var total: UInt64 = 0
        while true {
            try check(progress)
            let chunk = try input.read(upToCount: 65_536) ?? Data()
            if chunk.isEmpty { break }
            guard UInt64(chunk.count) <= limit - total else { throw SafeArchiveError.limitExceeded }
            total += UInt64(chunk.count)
            try output.write(contentsOf: chunk)
        }
        var after = stat()
        guard fstat(fd, &after) == 0, after.st_size == before.st_size, total == UInt64(before.st_size) else { throw SafeArchiveError.invalidArchive }
        #if canImport(Darwin)
        guard after.st_mtimespec.tv_sec == before.st_mtimespec.tv_sec,
              after.st_mtimespec.tv_nsec == before.st_mtimespec.tv_nsec,
              after.st_ctimespec.tv_sec == before.st_ctimespec.tv_sec,
              after.st_ctimespec.tv_nsec == before.st_ctimespec.tv_nsec else { throw SafeArchiveError.invalidArchive }
        #else
        guard after.st_mtim.tv_sec == before.st_mtim.tv_sec, after.st_mtim.tv_nsec == before.st_mtim.tv_nsec,
              after.st_ctim.tv_sec == before.st_ctim.tv_sec, after.st_ctim.tv_nsec == before.st_ctim.tv_nsec else { throw SafeArchiveError.invalidArchive }
        #endif
    }
    private static func exists(_ url: URL) -> Bool {
        var value = stat()
        return lstat(url.path, &value) == 0
    }
    private static func check(_ progress: Progress?) throws {
        try Task.checkCancellation()
        if progress?.isCancelled == true { throw CancellationError() }
    }
}
