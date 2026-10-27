// SPDX-License-Identifier: AGPL-3.0-only

/// Coordinates UI startup only. This is neither account authorization nor
/// evidence of a successful renewal. Used from the native main actor.
public struct LaunchReadiness: Sendable {
    public private(set) var databaseReady = false
    public private(set) var onboardingDismissed: Bool
    public private(set) var hasTransitioned = false

    public init(onboardingDismissed: Bool) {
        self.onboardingDismissed = onboardingDismissed
    }

    public mutating func databaseDidStart() { databaseReady = true }
    public mutating func dismissOnboarding() { onboardingDismissed = true }

    /// Both asynchronous completion orders have one, and only one, transition.
    /// A failed database start must never call databaseDidStart().
    public mutating func claimTransition() -> Bool {
        guard databaseReady, onboardingDismissed, !hasTransitioned else { return false }
        hasTransitioned = true
        return true
    }
}
