// Tetherless persistence boundary for native history and source-error screens.
// Only fixed diagnostic categories cross this boundary. Original errors remain
// available to their callers; this policy must never decide whether to retry,
// authenticate, suppress a failure, or mutate an app.
import Foundation

enum TetherlessErrorRecordPolicy {
    static let domain = "Tetherless.LoggedError"

    enum Category: Int, CaseIterable {
        case unexpected = 1
        case network
        case timedOut
        case offline
        case secureConnection
        case invalidResponse
        case authentication
        case filesystem
        case permissionDenied
        case storageFull
        case cancelled
        case server
        case missingFile

        var group: String {
            switch self {
            case .network, .timedOut, .offline, .secureConnection, .invalidResponse:
                return "network"
            case .filesystem, .permissionDenied, .storageFull, .missingFile:
                return "filesystem"
            case .authentication: return "authentication"
            case .server: return "server"
            case .cancelled: return "cancellation"
            case .unexpected: return "application"
            }
        }

        var message: String {
            switch self {
            case .unexpected: return "The operation failed."
            case .network: return "A network request failed."
            case .timedOut: return "A network request timed out."
            case .offline: return "The network connection is unavailable."
            case .secureConnection: return "A secure connection could not be established."
            case .invalidResponse: return "A network response was invalid."
            case .authentication: return "Account authentication failed."
            case .filesystem: return "A file operation failed."
            case .permissionDenied: return "A file operation was denied permission."
            case .storageFull: return "There was not enough storage for the file operation."
            case .cancelled: return "The operation was cancelled."
            case .server: return "The server request failed."
            case .missingFile: return "A required file was unavailable."
            }
        }
    }

    static func sanitized(_ error: NSError) -> NSError {
        // Do not enumerate userInfo, inspect underlying errors, evaluate an
        // error's description, or call its domain's userInfo value provider.
        return snapshot(domain: error.domain, code: error.code)
    }

    static func snapshot(domain sourceDomain: String, code sourceCode: Int) -> NSError {
        let category = category(domain: sourceDomain, code: sourceCode)
        return NSError(domain: domain, code: category.rawValue, userInfo: [
            NSLocalizedDescriptionKey: category.message,
            "category": category.group,
            "outcome": category == .cancelled ? "cancelled" : "failed"
        ])
    }

    private static func category(domain sourceDomain: String, code: Int) -> Category {
        // Reconstruct our own records from the closed code set. In particular,
        // never trust a stored description or metadata just because its domain
        // matches ours: legacy rows and repeated sanitization use this path.
        if sourceDomain == domain { return Category(rawValue: code) ?? .unexpected }
        switch sourceDomain {
        case NSURLErrorDomain:
            switch code {
            case NSURLErrorCancelled: return .cancelled
            case NSURLErrorTimedOut: return .timedOut
            case NSURLErrorNotConnectedToInternet: return .offline
            case NSURLErrorSecureConnectionFailed, NSURLErrorServerCertificateHasBadDate,
                 NSURLErrorServerCertificateUntrusted, NSURLErrorServerCertificateHasUnknownRoot,
                 NSURLErrorServerCertificateNotYetValid, NSURLErrorClientCertificateRejected,
                 NSURLErrorClientCertificateRequired:
                return .secureConnection
            case NSURLErrorBadServerResponse, NSURLErrorCannotParseResponse,
                 NSURLErrorCannotDecodeRawData, NSURLErrorCannotDecodeContentData:
                return .invalidResponse
            default: return .network
            }
        case NSCocoaErrorDomain:
            switch code {
            case NSUserCancelledError: return .cancelled
            case NSFileReadNoPermissionError, NSFileWriteNoPermissionError: return .permissionDenied
            case NSFileWriteOutOfSpaceError: return .storageFull
            case NSFileNoSuchFileError, NSFileReadNoSuchFileError: return .missingFile
            default: return .filesystem
            }
        case "SideSign.DeveloperPortalError": return .authentication
        case "SideSign.ServerError": return .server
        case "Swift.CancellationError": return .cancelled
        default: return .unexpected
        }
    }
}
