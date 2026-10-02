#!/usr/bin/env python3
"""Checked self-update recovery over the exact prepared native source."""
from pathlib import Path
import hashlib
import sys

INSTALL = 'SideStore/Core/Operations/PipelineOperations/InstallAppOperation.swift'
APP = 'AltStore/AppDelegate.swift'
FINGERPRINT = 'SideStore/Utils/common/AppBundleFingerprint.swift'
VALIDATE = 'SideStore/Core/Auth/Flows/CodeSignValidationFlow.swift'

def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Manager-update anchor changed: ' + old[:70])
    return source.replace(old, new, 1)

def replace_span(source, start, end, replacement):
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError('Manager-update boundaries changed')
    before, tail = source.split(start)
    _, after = tail.split(end)
    return before + replacement + end + after

def patch_install(source):
    source = once(source, '        @Managed var appVersion = context.appVersion', '''        try await NativeManagerUpdate.authorize(context: context, app: resignedAppBundle)
        try Task.checkCancellation()
        @Managed var appVersion = context.appVersion''')
    source = replace_span(source,
        '            // This preserves our data in a serilized format',
        '            return (installedApp, isDifferentSideStore, self.context.targetBundleIdentifier, isSelfReinstall, false)',
        '''            let isSelfReinstall = NativeManagerUpdate.isManager(self.context, app: resignedAppBundle)
            if isSelfReinstall {
                guard !isDifferentSideStore, let fingerprint = self.context.appBundleFingerprint else {
                    throw ManagerUpdateFailure.identityMismatch
                }
                try NativeManagerUpdate.prepare(app: installedApp, resigned: resignedAppBundle,
                    certificate: certificate, fingerprint: fingerprint, storeBuild: storeBuildVersion)
            }

''')
    source = once(source, "            if isSideBackup {", """            if isSideBackup {
                guard !NativeManagerUpdate.isManager(self.context, app: resignedAppBundle) else {
                    throw ManagerUpdateFailure.invalidRecord
                }""")
    source = once(source, '''        if isSelfReinstall {
            self.handleSelfReinstallation(for: installedApp)
        }''', '''        let suspension = isSelfReinstall ? self.handleSelfReinstallation(for: installedApp) : nil
        defer { suspension?.cancel() }
        try Task.checkCancellation()''')
    start = '    private func handleSelfReinstallation(for installedApp: InstalledApp) {'
    if source.count(start) != 1: raise ValueError('Self-suspension boundary changed')
    return source.split(start)[0] + '''    private func handleSelfReinstallation(for installedApp: InstalledApp) -> Task<Void, Never> {
        BackgroundServiceManager.stop()
        return Task {
            // If the installation fails/returns, its defer cancels this timer.
            // Never suspend a later unrelated screen after an old failed attempt.
            do { try await Task.sleep(nanoseconds: AppConstants.Installation.selfInstallSuspendDelayNs) }
            catch { return }
            guard !Task.isCancelled else { return }
            let handler = self.context.handler.installAppHandler
            guard await handler.isAppInForeground(), !Task.isCancelled else { return }
            await self.suspendToHomeScreen()
        }
    }
}
'''

def patch_app(source):
    return replace_span(source,
        '    static func reconcileSelfReinstallationIfNeeded() {',
        '\nextension AppDelegate: UNUserNotificationCenterDelegate {',
        '''    static func reconcileSelfReinstallationIfNeeded() async {
        do {
            try await NativeMutationGate.withLease { _ = try NativeManagerUpdate.reconcile() }
            UserDefaults.standard.removeObject(forKey: "tetherless.managerUpdate.recoveryFailed")
        } catch {
            // Retain the record; the foreground recovery screen can retry it.
            // No arbitrary staged Core Data graph or bundle-path heuristic.
            UserDefaults.standard.set(true, forKey: "tetherless.managerUpdate.recoveryFailed")
        }
    }
}
''')

def patch_fingerprint(source):
    marker = 'public enum AppBundleFingerprint {'
    if source.count(marker) != 1: raise ValueError('Fingerprint boundary changed')
    return source.split(marker)[0] + '''public enum AppBundleFingerprint {
    public static func compute(for bundleURL: URL) -> String? {
        try? BundleContentHash.bundle(bundleURL)
    }
}
'''

def patch_validation(source):
    source = once(source, '''            verboseLog("[CodeSignValidationFlow] Application bundle or provisioning profile nil, returning false")
            return false''', '''            throw ManagerUpdateFailure.invalidRecord''')
    start = '            if team.type != .free && (reason == .privateKeyLost || reason == .externalSigner) {'
    end = '            guard let handler = self.handler else {'
    source = replace_span(source, start, end, '')
    source = once(source, '''                debugLog("[CodeSignValidationFlow] No handler available to resolve resign.")
                return false''', '''                throw ManagerUpdateFailure.requiresForeground''')
    source = once(source, "return try await handler.resolveResign(mismatchReason: reason, context: operationContext)",
                  "guard try await handler.resolveResign(mismatchReason: reason, context: operationContext) else { throw CancellationError() }\n                return true")
    return once(source, '''                verboseLog("[CodeSignValidationFlow] Error occurred when handling resolveResign: \\(error)")
                return false''', '''                throw error''')

PATCHES = {INSTALL: patch_install, APP: patch_app, FINGERPRINT: patch_fingerprint, VALIDATE: patch_validation}
BLOBS = {'SideStore/Core/Operations/PipelineOperations/InstallAppOperation.swift': 'cf721ec87c065669a9c89f82eef30c9bc70a3115', 'AltStore/AppDelegate.swift': '3c94f806db756d0d26a63a6f6de94f198aa082e6', 'SideStore/Utils/common/AppBundleFingerprint.swift': 'e8a9dc9331002613219dc709e95ff34b53f77ded', 'SideStore/Core/Auth/Flows/CodeSignValidationFlow.swift': '6b14dd4dcebe3381370dbadac855f9a8b0bee6ba'}  # Pinned below from the reviewed 318faae prepared-source artifact.

def apply(root: Path):
    outputs = {}
    for path, patch in PATCHES.items():
        raw = (root/path).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != BLOBS[path]: raise ValueError('Unreviewed manager-update source: ' + path)
        outputs[root/path] = patch(raw.decode())
    for path, content in outputs.items(): path.write_text(content)

if __name__ == '__main__': apply(Path(sys.argv[1]))
