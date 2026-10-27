// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import SideSign

/// Called while the complete portal operation owns NativeMutationGate. Tokens
/// stay in the in-memory backend; only request-specific key/CSR live in the vault.
enum NativeCertificateIssuance {
    /// One namespace for normal issuance and explicit recovery. Caller holds
    /// NativeMutationGate; constructing the adapter does not write to Keychain.
    static func store(owner: CertificateIssuanceOwner) throws -> CertificateIssuanceStore {
        try owner.validate()
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        let scope = NativeRenewalStorage.digest(try encoder.encode(owner))
        return CertificateIssuanceStore(storage: try KeychainAuthenticationStorage(
            service: "org.tetherless.requests." + Bundle.Info.appbundleIdentifier,
            account: "certificate-v1." + scope))
    }

    static func perform(machineName: String, type: CertificateType, team: ALTTeam,
                        session: ALTAppleAPISession, allowNew: Bool) async throws -> ALTCertificate? {
        let account = try NativeAuthenticationStore.ready()
        guard account.credentials?.dsid == session.dsid, account.teamID == team.identifier else {
            throw AuthenticationStorageFailure.staleAttempt
        }
        guard CertificateType.allCases.contains(type), !(team.type == .free && type.isPaidOnly) else {
            throw DeveloperPortalError.invalidParameters(cause: "This certificate type is not available for the selected account.")
        }
        let owner = try CertificateIssuanceOwner(accountID: session.dsid, teamID: team.identifier, certificateType: type.rawValue)
        let requestStore = try store(owner: owner)
        let backend = NativeCertificateIssuanceBackend(account: account, team: team, session: session,
                                                       type: type, machineName: machineName)
        let result: IssuedCertificate?
        do {
            result = try await CertificateIssuanceCoordinator(store: requestStore)
                .issue(owner: owner, backend: backend, allowNew: allowNew)
        } catch CertificateIssuanceFailure.capacityReached {
            throw DeveloperPortalError.tooManyCertificates(cause: "Apple reported the certificate limit. No existing certificate was revoked.")
        }
        guard let result else { return nil }
        try NativeAuthenticationStore.assertCurrent(account)
        guard let saved = try CertificateManager.shared.getLocalCertificateVerified(serialNumber: result.serial),
              saved.data == result.der, !saved.privateKey.isEmpty else { throw AuthenticationStorageFailure.readbackMismatch }
        return saved
    }
}

struct NativeCertificateIssuanceBackend: CertificateIssuanceBackend, CertificateIssuanceLookup {
    let account: AuthenticationRecord
    let team: ALTTeam
    let session: ALTAppleAPISession
    let type: CertificateType
    let machineName: String

    func prepare() throws -> CertificateRequestMaterial {
        try NativeAuthenticationStore.assertCurrent(account)
        guard !machineName.isEmpty, machineName.utf8.count <= 128 else { throw CertificateIssuanceFailure.invalidRecord }
        let request = try CertificateRequest(machineName: machineName)
        let key = try CertificateKeyBinding.validate(privateKeyPEM: request.privateKey, csrPEM: request.csrData)
        return try CertificateRequestMaterial(machineName: machineName, privateKeyPEM: request.privateKey,
                                              csrPEM: request.csrData, publicKey: key)
    }
    func validate(_ material: CertificateRequestMaterial) throws {
        try NativeAuthenticationStore.assertCurrent(account)
        try material.validate()
        guard try CertificateKeyBinding.validate(privateKeyPEM: material.privateKeyPEM, csrPEM: material.csrPEM) == material.publicKey else {
            throw CertificateIssuanceFailure.keyMismatch
        }
    }
    func fetchCertificates() async throws -> [IssuedCertificate] {
        try NativeAuthenticationStore.assertCurrent(account)
        let list = try await ALTAppleAPI.shared.fetchCertificates(for: team, session: session)
        try NativeAuthenticationStore.assertCurrent(account)
        guard list.count <= 4096 else { throw CertificateIssuanceFailure.invalidRecord }
        return try list.filter { $0.expiryDate > Date() }.map(convert)
    }
    func submit(_ record: CertificateIssuanceRecord) async throws -> IssuedCertificate {
        try validate(record.material)
        let cert: ALTX509Certificate
        do {
            cert = try await ALTAppleAPI.shared.submitCertificateRequest(csrData: record.material.csrPEM,
                machineName: record.material.machineName, machineIdentifier: record.id.uuidString.uppercased(),
                type: type, to: team, session: session)
        } catch let error as DeveloperPortalError {
            switch error {
            case .tooManyCertificates: throw CertificateIssuanceFailure.capacityReached
            case .invalidCertificateRequest: throw CertificateIssuanceFailure.requestRejected
            default: throw error // Auth, network and other errors retain the key.
            }
        }
        try NativeAuthenticationStore.assertCurrent(account)
        return try convert(cert)
    }
    func validate(_ certificate: IssuedCertificate, for material: CertificateRequestMaterial) throws {
        try validate(material)
        guard let parsed = ALTX509Certificate(data: certificate.der), parsed.expiryDate > Date(),
              parsed.serialNumber.caseInsensitiveCompare(certificate.serial) == .orderedSame,
              try CertificateKeyBinding.certificatePublicKey(certificate.der) == material.publicKey,
              certificate.publicKey == material.publicKey else { throw CertificateIssuanceFailure.keyMismatch }
    }
    func persist(_ certificate: IssuedCertificate, material: CertificateRequestMaterial) throws {
        try validate(certificate, for: material)
        guard var parsed = ALTX509Certificate(data: certificate.der) else { throw CertificateIssuanceFailure.invalidRecord }
        parsed.machineName = material.machineName
        let signer = ALTCertificate(x509: parsed, privateKey: material.privateKeyPEM)
        try CertificateManager.shared.saveCertificate(signer)
        guard let saved = try CertificateManager.shared.getLocalCertificateVerified(serialNumber: certificate.serial),
              saved.data == certificate.der, !saved.privateKey.isEmpty else { throw AuthenticationStorageFailure.readbackMismatch }
        // Compare a P12 round-trip against the exact already-bound signer. A
        // nonempty but unrelated private key must never complete recovery.
        let expected = try ALTCertificate(p12Data: signer.unencryptedP12Data(), password: nil)
        guard saved.privateKey == expected.privateKey else { throw AuthenticationStorageFailure.readbackMismatch }
    }
    private func convert(_ certificate: ALTX509Certificate) throws -> IssuedCertificate {
        guard let der = certificate.data, certificate.expiryDate > Date() else { throw CertificateIssuanceFailure.invalidRecord }
        return try IssuedCertificate(serial: certificate.serialNumber, der: der,
                                     publicKey: CertificateKeyBinding.certificatePublicKey(der))
    }
}
