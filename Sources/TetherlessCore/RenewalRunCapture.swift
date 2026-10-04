// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// Per-invocation in-memory capture. It does not read old journal success as work
/// completed by this run and never persists profile/credential bytes. A runtime
/// uses this on a thrown exit to retain earlier committed results and alarms.
public final class RenewalRunCapture: @unchecked Sendable {
    private let lock = NSLock()
    private var report = RenewalRunResult()
    public init() {}
    public func record(_ result: RenewalRunResult) { lock.withLock { report = result } }
    public func interrupted(by failure: RenewalFailure) -> RenewalRunResult {
        lock.withLock {
            var result = report
            result.globalFailure = failure
            let accounted = Set(result.attempted + result.verified + result.appliedUnverified +
                                result.deferred + Array(result.failures.keys))
            result.deferred += (result.managedIDs ?? []).filter { !accounted.contains($0) }
            return result
        }
    }
}
