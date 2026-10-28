// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// Export protection is distinct from the device Keychain's internal envelope.
public enum CertificateExportPolicy {
    public static func validate(password: String, confirmation: String, serial: String) throws {
        guard password == confirmation, password.count >= 12, password.utf8.count <= 1024,
              password.trimmingCharacters(in: .whitespacesAndNewlines).count >= 12,
              password.caseInsensitiveCompare(serial) != .orderedSame else {
            throw CertificateExportFailure.passwordRequirements
        }
    }
}
public enum CertificateExportFailure: String, Error, LocalizedError, Sendable {
    case passwordRequirements, invalidIdentity, unavailable, encryptedExportUnavailable, useValidatedImport
    public var errorDescription: String? {
        switch self {
        case .useValidatedImport: return "Use Auto Renewal → Signing material to import and validate a P12 containing the matching private key."
        case .encryptedExportUnavailable: return "Encrypted native backup is not yet available. The existing key remains in Keychain; no unencrypted private key was exported."
        case .passwordRequirements: return "Use a new matching password of at least 12 characters (not the certificate serial). Keep it separately from the backup."
        case .invalidIdentity: return "The P12 must contain one matching certificate and private key. No signing identity was changed."
        case .unavailable: return "Signing material is unavailable. No certificate was created or revoked."
        }
    }
}
