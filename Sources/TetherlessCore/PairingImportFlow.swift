// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// Ephemeral UI request only; contains no persisted permission or pairing data.
public struct PairingImportRequest: Identifiable, Equatable, Sendable {
    public let id: UUID
    public init(id: UUID = UUID()) { self.id = id }
}

/// One selection per presentation. A selection grants no permission to read or
/// write until that SAME presentation is dismissed. Cancelling never imports.
/// The UI owner serializes access on the main actor; this is not the disk lock.
public struct PairingImportFlow: Sendable {
    public enum Outcome: Equatable, Sendable {
        case selected(URL), cancelled, invalidSelection
    }
    private enum Phase: Sendable {
        case idle
        case presenting(PairingImportRequest)
        case resolving(PairingImportRequest, Outcome)
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
        case .presenting(let request), .resolving(let request, _), .importing(let request): return request
        }
    }
    public mutating func begin() -> PairingImportRequest? {
        guard !isBusy else { return nil }
        let request = PairingImportRequest()
        phase = .presenting(request)
        return request
    }
    @discardableResult
    public mutating func resolve(_ outcome: Outcome, request: PairingImportRequest) -> Bool {
        guard case .presenting(let active) = phase, active == request else { return false }
        let accepted: Outcome
        if case .selected(let url) = outcome, !url.isFileURL { accepted = .invalidSelection }
        else { accepted = outcome }
        phase = .resolving(active, accepted)
        return true
    }
    /// Returns a selection at most once, and only after dismissal. UIKit may
    /// dismiss interactively without delivering documentPickerWasCancelled.
    public mutating func dismissed(_ request: PairingImportRequest) -> Outcome? {
        guard self.request == request else { return nil }
        switch phase {
        case .presenting:
            phase = .idle
            return .cancelled
        case .resolving(let request, let outcome):
            if case .selected = outcome { phase = .importing(request) }
            else { phase = .idle }
            return outcome
        case .idle, .importing: return nil
        }
    }
    @discardableResult
    public mutating func finished(_ request: PairingImportRequest) -> Bool {
        guard case .importing(let active) = phase, active == request else { return false }
        phase = .idle
        return true
    }
}
