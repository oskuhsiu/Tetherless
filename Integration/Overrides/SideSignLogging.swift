// Derived from SideSign Logging.swift, Copyright © 2026 SideSign.
// Tetherless modifications: payload-free diagnostic boundary.
import Foundation
#if canImport(AnisetteKit)
import AnisetteKit
#endif

/// Only fixed events may enter diagnostics. No account, key, header, URL,
/// server-provided description or partial token belongs in these messages.
public enum AuthenticationDiagnosticEvent: String, Sendable, CaseIterable {
    case started, challengeRequested, proofVerified, secondFactorRequired
    case accountRepairRequired, tokenReceived, transportFailed
}

public enum SideSignLogging {
    private final class State: @unchecked Sendable {
        private let lock = NSLock()
        private var enabled = false
        func set(_ value: Bool) { lock.lock(); defer { lock.unlock() }; enabled = value }
        func get() -> Bool { lock.lock(); defer { lock.unlock() }; return enabled }
    }
    private static let state = State()
    public static var isLoggingEnabled: Bool { state.get() }

    public static func setLogging(_ enabled: Bool) {
        state.set(enabled)
        // Third-party verbose output has not been independently redacted.
        // Enabling our fixed events must never enable their payload logger.
        #if canImport(AnisetteKit)
        AnisetteKitLogging.setLogging(false)
        #endif
    }

    public static func authentication(_ event: AuthenticationDiagnosticEvent) {
        guard isLoggingEnabled else { return }
        print("[Tetherless authentication] \(event.rawValue)")
    }
}

/// Keep source compatibility for inherited callers, but do not evaluate the
/// autoclosure: formatting a decrypted response itself creates another copy.
/// All callers requiring useful diagnostics must migrate to fixed events.
public func debugLog(_ text: @autoclosure () -> String) {}
public func verboseLog(_ text: @autoclosure () -> String) {}

/// These helpers are used only at diagnostic/error sites, not wire encoding.
/// Redact everything, including suffixes and unknown keys. No regex blacklist.
func prettyJSONString(from object: Any) -> String { "[payload omitted]" }
func formatPayload(_ data: Data) -> String? { "[payload omitted]" }
func sanitizeTokens(_ tokensDictionary: [String: any Sendable]) -> [String: any Sendable] { [:] }
public func sanitizeHeadersForLogging(_ headers: [String: String]) -> [String: String] { [:] }

/// For the interactive handler only. Error values use the fixed fallback URL
/// so query parameters cannot escape through NSError/debug descriptions.
func authenticationRepairURL(_ raw: String?, fallback: URL) -> URL {
    guard let raw, raw.utf8.count <= 8192,
          let url = URL(string: raw), url.scheme?.lowercased() == "https",
          url.user == nil, url.password == nil, url.port == nil || url.port == 443,
          let host = url.host?.lowercased(),
          ["account.apple.com", "appleid.apple.com", "developer.apple.com", "idmsa.apple.com"].contains(host)
    else { return fallback }
    return url
}
