import importlib.util
import json
import plistlib
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'run_diagnostic.py'
spec = importlib.util.spec_from_file_location('packaging_diagnostic_test_subject', SOURCE)
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


class DiagnosticTests(unittest.TestCase):
    def test_group_is_only_taken_from_the_exact_running_command(self):
        command = ['/usr/bin/xcodebuild', '-create-xcframework']
        base = {'outcome': 'running', 'pid': 123, 'process_group': 123, 'command': command}
        self.assertEqual(subject.owned_group(base, command), 123)
        for update in [{'pid': True}, {'pid': 1}, {'process_group': 124}, {'command': ['other']}]:
            with self.assertRaises(subject.DiagnosticError):
                subject.owned_group(dict(base, **update), command)
        self.assertIsNone(subject.owned_group(dict(base, outcome='success'), command))
        self.assertIsNone(subject.owned_group(None, command))

    def test_ps_selects_only_group_and_never_arguments_or_environment(self):
        command = subject.ps_command(123)
        self.assertEqual(command, ['/bin/ps', '-c', '-x', '-g', '123', '-o',
                                   'pid=,ppid=,pgid=,state=,lstart=,comm='])
        self.assertNotIn('-A', command)
        self.assertNotIn('-E', command)
        self.assertNotIn('args', command[-1])
        for group in [True, 0, -1, '123']:
            with self.assertRaises(subject.DiagnosticError): subject.ps_command(group)

    def test_rows_retain_start_state_and_only_the_selected_group(self):
        text = '123 77 123 Ss Tue Oct 6 00:00:00 2026 xcodebuild\n124 123 123 Z Tue Oct 6 00:00:01 2026 helper\n'
        rows = subject.parse_rows(text, 123)
        self.assertEqual(rows[1]['state'], 'Z')
        self.assertEqual(rows[0]['start_text'], 'Tue Oct 6 00:00:00 2026')
        self.assertEqual(rows[1]['executable_name'], 'helper')
        with self.assertRaises(subject.DiagnosticError): subject.parse_rows(text, 999)
        with self.assertRaises(subject.DiagnosticError): subject.parse_rows('bad row', 123)
        with self.assertRaises(subject.DiagnosticError): subject.parse_rows(text * 129, 123)

    def test_partial_status_is_not_group_absence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'status.json'
            self.assertIsNone(subject.read_status(path))
            path.write_text('{"outcome":')
            self.assertIsNone(subject.read_status(path))
            path.write_text(json.dumps({'outcome': 'running'}))
            self.assertEqual(subject.read_status(path), {'outcome': 'running'})
            link = path.with_name('link.json'); link.symlink_to(path)
            with self.assertRaises(subject.DiagnosticError): subject.read_status(link)

    def sample(self, rows, *, query_outcome='success', code=0, cleanup=True):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        package = root / 'package.txt'
        command = ['/usr/bin/xcodebuild', '-create-xcframework']
        subject.status_for(package).write_text(json.dumps({
            'outcome': 'running', 'pid': 123, 'process_group': 123, 'command': command}))
        stop = threading.Event(); observations = []; errors = []
        def capture(argv, **kwargs):
            self.assertEqual(argv, subject.ps_command(123))
            log = kwargs['log']; log.parent.mkdir(parents=True, exist_ok=True); log.write_text(rows)
            subject.status_for(log).write_text(json.dumps({
                'outcome': query_outcome, 'returncode': code,
                'cleanup': {'direct_child_reaped': cleanup, 'group_empty': cleanup}}))
            stop.set()
            if query_outcome != 'success': raise RuntimeError('controlled query failure')
        subject.sample_group(capture, command=command, package_log=package, work=root, output=root,
                             environment={}, stop=stop, observations=observations, owner_pid=77, errors=errors)
        return observations, errors

    def test_observer_records_owned_rows_after_join(self):
        observations, errors = self.sample('123 77 123 Ss Tue Oct 6 00:00:00 2026 xcodebuild\n')
        self.assertEqual(errors, [])
        self.assertEqual(observations[0]['members'][0]['ppid'], 77)
        self.assertTrue(observations[0]['root_identity_observed'])

    def test_unjoined_query_is_failure(self):
        observations, errors = self.sample('', cleanup=False)
        self.assertEqual(observations, [])
        self.assertEqual(errors, ['DiagnosticError'])

    def test_unexpected_group_leader_is_not_accepted(self):
        observations, errors = self.sample('123 88 123 Ss Tue Oct 6 00:00:00 2026 other\n')
        self.assertEqual(observations, [])
        self.assertEqual(errors, ['DiagnosticError'])

    def test_empty_ps_result_is_not_claimed_as_supervisor_empty_proof(self):
        observations, errors = self.sample('', query_outcome='nonzero_exit', code=1)
        self.assertEqual(observations[0]['members'], [])
        self.assertEqual(errors, ['group_leader_identity_not_observed'])

    def test_original_helper_is_not_monkeypatched_or_success_redefined(self):
        source = SOURCE.read_text()
        self.assertNotIn('subprocess.Popen', source)
        self.assertNotIn('os.kill', source)
        self.assertIn('raise primary_error', source)
        self.assertIn("'output_complete=false is outcome-derived, not independent pipe-EOF evidence.'", source)
        self.assertIn("'accepted_idevice_artifact': False", source)
        self.assertIn('daemon=False', source)
        self.assertIn('observer.join(timeout=5)', source)

    def test_package_environment_matches_real_four_key_boundary(self):
        environment = subject.packaging_environment(Path('/owned'), '/Applications/Xcode_26.3.app/Contents/Developer')
        self.assertEqual(set(environment), {'PATH', 'HOME', 'TMPDIR', 'DEVELOPER_DIR'})
        self.assertEqual(environment['HOME'], '/owned/aarch64-apple-ios/home')
        self.assertEqual(environment['TMPDIR'], '/owned/aarch64-apple-ios/tmp')
        self.assertNotIn('COMMAND_MODE', environment)
        self.assertNotIn('GITHUB_TOKEN', environment)
        with self.assertRaises(subject.DiagnosticError): subject.packaging_environment(Path('/owned'), None)

    def test_tiny_package_requires_both_exact_copied_archives_and_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); package = root / 'Fixture.xcframework'; package.mkdir()
            libraries, headers, entries = [], [], []
            for index, identifier in enumerate(['ios-arm64', 'ios-arm64-simulator']):
                original = root / str(index); original.mkdir()
                library = original / 'libfixture.a'; library.write_bytes(b'toy archive ' + bytes([index]))
                header = original / 'headers'; header.mkdir(); (header / 'fixture.h').write_bytes(b'toy header')
                libraries.append(library); headers.append(header)
                target = package / identifier; target.mkdir(); (target / 'Headers').mkdir()
                (target / 'libfixture.a').write_bytes(library.read_bytes())
                (target / 'Headers/fixture.h').write_bytes((header / 'fixture.h').read_bytes())
                entry = {'LibraryIdentifier': identifier, 'LibraryPath': 'libfixture.a',
                         'HeadersPath': 'Headers', 'SupportedPlatform': 'ios',
                         'SupportedArchitectures': ['arm64']}
                if index: entry['SupportedPlatformVariant'] = 'simulator'
                entries.append(entry)
            info = package / 'Info.plist'
            def write(entries): info.write_bytes(plistlib.dumps({'AvailableLibraries': entries}))
            write(entries)
            self.assertTrue(subject.verify_tiny_package(package, libraries, headers)['copied_archives_and_headers_match'])
            for invalid in [entries[:1], [entries[0], entries[0]],
                            [dict(entries[0], LibraryIdentifier='../escape'), entries[1]],
                            [dict(entries[0], SupportedArchitectures=['x86_64']), entries[1]]]:
                write(invalid)
                with self.assertRaises(subject.DiagnosticError): subject.verify_tiny_package(package, libraries, headers)
            write(entries)
            (package / 'ios-arm64/libfixture.a').write_bytes(b'different')
            with self.assertRaises(subject.DiagnosticError): subject.verify_tiny_package(package, libraries, headers)


if __name__ == '__main__':
    unittest.main()
