"""Transformation check; compiled native code is checked by the native CI job."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("prepare", Path(__file__).parents[1] / "prepare.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)

class SecretStorageTests(unittest.TestCase):
    def test_secrets_are_device_local_and_isolated(self):
        source = "KeychainAccess.Keychain(service: Bundle.Info.appbundleIdentifier)\n.accessibility(.afterFirstUnlock)\n.synchronizable(true)"
        result = prepare.patch_keychain(source)
        self.assertIn('"org.tetherless.credentials."', result)
        self.assertIn("afterFirstUnlockThisDeviceOnly", result)
        self.assertIn("synchronizable(false)", result)
        self.assertNotIn("synchronizable(true)", result)
        with self.assertRaises(ValueError): prepare.patch_keychain(result)
