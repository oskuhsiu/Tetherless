// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import CoreData
import SideSign
import Minimuxer
@preconcurrency import UIKit

/// The manager identity is read from its running Mach-O; other app identities
/// come from successful-install metadata. External replacement requires
/// reenrollment. Profile-store readback is not proof of kernel launch behavior.
@available(iOS 17.0, tvOS 17.0, *)
final class NativeRenewalBackend: RenewalBackend, @unchecked Sendable {
    private struct Descriptor {
        let bundleID: String
        let originalID: String
        let isManager: Bool
        let teamID: String
        let certificateDER: Data
        let certificateExpiry: Date
        let templates: [String: ALTProvisioningProfile]
        let identityDigest: String
        var components: Set<String> { Set(templates.keys) }
    }
    private let transport: NativeProfileTransport
    private var descriptors: [String: Descriptor] = [:]
    private var deviceID = ""
    private var team: ALTTeam?
    private var appIDs: [ALTAppID] = []

    init(deadline: ContinuousClock.Instant) {
        transport = NativeProfileTransport(deadline: deadline)
    }

    func snapshot() async throws -> [AppLease] {
        do { return try await snapshotImpl() }
        catch { throw NativeRenewalRuntime.classify(error) }
    }
    func refresh(_ app: AppLease) async throws -> RenewalEvidence {
        do { return try await refreshImpl(app) }
        catch { throw NativeRenewalRuntime.classify(error) }
    }
    func reconcile(_ pending: PendingRenewal) async throws -> RenewalEvidence? {
        do { return try await reconcileImpl(pending) }
        catch { throw NativeRenewalRuntime.classify(error) }
    }

