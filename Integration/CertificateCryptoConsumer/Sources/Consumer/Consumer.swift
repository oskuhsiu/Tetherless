// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Security
import CodeSignKit
import Crypto

enum ConsumerFailure: Error { case invalidFixture, consumerMismatch, nativeReadback, negativeAccepted }
@main struct CertificateCryptoConsumer {
    static func main() async throws {
        guard CommandLine.arguments.count == 2 else { throw ConsumerFailure.invalidFixture }
        let root = URL(fileURLWithPath: CommandLine.arguments[1])
        let checks = try await Task.detached {
            let certificateDER = try Data(contentsOf: root.appendingPathComponent("cert.der"))
            let privateDER = try Data(contentsOf: root.appendingPathComponent("key.der"))
            let password = "synthetic-consumer-test-only"
            let p12 = try NativeEncryptedP12.export(certificateDER: certificateDER, privateKeyDER: privateDER, password: password)
            try NativeEncryptedP12.validateImport(p12, password: password)
            // Exercise the exact pinned signer consumer, not a mock parser.
            let consumer = try CodeSignKit.PKCS12Parser(p12Data: p12, password: password)
            guard consumer.leafCertificate?.rawDER == certificateDER, let signer = consumer.rsaPrivateKey,
                  let certificate = SecCertificateCreateWithData(nil, certificateDER as CFData),
                  let publicKey = SecCertificateCopyKey(certificate) else { throw ConsumerFailure.consumerMismatch }
            let challenge = Data("Tetherless synthetic downstream signer test; not Apple authentication".utf8)
            let signature = try signer.signature(for: Crypto.SHA256.hash(data: challenge), padding: .insecurePKCS1v1_5)
            guard SecKeyVerifySignature(publicKey, .rsaSignatureMessagePKCS1v15SHA256,
                    challenge as CFData, signature.rawRepresentation as CFData, nil) else { throw ConsumerFailure.consumerMismatch }
            // Preserve the native container gate and exercise the same key proof
            // used by the app's import path. macOS must not persist this fixture.
            var items: CFArray?
            let status = SecPKCS12Import(p12 as CFData,
                [kSecImportExportPassphrase as String: password, kSecImportToMemoryOnly as String: true] as CFDictionary, &items)
            guard status == errSecSuccess, let entries = items as? [[String: Any]], entries.count == 1,
                  let raw = entries.first?[kSecImportItemIdentity as String],
                  CFGetTypeID(raw as CFTypeRef) == SecIdentityGetTypeID() else { throw ConsumerFailure.nativeReadback }
            let identity = raw as! SecIdentity
            var importedCertificate: SecCertificate?, importedKey: SecKey?
            guard SecIdentityCopyCertificate(identity, &importedCertificate) == errSecSuccess,
                  SecIdentityCopyPrivateKey(identity, &importedKey) == errSecSuccess,
                  let importedCertificate, let importedKey,
                  SecCertificateCopyData(importedCertificate) as Data == certificateDER else { throw ConsumerFailure.nativeReadback }
            try SigningKeyProof.requireMatch(privateKey: importedKey, certificate: importedCertificate)
            for wrong in ["", "incorrect-synthetic-password"] {
                var rejected = false
                do { try NativeEncryptedP12.validateImport(p12, password: wrong) } catch { rejected = true }
                guard rejected else { throw ConsumerFailure.negativeAccepted }
            }
            // MAC-only mutation: change the last byte of the MAC digest, not the
            // key ciphertext. This fixture is made by the same pinned Forge.
            let webOriginal = try Data(contentsOf: root.appendingPathComponent("web-original.p12"))
            try NativeEncryptedP12.validateImport(webOriginal, password: password)
            let webConsumer = try CodeSignKit.PKCS12Parser(p12Data: webOriginal, password: password)
            guard webConsumer.leafCertificate?.rawDER == certificateDER, let webSigner = webConsumer.rsaPrivateKey else { throw ConsumerFailure.consumerMismatch }
            let webSignature = try webSigner.signature(for: Crypto.SHA256.hash(data: challenge), padding: .insecurePKCS1v1_5)
            guard SecKeyVerifySignature(publicKey, .rsaSignatureMessagePKCS1v15SHA256, challenge as CFData,
                    webSignature.rawRepresentation as CFData, nil) else { throw ConsumerFailure.consumerMismatch }
            var webItems: CFArray?
            guard SecPKCS12Import(webOriginal as CFData,
                [kSecImportExportPassphrase as String: password, kSecImportToMemoryOnly as String: true] as CFDictionary, &webItems) == errSecSuccess else { throw ConsumerFailure.nativeReadback }
            let macTampered = try Data(contentsOf: root.appendingPathComponent("mac-tampered.p12"))
            var rejected = false
            do { try NativeEncryptedP12.validateImport(macTampered, password: password) } catch { rejected = true }
            guard rejected else { throw ConsumerFailure.negativeAccepted }
            for unsupported in ["合成測試密碼不可用於匯出", "synthetic-emoji-🔒"] {
                var rejected = false
                do { _ = try NativeEncryptedP12.export(certificateDER: certificateDER, privateKeyDER: privateDER, password: unsupported) }
                catch { rejected = true }
                guard rejected else { throw ConsumerFailure.negativeAccepted }
            }
            return ["pinned_consumer_certificate", "pinned_consumer_signature_native_verify", "security_container_readback",
                    "native_private_key_proof", "wrong_password_rejected", "empty_password_rejected", "mac_tamper_rejected", "non_ascii_export_rejected", "actual_web_export_native_consumer"]
        }.value
        let result = ["checks": checks]
        print(String(decoding: try JSONEncoder().encode(result), as: UTF8.self))
    }
}
