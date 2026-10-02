//
//  CertificateProvisioningFlow.swift
//  SideStore
//
//  Created by Magesh K on 13/09/26.
//  Copyright © 2026 SideStore. All rights reserved.
//
// Tetherless: checked local persistence and explicit quota decisions.
@preconcurrency import UIKit
import Foundation
import SideSign

protocol CertificateProvisioningHandler: AnyObject, Sendable {
    func resolveRevocation(certificates: [ALTX509Certificate], teamType: ALTTeamType) async throws -> RevokeDecision
    func resolveProvisioningError(_ error: Error) async -> ProvisioningErrorDecision
}

final class CertificateProvisioningFlow: @unchecked Sendable {
    weak var handler: CertificateProvisioningHandler?
    let skipCertificateProvisioning: Bool
    private(set) var portalCertificates: [ALTX509Certificate]?
    init(handler: CertificateProvisioningHandler? = nil, skipCertificateProvisioning: Bool = false) {
        self.handler = handler; self.skipCertificateProvisioning = skipCertificateProvisioning
    }
    func resolveCertificate(for team: ALTTeam) async throws -> ALTCertificate? {
        while true {
            try Task.checkCancellation()
            do {
                return try await NativeMutationGate.withLease {
                    if self.skipCertificateProvisioning {
                        // Explicit advanced skip is not evidence of a usable signer.
                        return try CertificateManager.shared.loadActiveCertificate()?.certificate
                    }
                    let certificate = try await self.fetchCertificate(for: team)
                    try CertificateManager.shared.setActiveCertificate(certificate)
                    return certificate
                }
            } catch {
                // Never offer "skip" or immediate create-again for a storage failure.
                if error is AuthenticationStorageFailure || error is CancellationError || error is PrivateFileError {
                    throw error
                }
                guard let handler else { throw error }
                switch await handler.resolveProvisioningError(error) {
                case .retry: continue
                case .skip: return nil // Caller explicitly acknowledges incomplete setup.
                case .cancel: throw CancellationError()
                }
            }
        }
    }
    func fetchPortalCertificates(for team: ALTTeam) async throws -> [ALTX509Certificate] {
        if let cached = portalCertificates { return cached }
        let fetched = try await DeveloperPortalProxy.shared.fetchCertificates(team: team)
        portalCertificates = fetched
        return fetched
    }
    private func matches(_ local: ALTCertificate, _ remote: ALTX509Certificate) -> Bool {
        local.serialNumber.caseInsensitiveCompare(remote.serialNumber) == .orderedSame &&
        local.data == remote.data && !local.privateKey.isEmpty && remote.expiryDate > Date()
    }
    private func fetchCertificate(for team: ALTTeam) async throws -> ALTCertificate {
        // Check storage BEFORE a remote create decision. Missing is different
        // from inaccessible/corrupt Keychain. Only current-Team portal matches count.
        let active = try CertificateManager.shared.loadActiveCertificate()
        let fetched = try await DeveloperPortalProxy.shared.fetchCertificates(team: team)
        portalCertificates = fetched
        if let active, let remote = fetched.first(where: { matches(active.certificate, $0) }) {
            return ALTCertificate(x509: remote, privateKey: active.certificate.privateKey)
        }
        let mainSerial = Bundle.main.object(forInfoDictionaryKey: Bundle.Info.certificateID) as? String
        let candidates = fetched.filter { $0.expiryDate > Date() }.sorted { left, right in
            let isLeft = mainSerial?.caseInsensitiveCompare(left.serialNumber) == .orderedSame
            let isRight = mainSerial?.caseInsensitiveCompare(right.serialNumber) == .orderedSame
            if isLeft != isRight { return isLeft }
            return left.serialNumber < right.serialNumber
        }
        for remote in candidates {
            if let local = try CertificateManager.shared.getLocalCertificateVerified(serialNumber: remote.serialNumber),
               matches(local, remote) {
                return ALTCertificate(x509: remote, privateKey: local.privateKey)
            }
        }
        // Existing certificates do not prove the quota is full. Try creation
        // without revocation first, then ask only upon Apple's actual limit error.
        do { return try await requestCertificate(for: team) }
        catch let error as DeveloperPortalError {
            guard case .tooManyCertificates = error else { throw error }
            guard let handler else { throw error }
            let current = try await DeveloperPortalProxy.shared.fetchCertificates(team: team)
            portalCertificates = current
            let decision = try await handler.resolveRevocation(certificates: current, teamType: team.type)
            try Task.checkCancellation()
            switch decision {
            case .keepExisting: throw error
            case .revokeSelected(let selected):
                guard !selected.isEmpty, selected.count <= current.count,
                      Set(selected.map { $0.serialNumber.lowercased() }).count == selected.count else {
                    throw AuthenticationStorageFailure.invalidRecord
                }
                // Confirmation refers to the exact public certificate, not just a
                // stale identifier captured under a different account/Team.
                for cert in selected {
                    guard current.contains(where: {
                        $0.serialNumber.caseInsensitiveCompare(cert.serialNumber) == .orderedSame && $0.data == cert.data
                    }) else { throw AuthenticationStorageFailure.staleAttempt }
                }
                for cert in selected {
                    try Task.checkCancellation()
                    guard try await DeveloperPortalProxy.shared.revokeCertificate(cert, team: team) else {
                        throw AuthenticationStorageFailure.unavailable
                    }
                }
                portalCertificates = current.filter { item in !selected.contains {
                    $0.serialNumber.caseInsensitiveCompare(item.serialNumber) == .orderedSame
                } }
                return try await requestCertificate(for: team)
            }
        }
    }
    private func requestCertificate(for team: ALTTeam) async throws -> ALTCertificate {
        // The proxy saves and reads back the returned private key before return.
        // No additional fetch can throw away the only available returned key.
        let cert = try await DeveloperPortalProxy.shared.createCertificate(machineName: "Tetherless", team: team)
        var current = portalCertificates ?? []
        current.removeAll { $0.serialNumber.caseInsensitiveCompare(cert.serialNumber) == .orderedSame }
        current.append(cert.x509)
        portalCertificates = current
        return cert
    }
}
