// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// Counts native entry before it is queued. Retirement rejects new entry and
/// runs cleanup only after every accepted call actually returns.
public final class NativeCallLifetime: @unchecked Sendable {
    private let lock = NSLock()
    private var accepting = true
    private var calls = 0
    private var cleanup: (@Sendable () -> Void)?

    public init() {}

    public func admit() -> Claim? {
        lock.lock()
        defer { lock.unlock() }
        guard accepting else { return nil }
        calls += 1
        return Claim(owner: self)
    }

    /// Invoke once when no future native call should be admitted. A timeout or
    /// cancellation request must never be treated as a returned call.
    @discardableResult
    public func retire(cleanup: @escaping @Sendable () -> Void) -> Bool {
        lock.lock()
        guard accepting else { lock.unlock(); return false }
        accepting = false
        self.cleanup = cleanup
        let action = takeCleanupIfQuiescent()
        lock.unlock()
        action?()
        return true
    }

    private func returned() {
        lock.lock()
        precondition(calls > 0)
        calls -= 1
        let action = takeCleanupIfQuiescent()
        lock.unlock()
        action?()
    }

    private func takeCleanupIfQuiescent() -> (@Sendable () -> Void)? {
        guard !accepting, calls == 0 else { return nil }
        let action = cleanup
        cleanup = nil
        return action
    }

    public final class Claim: @unchecked Sendable {
        private let lock = NSLock()
        private var owner: NativeCallLifetime?
        fileprivate init(owner: NativeCallLifetime) { self.owner = owner }

        public func returned() {
            lock.lock()
            let owner = self.owner
            self.owner = nil
            lock.unlock()
            owner?.returned()
        }
        deinit { returned() }
    }
}
