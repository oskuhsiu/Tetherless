// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// A thread-safe session cancellation/commit decision, including OS expiration
/// callbacks that arrive while the UI actor is busy. Cancellation is not a join.
public final class PairingCancellationController: @unchecked Sendable {
    private enum State { case open, cancelled, committing, finished }
    private let lock = NSLock()
    private var state: State = .open
    private var actions: [UUID: @Sendable () -> Void] = [:]

    public init() {}
    public var isCancelled: Bool { lock.lock(); defer { lock.unlock() }; return state == .cancelled }

    /// Registration after cancellation immediately signals that new resource.
    /// The owner still joins it before releasing its mutation lease.
    public func register(_ action: @escaping @Sendable () -> Void) -> Registration? {
        lock.lock()
        guard state == .open else { lock.unlock(); action(); return nil }
        let id = UUID()
        actions[id] = action
        lock.unlock()
        return Registration(owner: self, id: id)
    }

    @discardableResult public func cancel() -> Bool {
        lock.lock()
        switch state {
        case .cancelled: lock.unlock(); return true
        case .committing, .finished: lock.unlock(); return false
        case .open:
            state = .cancelled
            let current = Array(actions.values)
            lock.unlock()
            current.forEach { $0() }
            return true
        }
    }

    /// Called immediately before the synchronous protected-store mutation.
    /// The winning commit cannot be undone by a later cancellation request.
    public func beginPromotion() -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard state == .open else { return false }
        state = .committing
        return true
    }

    /// Only after every registered native/platform operation has joined.
    public func finish() {
        lock.lock()
        state = .finished
        let retired = actions
        actions = [:]
        lock.unlock()
        // Captured objects may reenter this controller from deinit.
        withExtendedLifetime(retired) {}
    }
    private func remove(_ id: UUID) {
        lock.lock(); let retired = actions.removeValue(forKey: id); lock.unlock()
        withExtendedLifetime(retired) {}
    }

    public final class Registration: @unchecked Sendable {
        private let lock = NSLock()
        private var owner: PairingCancellationController?
        private let id: UUID
        fileprivate init(owner: PairingCancellationController, id: UUID) { self.owner = owner; self.id = id }
        public func remove() {
            lock.lock(); let owner = self.owner; self.owner = nil; lock.unlock()
            owner?.remove(id)
        }
        deinit { remove() }
    }
}