    private func snapshotImpl() async throws -> [AppLease] {
        try transport.checkBudget()
        #if targetEnvironment(simulator)
        throw RenewalFailure.unavailable
        #else
        try await DatabaseManager.shared.start()
        guard AuthManager.shared.isAuthenticated else { throw RenewalFailure.needsAuthentication }
        guard UserDefaults.standard.useOnDeviceAnisette,
              !CellularRefreshManager.shared.isEnabled else { throw RenewalFailure.needsForeground }
        guard await MainActor.run(body: { ConnectionConfig.shared.useLocalVPN }) else {
            throw RenewalFailure.needsForeground
        }
        guard let pairing = PairingFileManager.shared.fetchPairingFile() else {
            throw RenewalFailure.needsPairing
        }
        syncMinimuxerBackendFromUserDefaults()
        minimuxer.core.setLogging(false)
        if UserDefaults.standard.enableEMPforWireguard { try await startEMProxy() }
        try await minimuxerStart(pairing, preferred: PairingFileManager.shared.preferredProtocol)
        try await ensureMinimuxerReady()
        deviceID = try await minimuxer.core.fetchUDID()
        guard !deviceID.isEmpty else { throw RenewalFailure.invalidEvidence }
        try transport.checkBudget()
        let selectedTeam = try await AuthManager.shared.getAuthenticatedTeam()
        team = selectedTeam
        let certificates = try await ALTAppleAPI.shared.fetchCertificates(for: selectedTeam, session: appleSession())
        appIDs = try await ALTAppleAPI.shared.fetchAppIDs(for: selectedTeam, session: appleSession())
        try transport.checkBudget()
        let context = DatabaseManager.shared.persistentContainer.newBackgroundContext()
        let localDeviceID = deviceID
        let values: [Descriptor] = try await context.perform {
            let apps = InstalledApp.fetchAppsForRefreshingAll(in: context)
            return try apps.map { app in
                let isManager = app.bundleIdentifier == StoreApp.altstoreAppID
                let bundleID = app.resignedBundleIdentifier
                guard ManagedBundleIdentifier.isSafe(bundleID),
                      app.appExtensions.allSatisfy({ ManagedBundleIdentifier.isSafe($0.resignedBundleIdentifier) }) else {
                    throw RenewalFailure.invalidEvidence
                }
                guard let certificate = CertificateManager.shared.getSigningCertificate(for: app),
                      let certificateDER = certificate.data,
                      certificates.contains(where: { $0.data == certificateDER }),
                      certificate.creationDate <= Date(), certificate.expiryDate > Date() else { throw RenewalFailure.identityChanged }
                var templates: [String: ALTProvisioningProfile] = [:]
                if isManager {
                    guard let running = ALTApplication(fileURL: Bundle.Info.activeBundleURL),
                          running.bundleIdentifier == bundleID else { throw RenewalFailure.invalidEvidence }
                    for component in running.allAppBundles {
                        guard let profile = component.provisioningProfile,
                              let leaf = CertificateManager.shared.getSigningCertificate(at: component.fileURL),
                              leaf.data == certificateDER else { throw RenewalFailure.needsForeground }
                        templates[component.bundleIdentifier] = profile
                    }
                } else {
                    // Shared/wildcard authorization needs its own enrollment model.
                    guard !app.useMainProfile else { throw RenewalFailure.needsForeground }
                    let required = [bundleID] + app.appExtensions.map(\.resignedBundleIdentifier)
                    for id in required {
                        let url = app.directoryURL.appendingPathComponent("ProvisioningProfiles")
                            .appendingPathComponent("\(id).mobileprovision")
                        guard let data = try NativeRenewalStorage.read(url, maximum: 1_048_576) else {
                            throw RenewalFailure.needsForeground
                        }
                        templates[id] = try ALTProvisioningProfile(data: data)
                    }
                }
                guard templates[bundleID] != nil, templates.count <= 32 else {
                    throw RenewalFailure.invalidEvidence
                }
                for (id, template) in templates {
                    guard template.bundleIdentifier == id,
                          template.teamIdentifier == selectedTeam.identifier,
                          template.deviceIDs.contains(localDeviceID),
                          template.certificates.contains(where: { $0.data == certificateDER }) else {
                        throw RenewalFailure.identityChanged
                    }
                }
                let identity: [String: Any] = [
                    "bundle": bundleID, "version": app.version, "build": app.buildVersion,
                    "team": selectedTeam.identifier,
                    "device": NativeRenewalStorage.digest(Data(localDeviceID.utf8)),
                    "certificate": NativeRenewalStorage.digest(certificateDER),
                    "components": try templates.keys.sorted().map { id -> [String: String] in
                        guard let profile = templates[id] else { throw RenewalFailure.invalidEvidence }
                        return ["id": id, "entitlements": NativeRenewalStorage.digest(try Self.entitlementBytes(profile))]
                    }
                ]
                let digest = NativeRenewalStorage.digest(try JSONSerialization.data(withJSONObject: identity, options: [.sortedKeys]))
                return Descriptor(bundleID: bundleID, originalID: app.bundleIdentifier, isManager: isManager,
                                  teamID: selectedTeam.identifier, certificateDER: certificateDER,
                                  certificateExpiry: certificate.expiryDate, templates: templates, identityDigest: digest)
            }
        }
        guard values.filter(\.isManager).count == 1,
              Set(values.map(\.bundleID)).count == values.count else { throw RenewalFailure.invalidEvidence }
        descriptors = Dictionary(uniqueKeysWithValues: values.map { ($0.bundleID, $0) })
        let installed = try await transport.readInstalledProfileBytes()
        return try values.map {
            try AppLease(bundleID: $0.bundleID, isManager: $0.isManager,
                         effectiveExpiry: effectiveExpiry(of: $0, in: installed))
        }
        #endif
    }

