"""Portable launcher/source checks; Apple executions are separate and never faked."""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('pairing_cold_read', ROOT / 'Integration/verify_pairing_cold_read.py')
cold = importlib.util.module_from_spec(spec); spec.loader.exec_module(cold)


class PairingColdReadTests(unittest.TestCase):
    def test_all_production_and_parser_inputs_are_frozen(self):
        lock, frozen = cold.inputs(ROOT)
        self.assertEqual(lock['source_commit'], '4838168e2692e087b0465fca349f4cba8704011d')
        self.assertEqual(lock['upstream_revision'], '12be70dc2627307a16bfd2dc7a009080d5bec909')
        self.assertEqual(len(lock['upstream']), 4)
        for source in lock['upstream']:
            data = frozen[source['path']]
            self.assertEqual(hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(), source['git_blob_sha1'])
        parser = frozen['Integration/fixtures/ColdPairingParser/PairingFile.swift'].decode()
        self.assertIn('public enum PairingFileParser', parser)
        self.assertIn('self.rawData = data', parser)
        self.assertNotIn('PropertyListSerialization.data(', parser)

    def test_external_seams_and_nonclaims_are_explicit(self):
        support = (ROOT / 'Integration/fixtures/PairingColdReadSupport.swift').read_text()
        main = (ROOT / 'Integration/fixtures/PairingColdReadMain.swift').read_text()
        self.assertIn('not CFPreferences', support)
        self.assertIn('actual IdeviceGateway is deliberately not compiled', support)
        self.assertIn('PairingFileParser.parse(content: content, preferred: preferred)', support)
        for forbidden in ['class PairingFileManager', 'enum PairingFileParser', 'enum PairingProtocol',
                          'struct PairingRecord', 'struct PrivateFileStore']:
            self.assertNotIn(forbidden, support + main)
        self.assertIn('saveValidatedRemotePairingRecord(record)', main)
        self.assertIn('remote.privateKey == privateKey && remote.publicKey == publicKey', main)
        self.assertIn('remote.rawData == Data(input.utf8)', main)
        self.assertIn('unrecognized-raw-value', main)
        cases = set(re.findall(r'"([a-z_]+)"', main))
        self.assertTrue(set(cold.SCENARIOS) <= cases)
        # Separate exact-save fixture stays present and remains explicitly stubbed.
        existing = (ROOT / 'Integration/fixtures/PairingGeneratedPromotionMain.swift').read_text()
        self.assertIn('testJoinedPromotionBorrowsOuterLeaseAndSavesExactBytes', existing)

    def test_unsupported_platform_is_unrun(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'evidence'
            report = cold.verify(ROOT, output, platform='linux')
            self.assertEqual(report['status'], 'unsupported_platform')
            self.assertFalse(report['native_execution'])
            self.assertEqual(report['phases'], {})
            self.assertEqual(json.loads((output / 'report.json').read_text()), report)

    @staticmethod
    def runner(calls, *, bad_reader=False, unjoined=False):
        def run(command, *, source, env, log, **kwargs):
            calls.append((list(command), dict(env)))
            lines = ''
            if len(command) == 3 and command[1] in ('write', 'read'):
                label = 'written=' if command[1] == 'write' else 'passed='
                lines = 'pairing_cold_fixture ' + label + command[2] + '\n'
                if bad_reader and command[1] == 'read': lines = 'SKIPPED\n'
            log.write_text(lines)
            status = {'outcome': 'success', 'returncode': 0, 'output_complete': True,
                      'cleanup': {'direct_child_reaped': True, 'group_empty': not unjoined}}
            log.with_name(log.name + '.status.json').write_text(json.dumps(status))
        return run

    def test_launcher_joins_writer_before_distinct_reader_in_both_configurations(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            report = cold.verify(ROOT, Path(directory) / 'evidence', platform='darwin', runner=self.runner(calls))
            self.assertEqual(report['status'], 'injected_runner_passed')
            self.assertFalse(report['native_execution'])
            self.assertTrue(report['scratch_removed_after_join'])
            self.assertEqual(len(report['phases']), 4 + 4 * len(cold.SCENARIOS))
            executions = [(cmd, env) for cmd, env in calls if len(cmd) == 3]
            self.assertEqual(len(executions), 4 * len(cold.SCENARIOS))
            roots = []
            for index in range(0, len(executions), 2):
                (write, write_env), (read, read_env) = executions[index:index + 2]
                self.assertEqual(write[1], 'write'); self.assertEqual(read[1], 'read')
                self.assertEqual(write[0], read[0]); self.assertEqual(write[2], read[2])
                self.assertEqual(write_env['TETHERLESS_COLD_PAIRING_ROOT'], read_env['TETHERLESS_COLD_PAIRING_ROOT'])
                roots.append(write_env['TETHERLESS_COLD_PAIRING_ROOT'])
            self.assertEqual(len(roots), len(set(roots)))
            common_compiles = [cmd for cmd, _ in calls if '-emit-library' in cmd]
            self.assertEqual(len(common_compiles), 2)
            for cmd in common_compiles:
                self.assertEqual(len([arg for arg in cmd if arg.endswith('.swift')]), 4)
                self.assertTrue(any(arg.endswith('/PairingFile.swift') for arg in cmd))

    def test_zero_exit_with_skip_cannot_pass_or_continue(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            report = cold.verify(ROOT, Path(directory) / 'evidence', platform='darwin', runner=self.runner(calls, bad_reader=True))
            self.assertEqual(report['status'], 'fixture_or_input_failure')
            self.assertFalse(report['native_execution'])
            self.assertEqual(len(calls), 4)
            self.assertFalse(report['phases']['debug-remote_identity-read']['passed'])

    def test_unjoined_process_retains_scratch_and_blocks_next_phase(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            report = cold.verify(ROOT, Path(directory) / 'evidence', platform='darwin', runner=self.runner(calls, unjoined=True))
            self.assertEqual(report['status'], 'cleanup_incomplete')
            self.assertFalse(report['scratch_removed_after_join'])
            self.assertEqual(len(calls), 1)
            retained = Path(report['retained_scratch'])
            self.assertTrue(retained.is_dir())
            # This runner is a pure Python test double and created no process.
            import shutil
            shutil.rmtree(retained)

    def test_evidence_output_must_be_new_and_not_an_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            alias = parent / 'alias'; alias.symlink_to(ROOT, target_is_directory=True)
            with self.assertRaises(ValueError): cold.verify(ROOT, parent, platform='linux')
            with self.assertRaises(ValueError): cold.verify(ROOT, alias / 'evidence', platform='linux')

    @unittest.skipUnless(sys.platform == 'darwin', 'UNRUN: actual manager/parser fixtures require Apple Foundation/UniformTypeIdentifiers')
    def test_actual_cold_reader_debug_and_optimized(self):
        # The explicit standalone launcher retains fixed logs and source hashes.
        # Ordinary test discovery uses a private temporary evidence directory.
        with tempfile.TemporaryDirectory() as directory:
            report = cold.verify(ROOT, Path(directory) / 'evidence')
            self.assertEqual(report['status'], 'passed')
            self.assertTrue(report['native_execution'])


if __name__ == '__main__': unittest.main()
