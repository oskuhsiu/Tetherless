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