    private func refreshImpl(_ app: AppLease) async throws -> RenewalEvidence {
        guard let descriptor = descriptors[app.bundleID], let team else { throw RenewalFailure.invalidEvidence }
        try transport.checkBudget()
        let current = try effectiveExpiry(of: descriptor, in: await transport.readInstalledProfileBytes())
        if current > app.effectiveExpiry {
            return try await commitReadback(app, descriptor: descriptor, expiry: current,
                                            installed: await transport.readInstalledProfileBytes())
        }
        guard current == app.effectiveExpiry else { throw RenewalFailure.invalidEvidence }
        var parts: [ProfileBatchPart] = []
        for id in descriptor.components.sorted() {
            try transport.checkBudget()
            guard let appID = appIDs.first(where: { $0.bundleIdentifier == id }) else {
                throw RenewalFailure.needsForeground
            }
            let received = try await ALTAppleAPI.shared.downloadProvisioningProfile(for: appID,
                    isTeamProfile: true, deviceType: DeveloperPortalProxy.currentDeviceType,
                    team: team, session: appleSession())
            let profile = try ALTProvisioningProfile(data: received.data)
            try validate(profile, componentID: id, descriptor: descriptor, requireFuture: true)
            parts.append(ProfileBatchPart(componentID: id, profileID: profile.uuid.uuidString,
                                          bytes: profile.data, expiry: profile.expirationDate))
        }
        let batch = ProfileBatch(bundleID: app.bundleID, identityDigest: descriptor.identityDigest,
                                 previousExpiry: app.effectiveExpiry,
                                 certificateExpiry: descriptor.certificateExpiry, parts: parts)
        do { try batch.validate(requiredComponents: descriptor.components, identityDigest: descriptor.identityDigest, now: Date()) }
        catch ProfileBatchFailure.expiredPlan { throw RenewalFailure.noExtension }
        try NativeRenewalStorage.saveBatch(batch)
        return try await complete(batch, app: app, descriptor: descriptor)
    }

    private func reconcileImpl(_ pending: PendingRenewal) async throws -> RenewalEvidence? {
        guard let descriptor = descriptors[pending.app.bundleID] else { throw RenewalFailure.identityChanged }
        let installed = try await transport.readInstalledProfileBytes()
        let current = try effectiveExpiry(of: descriptor, in: installed)
        if let batch = try NativeRenewalStorage.loadBatch(for: pending.app.bundleID),
           batch.previousExpiry == pending.app.effectiveExpiry {
            guard batch.bundleID == descriptor.bundleID, batch.identityDigest == descriptor.identityDigest else {
                throw RenewalFailure.identityChanged
            }
            // Re-parse persisted payloads; JSON metadata alone is not evidence.
            for part in batch.parts {
                let profile = try ALTProvisioningProfile(data: part.bytes)
                guard part.profileID == profile.uuid.uuidString, part.expiry == profile.expirationDate else {
                    throw RenewalFailure.invalidEvidence
                }
                try validate(profile, componentID: part.componentID, descriptor: descriptor, requireFuture: true)
            }
            return try await complete(batch, app: pending.app, descriptor: descriptor)
        }
        if current > pending.app.effectiveExpiry {
            return try await commitReadback(pending.app, descriptor: descriptor, expiry: current, installed: installed)
        }
        guard current == pending.app.effectiveExpiry else { throw RenewalFailure.invalidEvidence }
        return nil
    }

    private func complete(_ batch: ProfileBatch, app: AppLease, descriptor: Descriptor) async throws -> RenewalEvidence {
        do {
            _ = try await ProfileBatchExecutor.applyMissing(batch, requiredComponents: descriptor.components,
                    identityDigest: descriptor.identityDigest, transport: transport)
        } catch ProfileBatchFailure.identityChanged { throw RenewalFailure.identityChanged }
          catch ProfileBatchFailure.expiredPlan { throw RenewalFailure.needsForeground }
          catch let error as ProfileBatchFailure { throw error }
        let installed = try await transport.readInstalledProfileBytes()
        let expiry = try effectiveExpiry(of: descriptor, in: installed)
        guard expiry >= batch.newExpiry else { throw RenewalFailure.invalidEvidence }
        return try await commitReadback(app, descriptor: descriptor, expiry: expiry, installed: installed)
    }

    private func validate(_ profile: ALTProvisioningProfile, componentID: String,
                          descriptor: Descriptor, requireFuture: Bool) throws {
        guard let template = descriptor.templates[componentID],
              profile.bundleIdentifier == componentID,
              profile.teamIdentifier == descriptor.teamID,
              profile.deviceIDs.contains(deviceID),
              profile.certificates.contains(where: { $0.data == descriptor.certificateDER }),
              profile.creationDate.timeIntervalSince1970.isFinite,
              profile.expirationDate.timeIntervalSince1970.isFinite,
              profile.creationDate <= Date(), profile.expirationDate > profile.creationDate else {
            throw RenewalFailure.invalidEvidence
        }
        guard try Self.entitlementBytes(profile) == Self.entitlementBytes(template) else {
            throw RenewalFailure.needsForeground
        }
        if requireFuture && profile.expirationDate <= Date() { throw RenewalFailure.noExtension }
    }

