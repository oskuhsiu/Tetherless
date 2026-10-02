// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// Signing material crossing the app-bundle boundary must contain no private key.
/// Callers provide the public X.509 DER, not a PKCS#12 archive. This helper does
/// not claim to validate a certificate chain; signing/OS validation remain separate.
public enum PublicSigningMaterial {
    public static func writeCertificate(_ publicDER: Data, into appURL: URL) throws {
        guard !publicDER.isEmpty, publicDER.count <= 65_536, appURL.isFileURL else {
            throw RenewalFailure.invalidInput
        }
        let values = try appURL.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
        guard values.isDirectory == true, values.isSymbolicLink != true else {
            throw RenewalFailure.invalidInput
        }
        let legacy = appURL.appendingPathComponent("ALTCertificate.p12")
        // Only the known inherited metadata resource is removed, never arbitrary
        // user application .p12 assets (which may have a legitimate purpose).
        do { try FileManager.default.removeItem(at: legacy) }
        catch let error as NSError where error.domain == NSCocoaErrorDomain && error.code == NSFileNoSuchFileError {}
        let destination = appURL.appendingPathComponent("ALTCertificate.der")
        // Atomic replacement does not follow an existing destination symlink.
        try publicDER.write(to: destination, options: .atomic)
    }
}
