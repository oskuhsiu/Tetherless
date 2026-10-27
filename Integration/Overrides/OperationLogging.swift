// Derived from OperationLogging.swift, Copyright © 2026 SideStore.
// Tetherless modifications: fixed outcome/timing only; no app/account payloads.
// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

internal protocol OperationLogging {
    func debugLog(_ text: @autoclosure () -> String)
    func verboseLog(_ text: @autoclosure () -> String)
}

internal extension OperationLogging {
    func debugLog(_ text: @autoclosure () -> String) {}
    func verboseLog(_ text: @autoclosure () -> String) {}
}

/// Retain useful bounded timing without formatting arbitrary operation names,
/// target identifiers, Error descriptions or NSError userInfo. These values
/// remain available to the authorized UI, never this diagnostic sink.
func logOperationSummary(operation: String, target: String, status: String,
                         elapsed: Double, error: Error? = nil) {
    guard ["SUCCESS", "FAILED", "CANCELLED"].contains(status),
          elapsed.isFinite, elapsed >= 0, elapsed <= 86_400 else { return }
    print("[Tetherless operation] \(status) elapsed=\(String(format: "%.3f", elapsed))s")
}