    private func appleSession() async throws -> ALTAppleAPISession {
        try transport.checkBudget()
        guard let dsid = Keychain.shared.appleIDAdsid, !dsid.isEmpty,
              let token = Keychain.shared.appleIDXcodeToken, !token.isEmpty else {
            throw RenewalFailure.needsAuthentication
        }
        // Explicit local provider; a settings change cannot select remote fallback.
        let anisette = try await OnDeviceAnisetteManager.shared.fetchAnisetteData()
        let version = await AnisetteConfigManager.shared.resolvedXcodeVersion()
        try transport.checkBudget()
        return ALTAppleAPISession(dsid: dsid, authToken: token, anisetteData: anisette, xcodeVersion: version)
    }

    private static func entitlementBytes(_ profile: ALTProvisioningProfile) throws -> Data {
        let entitlements = profile.entitlements
        guard !entitlements.isEmpty, JSONSerialization.isValidJSONObject(entitlements) else {
            throw RenewalFailure.invalidEvidence
        }
        return try JSONSerialization.data(withJSONObject: entitlements, options: [.sortedKeys])
    }

    private func selectedProfiles(of descriptor: Descriptor, in bytes: [Data]) throws -> [String: ALTProvisioningProfile] {
        var profiles: [String: ALTProvisioningProfile] = [:]
        var uuidBytes: [UUID: Data] = [:]
        for data in bytes {
            guard let profile = try? ALTProvisioningProfile(data: data),
                  descriptor.components.contains(profile.bundleIdentifier) else { continue }
            if let previous = uuidBytes[profile.uuid], previous != data { throw RenewalFailure.invalidEvidence }
            uuidBytes[profile.uuid] = data
            guard (try? validate(profile, componentID: profile.bundleIdentifier,
                                 descriptor: descriptor, requireFuture: false)) != nil else { continue }
            if profiles[profile.bundleIdentifier].map({ $0.expirationDate >= profile.expirationDate }) != true {
                profiles[profile.bundleIdentifier] = profile
            }
        }
        guard Set(profiles.keys) == descriptor.components else { throw RenewalFailure.invalidEvidence }
        return profiles
    }

    private func effectiveExpiry(of descriptor: Descriptor, in bytes: [Data]) throws -> Date {
        try selectedProfiles(of: descriptor, in: bytes).values.map(\.expirationDate)
            .reduce(descriptor.certificateExpiry, min)
    }

    private func commitReadback(_ app: AppLease, descriptor: Descriptor, expiry: Date,
                                installed: [Data]) async throws -> RenewalEvidence {
        guard try effectiveExpiry(of: descriptor, in: installed) == expiry else {
            throw RenewalFailure.invalidEvidence
        }
        let evidence = RenewalEvidence(bundleID: app.bundleID, previousExpiry: app.effectiveExpiry,
                                       newExpiry: expiry, level: .deviceReadback, sameSigningIdentity: true)
        try evidence.validate(for: app, now: Date())
        let profiles = try selectedProfiles(of: descriptor, in: installed)
        let context = DatabaseManager.shared.persistentContainer.newBackgroundContext()
        do {
            try await context.perform {
                guard let record = InstalledApp.fetchAppsForRefreshingAll(in: context)
                    .first(where: { $0.resignedBundleIdentifier == descriptor.bundleID }),
                      record.bundleIdentifier == descriptor.originalID,
                      let main = profiles[descriptor.bundleID] else { throw RenewalFailure.invalidEvidence }
                record.update(provisioningProfile: main)
                record.expirationDate = expiry
                for item in record.appExtensions {
                    guard let profile = profiles[item.resignedBundleIdentifier] else { throw RenewalFailure.invalidEvidence }
                    item.update(provisioningProfile: profile)
                }
                try context.save()
            }
        } catch let error as RenewalFailure { throw error }
          catch { throw RenewalFailure.storageUnavailable }
        // Retain the batch for crash reconciliation until a later attempt replaces it.
        return evidence
    }
}
