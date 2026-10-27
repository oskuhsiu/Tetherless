// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

public enum CertificateIssuanceFailure: String, Error, LocalizedError, Sendable {
    case invalidRecord, unsupportedVersion, staleAttempt, awaitingPortalVisibility, ambiguousMatch, keyMismatch
    case capacityReached, requestRejected
    public var errorDescription: String? {
        switch self {
        case .awaitingPortalVisibility:
            return "The previous certificate request has no matching certificate on Apple yet. Retry checks that request; it does not create another certificate."
        case .ambiguousMatch: return "Multiple certificates match the saved request. No new certificate was created."
        case .capacityReached: return "Apple reported that the certificate limit was reached."
        case .requestRejected: return "Apple rejected this certificate request."
        default: return "Certificate request recovery needs attention: \(rawValue)."
        }
    }
}

/// Scoped to the Apple account and Team, NOT a token or login generation. A
/// user may reauthenticate the same account to recover an interrupted request.
public struct CertificateIssuanceOwner: Codable, Equatable, Sendable {
    public let accountID: String
    public let teamID: String
    public let certificateType: String
    public init(accountID: String, teamID: String, certificateType: String) throws {
        self.accountID = accountID; self.teamID = teamID; self.certificateType = certificateType
        try validate()
    }
    public func validate() throws {
        for (value, limit) in [(accountID, 1024), (teamID, 64), (certificateType, 64)] {
            guard !value.isEmpty, value.utf8.count <= limit,
                  !value.unicodeScalars.contains(where: { $0.value <= 32 || $0.value == 127 }) else {
                throw CertificateIssuanceFailure.invalidRecord
            }
        }
    }
}

/// Bounded storage model, not a cryptographic validator. The real native
/// backend validates the CSR signature and its private/public key binding.
public struct CertificateRequestMaterial: Codable, Equatable, Sendable {
    public let machineName: String
    public let privateKeyPEM: Data
    public let csrPEM: Data
    public let publicKey: Data
    public init(machineName: String, privateKeyPEM: Data, csrPEM: Data, publicKey: Data) throws {
        self.machineName = machineName; self.privateKeyPEM = privateKeyPEM
        self.csrPEM = csrPEM; self.publicKey = publicKey
        try validate()
    }
    public func validate() throws {
        guard !machineName.isEmpty, machineName.utf8.count <= 128,
              !machineName.unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 }),
              !privateKeyPEM.isEmpty, privateKeyPEM.count <= 8192,
              !csrPEM.isEmpty, csrPEM.count <= 8192,
              !publicKey.isEmpty, publicKey.count <= 2048 else { throw CertificateIssuanceFailure.invalidRecord }
    }
}

public struct IssuedCertificate: Codable, Equatable, Sendable {
    public let serial: String
    public let der: Data
    public let publicKey: Data
    public init(serial: String, der: Data, publicKey: Data) throws {
        self.serial = serial; self.der = der; self.publicKey = publicKey
        try validate()
    }
    public func validate() throws {
        guard !serial.isEmpty, serial.utf8.count <= 128,
              serial.utf8.allSatisfy({ (48...57).contains($0) || (65...70).contains($0) || (97...102).contains($0) }),
              !der.isEmpty, der.count <= 16_384, !publicKey.isEmpty, publicKey.count <= 2048 else {
                throw CertificateIssuanceFailure.invalidRecord
            }
    }
}

public struct CertificateIssuanceRecord: Codable, Equatable, Sendable {
    public enum Phase: String, Codable, Sendable { case prepared, submitted, issued }
    public let id: UUID
    public let owner: CertificateIssuanceOwner
    public let material: CertificateRequestMaterial
    public var phase: Phase
    public var certificate: IssuedCertificate?
    public init(id: UUID = UUID(), owner: CertificateIssuanceOwner, material: CertificateRequestMaterial) {
        self.id = id; self.owner = owner; self.material = material; self.phase = .prepared
    }
    public func validate() throws {
        try owner.validate(); try material.validate()
        if phase == .issued {
            guard let certificate else { throw CertificateIssuanceFailure.invalidRecord }
            try certificate.validate()
            guard certificate.publicKey == material.publicKey else { throw CertificateIssuanceFailure.keyMismatch }
        } else if certificate != nil { throw CertificateIssuanceFailure.invalidRecord }
    }
}

