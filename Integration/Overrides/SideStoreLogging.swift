// Derived from SideStoreLogging.swift, Copyright © 2026 SideStore.
// Tetherless modifications: do not evaluate or emit free-form diagnostic data.
// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// The inherited app logger receives account/device identifiers, input URLs,
/// certificate subjects and arbitrary Error descriptions. It has no safe
/// message boundary. Keep its API without evaluating payload autoclosures.
/// Structured renewal evidence and fixed PairingImportDiagnostic events are
/// independent of this compatibility sink and remain available.
public enum SideStoreLogging {
    public static var isLoggingEnabled: Bool { false }
    public static func setLogging(_ enabled: Bool) {}
}

public func debugLog(_ text: @autoclosure () -> String) {}
public func verboseLog(_ text: @autoclosure () -> String) {}

/// This helper is used only by the inherited logger. Do not attempt regex
/// redaction of arbitrary server text, URLs or unknown NSError values.
public func formatLogMessage(_ message: String) -> String { "[diagnostic payload omitted]" }
