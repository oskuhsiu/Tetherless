// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import SideSign
@preconcurrency import UIKit
import Minimuxer

@available(iOS 17.0, tvOS 17.0, *)
actor NativeRenewalRuntime {
    static let shared = NativeRenewalRuntime()
    static let enabledKey = "tetherless.autorenew.enabled"
    private var running = false

    func run(trigger: RenewalTrigger, force: Bool = false) async throws -> RenewalSummary {
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
            let summary = RenewalSummary(startedAt: started, finishedAt: Date(), trigger: trigger,
                managerWasForeground: foreground, result: result)
            try await saveEvidence(summary)
            return summary
        } catch {
            let failure = Self.classify(error)
            var result = RenewalRunResult()
            result.globalFailure = failure
            let summary = RenewalSummary(startedAt: started, finishedAt: Date(), trigger: trigger,
                managerWasForeground: foreground, result: result)
            try? await saveEvidence(summary)
            throw failure
        }
    }

    private func saveEvidence(_ summary: RenewalSummary) async throws {
        // Runtime actor serializes writers. The engine has already released its
        // mutation lock; notifications never keep the device channel locked.
        let timeline = try NativeRenewalStorage.record(summary)
        #if os(iOS)
        await NativeRenewalNotifications.update(timeline: timeline)
        #endif
    }

    /// Explicit user acknowledgement AFTER a successful foreground reinstall.
    /// No profile, certificate or app is deleted here. Only obsolete recovery
    /// metadata is retired after a new live snapshot validates the replacement.
    func reEnrollRepairedApps() async throws {
        guard !running else { throw RenewalFailure.busy }
        running = true
        defer { running = false }
        let lease = try NativeRenewalStorage.acquire()
        defer { lease.release() }
        let snapshot = try await NativeRenewalBackend(deadline: .now + .seconds(22)).snapshot()
        try snapshot.validate()
        let journal = try NativeRenewalStorage.journal()
        var state = try journal.load()
        var repaired = 0
        for app in snapshot.apps {
            guard let record = state.records[app.bundleID], record.failure == .identityChanged else { continue }
            // Same-identity pending work still requires reconciliation; it is
            // never silently discarded by a generic repair button.
            if let pending = record.pending, pending.app.identityDigest == app.identityDigest { continue }
            var replacement = RenewalRecord()
            replacement.lastKnownExpiry = app.effectiveExpiry
            state.records[app.bundleID] = replacement
            repaired += 1
        }
        guard repaired > 0 else { throw RenewalFailure.needsForeground }
        try journal.save(state)
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
        let snapshot = try await backend.snapshot()
        try snapshot.validate()
        let apps = snapshot.apps
        guard !apps.isEmpty else { throw RenewalFailure.needsForeground }
        let journal = try NativeRenewalStorage.journal()
        var state = try journal.load()
        state.gate = nil // Live authentication/pairing preflight succeeded.
        for (id, var record) in state.records where [.needsAuthentication, .needsPairing].contains(record.failure) {
            record.requiresInteraction = false
            record.retryAfter = nil
            record.failure = nil
            state.records[id] = record
        }
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
