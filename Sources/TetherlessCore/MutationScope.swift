// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// Reentrancy for an inherited call chain without releasing its underlying OS
/// lease while an admitted child operation is still alive. Callers supply the
/// actual cross-process lock; this class is NOT itself a process lock.
public enum MutationScope {
    private final class Token: @unchecked Sendable {
        let identity: String
        private let mutex = NSLock()
        private let release: @Sendable () -> Void
        private var open = true
        private var claims = 1
        init(identity: String, release: @escaping @Sendable () -> Void) {
            self.identity = identity
            self.release = release
        }
        func claim() -> Bool {
            mutex.lock()
            defer { mutex.unlock() }
            guard open else { return false }
            claims += 1
            return true
        }
        func finish(owner: Bool = false) {
            mutex.lock()
            if owner { open = false }
            claims -= 1
            let shouldRelease = claims == 0
            mutex.unlock()
            if shouldRelease { release() }
        }
    }
    @TaskLocal private static var token: Token?

    /// The ProcessLease transfers an already-acquired real descriptor here.
    /// Unlike withLease, this must not borrow an existing token and leak ownership.
    static func withOwnedLease<T: Sendable>(identity: String, release: @escaping @Sendable () -> Void,
                                  body: @Sendable () async throws -> T) async throws -> T {
        let scope = Token(identity: identity, release: release)
        defer { scope.finish(owner: true) }
        return try await $token.withValue(scope) { try await body() }
    }

    public static func withSynchronousLease<T>(identity: String,
                 acquire: () throws -> (@Sendable () -> Void),
                 body: () throws -> T) throws -> T {
        if let active = token, active.identity == identity, active.claim() {
            defer { active.finish() }
            return try body()
        }
        let release = try acquire()
        let scope = Token(identity: identity, release: release)
        defer { scope.finish(owner: true) }
        return try $token.withValue(scope) { try body() }
    }

    public static func withLease<T>(identity: String,
                 acquire: () throws -> (@Sendable () -> Void),
                 body: () async throws -> T) async throws -> T {
        if let active = token, active.identity == identity, active.claim() {
            defer { active.finish() }
            return try await body()
        }
        let release = try acquire()
        let scope = Token(identity: identity, release: release)
        defer { scope.finish(owner: true) }
        return try await $token.withValue(scope) { try await body() }
    }
}
