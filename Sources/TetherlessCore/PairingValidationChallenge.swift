// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
#if canImport(Security)
import Security
#endif
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

public enum PairingChallengeError: Error, Equatable, Sendable { case unavailable, invalidRandomness, changedFile, closed }

/// One independently random, protected app-container document. Borrowed native
/// validation owns a claim until its synchronous FFI actually returns.
/// The trusted app Library directory and the reserved child directory must have
/// no competing writer. Hold the process mutation lease; unrelated processes
/// with container-write access are outside this ownership/proof assumption.
/// fstatat/unlinkat cannot provide an atomic conditional unlink against them.
public final class PairingValidationChallenge: @unchecked Sendable, CustomDebugStringConvertible {
    public var debugDescription: String { "PairingValidationChallenge(<private>)" }
    public let relativePath: String
    private let directory: Int32
    private let file: Int32
    private let filename: String
    private let device: dev_t
    private let inode: ino_t
    private let expected: Data
    private let lifetime = NativeCallLifetime()
    private let lock = NSLock()
    private var result: Result<Void, PairingChallengeError>?
    private var waiters: [@Sendable (Result<Void, PairingChallengeError>) -> Void] = []
    private var closed = false

    public convenience init(libraryDirectory: URL) throws {
        try self.init(libraryDirectory: libraryDirectory, random: Self.secureRandom)
    }

    // Tests inject deterministic bytes. Production has no configurable RNG.
    convenience init(libraryDirectory: URL, random: (Int) throws -> Data) throws {
        let nameBytes = try random(32)
        let challenge = try random(32)
        guard nameBytes.count == 32, challenge.count == 32 else { throw PairingChallengeError.invalidRandomness }
        let filename = nameBytes.map { String(format: "%02x", $0) }.joined() + ".challenge"
        let root = libraryDirectory.appendingPathComponent("TetherlessPairingValidation", isDirectory: true)
        let store = try PrivateFileStore(root: root, maximumBytes: 32)
        try store.prepare()
        let dir = open(root.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard dir >= 0 else { throw PairingChallengeError.unavailable }
        var transferred = false
        defer { if !transferred { _ = close(dir) } }
        let file = openat(dir, filename, O_CREAT | O_EXCL | O_RDWR | O_NOFOLLOW | O_CLOEXEC, mode_t(0o600))
        guard file >= 0 else { throw PairingChallengeError.unavailable }
        var fileOwned = true
        defer {
            if fileOwned {
                // A failed initializer must not unlink a replacement supplied
                // at the same name. The still-open descriptor identifies ours.
                var owned = stat(), named = stat()
                if fstat(file, &owned) == 0, fstatat(dir, filename, &named, AT_SYMLINK_NOFOLLOW) == 0,
                   owned.st_dev == named.st_dev, owned.st_ino == named.st_ino,
                   (named.st_mode & S_IFMT) == S_IFREG, named.st_nlink == 1 {
                    _ = unlinkat(dir, filename, 0)
                }
            }
            if fileOwned { _ = close(file) }
        }
        var info = stat()
        guard fstat(file, &info) == 0, (info.st_mode & S_IFMT) == S_IFREG, info.st_nlink == 1,
              fchmod(file, mode_t(0o600)) == 0 else { throw PairingChallengeError.unavailable }
        #if os(iOS) || os(tvOS)
        // The fresh file contains no bytes before protection is applied.
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete],
                                             ofItemAtPath: root.appendingPathComponent(filename).path)
        #endif
        var current = stat()
        guard fstatat(dir, filename, &current, AT_SYMLINK_NOFOLLOW) == 0,
              current.st_dev == info.st_dev, current.st_ino == info.st_ino, current.st_nlink == 1 else {
            throw PairingChallengeError.changedFile
        }
        let handle = FileHandle(fileDescriptor: file, closeOnDealloc: false)
        try handle.write(contentsOf: challenge)
        guard fsync(file) == 0, fsync(dir) == 0 else { throw PairingChallengeError.unavailable }
        self.init(directory: dir, file: file, filename: filename, device: info.st_dev, inode: info.st_ino, expected: challenge)
        fileOwned = false; transferred = true
    }

    private init(directory: Int32, file: Int32, filename: String, device: dev_t, inode: ino_t, expected: Data) {
        self.directory = directory; self.file = file; self.filename = filename; self.device = device; self.inode = inode
        self.expected = expected
        relativePath = "Library/TetherlessPairingValidation/" + filename
    }

    private static func secureRandom(_ count: Int) throws -> Data {
        #if canImport(Security)
        var bytes = [UInt8](repeating: 0, count: count)
        let result = bytes.withUnsafeMutableBytes { SecRandomCopyBytes(kSecRandomDefault, count, $0.baseAddress!) }
        guard result == errSecSuccess else { throw PairingChallengeError.unavailable }
        return Data(bytes)
        #else
        throw PairingChallengeError.unavailable
        #endif
    }

    public func borrowForNative() throws -> Borrow {
        guard let claim = lifetime.admit() else { throw PairingChallengeError.closed }
        return Borrow(owner: self, claim: claim)
    }

    public func closeAfterValidation() async throws {
        try await withCheckedThrowingContinuation { continuation in
            retire { continuation.resume(with: $0.mapError { $0 as Error }) }
        }
    }

    private func retire(_ completed: @escaping @Sendable (Result<Void, PairingChallengeError>) -> Void) {
        lock.lock()
        if let result { lock.unlock(); completed(result); return }
        waiters.append(completed)
        lock.unlock()
        lifetime.retire { [self] in
            let outcome = removeOwnedFile()
            lock.lock(); result = outcome; let ready = waiters; waiters.removeAll(); lock.unlock()
            ready.forEach { $0(outcome) }
        }
    }

    private func removeOwnedFile() -> Result<Void, PairingChallengeError> {
        guard !closed else { return .success(()) }
        closed = true
        // Retain the original inode through identity check and unlink. Closing
        // it earlier would permit inode reuse at the same filename.
        defer { _ = close(file); _ = close(directory) }
        var current = stat()
        if fstatat(directory, filename, &current, AT_SYMLINK_NOFOLLOW) != 0 {
            return errno == ENOENT ? .success(()) : .failure(.unavailable)
        }
        guard current.st_dev == device, current.st_ino == inode,
              (current.st_mode & S_IFMT) == S_IFREG, current.st_nlink == 1 else { return .failure(.changedFile) }
        guard unlinkat(directory, filename, 0) == 0, fsync(directory) == 0 else { return .failure(.unavailable) }
        return .success(())
    }
    deinit {
        // Borrow retains the owner. No active native borrow can reach this point.
        if !closed { _ = removeOwnedFile() }
    }

    public final class Borrow: @unchecked Sendable, CustomDebugStringConvertible {
        public var debugDescription: String { "PairingValidationBorrow(<private>)" }
        public var relativePath: String { owner.relativePath }
        private let owner: PairingValidationChallenge
        private let claim: NativeCallLifetime.Claim
        fileprivate init(owner: PairingValidationChallenge, claim: NativeCallLifetime.Claim) { self.owner = owner; self.claim = claim }
        public func withExpectedBytes<T>(_ body: (UnsafeRawBufferPointer) throws -> T) rethrows -> T {
            try owner.expected.withUnsafeBytes(body)
        }
        public func returned() { claim.returned() }
        deinit { returned() }
    }
}
