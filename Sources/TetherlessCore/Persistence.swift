// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
#if canImport(Darwin)
import Darwin
#elseif canImport(Glibc)
import Glibc
#endif

/// Advisory cross-process exclusion. Never delete this file: deleting a locked
/// inode would allow another process to lock a new inode at the same pathname.
public final class ProcessLease: @unchecked Sendable {
    private let mutex = NSLock()
    private var descriptor: Int32
    private let identity: String
    private init(descriptor: Int32, identity: String) { self.descriptor = descriptor; self.identity = identity }

    private func takeDescriptor() throws -> Int32 {
        mutex.lock(); defer { mutex.unlock() }
        guard descriptor >= 0 else { throw RenewalFailure.lockUnavailable }
        let value = descriptor; descriptor = -1
        return value
    }

    /// Move descriptor ownership into a task-local mutation scope. Nested native
    /// calls borrow this real lock; admitted children keep it after the body exits.
    /// Releasing the old handle cannot prematurely unlock the transferred scope.
    public func withMutationScope<T: Sendable>(_ body: @Sendable () async throws -> T) async throws -> T {
        let fd = try takeDescriptor()
        return try await MutationScope.withOwnedLease(identity: identity, release: {
            _ = flock(fd, LOCK_UN)
            _ = close(fd)
        }, body: body)
    }

    public static func acquire(at url: URL) throws -> ProcessLease {
        guard url.isFileURL else { throw RenewalFailure.lockUnavailable }
        let fd = open(url.path, O_CREAT | O_RDWR | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK, mode_t(0o600))
        guard fd >= 0 else { throw RenewalFailure.lockUnavailable }
        var info = stat()
        guard fstat(fd, &info) == 0, (info.st_mode & S_IFMT) == S_IFREG else {
            _ = close(fd)
            throw RenewalFailure.lockUnavailable
        }
        guard flock(fd, LOCK_EX | LOCK_NB) == 0 else {
            let savedErrno = errno
            _ = close(fd)
            if savedErrno == EWOULDBLOCK || savedErrno == EAGAIN { throw RenewalFailure.busy }
            throw RenewalFailure.lockUnavailable
        }
        return ProcessLease(descriptor: fd, identity: url.resolvingSymlinksInPath().path)
    }

    public func release() {
        mutex.lock()
        defer { mutex.unlock() }
        guard descriptor >= 0 else { return }
        _ = flock(descriptor, LOCK_UN)
        _ = close(descriptor)
        descriptor = -1
    }
    deinit { release() }
}

/// Non-secret state only. All callers must hold the same ProcessLease through
/// load/mutate/save. No iCloud/shared-container assumption is made here.
public struct FileRenewalJournal: RenewalJournal {
    public let url: URL
    public init(url: URL) { self.url = url }

    public func load() throws -> RenewalState {
        guard url.isFileURL else { throw RenewalFailure.storageUnavailable }
        // Do not confuse an unreadable file with an absent journal.
        let fd = open(url.path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK)
        guard fd >= 0 else {
            if errno == ENOENT { return RenewalState() }
            throw RenewalFailure.storageUnavailable
        }
        defer { _ = close(fd) }
        var info = stat()
        guard fstat(fd, &info) == 0, (info.st_mode & S_IFMT) == S_IFREG,
              info.st_size >= 0, info.st_size <= 2_097_152 else { throw RenewalFailure.corruptJournal }
        let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: false)
        let data: Data
        do { data = try handle.read(upToCount: 2_097_153) ?? Data() }
        catch { throw RenewalFailure.storageUnavailable }
        guard data.count <= 2_097_152 else { throw RenewalFailure.corruptJournal }
        let state: RenewalState
        do { state = try JSONDecoder().decode(RenewalState.self, from: data) }
        catch { throw RenewalFailure.corruptJournal }
        try state.validate()
        return state
    }

    public func save(_ state: RenewalState) throws {
        try state.validate()
        do {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys]
            let data = try encoder.encode(state)
            guard data.count <= 2_097_152 else { throw RenewalFailure.storageUnavailable }
            #if os(iOS)
            try data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
            #else
            try data.write(to: url, options: .atomic)
            #endif
        } catch { throw RenewalFailure.storageUnavailable }
    }
}
