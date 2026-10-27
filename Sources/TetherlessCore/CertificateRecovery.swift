// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// This capability deliberately has no prepare, submit or persist operation.
/// A check cannot create a certificate or change locally selected signing keys.
public protocol CertificateIssuanceLookup: Sendable {
    func validate(_ material: CertificateRequestMaterial) throws
    func fetchCertificates() async throws -> [IssuedCertificate]
    func validate(_ certificate: IssuedCertificate, for material: CertificateRequestMaterial) throws
}

/// Safe UI metadata only: no account, certificate, CSR or private-key bytes.
public struct CertificateRecoveryObservation: Equatable, Sendable {
    public enum State: String, Sendable {
        case none, prepared, submitted, awaitingPortal, available, issued
    }
    public let requestID: UUID?
    public let state: State
    public var canSubmit: Bool { state == .prepared }
    public var canDiscard: Bool { state == .prepared }
    public var canSave: Bool { state == .available || state == .issued }
}

public enum CertificateRecoveryAction: Sendable {
    case saveExisting, submitPrepared, discardPrepared
}

/// Caller must hold the same mutation lease used by issuance, login and logout.
/// Checking is read-only, including the journal; explicit resolution is separate.
public struct CertificateRecoveryCoordinator: Sendable {
    public let store: CertificateIssuanceStore
    public init(store: CertificateIssuanceStore) { self.store = store }

    public func local(owner: CertificateIssuanceOwner) throws -> CertificateRecoveryObservation {
        guard let record = try read(owner: owner) else { return .init(requestID: nil, state: .none) }
        let state: CertificateRecoveryObservation.State
        switch record.phase {
        case .prepared: state = .prepared
        case .submitted: state = .submitted
        case .issued: state = .issued
        }
        return .init(requestID: record.id, state: state)
    }

    public func check(owner: CertificateIssuanceOwner, expectedID: UUID,
                      backend: any CertificateIssuanceLookup) async throws -> CertificateRecoveryObservation {
        try Task.checkCancellation()
        let record = try require(owner: owner, expectedID: expectedID)
        try backend.validate(record.material)
        let state: CertificateRecoveryObservation.State
        switch record.phase {
        case .prepared:
            state = .prepared // No request was sent; do not send one to "check".
        case .issued:
            guard let certificate = record.certificate else { throw CertificateIssuanceFailure.invalidRecord }
            try backend.validate(certificate, for: record.material)
            state = .issued // Locally saved response; not a fresh portal observation.
        case .submitted:
            let certificates = try await backend.fetchCertificates()
            guard certificates.count <= 4096 else { throw CertificateIssuanceFailure.invalidRecord }
            let matches = certificates.filter { $0.publicKey == record.material.publicKey }
            guard matches.count <= 1 else { throw CertificateIssuanceFailure.ambiguousMatch }
            if let certificate = matches.first {
                try certificate.validate()
                try backend.validate(certificate, for: record.material)
                state = .available
            } else {
                state = .awaitingPortal // Absence is NOT permission to resubmit or erase the key.
            }
        }
        try Task.checkCancellation()
        guard try store.read() == record else { throw CertificateIssuanceFailure.staleAttempt }
        return .init(requestID: record.id, state: state)
    }

    /// Local-only discard is restricted to a request provably never dispatched.
    /// A possibly accepted request's key cannot be discarded, even after repeated
    /// empty portal lookups. No time-based abandonment or silent revocation.
    public func discardPrepared(owner: CertificateIssuanceOwner, expectedID: UUID) throws {
        try Task.checkCancellation()
        let record = try require(owner: owner, expectedID: expectedID)
        guard record.phase == .prepared else { throw CertificateIssuanceFailure.staleAttempt }
        try store.replace(expected: record, with: nil)
    }

    public func resolve(owner: CertificateIssuanceOwner, expectedID: UUID,
                        action: CertificateRecoveryAction,
                        backend: any CertificateIssuanceBackend) async throws -> IssuedCertificate? {
        try Task.checkCancellation()
        let record = try require(owner: owner, expectedID: expectedID)
        switch action {
        case .discardPrepared:
            try discardPrepared(owner: owner, expectedID: expectedID)
            return nil
        case .submitPrepared:
            guard record.phase == .prepared else { throw CertificateIssuanceFailure.staleAttempt }
        case .saveExisting:
            guard record.phase != .prepared else { throw CertificateIssuanceFailure.staleAttempt }
        }
        // The exact request was checked under the caller's lease. The issuing
        // coordinator re-reads it and uses its existing durable key/CSR only.
        return try await CertificateIssuanceCoordinator(store: store)
            .issue(owner: owner, backend: backend, allowNew: false)
    }

    private func read(owner: CertificateIssuanceOwner) throws -> CertificateIssuanceRecord? {
        try owner.validate()
        let record = try store.read()
        guard record == nil || record?.owner == owner else { throw CertificateIssuanceFailure.staleAttempt }
        return record
    }
    private func require(owner: CertificateIssuanceOwner, expectedID: UUID) throws -> CertificateIssuanceRecord {
        guard let record = try read(owner: owner), record.id == expectedID else {
            throw CertificateIssuanceFailure.staleAttempt
        }
        return record
    }
}
