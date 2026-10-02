"""Patch-shape tests use small fixtures, not a fake full upstream checkout.
The native CI separately verifies pinned real Git blob hashes before applying.
"""
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
        with self.assertRaises(ValueError):
            prepare.patch_profile("changed upstream")

    def test_main_patch_is_not_applied_twice(self):
        fixture = "        self.setProgress(10)\n        installedApp.update(provisioningProfile: profiles.values.first!)"
        with self.assertRaises(ValueError):
            prepare.patch_profile(prepare.patch_profile(fixture))

    def test_initializer_error_resumes_continuation(self):
        fixture = ('            let operation = try? AppManager.shared.backgroundRefresh(apps) { result in\n'
                   '            }\n'
                   '            guard let operation else {\n'
                   '                debugLog("[RefreshAllAppsIntent] backgroundRefresh instance is nil")\n'
                   '                return \n'
                   '            }\n')
        output = prepare.patch_intent(fixture)
        self.assertNotIn("try?", output)
        self.assertIn("continuation.resume(throwing: error)", output)
        self.assertIn("operation = try AppManager", output)
        self.assertEqual(output.count("{"), output.count("}"))

    def test_duplicate_anchor_is_rejected(self):
        with self.assertRaises(ValueError):
            prepare.replace_once("same same", "same", "new")


if __name__ == "__main__":
    unittest.main()
