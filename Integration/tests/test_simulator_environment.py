from pathlib import Path
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('environment', ROOT / 'simulator_environment.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
RUNTIME = 'com.apple.CoreSimulator.SimRuntime.iOS-26-2'
KIND = 'com.apple.CoreSimulator.SimDeviceType.iPhone-SE-3rd-generation'
ID = 'F7D98FC7-1590-4A40-B6B7-B67E1EA2C910'


def fixtures():
    owner = {'schema': 1, 'id': ID, 'name': 'Tetherless-CI-owned', 'runtime': RUNTIME, 'deviceType': KIND}
    device = {'udid': ID, 'name': owner['name'], 'state': 'Booted', 'deviceTypeIdentifier': KIND, 'isAvailable': True}
    return owner, {'devices': {RUNTIME: [device]}}


class SimulatorEnvironmentTests(unittest.TestCase):
    def test_template_selection_keeps_compact_configuration(self):
        data = {'devices': {RUNTIME: [
            {'name': 'iPhone 17', 'isAvailable': True, 'deviceTypeIdentifier': 'com.apple.CoreSimulator.SimDeviceType.iPhone-17'},
            {'name': 'iPhone SE (3rd generation)', 'isAvailable': True, 'deviceTypeIdentifier': KIND}],
            'com.apple.CoreSimulator.SimRuntime.tvOS-99-0': []}}
        self.assertEqual(m.select_template(data), ('iPhone SE (3rd generation)', RUNTIME, KIND))
        data['devices'][RUNTIME][1]['isAvailable'] = False
        self.assertEqual(m.select_template(data)[0], 'iPhone 17')
        with self.assertRaises(RuntimeError): m.select_template({'devices': {}})

    def test_allocate_creates_new_device_does_not_boot_or_reset_template(self):
        data = {'devices': {RUNTIME: [{'name': 'iPhone SE', 'isAvailable': True, 'deviceTypeIdentifier': KIND}]}}
        with tempfile.TemporaryDirectory() as temp:
            old = os.getcwd(); os.chdir(temp)
            try:
                with patch.object(m, 'OWNER', Path('owner.json')), patch.object(m, 'listing', return_value=data), \
                     patch.object(m.subprocess, 'check_output', return_value=ID+'\n') as call, \
                     patch.dict(os.environ, {'GITHUB_ENV': str(Path(temp)/'env')}):
                    self.assertEqual(m.allocate(), ID)
                    self.assertEqual(call.call_count, 1)
                    args = call.call_args.args[0]
                    self.assertEqual(args[:3], ['xcrun','simctl','create'])
                    self.assertEqual(args[-2:], [KIND,RUNTIME])
                    self.assertEqual(json.loads(m.OWNER.read_text())['id'], ID)
                    self.assertIn(ID, Path('env').read_text())
                    with self.assertRaises(RuntimeError): m.allocate()
                    self.assertEqual(call.call_count, 1)
            finally:
                os.chdir(old)

    def test_cleanup_requires_exact_owned_id_name_runtime_and_type(self):
        owner, data = fixtures()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'owner.json'; path.write_text(json.dumps(owner))
            with patch.object(m,'OWNER',path), patch.object(m,'listing',return_value=data), \
                 patch.object(m.subprocess,'run') as run:
                m.shutdown(); self.assertEqual(run.call_args.args[0], ['xcrun','simctl','shutdown',ID])
                run.reset_mock()
                data['devices'][RUNTIME][0]['name'] = 'Someone else'
                with self.assertRaises(RuntimeError): m.shutdown()
                run.assert_not_called()

    def test_diagnostics_bound_output_and_record_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)/'log'
            result = m.capture([sys.executable,'-c','import sys;sys.stdout.write("a"*300000)'],out,5)
            self.assertEqual(result['exitCode'],0)
            self.assertEqual(result['originalBytes'],300000)
            self.assertEqual(len(out.read_bytes()),m.MAX_OUTPUT)
            self.assertTrue(result['truncated'])
            self.assertEqual(result['tailOffset'],300000-m.MAX_OUTPUT//2)

    def test_diagnostic_timeout_is_preserved_not_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            result = m.capture([sys.executable,'-c','import time;print("before",flush=True);time.sleep(10)'],
                               Path(temp)/'log',1)
            self.assertTrue(result['timeout'])
            self.assertNotIn('exitCode',result)
            self.assertIn(b'before', (Path(temp)/'log').read_bytes())

    def test_unowned_diagnostics_do_not_spawn_inside_any_device(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(m,'OWNER',Path(temp)/'missing'), patch.object(m,'DIAGNOSTICS',Path(temp)/'diag'), \
                 patch.object(m,'listing',return_value=fixtures()[1]), patch.object(m,'capture',return_value={}) as capture:
                m.diagnose()
                self.assertEqual(capture.call_count,3)
                self.assertFalse(any('simctl' in c.args[0] for c in capture.call_args_list))
                report=json.loads((m.DIAGNOSTICS/'manifest.json').read_text())
                self.assertIn('ownershipOrListingFailure',report[0])

    def test_workflow_boots_after_compile_retains_failures_and_never_retries(self):
        text=(ROOT.parent/'.github/workflows/native-simulator.yml').read_text()
        self.assertLess(text.index('simulator_environment.py allocate'),text.index('xcodebuild build'))
        self.assertLess(text.index('simulator_signing.py'),text.index('simulator_smoke.py prepare'))
        self.assertLess(text.index('simulator_smoke.py prepare'),text.index('simulator_smoke.py launch'))
        self.assertIn('-destination "generic/platform=iOS Simulator"',text)
        self.assertIn('if: failure()\n        run: python3 Integration/simulator_environment.py diagnose',text)
        self.assertIn('native-simulator-health',text)
        self.assertNotIn('continue-on-error',text)
        self.assertNotIn('-retry-tests-on-failure',text)
        self.assertIn('Shut down only the simulator created by this job',text)


if __name__ == '__main__': unittest.main()
