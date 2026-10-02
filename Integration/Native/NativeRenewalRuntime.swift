// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import SideSign
@preconcurrency import UIKit
import Minimuxer

struct NativeRenewalSummary: Codable, Sendable {
    let startedAt: Date
    let finishedAt: Date
    let trigger: RenewalTrigger
    let managerWasForeground: Bool
    let attempted: Int
    let verified: Int
    let unverified: Int
    let deferred: Int
    let failures: [String]
    var message: String {
        if !failures.isEmpty { return "Renewal needs attention: " + failures.joined(separator: ", ") }
        if unverified > 0 { return "Applied, but not fully verified. Check renewal status." }
        if verified > 0 { return "Verified profile renewal for \(verified) app(s)." }
        return "No renewal completed: apps were deferred or are not due."
    }
}

@available(iOS 17.0, tvOS 17.0, *)
actor NativeRenewalRuntime {
    static let shared = NativeRenewalRuntime()
    static let enabledKey = "tetherless.autorenew.enabled"
    private var running = false

    func run(trigger: RenewalTrigger, force: Bool = false) async throws -> NativeRenewalSummary {
        guard !running else { throw RenewalFailure.busy }
        guard trigger == .manual || UserDefaults.standard.bool(forKey: Self.enabledKey) else {
            throw RenewalFailure.needsForeground
        }
        running = true
        defer { running = false }
        let started = Date()
        let foreground = await MainActor.run { UIApplication.shared.applicationState == .active }
        let backend = NativeRenewalBackend(deadline: .now + .seconds(22))
        let journal = try NativeRenewalStorage.journal()
        #if DEBUG
        let interval: TimeInterval = UserDefaults.standard.bool(forKey: "tetherless.test.twoHourCadence") ? 7_200 : 86_400
        #else
        let interval: TimeInterval = 86_400
        #endif
        let engine = RenewalEngine(backend: backend, journal: journal,
                        policy: try RenewalPolicy(interval: interval), acquire: { try NativeRenewalStorage.acquire() })
        do {
            let result = try await engine.run(trigger: trigger, force: force)
            let summary = NativeRenewalSummary(startedAt: started, finishedAt: Date(), trigger: trigger,
                    managerWasForeground: foreground, attempted: result.attempted.count,
                    verified: result.verified.count, unverified: result.appliedUnverified.count,
                    deferred: result.deferred.count,
                    failures: Array(Set(result.failures.values.map(\.rawValue))).sorted())
            try NativeRenewalStorage.write(summary, to: NativeRenewalStorage.root().appendingPathComponent("last-run.json"))
            return summary
        } catch {
            let failure = Self.classify(error)
            let summary = NativeRenewalSummary(startedAt: started, finishedAt: Date(), trigger: trigger,
                    managerWasForeground: foreground, attempted: 0, verified: 0, unverified: 0,
                    deferred: 0, failures: [failure.rawValue])
            try? NativeRenewalStorage.write(summary, to: NativeRenewalStorage.root().appendingPathComponent("last-run.json"))
            throw failure
        }
    }

    /// Explicit preflight AFTER login/pairing repair. Pending work is preserved;
    /// signing identity changes still require the separate full-install workflow.
    func confirmRepair() async throws {
        guard !running else { throw RenewalFailure.busy }
        running = true
        defer { running = false }
        let lease = try NativeRenewalStorage.acquire()
        defer { lease.release() }
        let backend = NativeRenewalBackend(deadline: .now + .seconds(22))
        let apps = try await backend.snapshot()
        let journal = try NativeRenewalStorage.journal()
        var state = try journal.load()
        for app in apps {
            guard var record = state.records[app.bundleID], record.failure != .identityChanged else { continue }
            record.requiresInteraction = false
            record.retryAfter = nil
            record.failure = nil
            state.records[app.bundleID] = record
        }
        try journal.save(state)
    }

    nonisolated static func classify(_ error: Error) -> RenewalFailure {
        if let error = error as? RenewalFailure { return error }
        if error is CancellationError { return .cancelled }
        if let error = error as? ProfileBatchFailure {
            switch error {
            case .identityChanged: return .identityChanged
            case .expiredPlan: return .needsForeground
            case .invalidPlan, .readbackMismatch: return .invalidEvidence
            }
        }
        if let error = error as? DeveloperPortalError {
            switch error {
            case .incorrectCredentials, .appSpecificPasswordRequired, .noTeams,
                 .requiresTwoFactorAuthentication, .incorrectVerificationCode,
                 .authenticationHandshakeFailed, .accountRepairRequired, .invalid2FAResponse:
                return .needsAuthentication
            case .certificateDoesNotExist: return .identityChanged
            case .invalidDeviceID, .appIDDoesNotExist, .maximumAppIDLimitReached,
                 .tooManyCertificates, .invalidProvisioningProfileIdentifier,
                 .provisioningProfileDoesNotExist: return .needsForeground
            case .userCancelled: return .cancelled
            default: return .unavailable
            }
        }
        if let error = error as? MinimuxerError {
            switch error {
            case .invalidPairing, .pairingNotLoaded: return .needsPairing
            default: return .unavailable
            }
        }
        if let error = error as? OperationError {
            switch error {
            case .notAuthenticated: return .needsAuthentication
            case .invalidPairingFile, .pairingNotComplete: return .needsPairing
            default: return .unavailable
            }
        }
        return .unavailable
    }
}
