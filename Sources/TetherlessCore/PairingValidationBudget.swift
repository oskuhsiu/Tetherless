// SPDX-License-Identifier: AGPL-3.0-only

/// Allocates one attempt from the remaining shared validation window. The
/// caller owns the unchanged monotonic deadline, cancellation and native joins.
/// A timeout never authorizes abandoning an outstanding native call.
public enum PairingValidationBudget {
    public static let maximumMilliseconds: UInt32 = 10_000
    public static let maximumEndpoints = 4

    /// Equal integer shares reserve time for the other remaining endpoints.
    /// Recompute after the previous token has actually closed, so execution and
    /// cleanup both count against the same window. A sub-millisecond share is
    /// unusable and fails closed instead of spending another endpoint's share.
    public static func timeoutMilliseconds(remainingMilliseconds: UInt32,
                                           endpointsRemaining: Int) -> UInt32? {
        guard (1...maximumEndpoints).contains(endpointsRemaining) else { return nil }
        let available = min(remainingMilliseconds, maximumMilliseconds)
        let share = available / UInt32(endpointsRemaining)
        return share > 0 ? share : nil
    }
}
