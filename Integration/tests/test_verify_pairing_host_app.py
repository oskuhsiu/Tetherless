import importlib.util
import json
import os
import sys
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT.parent
spec = importlib.util.spec_from_file_location('host_app_verification', ROOT / 'Integration/verify_pairing_host_app.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def transcript(names, duplicate_summaries=True):
    output = ''.join("Test Case '-[TetherlessCoreTests.%s %s]' passed (0.001 seconds).\n" % tuple(name.split('.')) for name in names)
    summary = 'Executed %s tests, with 0 failures (0 unexpected)\n' % len(names)
    return output + summary + "Test Suite 'All tests' passed at synthetic-time\n" + (summary if duplicate_summaries else '')


class VerifyPairingHostAppTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='host-app-verifier-fixture-')
        self.base = Path(self.temporary.name).resolve()
        self.source = self.base / 'source'; self.source.mkdir()
        roots = [ROOT, WORK / 'tetherless-host-app-boundaries', WORK / 'tetherless-closure-next', WORK / 'tetherless-component-alias-ready', WORK / 'tetherless-native-build-tools']
        for relative in probe.EXPECTED:
            source = next(root / relative for root in roots if (root / relative).is_file())
            destination = self.source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        self.output = self.base / 'reports'
        self.commands = []; self.packages = []; self.names = list(probe.EXPECTED_FIXTURES)
        self.debug_outcome = 'success'; self.metadata_failure = False

    def tearDown(self):
        for package in self.packages:
            if package.exists(): shutil.rmtree(package.parent)
        self.temporary.cleanup()

    def runner(self, command, **options):
        self.commands.append(command)
        outcome = 'success'
        if '--find' in command: output = '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swift\n'
        elif '--version' in command:
            output = 'Apple Swift version synthetic-fixture\n'
            if self.metadata_failure: outcome = 'nonzero_exit'
        else:
            package = Path(command[command.index('--package-path') + 1]); self.packages.append(package)
            self.assertFalse((package / 'Sources/TetherlessCore/BoundedPairingHostBridge.swift').exists())
            self.assertTrue((package / 'Sources/TetherlessCore/PairingBonjourListener.swift').is_file())
            self.assertIn('-DTETHERLESS_BOUNDED_PAIRING_HOST', command)
            binary = package / '.build/synthetic-executable'; binary.parent.mkdir(exist_ok=True)
            binary.write_bytes(b'synthetic fixture only')
            output = transcript(self.names)
            if 'debug' in command: outcome = self.debug_outcome
        self.assertEqual(options['timeout_seconds'], 60)
        self.assertEqual(options['term_grace_seconds'] + options['kill_join_seconds'], 10)
        log = options['log']; log.write_text(output)
        status = {'outcome': outcome, 'returncode': 0 if outcome == 'success' else 1,
                  'pid': 12345, 'elapsed_seconds': 0, 'output_complete': outcome == 'success',
                  'cleanup': {'direct_child_reaped': True, 'group_empty': outcome != 'cleanup_incomplete'}}
        log.with_name(log.name + '.status.json').write_text(json.dumps(status))
        if outcome != 'success': raise ValueError('injected supervisor failure')
        return output

    def test_both_configurations_count_unique_results_and_allow_repeated_summaries(self):
        result = probe.verify(self.source, self.output, runner=self.runner, platform='darwin')
        self.assertEqual(result['status'], 'passed')
        self.assertIn('test', self.commands[0]); self.assertIn('debug', self.commands[0])
        self.assertEqual(result['runner'], 'injected_test_double')
        self.assertEqual(len(self.commands), 4)
        self.assertTrue(all(not p.exists() for p in self.packages))
        self.assertEqual(len(list(self.output.iterdir())), 9)
        self.assertTrue(all(p.suffix in ['.json', '.log'] for p in self.output.iterdir()))
        for configuration in ['debug', 'release']:
            phase = result['phases'][configuration]
            self.assertTrue(phase['passed'])
            self.assertEqual(len(phase['fixtures']['unique_passed_fixtures']), 19)
            self.assertEqual(len(phase['fixtures']['aggregate_summaries']), 2)

    def test_summary_only_or_duplicate_fixture_cannot_fake_nineteen_results(self):
        self.assertFalse(probe.fixture_summary("Test Suite 'All tests' passed\nExecuted 19 tests, with 0 failures\n")['passed'])
        self.names[-1] = self.names[0]
        result = probe.verify(self.source, self.output, runner=self.runner, platform='darwin')
        self.assertEqual(result['status'], 'fixture_or_metadata_failure')
        self.assertFalse(result['phases']['debug']['passed'])

    def test_swiftpm_dot_form_is_accepted_and_failed_repetition_rejected(self):
        value = ''.join("Test Case '%s' passed (0.01 seconds).\n" % n for n in self.names)
        value += "Test Suite 'All tests' passed\nExecuted 19 tests, with 0 failures\n"
        self.assertTrue(probe.fixture_summary(value)['passed'])
        self.assertFalse(probe.fixture_summary(value + "Test Case '%s' failed\n" % self.names[0])['passed'])

    def test_source_drift_during_first_real_fixture_phase_invalidates_observation(self):
        def drift(command, **options):
            result = self.runner(command, **options)
            (self.source / 'Sources/TetherlessCore/PairingPromotion.swift').write_text('ordinary changed source')
            return result
        result = probe.verify(self.source, self.output, runner=drift, platform='darwin')
        self.assertEqual(result['status'], 'input_or_output_failure')
        self.assertEqual(len(self.commands), 1)
        self.assertNotIn('release', result['phases'])

    def test_initial_identity_mismatch_never_executes_mismatched_source(self):
        (self.source / 'Package.swift').write_text('ordinary changed package')
        result = probe.verify(self.source, self.output, runner=self.runner, platform='darwin')
        self.assertEqual(result['status'], 'input_or_output_failure'); self.assertEqual(self.commands, [])

    def test_symlink_input_is_refused(self):
        original = self.source / 'Package.swift'; alternate = self.base / 'package-copy'
        shutil.copyfile(original, alternate); original.unlink(); original.symlink_to(alternate)
        result = probe.verify(self.source, self.output, runner=self.runner, platform='darwin')
        self.assertEqual(result['status'], 'input_or_output_failure'); self.assertEqual(self.commands, [])

    def test_existing_or_alias_output_is_refused(self):
        self.output.mkdir()
        with self.assertRaises(ValueError): probe.verify(self.source, self.output, runner=self.runner, platform='darwin')
        alias = self.base / 'alias'; alias.symlink_to(self.output, target_is_directory=True)
        with self.assertRaises(ValueError): probe.verify(self.source, alias / 'child', runner=self.runner, platform='darwin')

    def test_metadata_failure_cannot_mask_both_actual_fixture_results(self):
        self.metadata_failure = True
        result = probe.verify(self.source, self.output, runner=self.runner, platform='darwin')
        self.assertEqual(result['status'], 'fixture_or_metadata_failure')
        self.assertTrue(result['phases']['debug']['passed']); self.assertTrue(result['phases']['release']['passed'])

    def test_timeout_is_joined_and_recorded_without_masking_by_release(self):
        self.debug_outcome = 'timeout'
        result = probe.verify(self.source, self.output, runner=self.runner, platform='darwin')
        self.assertEqual(result['status'], 'fixture_or_metadata_failure')
        self.assertEqual(result['phases']['debug']['supervisor_status']['outcome'], 'timeout')
        self.assertTrue(result['phases']['release']['passed'])
        self.assertTrue(result['scratch_removed_after_join'])

    def test_incomplete_join_stops_all_later_phases_and_retains_owned_scratch(self):
        self.debug_outcome = 'cleanup_incomplete'
        result = probe.verify(self.source, self.output, runner=self.runner, platform='darwin')
        self.assertEqual(result['status'], 'cleanup_incomplete'); self.assertEqual(len(self.commands), 1)
        self.assertFalse(result['scratch_removed_after_join']); self.assertTrue(Path(result['retained_scratch']).is_dir())

    def test_malformed_sidecar_never_allows_scratch_deletion(self):
        def malformed(command, **options):
            self.runner(command, **options)
            log = options['log']
            log.with_name(log.name + '.status.json').write_text('{partial')
            raise ValueError('injected interrupted status write')
        result = probe.verify(self.source, self.output, runner=malformed, platform='darwin')
        self.assertEqual(result['status'], 'cleanup_incomplete')
        self.assertFalse(result['scratch_removed_after_join'])
        self.assertTrue(Path(result['retained_scratch']).is_dir())
        self.assertEqual(len(self.commands), 1)

    def test_unreadable_sidecar_never_allows_scratch_deletion(self):
        original = Path.read_bytes
        def unreadable(path):
            if path.name.endswith('.status.json'): raise OSError('injected unreadable sidecar')
            return original(path)
        with patch.object(Path, 'read_bytes', unreadable):
            result = probe.verify(self.source, self.output, runner=self.runner, platform='darwin')
        self.assertEqual(result['status'], 'cleanup_incomplete')
        self.assertFalse(result['scratch_removed_after_join'])
        self.assertTrue(Path(result['retained_scratch']).is_dir())
        self.assertEqual(len(self.commands), 1)

    def test_pid_absence_is_not_used_as_proof_no_child_was_created(self):
        def incomplete(command, **options):
            self.runner(command, **options)
            log = options['log']
            log.with_name(log.name + '.status.json').write_text(json.dumps({
                'outcome': 'supervision_error', 'elapsed_seconds': 0, 'cleanup': None, 'returncode': None
            }))
            raise ValueError('injected setup and cleanup failure')
        result = probe.verify(self.source, self.output, runner=incomplete, platform='darwin')
        self.assertEqual(result['status'], 'cleanup_incomplete')
        self.assertFalse(result['scratch_removed_after_join'])
        self.assertEqual(len(self.commands), 1)

    def test_exit_exception_after_success_sidecar_is_still_terminal(self):
        for number, exception in enumerate([KeyboardInterrupt, SystemExit]):
            with self.subTest(exception=exception.__name__):
                self.commands = []
                def exiting(command, **options):
                    self.runner(command, **options)
                    raise exception()
                result = probe.verify(self.source, self.base / ('exit-report-' + str(number)), runner=exiting, platform='darwin')
                self.assertEqual(result['status'], 'interrupted')
                self.assertEqual(len(self.commands), 1)
                self.assertTrue(result['scratch_removed_after_join'])
                self.assertTrue(result['phases']['debug']['interrupted_exception'])

    def test_scratch_removal_failure_preserves_the_final_report(self):
        with patch.object(probe.shutil, 'rmtree', side_effect=OSError('injected removal failure')):
            result = probe.verify(self.source, self.output, runner=self.runner, platform='darwin')
        self.assertEqual(result['status'], 'scratch_cleanup_failure')
        self.assertTrue((self.output / 'report.json').is_file())
        self.assertTrue(result['phases']['debug']['passed'])
        self.assertFalse(result['scratch_removed_after_join'])
        self.assertTrue(Path(result['retained_scratch']).is_dir())

    def test_signal_interruption_does_not_start_a_release_command(self):
        self.debug_outcome = 'interrupted'
        result = probe.verify(self.source, self.output, runner=self.runner, platform='darwin')
        self.assertEqual(result['status'], 'interrupted'); self.assertEqual(len(self.commands), 1)
        self.assertTrue(result['scratch_removed_after_join'])

    @unittest.skipUnless(os.name == 'posix', 'supervisor requires POSIX process groups')
    def test_exact_supervisor_snapshot_joins_an_actual_local_python_fixture(self):
        folder = self.base / 'supervisor'; folder.mkdir()
        for name in ['bounded_process.py', 'apply_patch.py']:
            shutil.copyfile(self.source / 'Integration/Dependencies/idevice' / name, folder / name)
        capture = probe.load_supervisor(folder)
        log = self.base / 'supervisor.log'
        capture([sys.executable, '-c', 'print("synthetic supervision fixture")'], source=self.source,
                env=os.environ.copy(), log=log, timeout_seconds=3, max_log_bytes=4096, tail_bytes=4096,
                term_grace_seconds=1, kill_join_seconds=1)
        status = json.loads(log.with_name(log.name + '.status.json').read_text())
        self.assertEqual(status['outcome'], 'success')
        self.assertEqual(status['cleanup']['direct_child_reaped'], True)
        self.assertEqual(status['cleanup']['group_empty'], True)

    def test_non_macos_is_explicit_not_swift_success(self):
        result = probe.verify(self.source, self.output, runner=self.runner, platform='linux')
        self.assertEqual(result['status'], 'unsupported_platform'); self.assertEqual(self.commands, [])


if __name__ == '__main__': unittest.main()
