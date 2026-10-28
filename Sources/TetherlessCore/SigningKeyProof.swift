// SPDX-License-Identifier: AGPL-3.0-only
#if canImport(Security)
import Foundation
import Security

/// Local proof of usable private parameters, not merely equal public n/e.
/// The fixed domain-separated challenge/signature is never sent or logged.
public enum SigningKeyProof {
    public static func requireMatch(privateKey: SecKey, certificate: SecCertificate) throws {
        guard let derived = SecKeyCopyPublicKey(privateKey), let publicKey = SecCertificateCopyKey(certificate),
              let derivedBytes = SecKeyCopyExternalRepresentation(derived, nil) as Data?,
              let publicBytes = SecKeyCopyExternalRepresentation(publicKey, nil) as Data?, derivedBytes == publicBytes else {
            throw CertificateExportFailure.invalidIdentity
        }
        let challenge = Data("Tetherless local signing-key possession check v1; not an authentication request".utf8)
        guard let signature = SecKeyCreateSignature(privateKey, .rsaSignatureMessagePKCS1v15SHA256, challenge as CFData, nil),
              SecKeyVerifySignature(publicKey, .rsaSignatureMessagePKCS1v15SHA256, challenge as CFData, signature, nil) else {
            throw CertificateExportFailure.invalidIdentity
        }
    }
}
#endif
