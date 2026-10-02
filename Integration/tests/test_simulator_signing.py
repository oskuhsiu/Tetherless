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

    def test_check_inspects_but_never_repairs_or_signs(self):
        import plistlib
        from types import SimpleNamespace
        class InfoFile:
            def read_bytes(self):
                return plistlib.dumps({'CFBundleIdentifier': 'org.tetherless.Tetherless'})
        class App:
            def __truediv__(self, name): return InfoFile()
            def __str__(self): return '/simulator/product.app'
        response = SimpleNamespace(stdout=plistlib.dumps({
            'application-identifier': 'XYZ0123456.org.tetherless.Tetherless'}))
        with patch.object(module.subprocess, 'run', return_value=response) as run:
            result = module.inspect(App(), 'XYZ0123456')
            self.assertTrue(result['keychainIdentityPresent'])
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(len(commands), 2)
            self.assertIn('--verify', commands[0])
            self.assertIn('--display', commands[1])
            self.assertTrue(all('--sign' not in command for command in commands))
