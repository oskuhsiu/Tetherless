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

if __name__ == '__main__': unittest.main()
