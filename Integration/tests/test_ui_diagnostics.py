import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('diagnostics', ROOT / 'retain_ui_diagnostics.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


class DiagnosticSelectionTests(unittest.TestCase):
    def exercise(self, data):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        root = Path(directory.name) / 'input'; root.mkdir()
        source = root / 'StandardOutputAndStandardError-org.tetherless.Tetherless.txt'
        source.write_bytes(data)
        (root / 'unrelated-host.log').write_bytes(b'not app data')
        output = root.parent / 'output'
        result = module.retain(root, output, limit=8)
        self.assertEqual(source.read_bytes(), data)
        self.assertEqual(len(result['files']), 1)
        self.assertFalse(result['uiResultInferred'])
        self.assertFalse((output / 'unrelated-host.log').exists())
        self.assertEqual(json.loads((output / 'manifest.json').read_text()), result)
        return output, result['files'][0]

    def test_small_and_boundary_logs_are_complete(self):
        for data in [b'', b'small', b'12345678']:
            with self.subTest(data=data):
                output, entry = self.exercise(data)
                self.assertFalse(entry['truncated']); self.assertEqual(entry['omittedBytes'], 0)
                self.assertEqual((output / entry['parts'][0]['file']).read_bytes(), data)

    def test_oversize_retains_head_and_tail_with_exact_omitted_range(self):
        output, entry = self.exercise(b'0123456789ABCDEF')
        self.assertTrue(entry['truncated']); self.assertEqual(entry['originalBytes'], 16)
        self.assertEqual(entry['omittedBytes'], 8)
        self.assertEqual([(p['offset'], p['bytes']) for p in entry['parts']], [(0, 4), (12, 4)])
        self.assertEqual([(output / p['file']).read_bytes() for p in entry['parts']], [b'0123', b'CDEF'])

    def test_links_are_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'input'; root.mkdir()
            target = root.parent / 'outside'; target.write_text('must not read')
            (root / 'SideStore-fake.ips').symlink_to(target)
            with self.assertRaises(OSError): module.retain(root, root.parent / 'output')
            self.assertFalse((root.parent / 'output/manifest.json').exists())

    def test_count_limit_is_not_silently_truncated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'input'; root.mkdir()
            for index in range(21): (root / f'SideStore-{index}.ips').write_text('report')
            with self.assertRaises(ValueError): module.retain(root, root.parent / 'output')
            self.assertFalse((root.parent / 'output').exists())

    def test_workflow_keeps_original_result_and_does_not_ignore_export_errors(self):
        text = (ROOT.parent / '.github/workflows/native-simulator.yml').read_text()
        self.assertIn('python3 Integration/retain_ui_diagnostics.py', text)
        self.assertIn('native-ui.xcresult', text)
        self.assertIn('native-ui-diagnostics', text)
        self.assertNotIn('continue-on-error', text)
        self.assertNotIn('Unexpected diagnostic size', text)
