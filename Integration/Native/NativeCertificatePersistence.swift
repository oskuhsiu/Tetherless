// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import SideSign

/// Does not create/revoke certificates or call Apple. No split-field fallback
/// is allowed after an authoritative envelope, including a tombstone, exists.
enum NativeCertificatePersistence {
    static func store() throws -> VerifiedSigningIdentityStore {
        VerifiedSigningIdentityStore(storage: try KeychainAuthenticationStorage(
            service: "org.tetherless.credentials." + Bundle.Info.appbundleIdentifier,
            account: "active-signing-v1"))
    }
    static func record(_ certificate: ALTCertificate) throws -> StoredSigningIdentity {
        let password = certificate.serialNumber
        let bytes = try CertificateManager.convert(certificate, password: password)
        let parsed = try CertificateManager.parse(bytes, password: password)
        guard parsed.serialNumber.caseInsensitiveCompare(certificate.serialNumber) == .orderedSame,
              parsed.data == certificate.data, !parsed.privateKey.isEmpty else {
            throw AuthenticationStorageFailure.readbackMismatch
        }
        return try StoredSigningIdentity(serial: certificate.serialNumber, p12: bytes, password: password)
    }
    static func decode(_ record: StoredSigningIdentity?) throws -> ActiveSigningCertificate? {
        guard let record else { return nil }
        try record.validate()
        let certificate = try CertificateManager.parse(record.p12, password: record.password)
        guard certificate.serialNumber.caseInsensitiveCompare(record.serial) == .orderedSame,
              !certificate.privateKey.isEmpty else { throw AuthenticationStorageFailure.invalidRecord }
        return ActiveSigningCertificate(certificate: certificate, p12Data: record.p12, password: record.password)
    }
    static func loadActive() throws -> ActiveSigningCertificate? {
        if let envelope = try store().read() { return try decode(envelope.identity) }
        return try NativeMutationGate.withSynchronousLease {
            if let envelope = try store().read() { return try decode(envelope.identity) }
            guard let (data, password) = try Keychain.shared.readLegacyActiveSigningVerified() else { return nil }
            let certificate = try CertificateManager.parse(data, password: password)
            let newRecord = try record(certificate)
            try store().save(newRecord)
            // The cache is saved before removing the only legacy active copy.
            try Keychain.shared.writeImportedCertificateVerified(newRecord.p12, serial: newRecord.serial)
            try Keychain.shared.removeActiveCertificateVerified()
            return try decode(newRecord)
        }
    }
    static func saveActive(_ record: StoredSigningIdentity?) throws {
        try NativeMutationGate.withSynchronousLease {
            _ = try decode(record) // Validate before touching the existing item.
            try store().save(record)
            try Keychain.shared.removeActiveCertificateVerified()
        }
    }
}
