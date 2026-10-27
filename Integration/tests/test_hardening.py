"""Fail-closed transformations; actual pinned files are exercised by native CI."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('hardening', Path(__file__).parents[1] / 'harden.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class HardeningTests(unittest.TestCase):
    def test_bundle_identity_replaces_both_reviewed_constants(self):
        source = 'static let storeAppBundleIdentifier = "com.SideStore.SideStore"\nstatic let appbundleIdentifier = "com.SideStore.SideStore"'
        result = mod.patch_bundle(source)
        self.assertNotIn('com.SideStore', result)
        self.assertEqual(result.count(mod.APP_ID), 2)
    def test_changed_bundle_anchor_fails_closed(self):
        with self.assertRaises(ValueError): mod.patch_bundle('new upstream implementation')
    def test_embed_only_calls_public_material_writer(self):
        result = mod.patch_embed('// retained copyright\nfinal class EmbedSigningCertOperation: OLD {}')
        self.assertTrue(result.startswith('// retained copyright'))
        self.assertIn('PublicSigningMaterial.writeCertificate', result)
        self.assertNotIn('p12Data', result)
        self.assertNotIn('CertificateManager.convert', result)
    def test_self_resign_never_embeds_active_private_key(self):
        source = 'before\n        if targetAppBundle.isAltStoreApp {\nOLD\n        // Prepare app\nafter'
        result = mod.patch_resign(source)
        self.assertIn('context.targetSigningCertificate', result)
        self.assertIn('PublicSigningMaterial.writeCertificate', result)
        self.assertNotIn('p12Data.write', result)
        self.assertTrue(result.endswith('after'))
    def test_router_disables_export_routes_and_accepts_only_own_schemes(self):
        source = '        guard let host = components.host?.lowercased() else {\n}\n        case "pairing":\nOLD EXPORT CODE\n        default:\n            return false\n'
        result = mod.patch_router(source)
        self.assertNotIn('OLD EXPORT CODE', result)
        self.assertIn('case "pairing", "certificate":\n            return false', result)
        self.assertIn('scheme == "tetherless"', result)
    def test_wrong_hash_rejected_without_partial_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / mod.BUILD).write_text('unreviewed')
            with self.assertRaisesRegex(ValueError, 'Unreviewed'): mod.harden(root)
            self.assertEqual((root / mod.BUILD).read_text(), 'unreviewed')

if __name__ == '__main__': unittest.main()
