import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('simulator_signing', ROOT/'simulator_signing.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class SimulatorSigningTests(unittest.TestCase):
    def test_app_identity_is_sufficient_without_shared_groups(self):
        for key in ['application-identifier', 'com.apple.application-identifier']:
            evidence = module.validate({'CFBundleIdentifier': 'org.tetherless.Tetherless'},
                         {key: 'XYZ0123456.org.tetherless.Tetherless'}, 'XYZ0123456')
            self.assertTrue(evidence['keychainIdentityPresent'])
            self.assertFalse(evidence['deviceValidated'])
            self.assertFalse(evidence['appleLoginValidated'])
            self.assertFalse(evidence['unattendedRenewalValidated'])

    def test_missing_identity_and_conflicting_alias_are_rejected(self):
        for entitlements in [{}, {'keychain-access-groups': ['unrelated']},
            {'application-identifier': 'wrong'},
            {'application-identifier': 'XYZ0123456.org.tetherless.Tetherless',
             'com.apple.application-identifier': 'wrong'}]:
            with self.subTest(entitlements=entitlements), self.assertRaises(ValueError):
                module.validate({'CFBundleIdentifier': 'org.tetherless.Tetherless'}, entitlements, 'XYZ0123456')

    def test_wrong_or_missing_bundle_is_rejected(self):
        for value in [None, '', 'com.unrelated.App', 'org.tetherless.TetherlessEvil']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.validate({'CFBundleIdentifier': value}, {}, 'XYZ0123456')

    def test_only_simulator_workflow_enables_ad_hoc_signing(self):
        workflow = (ROOT.parent/'.github/workflows/native-simulator.yml').read_text()
        self.assertEqual(workflow.count('CODE_SIGNING_ALLOWED=YES CODE_SIGNING_REQUIRED=YES CODE_SIGN_IDENTITY=-'), 2)
        self.assertIn('Integration/simulator_signing.py', workflow)
        self.assertIn('native-simulator-signing.json', workflow)
        # The distributable remains unsigned: never create a misleading IPA.
        self.assertIn('CODE_SIGNING_ALLOWED=NO', (ROOT.parent/'.github/workflows/native.yml').read_text())

    @staticmethod
    def binary(entitlements=None, platform=7):
        import plistlib, struct
        payload = plistlib.dumps(entitlements if entitlements is not None else {
            'application-identifier': 'XYZ0123456.org.tetherless.Tetherless'})
        end = 32 + 24 + 72 + 80
        header = struct.pack('<8I', 0xfeedfacf, 0x0100000c, 0, 2, 2, end-32, 0, 0)
        build = struct.pack('<6I', 0x32, 24, platform, 0, 0, 0)
        segment = struct.pack('<II16sQQQQiiII', 0x19, 152, b'__TEXT', 0, end+len(payload),
                              0, end+len(payload), 5, 5, 1, 0)
        section = struct.pack('<16s16sQQIIIIIIII', b'__entitlements', b'__TEXT', end,
                              len(payload), end, 0, 0, 0, 0, 0, 0, 0)
        return header + build + segment + section + payload

    def test_reads_simulated_entitlements_not_empty_host_signature(self):
        entitlements, digest = module.simulator_entitlements(self.binary())
        self.assertEqual(entitlements['application-identifier'], 'XYZ0123456.org.tetherless.Tetherless')
        self.assertEqual(len(digest), 64)

    def test_device_and_macos_platform_are_not_simulator_evidence(self):
        for platform in [1, 2, 6]:
            with self.subTest(platform=platform), self.assertRaises(ValueError):
                module.simulator_entitlements(self.binary(platform=platform))

    def test_truncation_invalid_offsets_and_huge_section_rejected(self):
        import struct
        for offset, value in [(16, 100000), (20, 99999999), (36, 0), (120, 2),
                              (168, 99999999), (176, 0), (192, 1)]:
            data = bytearray(self.binary());struct.pack_into('<I', data, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                module.simulator_entitlements(data)
        with self.assertRaises(ValueError): module.simulator_entitlements(self.binary()[:-50])

    def test_wrong_magic_missing_section_or_nondict_plist_rejected(self):
        import plistlib
        for data in [b'not macho', self.binary().replace(b'__entitlements', b'__other_section'),
                     self.binary(entitlements=['not a dict'])]:
            with self.subTest(data=data[:32]), self.assertRaises((ValueError, plistlib.InvalidFileException)):
                module.simulator_entitlements(data)

    def test_check_inspects_but_never_repairs_or_signs(self):
        import plistlib, tempfile
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            (app/'Info.plist').write_bytes(plistlib.dumps({
                'CFBundleIdentifier': 'org.tetherless.Tetherless', 'CFBundleExecutable': 'App'}))
            (app/'App').write_bytes(self.binary())
            response = SimpleNamespace(stdout=plistlib.dumps({}))
            with patch.object(module.subprocess, 'run', return_value=response) as run:
                result = module.inspect(app, 'XYZ0123456')
                self.assertTrue(result['keychainIdentityPresent'])
                self.assertTrue(result['signatureVerified'])
                self.assertFalse(result['runtimeKeychainAccessValidated'])
                commands = [call.args[0] for call in run.call_args_list]
                self.assertEqual(len(commands), 2)
                self.assertIn('--verify', commands[0]); self.assertIn('--xml', commands[1])
                self.assertTrue(all('--sign' not in command for command in commands))

    def test_invalid_output_retains_exact_failure_stage(self):
        import plistlib, tempfile
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            (app/'Info.plist').write_bytes(plistlib.dumps({
                'CFBundleIdentifier': 'org.tetherless.Tetherless', 'CFBundleExecutable': 'App'}))
            (app/'App').write_bytes(self.binary())
            evidence = {'keychainIdentityPresent': False}
            with patch.object(module.subprocess, 'run', return_value=SimpleNamespace(stdout=b'not xml')):
                with self.assertRaises(plistlib.InvalidFileException): module.inspect(app, 'XYZ0123456', evidence)
            self.assertTrue(evidence['signatureVerified'])
            self.assertEqual(evidence['failureStage'], 'hostEntitlementFormat')
            self.assertFalse(evidence['keychainIdentityPresent'])
