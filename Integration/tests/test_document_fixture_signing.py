from pathlib import Path
import hashlib
import importlib.util
import json
import plistlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
import document_fixture_app as fixture
import retain_ui_diagnostics as diagnostics

spec = importlib.util.spec_from_file_location('macho_fixture', ROOT/'tests/test_simulator_signing.py')
support = importlib.util.module_from_spec(spec); spec.loader.exec_module(support)
IDENTITY = 'XYZ0123456.org.tetherless.Tetherless.XYZ0123456'
SIMULATED = {'application-identifier': 'XYZ0123456.org.tetherless.testdocuments', 'get-task-allow': True}


class DocumentFixtureSigningTests(unittest.TestCase):
    def bundle(self, root, simulated=SIMULATED, platform=7):
        app = Path(root)/'DocumentFixture.app'
        fixture.build_inputs(app, IDENTITY)
        (app/'DocumentFixture').write_bytes(support.SimulatorSigningTests.binary(simulated, platform))
        return app

    def test_host_and_simulated_entitlement_inputs_are_distinct(self):
        with tempfile.TemporaryDirectory() as root:
            app = self.bundle(root)
            simulated = app.parent/'DocumentFixture.entitlements'
            host = fixture.host_entitlements(app)
            self.assertNotEqual(host, simulated)
            self.assertEqual(plistlib.loads(simulated.read_bytes()), SIMULATED)
            self.assertEqual(plistlib.loads(host.read_bytes()), {})
            command = fixture.signing_command(app)
            self.assertEqual(command[command.index('--entitlements') + 1], str(host))
            self.assertNotIn(str(simulated), command)
            self.assertIn('--sign', command)
            self.assertIn('--generate-entitlement-der', command)

    def test_actual_macho_section_and_empty_host_pass_without_inventing_launch(self):
        with tempfile.TemporaryDirectory() as root:
            app = self.bundle(root)
            # Only the macOS codesign tool is scripted here. The real production
            # reader parses the generated on-disk Mach-O entitlement section.
            with patch.object(fixture, 'command') as command, \
                 patch.object(fixture.subprocess, 'check_output', return_value=plistlib.dumps({})):
                result = fixture.inspect_signature(app, IDENTITY)
            self.assertTrue(result['signatureVerified'])
            self.assertTrue(result['simulatedIdentityVerified'])
            self.assertFalse(result['runtimeLaunchObserved'])
            self.assertEqual(result['hostEntitlementCount'], 0)
            self.assertEqual(result['executableSHA256'], hashlib.sha256((app/'DocumentFixture').read_bytes()).hexdigest())
            command.assert_called_once_with(['codesign', '--verify', '--strict', str(app)], 30)

    def test_prior_ios_privileges_in_host_signature_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            app = self.bundle(root)
            for invalid in [SIMULATED, {'get-task-allow': True}, {'application-identifier': SIMULATED['application-identifier']}, []]:
                with self.subTest(invalid=invalid), patch.object(fixture, 'command'), \
                     patch.object(fixture.subprocess, 'check_output', return_value=plistlib.dumps(invalid)):
                    with self.assertRaises(ValueError): fixture.inspect_signature(app, IDENTITY)

    def test_good_host_signature_cannot_hide_bad_simulator_identity(self):
        for invalid in [{}, {'application-identifier': 'wrong'},
                        dict(SIMULATED, **{'keychain-access-groups': ['unexpected']})]:
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as root:
                app = self.bundle(root, invalid)
                with patch.object(fixture, 'command'), \
                     patch.object(fixture.subprocess, 'check_output', return_value=plistlib.dumps({})):
                    with self.assertRaises(ValueError): fixture.inspect_signature(app, IDENTITY)

    def test_device_binary_or_wrong_bundle_is_not_accepted(self):
        for platform in [1, 2, 6]:
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as root:
                app = self.bundle(root, platform=platform)
                with patch.object(fixture, 'command'), \
                     patch.object(fixture.subprocess, 'check_output', return_value=b''):
                    with self.assertRaises(ValueError): fixture.inspect_signature(app, IDENTITY)
        with tempfile.TemporaryDirectory() as root:
            app = self.bundle(root)
            (app/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'other', 'CFBundleExecutable': 'DocumentFixture'}))
            with patch.object(fixture, 'command') as command:
                with self.assertRaises(ValueError): fixture.inspect_signature(app, IDENTITY)
                command.assert_not_called()

    def test_inspection_precedes_install_and_retains_existing_ui_acceptance(self):
        source = (ROOT/'document_fixture_app.py').read_text()
        self.assertLess(source.index('signature = inspect_signature('), source.index("command(['xcrun', 'simctl', 'install'"))
        self.assertIn("'-Xlinker', str(entitlement)", source)
        self.assertIn('command(signing_command(OUTPUT), 30)', source)
        ui = (ROOT/'UITests/TetherlessUITests.swift').read_text()
        self.assertIn('documents.launch()', ui)
        self.assertIn('fixture.documentReady', ui)
        self.assertIn('rejected.waitForExistence(timeout: 10)', ui)
        self.assertIn('XCTAssertFalse(pickerStillVisible', ui)
        workflow = (ROOT.parent/'.github/workflows/native-simulator.yml').read_text()
        self.assertIn('native-document-fixture-signing.json', workflow)
        self.assertNotIn('continue-on-error', workflow)

    def test_fixture_crash_is_retained_separately_under_existing_bounds(self):
        with tempfile.TemporaryDirectory() as root:
            raw = Path(root)/'raw'; raw.mkdir()
            crash = b'{"termination":{"namespace":"CODESIGNING","indicator":"Taskgated Invalid Signature"}}'
            (raw/'DocumentFixture-2026.ips').write_bytes(crash)
            (raw/'StandardOutputAndStandardError-org.tetherless.testdocuments.txt').write_bytes(b'fixture output')
            (raw/'Unrelated-2026.ips').write_bytes(b'not selected')
            out = Path(root)/'retained'
            report = diagnostics.retain(raw, out, limit=40)
            self.assertEqual({f['kind'] for f in report['files']}, {'fixture-crash','fixture-stdout'})
            self.assertFalse(report['uiResultInferred'])
            selected = next(f for f in report['files'] if f['kind'] == 'fixture-crash')
            self.assertTrue(selected['truncated'])
            self.assertEqual(sum(part['bytes'] for part in selected['parts']), 40)
            self.assertEqual((raw/'DocumentFixture-2026.ips').read_bytes(), crash)


if __name__ == '__main__': unittest.main()
