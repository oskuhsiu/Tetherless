// SPDX-License-Identifier: AGPL-3.0-only
#if canImport(Security)
import Foundation
import Security
import Testing
@testable import TetherlessCore

/// Ephemeral RSA keys created by Security on each run. The synthetic CSR and
/// certificate are signed, but have no Apple authority, account or device.
@Suite("Certificate binding: real ephemeral RSA signatures; not Apple trust")
struct CertificateKeyBindingTests {
    private let rsaOID = Data([0x30,0x0d,0x06,0x09,0x2a,0x86,0x48,0x86,0xf7,0x0d,0x01,0x01,0x01,0x05,0x00])
    private let signatureOID = Data([0x30,0x0d,0x06,0x09,0x2a,0x86,0x48,0x86,0xf7,0x0d,0x01,0x01,0x0b,0x05,0x00])
    private func tlv(_ tag: UInt8, _ bytes: Data) -> Data {
        var length = bytes.count
        var encoding: [UInt8] = []
        if length < 128 { encoding = [UInt8(length)] }
        else {
            while length > 0 { encoding.insert(UInt8(length & 255), at: 0); length >>= 8 }
            encoding.insert(0x80 | UInt8(encoding.count), at: 0)
        }
        return Data([tag] + encoding) + bytes
    }
    private func seq(_ value: Data) -> Data { tlv(0x30, value) }
    private func pem(_ data: Data, _ label: String) -> Data {
        Data(("-----BEGIN \(label)-----\n" + data.base64EncodedString(options: .lineLength64Characters) + "\n-----END \(label)-----\n").utf8)
    }
    private func sign(_ bytes: Data, using key: SecKey) throws -> Data {
        try #require(SecKeyCreateSignature(key, .rsaSignatureMessagePKCS1v15SHA256, bytes as CFData, nil) as Data?)
    }
    private func fixture() throws -> (privatePEM: Data, csrDER: Data, csrPEM: Data, publicDER: Data, certDER: Data) {
        let attrs: [String: Any] = [kSecAttrKeyType as String: kSecAttrKeyTypeRSA, kSecAttrKeySizeInBits as String: 2048]
        let key = try #require(SecKeyCreateRandomKey(attrs as CFDictionary, nil))
        let publicKey = try #require(SecKeyCopyPublicKey(key))
        let privateDER = try #require(SecKeyCopyExternalRepresentation(key, nil) as Data?)
        let publicDER = try #require(SecKeyCopyExternalRepresentation(publicKey, nil) as Data?)
        let name = seq(tlv(0x31, seq(Data([0x06,0x03,0x55,0x04,0x03]) + tlv(0x0c, Data("Disposable Test".utf8)))))
        let spki = seq(rsaOID + tlv(0x03, Data([0]) + publicDER))
        let info = seq(tlv(0x02, Data([0])) + name + spki + tlv(0xa0, Data()))
        let csr = try seq(info + signatureOID + tlv(0x03, Data([0]) + sign(info, using: key)))
        let validity = seq(tlv(0x17, Data("260101000000Z".utf8)) + tlv(0x17, Data("300101000000Z".utf8)))
        let tbs = seq(tlv(0xa0, tlv(0x02, Data([2]))) + tlv(0x02, Data([1])) + signatureOID + name + validity + name + spki)
        let cert = try seq(tbs + signatureOID + tlv(0x03, Data([0]) + sign(tbs, using: key)))
        return (pem(privateDER, "RSA PRIVATE KEY"), csr, pem(csr, "CERTIFICATE REQUEST"), publicDER, cert)
    }
    @Test func signedCSRAndCertificateMatchTheGeneratedPrivateKey() throws {
        let f = try fixture()
        #expect(try CertificateKeyBinding.validate(privateKeyPEM: f.privatePEM, csrPEM: f.csrPEM) == f.publicDER)
        #expect(try CertificateKeyBinding.certificatePublicKey(f.certDER) == f.publicDER)
    }
    @Test func anotherPrivateKeyCannotOwnTheCSR() throws {
        let f = try fixture(), other = try fixture()
        #expect(throws: CertificateIssuanceFailure.keyMismatch) {
            try CertificateKeyBinding.validate(privateKeyPEM: other.privatePEM, csrPEM: f.csrPEM)
        }
        #expect(try CertificateKeyBinding.certificatePublicKey(other.certDER) != f.publicDER)
    }
    @Test func invalidCSRSignatureCannotBePersistedAsValid() throws {
        let f = try fixture()
        var csr = f.csrDER; csr[csr.count - 1] ^= 1
        #expect(throws: CertificateIssuanceFailure.keyMismatch) {
            try CertificateKeyBinding.validate(privateKeyPEM: f.privatePEM, csrPEM: pem(csr, "CERTIFICATE REQUEST"))
        }
    }
    @Test func trailingAndMalformedDERCannotBeIgnored() throws {
        let f = try fixture()
        for malformed in [f.csrDER + Data([0]), Data([0x30,0x80,0,0]), Data([0x30,0xff,1]), Data([0x30])] {
            #expect(throws: CertificateIssuanceFailure.self) {
                try CertificateKeyBinding.validate(privateKeyPEM: f.privatePEM, csrPEM: pem(malformed, "CERTIFICATE REQUEST"))
            }
        }
        #expect(throws: CertificateIssuanceFailure.invalidRecord) {
            try CertificateKeyBinding.certificatePublicKey(f.certDER + Data([0]))
        }
    }
    @Test func multiplePEMBlocksAndOversizeInputsAreRejected() throws {
        let f = try fixture()
        #expect(throws: CertificateIssuanceFailure.invalidRecord) {
            try CertificateKeyBinding.validate(privateKeyPEM: f.privatePEM + f.privatePEM, csrPEM: f.csrPEM)
        }
        #expect(throws: CertificateIssuanceFailure.invalidRecord) {
            try CertificateKeyBinding.validate(privateKeyPEM: Data(repeating: 65, count: 8193), csrPEM: f.csrPEM)
        }
        #expect(throws: CertificateIssuanceFailure.invalidRecord) {
            try CertificateKeyBinding.certificatePublicKey(Data(repeating: 0, count: 16_385))
        }
    }
}
#endif
