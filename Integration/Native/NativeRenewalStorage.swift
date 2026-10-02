// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import CryptoKit
import Darwin

/// One container and one inode for both new renewal work and inherited pipelines.
/// No App Group entitlement is needed; the intents run in the main app target.
enum NativeRenewalStorage {
    static func digest(_ bytes: Data) -> String {
        SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
    }
    static func root() throws -> URL {
        let parent = try FileManager.default.url(for: .applicationSupportDirectory,
                                                in: .userDomainMask, appropriateFor: nil, create: true)
        let url = parent.appendingPathComponent("TetherlessRenewal", isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        let values = try url.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
        guard values.isDirectory == true, values.isSymbolicLink != true else {
            throw RenewalFailure.storageUnavailable
        }
        #if os(iOS)
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication],
                                              ofItemAtPath: url.path)
        #endif
        var mutable = url
        var resources = URLResourceValues()
        resources.isExcludedFromBackup = true
        try mutable.setResourceValues(resources)
        return url.resolvingSymlinksInPath()
    }
    static func acquire() throws -> ProcessLease {
        try ProcessLease.acquire(at: root().appendingPathComponent("device-mutation.lock"))
    }
    static func journal() throws -> FileRenewalJournal {
        FileRenewalJournal(url: try root().appendingPathComponent("renewal.json"))
    }
    static func batchURL(_ bundleID: String) throws -> URL {
        try root().appendingPathComponent("batch-\(digest(Data(bundleID.utf8))).json")
    }
    static func read(_ url: URL, maximum: Int = 16_777_216) throws -> Data? {
        let fd = open(url.path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK)
        guard fd >= 0 else {
            if errno == ENOENT { return nil }
            throw RenewalFailure.storageUnavailable
        }
        defer { _ = close(fd) }
        var info = stat()
        guard fstat(fd, &info) == 0, (info.st_mode & S_IFMT) == S_IFREG,
              info.st_size >= 0, info.st_size <= maximum else { throw RenewalFailure.corruptJournal }
        let file = FileHandle(fileDescriptor: fd, closeOnDealloc: false)
        guard let bytes = try file.read(upToCount: maximum + 1), bytes.count <= maximum else {
            throw RenewalFailure.corruptJournal
        }
        return bytes
    }
    static func write<T: Encodable>(_ value: T, to url: URL) throws {
        let bytes = try JSONEncoder().encode(value)
        guard bytes.count <= 16_777_216 else { throw RenewalFailure.storageUnavailable }
        #if os(iOS)
        try bytes.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        #else
        try bytes.write(to: url, options: .atomic)
        #endif
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
    }
    static func loadBatch(for bundleID: String) throws -> ProfileBatch? {
        guard let bytes = try read(batchURL(bundleID)) else { return nil }
        do { return try JSONDecoder().decode(ProfileBatch.self, from: bytes) }
        catch { throw RenewalFailure.corruptJournal }
    }
    static func saveBatch(_ batch: ProfileBatch) throws {
        do { try write(batch, to: batchURL(batch.bundleID)) }
        catch { throw RenewalFailure.storageUnavailable }
    }
}

/// Task-local reentrancy is only for nested INHERITED operations. A completed
/// scope is invalidated so a surviving child cannot bypass a later lock holder.
/// The new RenewalEngine obtains the very same file lock independently.
enum NativeMutationGate {
    private final class Token: @unchecked Sendable {
        private let mutex = NSLock()
        private var active = true
        var isActive: Bool { mutex.lock(); defer { mutex.unlock() }; return active }
        func end() { mutex.lock(); active = false; mutex.unlock() }
    }
    @TaskLocal private static var token: Token?

    static func withLease<T>(_ body: () async throws -> T) async throws -> T {
        if token?.isActive == true { return try await body() }
        let lease = try NativeRenewalStorage.acquire()
        let scope = Token()
        defer { scope.end(); lease.release() }
        return try await $token.withValue(scope) { try await body() }
    }
}
