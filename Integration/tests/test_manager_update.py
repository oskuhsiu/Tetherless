"""Transformation guards, separate from Swift state-machine and native CI tests."""
import importlib.util
from pathlib import Path
import unittest
ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('manager_update', ROOT/'manager_update.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
class ManagerUpdateTransforms(unittest.TestCase):
    def test_fingerprint_replaces_names_and_lengths(self):
        result=m.patch_fingerprint('import Foundation\npublic enum AppBundleFingerprint { OLD_SIZE_ONLY }')
        self.assertNotIn('OLD_SIZE_ONLY',result)
        self.assertIn('BundleContentHash.bundle',result)
    def test_wrong_inputs_rejected(self):
        for patch in m.PATCHES.values():
            with self.assertRaises(ValueError): patch('unreviewed source')
    def test_no_graph_or_bundle_path_recovery(self):
        result=m.patch_app('prefix\n    static func reconcileSelfReinstallationIfNeeded() {\nOLD GRAPH\n}\n}\n\nextension AppDelegate: UNUserNotificationCenterDelegate {\n}')
        self.assertNotIn('OLD GRAPH',result)
        self.assertIn('NativeMutationGate.withLease',result)
        self.assertIn('NativeManagerUpdate.reconcile()',result)
    def test_native_recovery_is_not_background_renewal(self):
        native=(ROOT/'Native/NativeManagerUpdate.swift').read_text()
        self.assertIn('applicationState == .active',native)
        self.assertIn('context.save()',native)
        self.assertIn('verify.performAndWait',native)
        self.assertNotIn('InstalledApp.deserialize',native)
        self.assertNotIn('lastBundlePath',native)
        renewal=(ROOT/'Native/NativeRenewalBackend.swift').read_text()
        self.assertNotIn('NativeManagerUpdate.prepare',renewal)
        self.assertIn('update.phase.isPending',(ROOT/'Native/NativeProfileTransport.swift').read_text())
    def test_short_integration_runner_executes_after_auth(self):
        source=(ROOT/'network_safety.py').read_text()
        self.assertLess(source.index('"auth_safety.py"'),source.index('"manager_update.py"'))
