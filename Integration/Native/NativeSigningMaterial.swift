// SPDX-License-Identifier: AGPL-3.0-only
#if os(iOS)
import Foundation
import Security
import SideSign

/// Explicit foreground file operations only. No Apple request, active-signer
/// change, key generation, password persistence or automatic export.
enum NativeSigningMaterial {
    static func validateP12(_ bytes: Data, password: String) throws -> ALTCertificate {
        guard !bytes.isEmpty, bytes.count <= 32_768, password.utf8.count <= 1024 else {
            throw CertificateExportFailure.invalidIdentity
        }
        try NativeEncryptedP12.validateImport(bytes, password: password)
        try Task.checkCancellation()
        var items: CFArray?
        let options = [kSecImportExportPassphrase as String: password] as CFDictionary
        guard SecPKCS12Import(bytes as CFData, options, &items) == errSecSuccess,
              let entries = items as? [[String: Any]], entries.count == 1,
              let raw = entries.first?[kSecImportItemIdentity as String],
              CFGetTypeID(raw as CFTypeRef) == SecIdentityGetTypeID() else {
            throw CertificateExportFailure.invalidIdentity
        }
        let identity = raw as! SecIdentity
        var certificate: SecCertificate?
        var privateKey: SecKey?
        guard SecIdentityCopyCertificate(identity, &certificate) == errSecSuccess,
              SecIdentityCopyPrivateKey(identity, &privateKey) == errSecSuccess,
              let certificate, let privateKey, let derived = SecKeyCopyPublicKey(privateKey),
              let publicKey = SecCertificateCopyKey(certificate),
              let derivedBytes = SecKeyCopyExternalRepresentation(derived, nil) as Data?,
              let publicBytes = SecKeyCopyExternalRepresentation(publicKey, nil) as Data?,
              derivedBytes == publicBytes else { throw CertificateExportFailure.invalidIdentity }
        let parsed = try CertificateManager.parse(bytes, password: password)
        guard !parsed.privateKey.isEmpty, parsed.data == SecCertificateCopyData(certificate) as Data else {
            throw CertificateExportFailure.invalidIdentity
        }
        return parsed
    }

    static func importP12(_ bytes: Data, password: String) throws -> String {
        try NativeMutationGate.withSynchronousLease {
            let certificate = try validateP12(bytes, password: password)
            guard certificate.x509.expiryDate > Date() else { throw CertificateExportFailure.invalidIdentity }
            try Task.checkCancellation()
            try CertificateManager.shared.saveCertificate(certificate)
            guard let saved = try CertificateManager.shared.getLocalCertificateVerified(serialNumber: certificate.serialNumber),
                  saved.data == certificate.data, saved.privateKey == certificate.privateKey else {
                throw AuthenticationStorageFailure.readbackMismatch
            }
            // Selection is left to normal setup, which verifies current-Team portal membership.
            return certificate.serialNumber
        }
    }

    static func encryptedP12(_ certificate: ALTCertificate, password: String, confirmation: String) throws -> Data {
        try CertificateExportPolicy.validate(password: password, confirmation: confirmation, serial: certificate.serialNumber)
        guard let certificateDER = certificate.data else { throw CertificateExportFailure.invalidIdentity }
        let bytes = try NativeEncryptedP12.export(certificateDER: certificateDER, privateKeyDER: certificate.privateKey, password: password)
        let parsed = try validateP12(bytes, password: password)
        guard parsed.data == certificate.data else { throw CertificateExportFailure.invalidIdentity }
        // Reject the known upstream defect: neither empty nor wrong password
        // may recover an identity from a purported encrypted export.
        if (try? validateP12(bytes, password: "")) != nil ||
           (try? validateP12(bytes, password: password + "-incorrect")) != nil {
            throw CertificateExportFailure.encryptedExportUnavailable
        }
        return bytes
    }

    static func backup(serial: String, password: String, confirmation: String) throws -> [String: Data] {
        try NativeMutationGate.withSynchronousLease {
            guard let certificate = try CertificateManager.shared.getLocalCertificateVerified(serialNumber: serial) else {
                throw CertificateExportFailure.unavailable
            }
            let p12 = try encryptedP12(certificate, password: password, confirmation: confirmation)
            var files: [String: Data] = ["identity.p12": p12]
            // Only bundle-local profiles are read; no account identifiers, tokens,
            // pairing files, database dumps or unrelated application files.
            var bundles = [Bundle.main.bundleURL]
            let plugins = Bundle.main.bundleURL.appendingPathComponent("PlugIns", isDirectory: true)
            if FileManager.default.fileExists(atPath: plugins.path) {
                let children = try FileManager.default.contentsOfDirectory(at: plugins, includingPropertiesForKeys: [.isSymbolicLinkKey])
                guard children.count <= 32 else { throw CertificateExportFailure.unavailable }
                for child in children where child.pathExtension == "appex" {
                    guard try child.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink != true else { throw CertificateExportFailure.unavailable }
                    bundles.append(child)
                }
            }
            var count = 0
            for bundle in bundles {
                let url = bundle.appendingPathComponent("embedded.mobileprovision")
                guard let bytes = try NativeRenewalStorage.read(url, maximum: 1_048_576) else { continue }
                let profile = try ALTProvisioningProfile(data: bytes)
                guard profile.certificates.contains(where: { $0.data == certificate.data }) else { continue }
                count += 1
                files["profile-\(count).mobileprovision"] = bytes
            }
            let note = """
            Tetherless signing-material backup
            identity.p12 contains the certificate AND private key, encrypted with the password you chose.
            Keep the password separately. Anyone with this file and password can use this signing identity.
            Included profiles: \(count). Only matching profiles embedded in this running app and its extensions were copied.
            This is NOT a complete account backup. Profiles may already be expired and contain device identifiers.
            Import identity.p12 in Signing material, then continue setup to verify Team membership and obtain current profiles.
            A P12 does not extend Apple's certificate/profile expiry or bypass installation limits.
            No Apple password, 2FA code, session, pairing record or export password is included.
            """
            files["README.txt"] = Data(note.utf8)
            return files
        }
    }
}
#endif
