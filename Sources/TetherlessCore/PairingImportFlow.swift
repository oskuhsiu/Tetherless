// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// Ephemeral UI request only; contains no persisted permission or pairing data.
public struct PairingImportRequest: Identifiable, Equatable, Sendable {
    public let id: UUID
    public init(id: UUID = UUID()) { self.id = id }
}

/// One selection per presentation. The explicit delegate outcome and completed
/// dismissal may arrive in either order; BOTH are required before any import.
/// The UI owner serializes access on the main actor; this is not the disk lock.
public struct PairingImportFlow: Sendable {
    public enum Outcome: Equatable, Sendable {
        case selected(URL), cancelled, invalidSelection

        public static func pickedDocuments(_ urls: [URL]) -> Self {
            guard urls.count == 1, let url = urls.first, url.isFileURL else { return .invalidSelection }
            return .selected(url)
        }
    }
    private enum Phase: Sendable {
        case idle
        case pending(PairingImportRequest, Outcome?, dismissed: Bool)
        case importing(PairingImportRequest)
    }
    private var phase: Phase = .idle
    public init() {}
    public var isBusy: Bool {
        if case .idle = phase { return false }
        return true
    }
    public var request: PairingImportRequest? {
        switch phase {
        case .idle: return nil
        case .pending(let request, _, _), .importing(let request): return request
        }
    }
    public mutating func begin() -> PairingImportRequest? {
        guard !isBusy else { return nil }
        let request = PairingImportRequest()
        phase = .pending(request, nil, dismissed: false)
        return request
    }
    @discardableResult
    public mutating func resolve(_ outcome: Outcome, request: PairingImportRequest) -> Bool {
        guard case .pending(let active, let existing, let dismissed) = phase,
              active == request, existing == nil else { return false }
        let accepted: Outcome
        if case .selected(let url) = outcome, !url.isFileURL { accepted = .invalidSelection }
        else { accepted = outcome }
        phase = .pending(active, accepted, dismissed: dismissed)
        return true
    }
    /// A completed cover dismissal is not a delegate cancellation. Keep the
    /// generation alive for a result delivered after the dismissal callback.
    public mutating func dismissed(_ request: PairingImportRequest) -> Outcome? {
        guard case .pending(let active, let outcome, _) = phase, active == request else { return nil }
        phase = .pending(active, outcome, dismissed: true)
        return consume(request)
    }
    /// Called after either event. Consumes only after the rendezvous; duplicate
    /// callbacks cannot import twice or consume a later presentation's result.
    public mutating func consume(_ request: PairingImportRequest) -> Outcome? {
        guard case .pending(let active, let pending, let dismissed) = phase,
              active == request, dismissed, let outcome = pending else { return nil }
        if case .selected = outcome { phase = .importing(active) }
        else { phase = .idle }
        return outcome
    }
    /// Explicit owner teardown, not onDismiss. An unresolved request cannot
    /// survive removal of its owning presenter. Never consume a selected URL
    /// here or replace an already delivered result with a cancellation.
    @discardableResult
    public mutating func abandon(_ request: PairingImportRequest) -> Bool {
        guard case .pending(let active, let outcome, _) = phase,
              active == request, outcome == nil else { return false }
        phase = .idle
        return true
    }
    @discardableResult
    public mutating func finished(_ request: PairingImportRequest) -> Bool {
        guard case .importing(let active) = phase, active == request else { return false }
        phase = .idle
        return true
    }
}

/// The actual picker coordinator owns this generation-bound, single-shot relay.
/// Strong ownership lasts through the delegate callback, independently of the
/// picker's own dismissal. Explicit teardown abandons only an unresolved relay.
@MainActor public final class PairingImportResultRelay {
    private let request: PairingImportRequest
    private var onResolve: (@MainActor (PairingImportRequest, PairingImportFlow.Outcome) -> Void)?
    private var onAbandon: (@MainActor (PairingImportRequest) -> Void)?

    public init(request: PairingImportRequest,
                onResolve: @escaping @MainActor (PairingImportRequest, PairingImportFlow.Outcome) -> Void,
                onAbandon: @escaping @MainActor (PairingImportRequest) -> Void) {
        self.request = request; self.onResolve = onResolve; self.onAbandon = onAbandon
    }
    public var isPending: Bool { onResolve != nil }
    @discardableResult
    public func resolve(_ outcome: PairingImportFlow.Outcome) -> Bool {
        guard let callback = onResolve else { return false }
        // Clear before reentering the owner; callbacks may trigger teardown.
        onResolve = nil; onAbandon = nil
        callback(request, outcome)
        return true
    }
    @discardableResult
    public func invalidate() -> Bool {
        let callback = onAbandon
        onResolve = nil; onAbandon = nil
        callback?(request)
        return callback != nil
    }
}
