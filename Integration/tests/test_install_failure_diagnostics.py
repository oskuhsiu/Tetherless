from pathlib import Path
import importlib.util
import json
import os
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('install_environment', ROOT/'simulator_environment.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
SHA = 'a' * 40
ID = 'F7D98FC7-1590-4A40-B6B7-B67E1EA2C910'
RUNTIME = 'com.apple.CoreSimulator.SimRuntime.iOS-26-2'
TYPE = 'com.apple.CoreSimulator.SimDeviceType.iPhone-SE-3rd-generation'
BUNDLE = 'org.tetherless.Tetherless.XYZ0123456'


def fixture():
    owner = dict(schema=1, id=ID, name='Tetherless-CI-test', runtime=RUNTIME,
                 deviceType=TYPE, sourceCommit=SHA)
    device = dict(udid=ID, name=owner['name'], state='Booted', deviceTypeIdentifier=TYPE)
    smoke = dict(sourceCommit=SHA, simulatorID=ID, bundleID=BUNDLE,
                 failedStage='native-simulator-install.log', failure='timeout',
                 lastCommand=['xcrun','simctl','install'], installed=False, launched=False,
                 smokePassed=False, uiFlowsTested=False)
    return owner, device, smoke


class InstallFailureDiagnosticsTests(unittest.TestCase):
    def run_fixture(self, action):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); owner, device, smoke = fixture()
            with patch.object(m, 'OWNER', root/'owner.json'), patch.object(m, 'SMOKE', root/'smoke.json'), \
                 patch.object(m, 'DIAGNOSTICS', root/'health'), patch.dict(os.environ, {'GITHUB_SHA': SHA}):
                m.OWNER.write_text(json.dumps(owner)); m.SMOKE.write_text(json.dumps(smoke))
                action(owner, device, smoke)

    def test_timeout_readback_is_read_only_focused_and_does_not_change_failure(self):
        def check(owner, device, smoke):
            original = m.SMOKE.read_bytes()
            commands = m.install_failure_commands(device)
            self.assertEqual(len(commands), 3)
            self.assertEqual(commands[0], (['xcrun','simctl','get_app_container',ID,BUNDLE,'app'],
                                           'install-container-readback.log'))
            self.assertEqual(commands[1][0][-1], 'process == "installd" OR process == "lsd"')
            self.assertEqual(commands[2][0][-1], 'eventMessage CONTAINS "' + BUNDLE + '"')
            self.assertEqual(m.SMOKE.read_bytes(), original)
            for command, name in commands:
                self.assertNotIn('install', command)
                self.assertNotIn('launch', command)
                self.assertNotIn('shutdown', command)
                self.assertNotIn('erase', command)
                self.assertNotIn('/', name)
        self.run_fixture(check)

    def test_mixed_sha_uuid_or_previous_success_rejects_commands(self):
        def check(owner, device, smoke):
            for key, value in [('sourceCommit','b'*40), ('simulatorID','11111111-1111-1111-1111-111111111111'),
                               ('installed', True), ('launched', True), ('installed', 'false'),
                               ('lastCommand',['xcrun','simctl','launch'])]:
                m.SMOKE.write_text(json.dumps(dict(smoke, **{key:value})))
                with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                    m.install_failure_commands(device)
            m.SMOKE.write_text(json.dumps(smoke))
            m.OWNER.write_text(json.dumps(dict(owner, sourceCommit='c'*40)))
            with self.assertRaises(ValueError): m.install_failure_commands(device)
        self.run_fixture(check)

    def test_no_query_for_missing_smoke_or_a_ui_failure(self):
        def check(owner, device, smoke):
            m.SMOKE.write_text(json.dumps(dict(smoke, failedStage='native-ui.log')))
            self.assertEqual(m.install_failure_commands(device), [])
            m.SMOKE.unlink()
            self.assertEqual(m.install_failure_commands(device), [])
        self.run_fixture(check)

    def test_untrusted_bundle_cannot_enter_log_predicate(self):
        def check(owner, device, smoke):
            for value in ['org.tetherless.Tetherless" OR true', 'org.other.App',
                          'org.tetherless.Tetherless/secret', '-bundle', '', None, 123]:
                m.SMOKE.write_text(json.dumps(dict(smoke, bundleID=value)))
                with self.subTest(value=value), self.assertRaises(ValueError): m.install_failure_commands(device)
        self.run_fixture(check)

    def test_malformed_oversized_or_stopped_state_rejected(self):
        def check(owner, device, smoke):
            for data in ['{', '[]', ' '*65_537]:
                m.SMOKE.write_text(data)
                with self.assertRaises(ValueError): m.install_failure_commands(device)
            m.SMOKE.write_text(json.dumps(smoke))
            with self.assertRaises(ValueError): m.install_failure_commands(dict(device, state='Shutdown'))
        self.run_fixture(check)

    def test_diagnose_runs_focused_queries_first_and_never_promotes_timeout(self):
        def check(owner, device, smoke):
            original = m.SMOKE.read_bytes()
            with patch.object(m, 'listing', return_value={'devices':{RUNTIME:[device]}}), \
                 patch.object(m, 'capture', return_value={'exitCode':0}) as capture:
                m.diagnose()
                self.assertEqual(capture.call_count, 8)
                self.assertEqual(capture.call_args_list[0].args[0][:3], ['xcrun','simctl','get_app_container'])
                self.assertEqual(capture.call_args_list[1].args[0][-1], 'process == "installd" OR process == "lsd"')
                self.assertEqual(capture.call_args_list[3].args[0][0], 'ps')
            self.assertEqual(m.SMOKE.read_bytes(), original)
            self.assertFalse(json.loads(m.SMOKE.read_text())['installed'])
        self.run_fixture(check)

    def test_invalid_smoke_records_gap_but_retains_other_diagnostics(self):
        def check(owner, device, smoke):
            m.SMOKE.write_text('{')
            with patch.object(m,'listing',return_value={'devices':{RUNTIME:[device]}}), \
                 patch.object(m,'capture',return_value={'exitCode':0}) as capture:
                m.diagnose()
                self.assertEqual(capture.call_count,5)
                self.assertFalse(any('get_app_container' in call.args[0] for call in capture.call_args_list))
            report = json.loads((m.DIAGNOSTICS/'manifest.json').read_text())
            self.assertEqual(report[0], {'installInspection':'rejected-unbound-evidence'})
        self.run_fixture(check)

    def test_original_install_deadline_and_no_retry_ui_contract_unchanged(self):
        smoke = (ROOT/'simulator_smoke.py').read_text()
        self.assertIn("'native-simulator-install.log', 120)", smoke)
        self.assertEqual(smoke.count("['xcrun', 'simctl', 'install'"), 1)
        ui = (ROOT/'UITests/TetherlessUITests.swift').read_text()
        self.assertIn('inspectIndependentPickerControl(after: app, documents: documents)', ui)
        self.assertIn('let outcomeAppeared = rejected.waitForExistence(timeout: 10)', ui)
        self.assertIn('XCTAssertTrue(outcomeAppeared', ui)
        workflow = (ROOT.parent/'.github/workflows/native-simulator.yml').read_text()
        self.assertIn('if: failure()\n        run: python3 Integration/simulator_environment.py diagnose', workflow)
        self.assertNotIn('continue-on-error', workflow)

if __name__ == '__main__': unittest.main()
