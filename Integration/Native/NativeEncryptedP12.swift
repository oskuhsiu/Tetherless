// SPDX-License-Identifier: AGPL-3.0-only
#if canImport(JavaScriptCore) && canImport(Security)
import Foundation
import JavaScriptCore
import Security
import CryptoKit

/// A fresh, isolated JavaScriptCore context per explicit export. It has no
/// browser/network APIs and uses only Security.framework entropy. No JS value,
/// key, password or context is retained on success or failure.
enum NativeEncryptedP12 {
    private static let forgeSHA256 = "d9b9074e6861200d676e25dcfe97889db5e8f4150bb766d29c491ad709a51b58"
    private static let adapterSHA256 = "80881a595fb287373f1bb6d771b96aec500f947da15509c274af678dd546c296"
    private static let environmentSHA256 = "2b7eb0137ba46b90f0fa7533710091221f650db47ac7e30ec00fcfbda759f226"
    static func export(certificateDER: Data, privateKeyDER: Data, password: String) throws -> Data {
        guard !certificateDER.isEmpty, certificateDER.count <= 16_384,
              !privateKeyDER.isEmpty, privateKeyDER.count <= 16_384,
              password.utf8.count <= 1024 else { throw CertificateExportFailure.invalidIdentity }
        let encoded = try call("tetherlessEncryptP12", arguments: [certificateDER.base64EncodedString(), privateKeyDER.base64EncodedString(), password])
        guard encoded.utf8.count <= 65_536, let bytes = Data(base64Encoded: encoded), !bytes.isEmpty, bytes.count <= 32_768 else {
            throw CertificateExportFailure.encryptedExportUnavailable
        }
        return bytes
    }
    static func validateImport(_ data: Data, password: String) throws {
        guard data.count <= 32_768, password.utf8.count <= 1024,
              try call("tetherlessValidateP12", arguments: [data.base64EncodedString(), password]) == "valid" else {
            throw CertificateExportFailure.invalidIdentity
        }
    }
    private static func call(_ functionName: String, arguments: [String]) throws -> String {
        try Task.checkCancellation()
        guard !Thread.isMainThread else { throw CertificateExportFailure.encryptedExportUnavailable }
        guard let forgeURL = Bundle.main.url(forResource: "TetherlessForge.min", withExtension: "js"),
              let adapterURL = Bundle.main.url(forResource: "TetherlessSigningCrypto", withExtension: "js"),
              let environmentURL = Bundle.main.url(forResource: "TetherlessCryptoEnvironment", withExtension: "js"),
              let context = JSContext() else { throw CertificateExportFailure.encryptedExportUnavailable }
        let forge = try Data(contentsOf: forgeURL), adapter = try Data(contentsOf: adapterURL), environment = try Data(contentsOf: environmentURL)
        guard forge.count <= 1_048_576, adapter.count <= 16_384, environment.count <= 16_384,
              SHA256.hash(data: forge).map({ String(format: "%02x", $0) }).joined() == forgeSHA256,
              SHA256.hash(data: adapter).map({ String(format: "%02x", $0) }).joined() == adapterSHA256,
              SHA256.hash(data: environment).map({ String(format: "%02x", $0) }).joined() == environmentSHA256,
              let setup = String(data: environment, encoding: .utf8),
              let library = String(data: forge, encoding: .utf8), let script = String(data: adapter, encoding: .utf8) else {
            throw CertificateExportFailure.encryptedExportUnavailable
        }
        let random: @convention(block) (Int) -> NSArray? = { count in
            guard count >= 0, count <= 65536 else { return nil }
            var bytes = [UInt8](repeating: 0, count: count)
            guard SecRandomCopyBytes(kSecRandomDefault, count, &bytes) == errSecSuccess else { return nil }
            return bytes.map { NSNumber(value: $0) } as NSArray
        }
        context.setObject(random, forKeyedSubscript: "nativeSecureRandom" as NSString)
        defer {
            context.exception = nil
            context.setObject(nil, forKeyedSubscript: "nativeSecureRandom" as NSString)
            context.setObject(nil, forKeyedSubscript: "tetherlessEncryptP12" as NSString)
            context.setObject(nil, forKeyedSubscript: "tetherlessValidateP12" as NSString)
        }
        // Forge's UMD wrapper expects window. A cryptographic seed is also
        // supplied before library initialization; Math.random is forbidden.
        context.evaluateScript(setup)
        guard context.exception == nil else { throw CertificateExportFailure.encryptedExportUnavailable }
        context.evaluateScript(library)
        guard context.exception == nil else { throw CertificateExportFailure.encryptedExportUnavailable }
        context.evaluateScript(script)
        guard context.exception == nil, let function = context.objectForKeyedSubscript(functionName), !function.isUndefined else {
            throw CertificateExportFailure.encryptedExportUnavailable
        }
        let result = function.call(withArguments: arguments)
        guard context.exception == nil, let encoded = result?.toString(), encoded.utf8.count <= 65_536 else {
            throw CertificateExportFailure.encryptedExportUnavailable
        }
        try Task.checkCancellation()
        return encoded
    }
}
#endif