/// All reads and writes are performed under the common native mutation lease.
/// Never drops an uncertain request on age, restart, cancellation or re-login.
public struct CertificateIssuanceStore: Sendable {
    private struct Envelope: Codable { var schemaVersion = 1; var pending: CertificateIssuanceRecord? }
    private let storage: any AuthenticationRecordStorage
    public init(storage: any AuthenticationRecordStorage) { self.storage = storage }
    public func read() throws -> CertificateIssuanceRecord? {
        guard let bytes = try storage.read() else { return nil }
        guard !bytes.isEmpty, bytes.count <= 65_536 else { throw CertificateIssuanceFailure.invalidRecord }
        let envelope: Envelope
        do { envelope = try JSONDecoder().decode(Envelope.self, from: bytes) }
        catch { throw CertificateIssuanceFailure.invalidRecord }
        guard envelope.schemaVersion == 1 else { throw CertificateIssuanceFailure.unsupportedVersion }
        try envelope.pending?.validate()
        return envelope.pending
    }
    public func stage(_ record: CertificateIssuanceRecord) throws {
        guard record.phase == .prepared else { throw CertificateIssuanceFailure.invalidRecord }
        try replace(expected: nil, with: record)
    }
    public func replace(expected: CertificateIssuanceRecord?, with record: CertificateIssuanceRecord?) throws {
        guard try read() == expected else { throw CertificateIssuanceFailure.staleAttempt }
        try record?.validate()
        let bytes = try JSONEncoder().encode(Envelope(pending: record))
        guard bytes.count <= 65_536 else { throw CertificateIssuanceFailure.invalidRecord }
        try storage.write(bytes)
        guard try storage.read() == bytes else { throw AuthenticationStorageFailure.readbackMismatch }
    }
}

public protocol CertificateIssuanceBackend: Sendable {
    func prepare() throws -> CertificateRequestMaterial
    func validate(_ material: CertificateRequestMaterial) throws
    /// Fetch only from the authenticated owner's Team. A failed or incomplete
    /// fetch is never evidence that a submitted request was not accepted.
    func fetchCertificates() async throws -> [IssuedCertificate]
    func submit(_ record: CertificateIssuanceRecord) async throws -> IssuedCertificate
    func validate(_ certificate: IssuedCertificate, for material: CertificateRequestMaterial) throws
    /// Must round-trip the saved private key from its durable storage.
    func persist(_ certificate: IssuedCertificate, material: CertificateRequestMaterial) throws
}

/// Executes the exact production state machine; the backend is the Apple and
/// cryptography boundary. Caller owns the cross-process native mutation lease.
public struct CertificateIssuanceCoordinator: Sendable {
    public let store: CertificateIssuanceStore
    public init(store: CertificateIssuanceStore) { self.store = store }

    public func issue(owner: CertificateIssuanceOwner, backend: any CertificateIssuanceBackend,
                      allowNew: Bool = true) async throws -> IssuedCertificate? {
        try owner.validate()
        try Task.checkCancellation()
        var record: CertificateIssuanceRecord
        if let pending = try store.read() {
            guard pending.owner == owner else { throw CertificateIssuanceFailure.staleAttempt }
            record = pending
        } else {
            guard allowNew else { return nil }
            let material = try backend.prepare()
            try backend.validate(material)
            record = CertificateIssuanceRecord(owner: owner, material: material)
            // Key and CSR MUST be durable before any remote mutation.
            try store.stage(record)
        }
        try backend.validate(record.material)
        if record.phase == .prepared {
            try Task.checkCancellation()
            var sent = record; sent.phase = .submitted
            try store.replace(expected: record, with: sent)
            record = sent // A crash from here on means query, never create-again.
            let certificate: IssuedCertificate
            do { certificate = try await backend.submit(record) }
            catch let error as CertificateIssuanceFailure where error == .capacityReached || error == .requestRejected {
                // Only an explicit pre-acceptance server rejection may discard
                // the key. Transport, parsing, auth or timeout errors may not.
                try store.replace(expected: record, with: nil)
                throw error
            }
            try backend.validate(certificate, for: record.material)
            guard certificate.publicKey == record.material.publicKey else { throw CertificateIssuanceFailure.keyMismatch }
            var issued = record; issued.phase = .issued; issued.certificate = certificate
            try store.replace(expected: record, with: issued)
            record = issued
        } else if record.phase == .submitted {
            let certificates = try await backend.fetchCertificates()
            guard certificates.count <= 4096 else { throw CertificateIssuanceFailure.invalidRecord }
            let matches = certificates.filter { $0.publicKey == record.material.publicKey }
            guard !matches.isEmpty else { throw CertificateIssuanceFailure.awaitingPortalVisibility }
            guard matches.count == 1 else { throw CertificateIssuanceFailure.ambiguousMatch }
            let certificate = matches[0]
            try backend.validate(certificate, for: record.material)
            var issued = record; issued.phase = .issued; issued.certificate = certificate
            try store.replace(expected: record, with: issued)
            record = issued
        }
        guard let certificate = record.certificate, record.phase == .issued else {
            throw CertificateIssuanceFailure.invalidRecord
        }
        try backend.validate(certificate, for: record.material)
        // Even if cancellation was requested after the server accepted, first
        // preserve the returned key. No cancellation check destroys that chance.
        try backend.persist(certificate, material: record.material)
        try store.replace(expected: record, with: nil)
        return certificate
    }
}
