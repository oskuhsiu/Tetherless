// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// Local setup observations, NOT proof of Apple authorization, a live tunnel,
/// a configured Shortcuts automation, or unattended execution.
public struct SetupReadiness: Equatable, Sendable {
    public var pairingStored = false
    public var accountStored = false
    public var signingKeyStored = false
    public var localAnisetteSelected = false
    public var renewalPermitted = false
    public var localObservationFailed = false
    public init() {}
    public var canAttemptVerification: Bool {
        !localObservationFailed && pairingStored && accountStored && signingKeyStored &&
        localAnisetteSelected && renewalPermitted
    }
    public var title: String {
        if localObservationFailed { return "Setup status could not be read" }
        return canAttemptVerification ? "Ready for a renewal check" : "Setup is not finished"
    }
    public var detail: String {
        if localObservationFailed { return "Existing records were not reset. Retry after the current operation finishes." }
        if canAttemptVerification {
            return "Local prerequisites are present. A live renewal check and your Shortcuts automation still need verification."
        }
        return "You can explore Tetherless now and return to the missing steps. Automatic renewal is not ready."
    }
}

/// A navigation checkpoint only. Restoring it never restores credentials,
/// grants renewal consent or changes the separately observed prerequisites.
/// Stable string keys tolerate future reordering of the visible steps.
public enum SetupStep: String, CaseIterable, Sendable {
    case welcome, pairing, connection, account, automation, review

    public static let storageKey = "tetherless.setup.currentStep"
    public static func resuming(_ savedValue: String) -> Self {
        Self(rawValue: savedValue) ?? .welcome
    }
    public var ordinal: Int { Self.allCases.firstIndex(of: self)! + 1 }
    public var title: String {
        switch self {
        case .welcome: return "Welcome to Tetherless"
        case .pairing: return "Device pairing"
        case .connection: return "Local connection"
        case .account: return "Your Apple Account"
        case .automation: return "Automatic renewal"
        case .review: return "Review setup"
        }
    }
    public func moved(by delta: Int) -> Self? {
        guard delta == -1 || delta == 1 else { return nil }
        let index = ordinal - 1 + delta
        return Self.allCases.indices.contains(index) ? Self.allCases[index] : nil
    }
}
