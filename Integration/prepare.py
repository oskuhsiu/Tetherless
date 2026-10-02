#!/usr/bin/env python3
"""Prepare a disposable pinned native app. Compilation is not device validation."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import plistlib
import re
import shutil
import subprocess

BASELINE = "0dd743f75afc358b0ba4a002feb5f19474492371"
PROFILE_PATH = "SideStore/Core/Operations/PipelineOperations/RefreshAppOperation.swift"
INTENT_PATH = "AltStore/Intents/App Intents/RefreshAllAppsIntent.swift"
RUNNER_PATH = "SideStore/Core/Operations/PipelineRunner.swift"
PORTAL_PATH = "SideStore/Core/Auth/DeveloperPortalProxy.swift"
APP_PATH = "AltStore/AppDelegate.swift"
TAB_PATH = "AltStore/TabBarController.swift"
BOOT_PATH = "SideStore/AppBootManager.swift"
SERVICE_PATH = "SideStore/Core/BackgroundServices/BackgroundService.swift"
KEYCHAIN_PATH = "AltStore/Core/Components/Keychain.swift"
BLOBS = {
    KEYCHAIN_PATH: "bb4133fdea00db6ac3f86c062e326adf36c0eda7",
    PROFILE_PATH: "bf23bf8b2d98364f7f3e94aaae27ae626439c2f1",
    INTENT_PATH: "11b9bfb6ae823fd6acee0fe31c21be283b45eb52",
    RUNNER_PATH: "a76344edcf8ed2518f52cff5b19de68fe1d0a991",
    PORTAL_PATH: "97ac67f578dddb5a8fb1eb720511e553bda279fa",
    APP_PATH: "eb41f3e35f9e27feeb1d7137b7aca74b6263e254",
    TAB_PATH: "83d6fb4ee8f03831db1ea65be6cbce147f19447f",
    BOOT_PATH: "ec9becb434c4a8736f202055fb84fa782f795419",
    SERVICE_PATH: "9dae8c7b91141eec0282939b91cd1545a70575eb",
    "AltStore/Info.plist": "868efe81e61393ccab1b6538e7f18439570aebdb",
    "AltStore.xcodeproj/project.pbxproj": "a511c447bd71311bffb6d116a3cb0025a75561d4",
}


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("Upstream patch anchor changed or duplicated; review required")
    return source.replace(old, new, 1)


def patch_profile(source: str) -> str:
    source = replace_once(source,
        "        installedApp.update(provisioningProfile: profiles.values.first!)",
        "        let mainProfile = try ProfileSelection.requireMainProfile(\n"
        "            in: profiles, bundleID: self.context.targetBundleIdentifier)\n"
        "        installedApp.update(provisioningProfile: mainProfile)")
    return replace_once(source, "        self.setProgress(10)",
        "        _ = try ProfileSelection.requireMainProfile(\n"
        "            in: profiles, bundleID: self.context.targetBundleIdentifier)\n"
        "        self.setProgress(10)")


def patch_intent(source: str) -> str:
    marker = "@available(iOS 17.0, tvOS 17.0, *)\nextension RefreshAllAppsIntent\n"
    if source.count(marker) != 1:
        raise ValueError("Inherited intent boundary changed")
    result = source.split(marker)[0]
    if "struct InstallIPAIntent" not in result or "class IntentError" not in result:
        raise ValueError("Required existing IPA intent declarations missing")
    return result


def patch_runner(source: str) -> str:
    signature = ("    func perform(_ operations: [AppOperation],\n"
                 "                 handler: PipelineExecutionHandler,\n"
                 "                 group: RefreshGroup) async throws -> RefreshGroup\n    {")
    replacement = signature + "\n        try await NativeMutationGate.withLease {\n" \
        "            try await self.performWithNativeLease(operations, handler: handler, group: group)\n" \
        "        }\n    }\n\n" + signature.replace("func perform(", "private func performWithNativeLease(")
    source = replace_once(source, signature, replacement)
    parallel = """        try await withThrowingTaskGroup(of: Void.self) { taskGroup in
            for operation in operations {
                taskGroup.addTask {
                    try await self.performOperation(for: operation, handler: handler, group: group, operationsCount: operationsCount)
                }
            }
            while let _ = try await taskGroup.next() {}
        }"""
    source = replace_once(source, parallel, """        for operation in operations {
            try Task.checkCancellation()
            try await self.performOperation(for: operation, handler: handler, group: group, operationsCount: operationsCount)
        }""")
    return replace_once(source,
        '                debugLog("[AppManager] perform(): Failed to save InstalledApp to database. \\(error.localizedDescription)")',
        '                throw RenewalFailure.storageUnavailable')


def patch_portal(source: str) -> str:
    methods = {"addCertificate", "revokeCertificate", "registerDevice", "updateDevice", "disableDevice",
               "deleteDevice", "addAppID", "updateAppID", "deleteAppID", "addAppGroup", "updateAppGroup",
               "assign", "deleteAppGroup", "createProvisioningProfile", "updateProvisioningProfile", "deleteProvisioningProfile"}
    count = 0
    lines = []
    for line in source.splitlines(keepends=True):
        match = re.fullmatch(r"(\s*)return try await (ALTAppleAPI\.shared\.([A-Za-z]+)\([^\n]+\))\n", line)
        if match and match[3] in methods:
            line = f"{match[1]}return try await NativeMutationGate.withLease {{ try await {match[2]} }}\n"
            count += 1
        lines.append(line)
    if count != 18:
        raise ValueError(f"Expected 18 reviewed portal mutation calls, found {count}")
    return "".join(lines)


def patch_app(source: str) -> str:
    source = replace_once(source, "        UserDefaults.registerDefaults()", """        UserDefaults.registerDefaults()
        if UserDefaults.standard.firstLaunch == nil { UserDefaults.standard.useOnDeviceAnisette = true }
        #if os(iOS)
        if #available(iOS 17.0, *) { NativeRenewalBackground.register() }
        #endif""")
    call = "        BackgroundServiceManager.ensureBackgroundServicesStarted()"
    if source.count(call) != 4:
        raise ValueError("Background service lifecycle call count changed")
    source = source.replace(call, "        // Tetherless does not use audio/location keepalive.")
    source = replace_once(source, "        consoleLog.startCapturing()", "        // Persistent full-console capture disabled in Tetherless.")
    source = replace_once(source, "        UserDefaults.enableGlobalLogging()", "        // Do not enable verbose credential-adjacent logs on debug launches.")
    return source


