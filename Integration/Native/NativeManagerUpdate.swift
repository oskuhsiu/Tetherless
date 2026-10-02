// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import CoreData
import SideSign
@preconcurrency import UIKit

/// Normal profile refresh does not call this. Complete manager replacement is
/// foreground-only, same-container/same-Team, and has its own durable receipt.
enum NativeManagerUpdate {
    static func journal() throws -> ManagerUpdateJournal {
        ManagerUpdateJournal(storage: try FileManagerUpdateStorage(root: NativeRenewalStorage.root()))
    }
    static func identity(at url: URL) throws -> ManagerUpdateIdentity {
        guard let app = ALTApplication(fileURL: url), let main = app.provisioningProfile else {
            throw ManagerUpdateFailure.invalidRecord
        }
        var components: [ManagerUpdateComponent] = []
        for item in [app] + app.appExtensions {
            guard let profile = item.provisioningProfile, let executable = item.executableURL,
                  profile.bundleIdentifier == item.bundleIdentifier,
                  profile.teamIdentifier == main.teamIdentifier else {
                throw ManagerUpdateFailure.identityMismatch
            }
            components.append(.init(bundleID: item.bundleIdentifier,
                profileSHA256: NativeRenewalStorage.digest(profile.data),
                executableSHA256: try BundleContentHash.file(executable)))
        }
        let result = ManagerUpdateIdentity(bundleID: app.bundleIdentifier, teamID: main.teamIdentifier,
            version: app.version, build: app.buildVersion, components: components)
        try result.validate()
        return result
    }
    static func isManager(_ context: InstallAppOperationContext, app: ALTApplication) -> Bool {
        context.bundleIdentifier == StoreApp.altstoreAppID ||
        context.targetBundleIdentifier == Bundle.Info.activeBundleIdentifier || app.isAltStoreApp
    }
    /// Executed inside PipelineRunner's existing mutation lease, before it
    /// changes Core Data or dispatches the installer. No private key is exported.
    static func authorize(context: InstallAppOperationContext, app: ALTApplication) async throws {
        guard isManager(context, app: app) else { return }
        #if targetEnvironment(simulator)
        throw ManagerUpdateFailure.requiresForeground
        #else
        let before = try identity(at: Bundle.Info.activeBundleURL)
        let after = try identity(at: app.fileURL)
        guard before.bundleID == after.bundleID, before.teamID == after.teamID,
              try NativeAuthenticationStore.ready().teamID == after.teamID else {
            throw ManagerUpdateFailure.identityMismatch
        }
        if let record = try journal().read(), record.phase.isPending { throw ManagerUpdateFailure.pendingUpdate }
        try await ManagerUpdateConfirmation().request()
        try Task.checkCancellation()
        #endif
    }
    /// Synchronous because its caller is already in a Core Data transaction.
    /// This does not acquire another lock while the pipeline owns the lease.
    static func prepare(app: InstalledApp, resigned: ALTApplication, certificate: ALTCertificate,
                        fingerprint: String, storeBuild: String?) throws {
        let before = try identity(at: Bundle.Info.activeBundleURL)
        let after = try identity(at: resigned.fileURL)
        var extensions: [String: String] = [:]
        for item in app.appExtensions {
            guard extensions.updateValue(item.bundleIdentifier, forKey: item.resignedBundleIdentifier) == nil else {
                throw ManagerUpdateFailure.invalidRecord
            }
        }
        let metadata = ManagerUpdateMetadata(originalBundleID: app.bundleIdentifier, cacheFingerprint: fingerprint,
            certificateSerial: certificate.serialNumber, storeBuild: storeBuild, extensionOriginalIDs: extensions)
        let record = ManagerUpdateRecord(before: before, after: after, metadata: metadata)
        let store = try journal()
        try store.stage(record, running: before)
        try store.beginApplying(id: record.id)
    }
    @discardableResult
    static func reconcile() throws -> Bool {
        let store = try journal()
        guard let pending = try store.read(), pending.phase.isPending else { return false }
        let running = try identity(at: Bundle.Info.activeBundleURL)
        guard let app = ALTApplication(fileURL: Bundle.Info.activeBundleURL), let profile = app.provisioningProfile else {
            throw ManagerUpdateFailure.invalidRecord
        }
        return try store.reconcile(running: running) { record in
            let metadata = record.metadata
            let context = DatabaseManager.shared.persistentContainer.newBackgroundContext()
            try context.performAndWait {
                let request = InstalledApp.fetchRequest()
                request.predicate = NSPredicate(format: "%K == %@", #keyPath(InstalledApp.resignedBundleIdentifier), running.bundleID)
                request.fetchLimit = 2
                let rows = try context.fetch(request)
                guard rows.count == 1, let row = rows.first, row.bundleIdentifier == metadata.originalBundleID else {
                    throw ManagerUpdateFailure.identityMismatch
                }
                row.update(resignedAppBundle: app, certificateSerialNumber: metadata.certificateSerial,
                           storeBuildVersion: metadata.storeBuild)
                // Startup already caches the actually running manager. Preserve
                // that content-derived key rather than trusting an old graph.
                guard let cached = row.appBundleFingerprint, !cached.isEmpty else {
                    throw ManagerUpdateFailure.invalidRecord
                }
                for item in app.appExtensions {
                    guard let original = metadata.extensionOriginalIDs[item.bundleIdentifier],
                          let stored = row.appExtensions.first(where: { $0.resignedBundleIdentifier == item.bundleIdentifier }),
                          stored.bundleIdentifier == original else { throw ManagerUpdateFailure.identityMismatch }
                    stored.update(resignedAppExtensionBundle: item)
                }
                guard row.appExtensions.count == app.appExtensions.count else { throw ManagerUpdateFailure.identityMismatch }
                try context.save()
            }
            // Independently read back the persisted manager, not the dirty
            // managed object. A failure retains the journal for next startup.
            let verify = DatabaseManager.shared.persistentContainer.newBackgroundContext()
            try verify.performAndWait {
                let request = InstalledApp.fetchRequest()
                request.predicate = NSPredicate(format: "%K == %@", #keyPath(InstalledApp.resignedBundleIdentifier), running.bundleID)
                request.fetchLimit = 2
                let rows = try verify.fetch(request)
                guard rows.count == 1, let row = rows.first, row.bundleIdentifier == metadata.originalBundleID,
                      row.version == running.version, row.buildVersion == running.build,
                      row.storeBuildVersion == metadata.storeBuild,
                      row.certificateSerialNumber == metadata.certificateSerial,
                      row.expirationDate == profile.expirationDate,
                      row.appExtensions.count == app.appExtensions.count else { throw ManagerUpdateFailure.storageMismatch }
                for item in app.appExtensions {
                    guard let currentProfile = item.provisioningProfile,
                          let original = metadata.extensionOriginalIDs[item.bundleIdentifier],
                          let saved = row.appExtensions.first(where: { $0.resignedBundleIdentifier == item.bundleIdentifier }),
                          saved.bundleIdentifier == original, saved.version == item.version,
                          saved.expirationDate == currentProfile.expirationDate,
                          saved.refreshedDate == currentProfile.creationDate else {
                        throw ManagerUpdateFailure.storageMismatch
                    }
                }
            }
            // A proven, explicitly authorized replacement supersedes only the
            // old manager's renewal transaction; all other app/account gates stay.
            let renewal = try NativeRenewalStorage.journal()
            var state = try renewal.load()
            var fresh = RenewalRecord(); fresh.lastKnownExpiry = profile.expirationDate
            state.records[running.bundleID] = fresh
            try renewal.save(state)
        }
    }
    @MainActor static func abandonUnapplied() throws {
        guard UIApplication.shared.applicationState == .active else { throw ManagerUpdateFailure.requiresForeground }
        try journal().abandonUnapplied(running: identity(at: Bundle.Info.activeBundleURL))
    }
}

@MainActor
private final class ManagerUpdateConfirmation {
    private var continuation: CheckedContinuation<Void, Error>?
    private var alert: UIAlertController?
    func request() async throws {
        try await withTaskCancellationHandler {
            try Task.checkCancellation()
            guard UIApplication.shared.applicationState == .active,
                  let presenter = UIApplication.shared.topViewController(), !(presenter is UIAlertController) else {
                throw ManagerUpdateFailure.requiresForeground
            }
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                self.continuation = continuation
                let alert = UIAlertController(title: "Update Tetherless?",
                    message: "This replaces the manager itself and may move to the Home Screen. Your account and pairing stay on this device. This is not needed for ordinary daily profile renewal.", preferredStyle: .alert)
                self.alert = alert
                alert.addAction(UIAlertAction(title: "Cancel", style: .cancel) { [weak self] _ in self?.finish(.failure(CancellationError())) })
                alert.addAction(UIAlertAction(title: "Update", style: .default) { [weak self] _ in self?.finish(.success(())) })
                if Task.isCancelled { finish(.failure(CancellationError())); return }
                presenter.present(alert, animated: true)
            }
        } onCancel: {
            Task { @MainActor in self.finish(.failure(CancellationError())) }
        }
    }
    private func finish(_ result: Result<Void, Error>) {
        guard let continuation else { return }
        self.continuation = nil
        alert?.dismiss(animated: true); alert = nil
        continuation.resume(with: result)
    }
}
