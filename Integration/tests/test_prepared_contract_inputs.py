"""Portable storage/gate tests; synthetic bytes do not validate native sources."""
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

INTEGRATION = Path(__file__).parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, INTEGRATION / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inputs = load('prepared_contract_inputs')
runner = load('run_prepared_contract_tests')


class PreparedContractInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        # macOS /var is an OS symlink; use the canonical temporary directory.
        self.base = Path(self.temporary.name).resolve()
        self.app = self.base / 'App'
        self.app.mkdir()
        self.raw = b'// SYNTHETIC STORAGE TEST ONLY\nstruct Example {}\n'
        self.path = Path('Sources/Example.swift')
        self.source = self.app / self.path
        self.source.parent.mkdir()
        self.source.write_bytes(self.raw)
        self.expected = inputs.blob(self.raw)
        self.snapshots = self.base / inputs.DIRECTORY

    def contract(self, stage):
        self.assertIn(stage, inputs.STAGES)
        return self.path, self.expected

    def capture(self, stage='ipa_input_safety'):
        with patch.object(inputs, 'contract', side_effect=self.contract):
            return inputs.capture(self.app, stage)

    def capture_all(self):
        for stage in inputs.STAGES:
            self.capture(stage)

    def verify(self):
        with patch.object(inputs, 'contract', side_effect=self.contract):
            return inputs.verify(self.snapshots)

    def test_contracts_use_the_transform_modules_original_paths_and_expected_hashes(self):
        for stage in inputs.STAGES:
            original = load(stage)
            self.assertEqual(inputs.contract(stage), (Path(original.SOURCE), original.EXPECTED))
            self.assertEqual(len(original.EXPECTED), 40)

    def test_capture_preserves_source_and_only_writes_fixed_source_preimages(self):
        self.capture_all()
        roots = self.verify()
        self.assertEqual(set(roots), set(inputs.STAGES.values()))
        self.assertEqual(self.source.read_bytes(), self.raw)
        self.assertEqual(list(self.app.rglob('*')), [self.source.parent, self.source])
        self.assertEqual(len([p for p in self.snapshots.rglob('*') if p.is_file()]), 3)
        for stage, environment in inputs.STAGES.items():
            target = self.snapshots / stage / self.path
            self.assertEqual(target.read_bytes(), self.raw)
            self.assertEqual(Path(roots[environment]), target.parents[1])
        # Later app transforms cannot rewrite the retained preimage.
        self.source.write_bytes(b'// later transformation')
        self.verify()
        self.assertEqual((self.snapshots / 'ipa_input_safety' / self.path).read_bytes(), self.raw)

    def test_missing_unknown_and_changed_source_fail_before_any_write(self):
        with self.assertRaises(ValueError):
            inputs.capture(self.app, '../unreviewed')
        for contents in [b'', b'changed', b'X' * (inputs.MAXIMUM_SOURCE_BYTES + 1)]:
            self.source.write_bytes(contents)
            with self.assertRaises(ValueError):
                self.capture()
            self.assertFalse(self.snapshots.exists())
            self.assertEqual(self.source.read_bytes(), contents)
        self.source.unlink()
        with self.assertRaises(FileNotFoundError):
            self.capture()
        self.assertFalse(self.snapshots.exists())

    def test_source_file_directory_symlink_and_hardlink_are_rejected(self):
        outside = self.base / 'outside.swift'
        outside.write_bytes(self.raw)
        self.source.unlink()
        self.source.symlink_to(outside)
        with self.assertRaises(OSError):
            self.capture()
        self.source.unlink()
        os.link(outside, self.source)
        with self.assertRaises(ValueError):
            self.capture()
        self.source.unlink()
        self.source.parent.rmdir()
        self.source.parent.symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(OSError):
            self.capture()
        self.assertFalse(self.snapshots.exists())
        self.assertEqual(outside.read_bytes(), self.raw)

    def test_nonregular_source_rejected_without_blocking(self):
        self.source.unlink()
        os.mkfifo(self.source)
        with self.assertRaises(ValueError):
            self.capture()
        self.assertFalse(self.snapshots.exists())

    def test_output_symlink_and_existing_stage_never_overwritten(self):
        outside = self.base / 'outside'
        outside.mkdir()
        self.snapshots.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.capture()
        self.assertEqual(list(outside.iterdir()), [])
        self.snapshots.unlink()
        target = self.capture()
        before = (target / self.path).read_bytes()
        with self.assertRaises(ValueError):
            self.capture()
        self.assertEqual((target / self.path).read_bytes(), before)
        (self.snapshots / 'oda_metadata_safety').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.capture('oda_metadata_safety')
        self.assertEqual(list(outside.iterdir()), [])

    def test_root_symlink_traversal_and_snapshot_root_are_rejected(self):
        linked = self.base / 'linked'
        linked.symlink_to(self.app, target_is_directory=True)
        for path in [linked, self.app / '..' / 'App', Path('/')]:
            with patch.object(inputs, 'contract', side_effect=self.contract):
                with self.assertRaises((OSError, ValueError)):
                    inputs.capture(path, 'ipa_input_safety')
        self.snapshots.mkdir()
        with patch.object(inputs, 'contract', side_effect=self.contract):
            with self.assertRaises(ValueError):
                inputs.capture(self.snapshots, 'ipa_input_safety')
        self.assertEqual(list(self.snapshots.iterdir()), [])

    def test_missing_stage_bad_digest_or_extra_file_fails_verification(self):
        self.capture()
        with self.assertRaises(ValueError):
            self.verify()
        self.capture('anisette_cache_safety')
        self.capture('oda_metadata_safety')
        target = self.snapshots / 'ipa_input_safety' / self.path
        target.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            self.verify()
        target.write_bytes(self.raw)
        unexpected = target.parent / 'unexpected.swift'
        unexpected.write_bytes(b'extra')
        with self.assertRaises(ValueError):
            self.verify()
        unexpected.unlink()
        for index in range(4):
            (self.snapshots / str(index)).mkdir()
        with self.assertRaises(ValueError):
            self.verify()

    def test_snapshot_file_symlink_is_rejected_on_readback(self):
        self.capture_all()
        target = self.snapshots / 'ipa_input_safety' / self.path
        target.unlink()
        target.symlink_to(self.source)
        with self.assertRaises(OSError):
            self.verify()

    def test_real_cli_rejects_unknown_bytes_without_creating_snapshots(self):
        source, _ = inputs.contract('ipa_input_safety')
        target = self.app / source
        target.parent.mkdir(parents=True)
        target.write_bytes(self.raw)
        result = subprocess.run([sys.executable, str(INTEGRATION / 'prepared_contract_inputs.py'),
                                 str(self.app), 'ipa_input_safety'], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Unreviewed prepared contract input', result.stderr)
        self.assertFalse(self.snapshots.exists())
        self.assertEqual(target.read_bytes(), self.raw)

    def test_capture_hooks_immediately_precede_their_real_transform(self):
        text = (INTEGRATION / 'network_safety.py').read_text()
        for stage in inputs.STAGES:
            capture = '    subprocess.run([sys.executable, str(Path(__file__).with_name("prepared_contract_inputs.py")), str(root), "' + stage + '"], check=True)'
            transform = '    subprocess.run([sys.executable, str(Path(__file__).with_name("' + stage + '.py")), str(root)], check=True)'
            self.assertEqual(text.count(capture + '\n' + transform), 1)
        workflow = (INTEGRATION.parent / '.github/workflows/native.yml').read_text()
        before = workflow.index('run: python3 -m unittest discover -s Integration/tests -v')
        prepare = workflow.index('run: python3 Integration/prepare.py')
        after = workflow.index('run: python3 Integration/run_prepared_contract_tests.py')
        build = workflow.index('- name: Compile unsigned iOS app')
        self.assertLess(before, prepare)
        self.assertLess(prepare, after)
        self.assertLess(after, build)


class PreparedContractRunnerTests(unittest.TestCase):
    def test_real_suite_contains_all_six_required_contracts(self):
        suite = runner.load_suite()
        self.assertTrue(runner.REQUIRED_TESTS.issubset(set(runner.test_ids(suite))))
        self.assertEqual(suite.countTestCases(), 13)

    def test_missing_swift_or_unverified_inputs_never_runs_tests(self):
        with patch.object(runner.shutil, 'which', return_value=None), patch.object(runner, 'load_suite') as loader:
            with self.assertRaises(ValueError):
                runner.run(Path('/unused'))
            loader.assert_not_called()
        with patch.object(runner.shutil, 'which', return_value='/synthetic/swiftc'), \
             patch.object(runner.inputs, 'verify', side_effect=ValueError('unverified')), \
             patch.object(runner, 'load_suite') as loader:
            with self.assertRaises(ValueError):
                runner.run(Path('/unused'))
            loader.assert_not_called()

    def test_test_gate_fails_skips_failures_errors_and_unexpected_success(self):
        class Cases(unittest.TestCase):
            def test_pass(self): pass
            def test_skip(self): self.skipTest('synthetic skip')
            def test_failure(self): self.fail('synthetic failure')
            def test_error(self): raise ValueError('synthetic error')
            @unittest.expectedFailure
            def test_unexpected_success(self): pass
            @unittest.expectedFailure
            def test_expected_failure(self): self.fail('synthetic expected failure')
        for name, status in [('pass', 0), ('skip', 1), ('failure', 1), ('error', 1), ('unexpected_success', 1), ('expected_failure', 1)]:
            with self.subTest(name=name), patch.object(runner.shutil, 'which', return_value='/synthetic/swiftc'), \
                 patch.object(runner.inputs, 'verify', return_value={}), \
                 patch.object(runner, 'load_suite', return_value=unittest.TestSuite([Cases('test_' + name)])):
                self.assertEqual(runner.run(Path('/unused'), stream=io.StringIO()), status)

    def test_inputs_are_selected_before_loading_tests_and_environment_is_restored(self):
        environment = {value: '/synthetic/' + stage for stage, value in inputs.STAGES.items()}
        previous = {key: os.environ.get(key) for key in environment}
        def loader():
            for key, value in environment.items():
                self.assertEqual(os.environ[key], value)
            return unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])
        with patch.object(runner.shutil, 'which', return_value='/synthetic/swiftc'), \
             patch.object(runner.inputs, 'verify', return_value=environment), \
             patch.object(runner, 'load_suite', side_effect=loader):
            self.assertEqual(runner.run(Path('/unused'), stream=io.StringIO()), 0)
        self.assertEqual({key: os.environ.get(key) for key in environment}, previous)

    def test_loader_cannot_silently_omit_required_tests(self):
        with patch.object(runner.unittest.TestLoader, 'loadTestsFromModule', return_value=unittest.TestSuite()):
            with self.assertRaises(ValueError):
                runner.load_suite()


if __name__ == '__main__':
    unittest.main()
