"""Small transformation fixtures; native CI separately checks real source hashes."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("prepare", Path(__file__).parents[1] / "prepare.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)

class PatchTests(unittest.TestCase):
    def test_exact_main_profile_and_preflight(self):
        fixture = "        self.setProgress(10)\n        installedApp.update(provisioningProfile: profiles.values.first!)\n"
        output = prepare.patch_profile(fixture)
        self.assertNotIn("profiles.values.first!", output)
        self.assertEqual(output.count("bundleID: self.context.targetBundleIdentifier"), 2)
        self.assertLess(output.index("requireMainProfile"), output.index("setProgress"))
    def test_main_patch_fails_closed_on_upstream_drift(self):
        with self.assertRaises(ValueError): prepare.patch_profile("changed upstream")
    def test_main_patch_is_not_applied_twice(self):
        fixture = "        self.setProgress(10)\n        installedApp.update(provisioningProfile: profiles.values.first!)"
        with self.assertRaises(ValueError): prepare.patch_profile(prepare.patch_profile(fixture))
    def test_foreground_intent_removed_without_removing_ipa_intent(self):
        fixture = "class IntentError {}\nstruct InstallIPAIntent {}\n@available(iOS 17.0, tvOS 17.0, *)\nextension RefreshAllAppsIntent\n{ requestToContinueInForeground() }"
        result = prepare.patch_intent(fixture)
        self.assertIn("InstallIPAIntent", result)
        self.assertNotIn("requestToContinueInForeground", result)
        self.assertNotIn("RefreshAllAppsIntent", result)
    def test_intent_drift_rejected(self):
        with self.assertRaises(ValueError): prepare.patch_intent("changed upstream")
    def test_duplicate_anchor_is_rejected(self):
        with self.assertRaises(ValueError): prepare.replace_once("same same", "same", "new")
    def test_all_reviewed_portal_mutations_are_gated(self):
        fixture = "        return try await ALTAppleAPI.shared.revokeCertificate(cert, for: team)\n" * 18
        result = prepare.patch_portal(fixture)
        self.assertEqual(result.count("NativeMutationGate.withLease"), 18)
        with self.assertRaises(ValueError): prepare.patch_portal(fixture + fixture)
    def test_boot_no_longer_probes_jit(self):
        fixture = "class Boot {\n    public nonisolated func performBootSequence() async {\n        startJIT()\n    }\n}\n"
        result = prepare.patch_boot(fixture)
        self.assertIn("NativeMutationGate.withLease", result)
        self.assertNotIn("startJIT()", result)
    def test_lifecycle_keeps_registration_before_finish(self):
        fixture = "        UserDefaults.registerDefaults()\n" + "        BackgroundServiceManager.ensureBackgroundServicesStarted()\n" * 3 + "        consoleLog.startCapturing()\n        UserDefaults.enableGlobalLogging()\nreturn true"
        result = prepare.patch_app(fixture)
        self.assertIn("NativeRenewalBackground.register()", result)
        self.assertNotIn("ensureBackgroundServicesStarted()", result)
        self.assertNotIn("consoleLog.startCapturing()", result)
    def test_native_overlay_has_no_foreground_escalation(self):
        source = (Path(__file__).parents[1] / "Native/TetherlessRefreshIntent.swift").read_text()
        self.assertIn("openAppWhenRun = false", source)
        self.assertNotIn("ForegroundContinuableIntent", source)
        self.assertNotIn("requestToContinueInForeground", source)
    def test_simulator_transport_fails_instead_of_claiming_readback(self):
        source = (Path(__file__).parents[1] / "Native/NativeProfileTransport.swift").read_text()
        self.assertEqual(source.count("#if targetEnvironment(simulator)"), 2)
        self.assertEqual(source.count("throw RenewalFailure.unavailable"), 4)

class KeepaliveTests(unittest.TestCase):
    def test_central_manager_disables_all_entry_points(self):
        source = "public protocol BackgroundService {}\npublic final class BackgroundServiceManager: @unchecked Sendable {\n    BackgroundAudioService.shared.start()\n}\n"
        result = prepare.patch_services(source)
        self.assertNotIn("BackgroundAudioService.shared", result)
        self.assertNotIn("BackgroundLocationService.shared", result)
        self.assertIn("func prepare() async -> Bool { false }", result)
        self.assertIn("static func ensureBackgroundServicesStarted() -> Bool", result)
        self.assertIn("isBackgroundServiceEnabled = false", result)

    def test_service_boundary_drift_fails_closed(self):
        with self.assertRaises(ValueError):
            prepare.patch_services("unexpected upstream")


if __name__ == "__main__": unittest.main()
