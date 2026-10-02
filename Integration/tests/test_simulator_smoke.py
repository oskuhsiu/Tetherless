from pathlib import Path
import importlib.util
import json
import os
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('smoke', ROOT/'simulator_smoke.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class SmokeEvidenceTests(unittest.TestCase):
    def test_no_claims_from_creating_an_evidence_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(m, 'EVIDENCE', Path(tmp)/'evidence.json'):
                m.record(installed=True)
                data=json.loads(m.EVIDENCE.read_text())
                self.assertFalse(data['launched'])
                self.assertFalse(data['screenshotCaptured'])
                self.assertFalse(data['deviceValidated'])
                self.assertFalse(data['unattendedRenewalValidated'])
                self.assertFalse(data['uiFlowsTested'])
                m.record(failure='timeout')
                self.assertTrue(json.loads(m.EVIDENCE.read_text())['installed'])
    def test_blank_or_corrupt_screenshot_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'image.png'
            for content in [b'', b'bad'+b'x'*200, b'\x89PNG\r\n\x1a\n']:
                path.write_bytes(content)
                with self.assertRaises(RuntimeError): m.ensure_png(path)
    def test_render_readiness_is_checked_before_installation(self):
        source=(ROOT.parent/'.github/workflows/native-simulator.yml').read_text()
        self.assertLess(source.index('simulator_smoke.py prepare'),source.index('simulator_smoke.py launch'))
        self.assertNotIn('continue-on-error',source)
        self.assertIn('native-simulator-prepare.log',source)
        self.assertIn('native-simulator-install.log',source)

class SimulatorBootOrderingTests(unittest.TestCase):
    def prepare_commands(self, state):
        listing=json.dumps({'devices': {'iOS': [{'udid': 'selected', 'state': state}]}})
        with patch.object(m.subprocess, 'check_output', side_effect=['/Developer', listing]), \
             patch.object(m, 'command') as command, patch.object(m, 'record'), patch.object(m, 'ensure_png'):
            m.prepare('selected')
            return [call.args[0] for call in command.call_args_list]
    def test_cli_boot_completes_before_gui_without_second_boot_request(self):
        commands=self.prepare_commands('Shutdown')
        self.assertEqual(commands[0], ['xcrun', 'simctl', 'boot', 'selected'])
        self.assertEqual(commands[1], ['xcrun', 'simctl', 'bootstatus', 'selected'])
        self.assertEqual(commands[2][0], 'open')
        self.assertEqual(commands[3][2], 'io')
    def test_running_or_booting_device_is_only_monitored(self):
        for state in ['Booted', 'Booting']:
            with self.subTest(state=state):
                commands=self.prepare_commands(state)
                self.assertEqual(commands[0], ['xcrun', 'simctl', 'bootstatus', 'selected'])
                self.assertEqual(commands[1][0], 'open')
                self.assertFalse(any('-b' in command for command in commands))
    def test_unavailable_state_does_not_launch_or_claim_ready(self):
        with self.assertRaises(RuntimeError): self.prepare_commands('Unavailable')

if __name__ == '__main__': unittest.main()