def patch_tabs(source: str) -> str:
    source = replace_once(source, "@preconcurrency import UIKit", "@preconcurrency import UIKit\nimport SwiftUI")
    marker = "        self.sourcesViewController = sourcesNavigationController.viewControllers.first as? SourcesViewController"
    return replace_once(source, marker, marker + """
        #if os(iOS)
        if #available(iOS 17.0, *) {
            let renewal = UIHostingController(rootView: NativeRenewalSettings(
                openAccountAndPairing: { [weak self] in self?.selectedIndex = Tab.settings.rawValue },
                openAppLibrary: { [weak self] in self?.selectedIndex = Tab.myApps.rawValue }))
            renewal.tabBarItem = UITabBarItem(title: "Auto Renewal", image: UIImage(systemName: "arrow.triangle.2.circlepath"), tag: 0)
            self.viewControllers?[Tab.news.rawValue] = renewal
        }
        #endif""")


def patch_boot(source: str) -> str:
    marker = "    public nonisolated func performBootSequence() async {"
    if source.count(marker) != 1 or not source.rstrip().endswith("}\n}"):
        raise ValueError("Boot function boundary changed")
    return source.split(marker)[0] + """    public nonisolated func performBootSequence() async {
        // Ordinary UI boot must not race headless work or probe JIT servers.
        do {
            try await NativeMutationGate.withLease {
                guard let pairing = PairingFileManager.shared.fetchPairingFile() else {
                    self.needsPairingPrompt = true
                    return
                }
                try await self.startMinimuxer(pairingFile: pairing)
            }
        } catch {
            // A headless operation may already own the device. Do not reset it.
        }
    }
}
"""


def patch_legacy_fetch(source: str) -> str:
    start = "    func application(_ application: UIApplication, performFetchWithCompletionHandler backgroundFetchCompletionHandler: @escaping (UIBackgroundFetchResult) -> Void)"
    end = "    func performBackgroundFetch(backgroundFetchCompletionHandler:"
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError("Legacy background fetch boundary changed")
    prefix, tail = source.split(start)
    discarded, suffix = tail.split(end)
    if "BackgroundTaskManager.shared.performExtendedBackgroundTask" not in discarded:
        raise ValueError("Unexpected legacy background implementation")
    return prefix + start + """
    {
        #if os(iOS)
        if #available(iOS 17.0, *) {
            Task {
                do {
                    let report = try await NativeRenewalRuntime.shared.run(trigger: .background)
                    backgroundFetchCompletionHandler(report.failures.isEmpty && report.unverified == 0
                        ? (report.verified > 0 ? .newData : .noData) : .failed)
                } catch { backgroundFetchCompletionHandler(.failed) }
            }
            return
        }
        #endif
        backgroundFetchCompletionHandler(.noData)
    }

""" + end + suffix


