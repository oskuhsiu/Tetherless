// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import SideSign

/// Foreground-only controls call these helpers, never a background trigger.
/// Recovery saves request-specific material but never selects an active signer.
enum NativeCertificateRecovery {
    static func local(type: CertificateType) throws -> CertificateRecoveryObservation {
        try NativeMutationGate.withSynchronousLease {
            let account = try NativeAuthenticationStore.ready()
            let owner = try owner(account, type: type)
            let value = try CertificateRecoveryCoordinator(store: NativeCertificateIssuance.store(owner: owner)).local(owner: owner)
            try NativeAuthenticationStore.assertCurrent(account)
            return value
        }
    }

    /// No auth-header fetch, network call, active-signer change or certificate
    /// revocation. The common lease and exact request UUID bind confirmation.
    static func discardPrepared(type: CertificateType, expectedID: UUID) throws {
        try NativeMutationGate.withSynchronousLease {
            let account = try NativeAuthenticationStore.ready()
            let owner = try owner(account, type: type)
            try CertificateRecoveryCoordinator(store: NativeCertificateIssuance.store(owner: owner))
                .discardPrepared(owner: owner, expectedID: expectedID)
            try NativeAuthenticationStore.assertCurrent(account)
        }
    }

    /// Portal proxy holds the complete lease, including authentication/session
    /// setup. This method cannot generate, submit or persist request material.
    static func check(type: CertificateType, expectedID: UUID, team: ALTTeam,
                      session: ALTAppleAPISession) async throws -> CertificateRecoveryObservation {
        let (account, owner, backend) = try context(type: type, team: team, session: session)
        let value = try await CertificateRecoveryCoordinator(store: NativeCertificateIssuance.store(owner: owner))
            .check(owner: owner, expectedID: expectedID, backend: backend)
        try NativeAuthenticationStore.assertCurrent(account)
        return value
    }

    static func resolve(type: CertificateType, expectedID: UUID, action: CertificateRecoveryAction,
                        team: ALTTeam, session: ALTAppleAPISession) async throws {
        let (account, owner, backend) = try context(type: type, team: team, session: session)
        _ = try await CertificateRecoveryCoordinator(store: NativeCertificateIssuance.store(owner: owner))
            .resolve(owner: owner, expectedID: expectedID, action: action, backend: backend)
        try NativeAuthenticationStore.assertCurrent(account)
    }

    private static func owner(_ account: AuthenticationRecord, type: CertificateType) throws -> CertificateIssuanceOwner {
        guard let credentials = account.credentials, let teamID = account.teamID,
              CertificateType.allCases.contains(type) else { throw AuthenticationStorageFailure.notReady }
        return try CertificateIssuanceOwner(accountID: credentials.dsid, teamID: teamID, certificateType: type.rawValue)
    }
    private static func context(type: CertificateType, team: ALTTeam, session: ALTAppleAPISession)
        throws -> (AuthenticationRecord, CertificateIssuanceOwner, NativeCertificateIssuanceBackend) {
        let account = try NativeAuthenticationStore.ready()
        let owner = try owner(account, type: type)
        guard owner.accountID == session.dsid, owner.teamID == team.identifier,
              !(team.type == .free && type.isPaidOnly) else { throw AuthenticationStorageFailure.staleAttempt }
        return (account, owner, NativeCertificateIssuanceBackend(account: account, team: team, session: session,
                                                                type: type, machineName: "Tetherless"))
    }
}
