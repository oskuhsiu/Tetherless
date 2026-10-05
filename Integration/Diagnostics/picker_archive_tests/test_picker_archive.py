"""Portable contracts; passing these tests does not decode an Apple archive."""
import contextlib
from datetime import datetime
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('picker_archive', ROOT / 'picker_archive.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def event(**overrides):
    result = {'timestamp': '2026-10-05 10:55:46.100000+0000', 'processID': 22858,
              'subsystem': 'com.apple.DocumentManager',
              'eventMessage': 'navigation request; enumerate root folder; Error Domain=NSFileProviderErrorDomain Code=-1005'}
    result.update(overrides)
    return result


def lines(*records):
    return ('\n'.join(json.dumps(x) for x in records) + '\n').encode()


def archive(extra=None, owner=None):
    output = io.BytesIO()
    contents = {
        'native-ui.xcresult/Info.plist': b'fixture result',
        'native-ui.xcresult/Data/data.fixture': b'fixture payload',
        'native-simulator-owner.json': json.dumps(owner or {'id': m.DEVICE, 'sourceCommit': m.SOURCE_SHA,
            'runtime': 'com.apple.CoreSimulator.SimRuntime.iOS-26-2'}).encode(),
        'native-launch-evidence.json': json.dumps({'sourceCommit': m.SOURCE_SHA,
            'simulatorID': m.DEVICE, 'bundleID': m.BUNDLE}).encode(),
        'unrelated.log': b'never extract me',
    }
    with zipfile.ZipFile(output, 'w') as z:
        for name, data in contents.items():
            z.writestr(name, data)
        if extra:
            for name, data in extra:
                z.writestr(name, data)
    return output.getvalue()


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def extract(self, data, name='out'):
        return m.extract_result(data, self.base / name,
                                expected_sha=m.sha(data), expected_bytes=len(data))

    def test_exact_archive_and_selected_input_bytes(self):
        result, before = self.extract(archive())
        self.assertEqual((result / 'Data/data.fixture').read_bytes(), b'fixture payload')
        self.assertEqual(before['files'], 2)
        self.assertFalse((result.parent / 'unrelated.log').exists())
        (result / 'Data/data.fixture').write_bytes(b'changed')
        self.assertNotEqual(m.tree_manifest(result.parent), before)

    def test_wrong_digest_refuses_before_extraction(self):
        data = archive()
        with self.assertRaisesRegex(ValueError, 'artifact_identity'):
            m.extract_result(data, self.base / 'out')
        self.assertFalse((self.base / 'out').exists())

    def test_zip_paths_and_symlinks_rejected(self):
        for i, name in enumerate(('../escape', '/absolute', 'native-ui.xcresult/../bad', 'bad\\path', './dot')):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.extract(archive([(name, b'bad')]), str(i))
        link = zipfile.ZipInfo('native-ui.xcresult/evil')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaises(ValueError):
            self.extract(archive([(link, b'/private/secret')]), 'link')

    def test_duplicate_and_mixed_identity_rejected(self):
        with self.assertRaises(ValueError):
            self.extract(archive([('native-ui.xcresult/Data/data.fixture', b'override')]))
        with self.assertRaisesRegex(ValueError, 'owned_identity'):
            self.extract(archive(owner={'id': 'other'}), 'mixed')

    def test_tree_total_is_enforced_before_reading_excess_bytes(self):
        tree = self.base / 'tree'; tree.mkdir()
        (tree / 'one').write_bytes(b'a')
        (tree / 'two').write_bytes(b'b')
        with mock.patch.object(m, 'MAX_TOTAL', 1), mock.patch.object(m, 'regular', wraps=m.regular) as reader:
            with self.assertRaisesRegex(ValueError, 'tree_limit'):
                m.tree_manifest(tree)
            self.assertEqual(reader.call_count, 1)

    def test_member_byte_cap(self):
        with mock.patch.object(m, 'MAX_FILE', 1), self.assertRaises(ValueError):
            self.extract(archive())

    def test_regular_file_rejects_symlink_and_growth_limit(self):
        (self.base / 'file').write_bytes(b'test')
        (self.base / 'link').symlink_to(self.base / 'file')
        with self.assertRaises(ValueError):
            m.regular(self.base / 'link', 100)
        with self.assertRaises(ValueError):
            m.regular(self.base / 'file', 1)

    def test_closed_output_does_not_publish_payload_paths_addresses_or_ids(self):
        private = '/Users/alice/Documents/key.plist alice@example.com 10.11.12.13 12345678-1234-1234-1234-123456789abc token=not-a-real-secret'
        msg = event()['eventMessage'] + ' ' + private + ' <private>'
        value = m.sanitize_events(lines(event(eventMessage=msg)))
        text = json.dumps(value)
        for secret in private.split():
            self.assertNotIn(secret, text)
        row = value['events'][0]
        self.assertTrue(row['privateMarkerPresent'])
        self.assertEqual(row['messageSHA256'], m.sha(msg.encode()))
        self.assertEqual(row['errorCodes'], [{'domain': 'NSFileProviderErrorDomain', 'code': -1005}])
        self.assertIn('enumerationMention', row['classes'])
        self.assertNotIn('completed', row)

    def test_unknown_domains_stay_unprinted(self):
        value = m.sanitize_events(lines(event(eventMessage='Error Domain=alice.private.internal Code=-12')))
        self.assertNotIn('alice.private', json.dumps(value))
        self.assertIn('unlistedErrorDomain', value['events'][0]['classes'])

    def test_scope_rejects_unowned_pid_subsystem_and_shared_daemon_noise(self):
        for record in (event(processID=99), event(processID=True),
                       event(subsystem='com.apple.accounts'),
                       event(processID=12472, eventMessage='enumerating someone else')):
            with self.subTest(record=record):
                result = m.sanitize_events(lines(record))
                self.assertFalse(result['events'])
                self.assertTrue(result['gaps'])
        result = m.sanitize_events(lines(event(processID=12472,
            subsystem='com.apple.FileProvider', eventMessage='com.apple.FileProvider.LocalStorage enumerate')))
        self.assertEqual(result['events'][0]['processRole'], 'fileprovider')

    def test_timestamps_are_aware_and_within_exact_window(self):
        for timestamp in ('2026-10-05 10:54:57+0000', '2026-10-05 10:55:57.001+0000',
                          '2026-10-05 10:55:46', 'not-a-time'):
            self.assertTrue(m.sanitize_events(lines(event(timestamp=timestamp)))['gaps'])
        for timestamp in (m.START, m.END):
            self.assertFalse(m.sanitize_events(lines(event(timestamp=timestamp)))['gaps'])

    def test_empty_malformed_truncated_and_excess_records_are_gaps(self):
        for raw in (b'', b'[]\n', b'{"eventMessage":', b'Warning: clock changed\n'):
            self.assertTrue(m.sanitize_events(raw)['gaps'])
        with mock.patch.object(m, 'MAX_EVENTS', 1):
            self.assertIn('event_limit', m.sanitize_events(lines(event(), event()))['gaps'])

    def test_error_code_omissions_are_explicit_gaps(self):
        message = ' '.join('Error Domain=NSPOSIXErrorDomain Code=1' for _ in range(17))
        result = m.sanitize_events(lines(event(eventMessage=message)))
        self.assertEqual(result['events'][0]['omittedErrorCodeCount'], 1)
        self.assertIn('error_code_limit', result['gaps'])

    def test_no_unreviewed_predicate_field(self):
        with self.assertRaises(ValueError):
            m.query_predicate('process OR true')
        query = m.query_predicate('processIdentifier')
        for pid in m.PIDS:
            self.assertIn(str(pid), query)
        self.assertNotIn('accounts', query)
        self.assertNotIn('apsd', query)

    def test_supervisor_is_byte_pinned_and_real_process_group_is_joined(self):
        # Normal repository layout; local candidate review can point at its base.
        source = Path(os.environ.get('PICKER_ARCHIVE_SOURCE_ROOT', ROOT.parents[1]))
        if not (source / 'Integration/Dependencies/idevice/bounded_process.py').is_file():
            self.skipTest('reviewed repository supervisor is not in this candidate-only tree')
        scratch = self.base / 'private'; scratch.mkdir()
        run = m.load_supervisor(source, scratch)
        log = scratch / 'probe.raw'
        run([sys.executable, '-c', 'print("synthetic")'], source=scratch, env=dict(os.environ), log=log,
            timeout_seconds=3, max_log_bytes=100, tail_bytes=1, term_grace_seconds=1, kill_join_seconds=1)
        status = json.loads(log.with_name(log.name + '.status.json').read_text())
        self.assertTrue(status['output_complete'])
        self.assertTrue(status['cleanup']['direct_child_reaped'])
        self.assertTrue(status['cleanup']['group_empty'])


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.input = self.base / 'download'; self.input.mkdir()
        self.data = archive(); (self.input / 'artifact.zip').write_bytes(self.data)
        self.info = plistlib.dumps({'ArchiveIdentifier': m.ARCHIVE_ID})
        self.calls = []
        self.fault = None
        self.help64 = False
        self.scratch = None

    def tearDown(self):
        self.temp.cleanup()
        if self.scratch is not None and self.scratch.exists():
            # These paths belong only to our synthetic runner, never an Apple child.
            shutil.rmtree(self.scratch)

    def runner(self, command, **options):
        self.calls.append(command)
        self.scratch = options['source']
        phase = options['log'].stem
        output = b''
        if phase == 'exportHelp': output = b'--path --output-path --id --type directory --legacy'
        elif phase == 'logShowHelp': output = b'<archive> --start --end --style ndjson --timezone --predicate --[no-]info --[no-]debug'
        elif phase == 'predicateHelp': output = b'processIdentifier'
        elif phase == 'exportOwnedArchive':
            folder = Path(command[command.index('--output-path') + 1]); folder.mkdir()
            (folder / 'Info.plist').write_bytes(self.info)
            (folder / 'log.tracev3').write_bytes(b'synthetic log')
        elif phase == 'scopedArchiveQuery': output = lines(event())
        status = {'outcome': 'success', 'returncode': 0, 'output_truncated': False,
                  'output_complete': True, 'stop_reason': None, 'elapsed_seconds': 0.01,
                  'cleanup': {'direct_child_reaped': True, 'group_empty': True}}
        if self.help64 and phase == 'logShowHelp':
            status.update(outcome='nonzero_exit', returncode=64, output_complete=False, stop_reason='nonzero_exit')
        if self.fault == 'malformed_status':
            options['log'].write_bytes(b'')
            options['log'].with_name(options['log'].name + '.status.json').write_bytes(b'{')
            raise ValueError('synthetic status failure')
        if phase == self.fault:
            status.update(outcome='output_limit', output_complete=False, output_truncated=True,
                          returncode=-15, stop_reason='output_limit')
        options['log'].write_bytes(output)
        options['log'].with_name(options['log'].name + '.status.json').write_text(json.dumps(status))
        if status['outcome'] != 'success':
            raise ValueError('synthetic raw error /private/not-for-report')
        return ''

    def analyze(self):
        original = m.extract_result
        def selected(data, dest):
            return original(data, dest, expected_sha=m.sha(self.data), expected_bytes=len(self.data))
        result_rows = [['native-ui.xcresult/Data/data.fixture', 15, m.sha(b'fixture payload')],
                       ['native-ui.xcresult/Info.plist', 14, m.sha(b'fixture result')]]
        archive_rows = [['Info.plist', len(self.info), m.sha(self.info)],
                        ['log.tracev3', 13, m.sha(b'synthetic log')]]
        def manifest(rows):
            return {'files': len(rows), 'bytes': sum(r[1] for r in rows),
                    'sha256': m.sha(json.dumps(rows, separators=(',', ':')).encode())}
        with mock.patch.object(m, 'extract_result', selected), mock.patch.object(m, 'INFO_SHA', m.sha(self.info)), \
                mock.patch.object(m, 'EXPECTED_RESULT_TREE', manifest(result_rows)), \
                mock.patch.object(m, 'EXPECTED_ARCHIVE_TREE', manifest(archive_rows)):
            return m.analyze(self.input, self.base, self.base / 'report', runner=self.runner, platform='darwin')

    def test_complete_offline_sequence_has_no_simulator_or_privacy_mutation(self):
        result = self.analyze()
        self.assertTrue(result['collectionComplete'])
        self.assertEqual(result['status'], 'complete')
        self.assertFalse(result['rootCauseInferred'])
        self.assertFalse(result['productAccepted'])
        flat = ' '.join(' '.join(c) for c in self.calls)
        for forbidden in ('simctl', 'boot', '--privacy', 'config', 'sudo', 'xcodebuild', 'diagnostics'):
            self.assertNotIn(forbidden, flat)
        self.assertIn(m.ARCHIVE_REF, flat)
        query = self.calls[-1]
        self.assertEqual(query[query.index('--start') + 1], m.START)
        self.assertEqual(query[query.index('--end') + 1], m.END)
        self.assertTrue(query[-1].endswith('/owned.logarchive'))
        self.assertTrue(result['temporaryCleanupConfirmed'])
        self.assertEqual([p.name for p in (self.base / 'report').iterdir()], ['report.json'])
        self.assertNotIn('/private/not-for-report', json.dumps(result))

    def test_help_usage_exit_is_not_misreported_complete(self):
        self.help64 = True
        result = self.analyze()
        phase = result['phases']['logShowHelp']
        self.assertTrue(phase['helpUsageExitAcceptedForSyntaxOnly'])
        self.assertFalse(phase['outputComplete'])
        self.assertEqual(result['status'], 'complete')

    def test_capped_query_stays_incomplete_and_no_raw_text_is_exported(self):
        self.fault = 'scopedArchiveQuery'
        result = self.analyze()
        self.assertFalse(result['collectionComplete'])
        self.assertNotIn('events', result)
        self.assertEqual(result['status'], 'gaps')
        self.assertNotIn('/private/not-for-report', json.dumps(result))

    def test_unreadable_supervisor_status_retains_unjoined_scratch(self):
        self.fault = 'malformed_status'
        result = self.analyze()
        self.assertFalse(result['temporaryCleanupConfirmed'])
        self.assertTrue(self.scratch.exists())
        self.assertIn('supervised_cleanup_unconfirmed', result['gaps'])
        self.assertEqual(len(self.calls), 1)

    def test_native_export_failure_stops_before_log_query(self):
        self.fault = 'exportOwnedArchive'
        result = self.analyze()
        self.assertFalse(result['collectionComplete'])
        self.assertNotIn('scopedArchiveQuery', result['phases'])

    def test_extra_download_and_unsupported_platform_do_not_run_tools(self):
        (self.input / 'extra').write_bytes(b'x')
        result = self.analyze()
        self.assertEqual(result['status'], 'gaps')
        self.assertEqual(self.calls, [])
        result = m.analyze(self.input, self.base, self.base / 'linux-report', runner=self.runner, platform='linux')
        self.assertEqual(result['status'], 'gaps')
        self.assertEqual(self.calls, [])


class WorkflowTests(unittest.TestCase):
    def test_workflow_is_exact_branch_read_only_and_uploads_one_sanitized_file(self):
        workflow = ROOT.parents[1] / '.github/workflows/picker-archive.yml'
        text = workflow.read_text()
        for value in ('branches: [verify/staged-pairing-native]', "github.ref == 'refs/heads/verify/staged-pairing-native'",
                      'contents: read', 'actions: read', 'persist-credentials: false', 'submodules: false',
                      'skip-decompress: true', 'digest-mismatch: error', "artifact-ids: '11341735733'",
                      'run-id: 37298228388', 'download-artifact@70fc10c6e5e1ce46ad2ea6f2b72d43f7d47b13c3',
                      'path: ${{ runner.temp }}/picker-archive-report/report.json'):
            self.assertIn(value, text)
        for value in ('pull_request:', 'develop]', 'contents: write', 'actions: write', 'simctl', '--private'):
            self.assertNotIn(value, text)


if __name__ == '__main__':
    unittest.main()
