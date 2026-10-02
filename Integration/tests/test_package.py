"""Packaging input boundaries, not Mach-O signing or iOS execution tests."""
import importlib.util
from pathlib import Path
import plistlib
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('package_unsigned', Path(__file__).parents[1] / 'package_unsigned.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = self.root / 'Test.app'
        self.app.mkdir()
        self.info = {'CFBundleExecutable': 'Test', 'CFBundleIdentifier': 'test.app'}
        self.write_info()
        (self.app / 'Test').write_bytes(b'fixture; not a real Mach-O')
    def tearDown(self):
        self.tmp.cleanup()
    def write_info(self):
        (self.app / 'Info.plist').write_bytes(plistlib.dumps(self.info))
    def test_regular_bundle_metadata(self):
        self.assertEqual(module.validate_app(self.app)['CFBundleIdentifier'], 'test.app')
    def test_missing_executable(self):
        (self.app / 'Test').unlink()
        with self.assertRaises(ValueError): module.validate_app(self.app)
    def test_executable_path_escape(self):
        self.info['CFBundleExecutable'] = '../secret'; self.write_info()
        with self.assertRaises(ValueError): module.validate_app(self.app)
    def test_signing_material_rejected(self):
        for name in ('secret.p12', 'AuthKey.p8', 'embedded.mobileprovision'):
            with self.subTest(name=name):
                p = self.app / name; p.write_bytes(b'sensitive fixture')
                with self.assertRaises(ValueError): module.validate_app(self.app)
                p.unlink()
    def test_symlink_outside_bundle_rejected(self):
        outside = self.root / 'secret'; outside.write_bytes(b'fixture')
        (self.app / 'link').symlink_to(outside)
        with self.assertRaises(ValueError): module.validate_app(self.app)
    def test_private_pem_rejected(self):
        (self.app / 'private.pem').write_bytes(b'-----BEGIN PRIVATE KEY-----')
        with self.assertRaises(ValueError): module.validate_app(self.app)
    def test_invalid_commit_rejected_before_output_is_created(self):
        output = self.root / 'output'
        with self.assertRaises(ValueError): module.package(self.app, output, 'main', 'Debug')
        self.assertFalse(output.exists())

if __name__ == '__main__': unittest.main()
