// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

public enum LibraryCacheMaintenanceFailure: String, Error, LocalizedError, Sendable {
    case busy, unsafeFile, unavailable, limitExceeded
    public var errorDescription: String? { "Library cache maintenance: \(rawValue)." }
}

/// A separate stable lock for provider lifetime, not a replacement for the
/// native mutation lease. Never unlink this file, including during cleanup.
/// Immutable ownership ends only when the final strong reference disappears.
public final class LibraryCacheUsage: @unchecked Sendable {
    private let descriptor: Int32
    private init(_ descriptor: Int32) { self.descriptor = descriptor }
    public static func acquire(in root: URL, exclusive: Bool = false) throws -> LibraryCacheUsage {
        guard root.isFileURL else { throw LibraryCacheMaintenanceFailure.unsafeFile }
        let directory = open(root.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard directory >= 0 else { throw LibraryCacheMaintenanceFailure.unsafeFile }
        defer { _ = close(directory) }
        let fd = openat(directory, "usage.lock", O_CREAT | O_RDWR | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK, mode_t(0o600))
        guard fd >= 0 else { throw LibraryCacheMaintenanceFailure.unsafeFile }
        var owned = false
        defer { if !owned { _ = close(fd) } }
        var info = stat()
        guard fstat(fd, &info) == 0, info.st_mode & S_IFMT == S_IFREG,
              info.st_nlink == 1 else { throw LibraryCacheMaintenanceFailure.unsafeFile }
        guard flock(fd, (exclusive ? LOCK_EX : LOCK_SH) | LOCK_NB) == 0 else {
            if errno == EWOULDBLOCK || errno == EAGAIN { throw LibraryCacheMaintenanceFailure.busy }
            throw LibraryCacheMaintenanceFailure.unavailable
        }
        var linked = stat()
        guard fstatat(directory, "usage.lock", &linked, AT_SYMLINK_NOFOLLOW) == 0,
              linked.st_dev == info.st_dev, linked.st_ino == info.st_ino, linked.st_nlink == 1 else {
            throw LibraryCacheMaintenanceFailure.unsafeFile
        }
        owned = true
        return LibraryCacheUsage(fd)
    }
    deinit { _ = flock(descriptor, LOCK_UN); _ = close(descriptor) }
}

/// Reclaims only canonical generation/stage names inside a caller-owned slot.
/// The active receipt is read/verified UNDER exclusive usage ownership. Busy
/// means no deletion, not permission to evict a running provider. Unexpected
/// entries are preserved. The stable lock and receipt are never removed.
public enum LibraryCacheMaintenance {
    public static func reclaim(in root: URL, currentGeneration: () throws -> String?) throws -> Bool {
        let lock: LibraryCacheUsage
        do { lock = try LibraryCacheUsage.acquire(in: root, exclusive: true) }
        catch LibraryCacheMaintenanceFailure.busy { return false }
        defer { withExtendedLifetime(lock) {} }
        let keep = try currentGeneration()
        if let keep, !canonical(keep, prefix: "version-") {
            throw LibraryCacheMaintenanceFailure.unsafeFile
        }
        let directory = open(root.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard directory >= 0 else { throw LibraryCacheMaintenanceFailure.unsafeFile }
        defer { _ = close(directory) }
        let names = try children(directory)
        let candidates = names.filter {
            $0 != keep && (canonical($0, prefix: "version-") || canonical($0, prefix: "stage-") || canonical($0, prefix: ".staging-"))
        }
        var remaining = 32_768
        // Validate the whole candidate set first. A link/FIFO never becomes a
        // recursive delete target, and no valid earlier candidate is lost.
        for name in candidates { try walk(directory, name: name, depth: 0, remaining: &remaining, remove: false) }
        remaining = 32_768
        for name in candidates { try walk(directory, name: name, depth: 0, remaining: &remaining, remove: true) }
        guard fsync(directory) == 0 else { throw LibraryCacheMaintenanceFailure.unavailable }
        return true
    }

    private static func canonical(_ name: String, prefix: String) -> Bool {
        guard name.hasPrefix(prefix) else { return false }
        let suffix = String(name.dropFirst(prefix.count))
        return UUID(uuidString: suffix)?.uuidString == suffix
    }
    private static func children(_ descriptor: Int32) throws -> [String] {
        // A new open file description avoids sharing readdir offsets with the
        // caller or with a later preflight/deletion pass.
        let scan = openat(descriptor, ".", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard scan >= 0 else { throw LibraryCacheMaintenanceFailure.unavailable }
        guard let stream = fdopendir(scan) else { _ = close(scan); throw LibraryCacheMaintenanceFailure.unavailable }
        defer { _ = closedir(stream) }
        var result: [String] = []
        while true {
            errno = 0
            guard let entry = readdir(stream) else {
                guard errno == 0 else { throw LibraryCacheMaintenanceFailure.unavailable }
                return result.sorted()
            }
            let name = withUnsafePointer(to: &entry.pointee.d_name) { pointer in
                pointer.withMemoryRebound(to: CChar.self, capacity: MemoryLayout.size(ofValue: entry.pointee.d_name)) { String(cString: $0) }
            }
            if name == "." || name == ".." { continue }
            guard result.count < 4096, PrivateFileStore.validName(name) else { throw LibraryCacheMaintenanceFailure.limitExceeded }
            result.append(name)
        }
    }
    private static func walk(_ parent: Int32, name: String, depth: Int,
                             remaining: inout Int, remove: Bool) throws {
        guard remaining > 0, depth <= 18 else { throw LibraryCacheMaintenanceFailure.limitExceeded }
        remaining -= 1
        var info = stat()
        guard fstatat(parent, name, &info, AT_SYMLINK_NOFOLLOW) == 0 else { throw LibraryCacheMaintenanceFailure.unavailable }
        let isDirectory = info.st_mode & S_IFMT == S_IFDIR
        guard isDirectory || (info.st_mode & S_IFMT == S_IFREG && info.st_nlink == 1) else {
            throw LibraryCacheMaintenanceFailure.unsafeFile
        }
        let fd = openat(parent, name, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK | (isDirectory ? O_DIRECTORY : 0))
        guard fd >= 0 else { throw LibraryCacheMaintenanceFailure.unsafeFile }
        defer { _ = close(fd) }
        var opened = stat()
        guard fstat(fd, &opened) == 0, opened.st_dev == info.st_dev, opened.st_ino == info.st_ino,
              opened.st_mode & S_IFMT == info.st_mode & S_IFMT else { throw LibraryCacheMaintenanceFailure.unsafeFile }
        if isDirectory {
            for child in try children(fd) { try walk(fd, name: child, depth: depth + 1, remaining: &remaining, remove: remove) }
            if remove, fsync(fd) != 0 { throw LibraryCacheMaintenanceFailure.unavailable }
        }
        if remove {
            var linked = stat()
            guard fstatat(parent, name, &linked, AT_SYMLINK_NOFOLLOW) == 0,
                  linked.st_dev == opened.st_dev, linked.st_ino == opened.st_ino,
                  linked.st_mode & S_IFMT == opened.st_mode & S_IFMT,
                  isDirectory || linked.st_nlink == 1 else { throw LibraryCacheMaintenanceFailure.unsafeFile }
            guard unlinkat(parent, name, isDirectory ? AT_REMOVEDIR : 0) == 0 else { throw LibraryCacheMaintenanceFailure.unavailable }
        }
    }
}