def patch_services(source: str) -> str:
    marker = "public final class BackgroundServiceManager: @unchecked Sendable {"
    if source.count(marker) != 1:
        raise ValueError("Background service manager boundary changed")
    return source.split(marker)[0] + """// Tetherless disables audio/location keepalive across all callers.
private struct TetherlessDisabledBackgroundService: BackgroundService {
    var isRunning: Bool { false }
    func start() -> Bool { false }
    func stop() {}
    func prepare() async -> Bool { false }
}
public final class BackgroundServiceManager: @unchecked Sendable {
    public static var shared: any BackgroundService { TetherlessDisabledBackgroundService() }
    public static func service(for mode: BackgroundServiceMode) -> any BackgroundService { shared }
    public static func stop() {}
    public static func switchTo(mode: BackgroundServiceMode) {
        UserDefaults.standard.isBackgroundServiceEnabled = false
    }
    public static func setEnabled(_ enabled: Bool) {
        UserDefaults.standard.isBackgroundServiceEnabled = false
    }
    @discardableResult public static func ensureBackgroundServicesStarted() -> Bool {
        UserDefaults.standard.isBackgroundServiceEnabled = false
        return false
    }
    private init() {}
}
"""


def patch_keychain(source: str) -> str:
    source = replace_once(source,
        "KeychainAccess.Keychain(service: Bundle.Info.appbundleIdentifier)",
        'KeychainAccess.Keychain(service: "org.tetherless.credentials." + Bundle.Info.appbundleIdentifier)')
    source = replace_once(source, ".accessibility(.afterFirstUnlock)",
                          ".accessibility(.afterFirstUnlockThisDeviceOnly)")
    # Never silently copy or remove another app's synchronized credentials.
    return replace_once(source, ".synchronizable(true)", ".synchronizable(false)")


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True).strip()


def prepare(root: Path) -> Path:
    vendor = root / "Vendor/SideStore"
    if git(vendor, "rev-parse", "HEAD") != BASELINE:
        raise ValueError("Unexpected upstream revision")
    if git(vendor, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Upstream tree is dirty")
    statuses = git(vendor, "submodule", "status", "--recursive")
    if any(line.startswith(("-", "+", "U")) for line in statuses.splitlines()):
        raise ValueError("Dependencies must be initialized at recorded revisions")
    for path, expected in BLOBS.items():
        if git_blob((vendor / path).read_bytes()) != expected:
            raise ValueError(f"Unreviewed source content: {path}")
    output = root / ".generated/SideStore"
    if output.exists() or output.is_symlink():
        raise ValueError("Output exists; review/remove it explicitly")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.is_symlink():
        raise ValueError("Generated directory must not be a symlink")
    shutil.copytree(vendor, output, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", ".build", "DerivedData", "xcuserdata"))
    for path, patch in ((PROFILE_PATH, patch_profile), (INTENT_PATH, patch_intent),
                        (RUNNER_PATH, patch_runner), (PORTAL_PATH, patch_portal),
                        (APP_PATH, lambda text: patch_legacy_fetch(patch_app(text))),
                        (TAB_PATH, patch_tabs), (BOOT_PATH, patch_boot),
                        (SERVICE_PATH, patch_services), (KEYCHAIN_PATH, patch_keychain)):
        destination = output / path
        destination.write_text(patch(destination.read_text()), encoding="utf-8")
    shutil.copytree(root / "Sources/TetherlessCore", output / "SideStore/TetherlessCore")
    shutil.copytree(root / "Integration/Native", output / "SideStore/TetherlessNative")
    info_path = output / "AltStore/Info.plist"
    info = plistlib.loads(info_path.read_bytes())
    info["CFBundleDisplayName"] = "Tetherless"
    info["BGTaskSchedulerPermittedIdentifiers"] = ["org.tetherless.profile-renewal"]
    info["UIBackgroundModes"] = ["fetch", "processing"]
    info_path.write_bytes(plistlib.dumps(info, sort_keys=False))
    sample = output / "CodeSigning.xcconfig.sample"
    if sample.exists():
        shutil.copyfile(sample, output / "CodeSigning.xcconfig")
    (output / "TETHERLESS_PREPARATION.json").write_text(json.dumps({
        "upstream": BASELINE, "reviewed_blobs": BLOBS,
        "runtime_adapter_integrated": True, "device_validated": False,
    }, indent=2) + "\n")
    return output


if __name__ == "__main__":
    print(prepare(Path(__file__).resolve().parents[1]))
