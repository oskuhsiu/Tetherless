"""Synthetic exact-event/privacy tests. No Apple tools or archive queries."""
from datetime import datetime
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('picker_event', ROOT / 'picker_archive_event.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
MESSAGE = 'navigation timed out for an intentionally private synthetic name'
ACTIVITY = 1234


def event(**changes):
    r = {'timestamp': m.TARGET_TIME, 'processID': m.TARGET_PID,
         'subsystem': 'com.apple.DocumentManager', 'eventMessage': MESSAGE,
         'activityIdentifier': ACTIVITY, 'formatString': 'Navigation timed out while waiting for root item %{private}@'}
    r.update(changes)
    return r


def encode(*events):
    return ('\n'.join(json.dumps(e) for e in events) + '\n').encode()


class PrivacyTests(unittest.TestCase):
    def test_template_keeps_operation_but_never_dynamic_message(self):
        r = m.event_details(event())
        self.assertEqual(r['reportedOperations'], ['navigation'])
        self.assertTrue(r['timeoutExplicitInTemplate'])
        self.assertIn('<value>', r['staticFormat']['template'])
        self.assertNotIn('synthetic name', json.dumps(r))

    def test_unrecognized_prefixes_do_not_authorize_disclosure(self):
        r = m.event_details(event(formatString='Navigation DOCSecretTokenAbc failed',
            eventMessage='Error Domain=NSSecretTokenAbcErrorDomain Code=7'))
        self.assertNotIn('DOCSecretTokenAbc', json.dumps(r))
        self.assertNotIn('NSSecretTokenAbcErrorDomain', json.dumps(r))
        self.assertEqual(r['technicalErrors'], [])
        self.assertEqual(r['unretainedDomainCount'], 1)

    def test_supported_static_framework_identifiers_are_exact(self):
        r = m.redact_template('NSFileCoordinator failed waiting for DOCNodeCollectionDelegate')
        self.assertIn('NSFileCoordinator', r['technicalSymbols'])
        self.assertIn('DOCNodeCollectionDelegate', r['technicalSymbols'])
        self.assertIn('DOCNodeCollectionDelegate', r['template'])

    def test_printf_tokenizer_elides_supported_forms_and_rejects_unknown(self):
        r = m.redact_template('navigation %1$*2$.*3$f %{private}@ %llu %{public,uuid_t}.16P %% failed')
        self.assertEqual(r['interpolatedValueCount'], 4)
        for s in ('navigation %Q failed', 'navigation %', 'navigation %{private', 'navigation %999'):
            self.assertIsNone(m.redact_template(s))

    def test_escaped_and_balanced_payload_delimiters_are_elided(self):
        for payload in ('"private \\" DOCSecretTokenAbc \\" data"', "'navigation timed out'",
                        '`navigation timed out`', '<navigation timed out>', '{payload:{navigation:timeout}}',
                        '“navigation timed out”'):
            r = m.redact_template('operation ' + payload)
            self.assertIsNotNone(r)
            self.assertNotIn('navigation', r['template'].lower())
            self.assertNotIn('DOCSecretTokenAbc', r['template'])

    def test_unbalanced_payload_delimiters_fail_closed(self):
        for s in ('operation "navigation failed', "operation 'navigation failed", 'operation `navigation failed',
                  'operation <navigation failed', 'operation {navigation failed', 'operation “navigation failed'):
            self.assertIsNone(m.redact_template(s))

    def test_embedded_quotes_are_not_contractions_and_negation_survives(self):
        value = m.redact_template("operation a'navigation timed out'file")
        self.assertNotIn('navigation', value['template'])
        self.assertNotIn('timeout', value['template'])
        value = m.redact_template("can't navigate and don't retry")
        self.assertIn('cannot navigate', value['template'])
        self.assertIn('do not retry', value['template'])
        self.assertEqual(m.event_details(event(formatString="operation a'navigation timed out'file"))['status'], 'inconclusive')

    def test_literal_credentials_paths_addresses_payloads_and_names_are_removed(self):
        samples = ['password=navigation private token; operation failed',
                   'operation /Users/Alice/Navigation Root; failed',
                   'operation file:///private/key.plist failed', 'operation alice@example.com failed',
                   'operation 10.11.12.13 failed', 'operation 2001:db8::1234 failed',
                   'operation 12345678-1234-1234-1234-123456789abc failed',
                   'operation 0x123456abcdef failed', 'operation AliceBobCompany failed',
                   r'operation C:\documents\private\file; failed', 'operation documents/file; failed']
        for s in samples:
            r = m.redact_template(s)
            self.assertIsNotNone(r)
            text = r['template']
            for bad in ('Alice', 'Navigation Root', 'alice@example.com', '10.11.12.13', '2001:db8',
                        '12345678', '0x123456abcdef', 'private token', 'password'):
                self.assertNotIn(bad, text)

    def test_relative_and_windows_paths_are_elided_whole(self):
        for path in ('documents/file', r'C:\documents\private\file', '../documents/file'):
            value = m.redact_template('operation ' + path + '; failed')
            self.assertNotIn('documents', value['template'])
            self.assertNotIn('file', value['template'])
        self.assertIn('navigation', m.redact_template('NaViGaTiOn failed')['template'])
        self.assertNotIn('NaViGaTiOn', m.redact_template('NaViGaTiOn failed')['template'])

    def test_template_size_controls_and_unicode_do_not_leak(self):
        self.assertIsNone(m.redact_template('navigation\0failed'))
        self.assertIsNone(m.redact_template('x' * 9000))
        r = m.redact_template('navigation 사용자명 비밀 failed')
        self.assertNotIn('사용자', r['template'])

    def test_only_complete_recognized_error_codes_are_retained(self):
        r = m.event_details(event(formatString=None, eventMessage='Error Domain=NSCocoaErrorDomain Code=-123 (detail)'))
        self.assertEqual(r['technicalErrors'], [{'domain': 'NSCocoaErrorDomain', 'code': -123}])
        self.assertEqual(r['status'], 'classified')
        for code in ('7.123', '7/123', '7-123', '123456789012', '2147483648'):
            r = m.event_details(event(formatString=None, eventMessage='Error Domain=NSCocoaErrorDomain Code=' + code))
            self.assertFalse(r['technicalErrors'])
            self.assertEqual(r['status'], 'inconclusive')

    def test_missing_unsafe_or_irrelevant_template_is_not_raw_fallback(self):
        for fmt in (None, 'AliceBobCompany', '"navigation failed', '%Q'):
            r = m.event_details(event(formatString=fmt))
            self.assertEqual(r['status'], 'inconclusive')
            self.assertNotIn(MESSAGE, json.dumps(r))

    def test_error_detail_limit_has_no_silent_truncation(self):
        r = m.event_details(event(eventMessage=' '.join('Error Domain=NSCocoaErrorDomain Code=7' for _ in range(17))))
        self.assertEqual(r['reason'], 'error_detail_limit')


class IdentityTests(unittest.TestCase):
    def classify(self, raw):
        with mock.patch.object(m, 'TARGET_MESSAGE_SHA', m.sha(MESSAGE.encode())), \
             mock.patch.object(m, 'TARGET_ACTIVITY_SHA', m.sha(str(ACTIVITY).encode())):
            return m.identify(raw, ('com.apple.DocumentManager',))

    def test_exact_identity_is_required_before_content_is_read(self):
        self.assertEqual(self.classify(encode(event()))['status'], 'classified')
        for changed in ({'processID': True}, {'processID': 99}, {'timestamp': '2026-10-05T10:55:56+00:00'},
                        {'timestamp': '2026-10-05T10:55:56.651894'}, {'activityIdentifier': 0},
                        {'activityIdentifier': True}, {'activityIdentifier': 1235}, {'subsystem': 'com.apple.accounts'},
                        {'eventMessage': MESSAGE + ' changed'}):
            r = self.classify(encode(event(**changed)))
            self.assertEqual(r['status'], 'inconclusive')
            self.assertFalse(r['eventIdentified'])
            self.assertNotIn('staticFormat', r)

    def test_duplicate_exact_event_is_ambiguous(self):
        r = self.classify(encode(event(), event()))
        self.assertEqual(r['exactMatchCount'], 2)
        self.assertEqual(r['status'], 'inconclusive')
        self.assertNotIn('staticFormat', r)

    def test_unrelated_events_are_not_exposed(self):
        r = self.classify(encode(event(eventMessage='not-the-target-private-secret'), event()))
        self.assertEqual(r['nonmatchingRecordCount'], 1)
        self.assertNotIn('not-the-target', json.dumps(r))
        self.assertEqual(r['status'], 'classified')

    def test_unparsed_lines_prevent_unique_classification_but_provisional_detail_is_safe(self):
        r = self.classify(b'Unknown private warning /Users/Alice\n' + encode(event()))
        self.assertFalse(r['eventIdentified'])
        self.assertTrue(r['matchingEventObserved'])
        self.assertEqual(r['status'], 'inconclusive')
        self.assertEqual(r['unsupportedLineCount'], 1)
        self.assertIn('provisionalExactMatchDetails', r)
        self.assertNotIn('Alice', json.dumps(r))

    def test_line_limit_does_not_establish_a_result(self):
        with mock.patch.object(m, 'MAX_LINES', 1), self.assertRaises(ValueError):
            self.classify(encode(event(), event()))

    def test_predicate_and_window_are_narrower_than_original(self):
        query = m.predicate('processIdentifier', ('com.apple.DocumentManager',))
        self.assertIn('22858', query)
        self.assertNotIn('12472', query)
        self.assertNotIn('25024', query)
        self.assertGreater(datetime.fromisoformat(m.QUERY_START), datetime.fromisoformat('2026-10-05 10:54:58+0000'))
        self.assertEqual((datetime.fromisoformat(m.QUERY_END) - datetime.fromisoformat(m.QUERY_START)).total_seconds(), 1)
        with self.assertRaises(ValueError): m.predicate('process OR TRUE', ())


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve()
        self.source = Path(os.environ.get('PICKER_EVENT_SOURCE_ROOT', ROOT.parents[1]))

    def tearDown(self): self.temp.cleanup()

    def test_exact_helper_snapshot_and_actual_supervisor(self):
        if not (self.source / 'Integration/Diagnostics/picker_archive.py').is_file():
            self.skipTest('candidate-only tree requires assembled source-root environment')
        base = m.load_base(self.source, self.root)
        self.assertEqual(base.ARCHIVE_ID, 'A8B6986C-2BB8-45F8-B6EF-23650E916F85')
        invoke = base.load_supervisor(self.source, self.root)
        raw = self.root / 'synthetic.raw'
        invoke([sys.executable, '-c', 'print("synthetic")'], source=self.root, env=dict(os.environ),
               log=raw, timeout_seconds=3, max_log_bytes=100, tail_bytes=1, term_grace_seconds=1, kill_join_seconds=1)
        status = json.loads(raw.with_name(raw.name + '.status.json').read_text())
        self.assertTrue(status['output_complete'])
        self.assertTrue(status['cleanup']['group_empty'])

    def test_wrong_helper_is_refused_without_import(self):
        source = self.root / 'source/Integration/Diagnostics'; source.mkdir(parents=True)
        (source / 'picker_archive.py').write_text('raise RuntimeError("do not import")')
        scratch = self.root / 'scratch'; scratch.mkdir()
        with self.assertRaisesRegex(ValueError, 'helper_identity'):
            m.load_base(self.root / 'source', scratch)
        self.assertFalse((scratch / 'picker_archive_base.py').exists())


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve()
        self.source = Path(os.environ.get('PICKER_EVENT_SOURCE_ROOT', ROOT.parents[1]))
        if not (self.source / 'Integration/Diagnostics/picker_archive.py').is_file():
            self.skipTest('candidate-only tree requires assembled source-root environment')
        boot = self.root / 'boot'; boot.mkdir()
        self.base = m.load_base(self.source, boot)
        self.download = self.root / 'download'; self.download.mkdir()
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as z:
            z.writestr('native-ui.xcresult/Info.plist', b'fixture')
            z.writestr('native-simulator-owner.json', json.dumps({'id': self.base.DEVICE,
                'sourceCommit': self.base.SOURCE_SHA, 'runtime': 'com.apple.CoreSimulator.SimRuntime.iOS-26-2'}))
            z.writestr('native-launch-evidence.json', json.dumps({'simulatorID': self.base.DEVICE,
                'sourceCommit': self.base.SOURCE_SHA, 'bundleID': self.base.BUNDLE}))
        raw = data.getvalue(); (self.download / 'artifact.zip').write_bytes(raw)
        original = self.base.extract_result
        def extraction(raw, destination):
            return original(raw, destination, expected_sha=m.sha(data.getvalue()), expected_bytes=len(data.getvalue()))
        self.base.extract_result = extraction
        preview = self.root / 'preview'
        _, self.base.EXPECTED_RESULT_TREE = extraction(raw, preview)
        info = plistlib.dumps({'ArchiveIdentifier': self.base.ARCHIVE_ID})
        self.info = info
        self.base.INFO_SHA = m.sha(info)
        archive = self.root / 'archive'; archive.mkdir()
        (archive / 'Info.plist').write_bytes(info)
        (archive / 'data.tracev3').write_bytes(b'fixture')
        self.base.EXPECTED_ARCHIVE_TREE = self.base.tree_manifest(archive, exported=True)
        self.calls, self.scratch, self.fault = [], None, None
        self.raw_query = encode(event())

    def tearDown(self):
        self.temp.cleanup()
        if getattr(self, 'scratch', None) is not None and self.scratch.exists():
            # Synthetic runner only; never delete an actual unjoined process tree.
            shutil.rmtree(self.scratch)

    def runner(self, command, **kw):
        self.calls.append(command); self.scratch = kw['source']
        name = kw['log'].stem
        raw = b''
        if name == 'exportHelp': raw = b'--path --output-path --id --type directory --legacy'
        elif name == 'logHelp': raw = b'<archive> --start --end --style ndjson --timezone --predicate --[no-]info --[no-]debug'
        elif name == 'predicateHelp': raw = b'processIdentifier'
        elif name == 'exportOwnedArchive':
            archive = Path(command[command.index('--output-path') + 1]); archive.mkdir()
            (archive / 'Info.plist').write_bytes(self.info)
            (archive / 'data.tracev3').write_bytes(b'fixture')
        elif name == 'exactSecondQuery': raw = self.raw_query
        status = {'outcome': 'success', 'returncode': 0, 'output_complete': True,
                  'output_truncated': False, 'stop_reason': None,
                  'cleanup': {'direct_child_reaped': True, 'group_empty': True}}
        kw['log'].write_bytes(raw)
        sidecar = kw['log'].with_name(kw['log'].name + '.status.json')
        if self.fault == 'malformed':
            sidecar.write_bytes(b'{'); raise ValueError('private synthetic status detail')
        if self.fault == name:
            status.update(outcome='output_limit', returncode=-15, output_complete=False,
                          output_truncated=True, stop_reason='output_limit')
        sidecar.write_text(json.dumps(status))
        if status['outcome'] != 'success': raise ValueError('private synthetic failure detail')
        return ''

    def run_analysis(self):
        with mock.patch.object(m, 'TARGET_MESSAGE_SHA', m.sha(MESSAGE.encode())), \
             mock.patch.object(m, 'TARGET_ACTIVITY_SHA', m.sha(str(ACTIVITY).encode())):
            return m.analyze(self.download, self.source, self.root / 'report', runner=self.runner,
                             base=self.base, platform='darwin')

    def test_pipeline_reuses_exact_archive_and_only_one_narrow_query(self):
        result = self.run_analysis()
        self.assertEqual(result['status'], 'classified')
        self.assertTrue(result['eventIdentified'])
        self.assertTrue(result['temporaryCleanupConfirmed'])
        commands = ' '.join(' '.join(c) for c in self.calls)
        self.assertIn(self.base.ARCHIVE_REF, commands)
        for banned in ('simctl', 'xcodebuild', '--privacy', 'diagnostics', 'boot'):
            self.assertNotIn(banned, commands)
        queries = [c for c in self.calls if '--start' in c]
        self.assertEqual(len(queries), 1)
        self.assertEqual(queries[0][queries[0].index('--start') + 1], m.QUERY_START)
        self.assertEqual(queries[0][queries[0].index('--end') + 1], m.QUERY_END)
        self.assertEqual([p.name for p in (self.root / 'report').iterdir()], ['report.json'])
        self.assertNotIn(MESSAGE, json.dumps(result))

    def test_capped_query_stops_without_processing_partial_event(self):
        self.fault = 'exactSecondQuery'
        result = self.run_analysis()
        self.assertEqual(result['status'], 'inconclusive')
        self.assertNotIn('staticFormat', result)
        self.assertNotIn('private synthetic', json.dumps(result))

    def test_unconfirmed_cleanup_preserves_its_own_scratch(self):
        self.fault = 'malformed'
        result = self.run_analysis()
        self.assertFalse(result['temporaryCleanupConfirmed'])
        self.assertTrue(self.scratch.exists())
        self.assertEqual(len(self.calls), 1)

    def test_wrong_input_tree_stops_before_native_calls(self):
        self.base.EXPECTED_RESULT_TREE = {'files': 0}
        result = self.run_analysis()
        self.assertEqual(result['status'], 'inconclusive')
        self.assertEqual(self.calls, [])

    def test_wrong_export_tree_stops_before_log_query(self):
        self.base.EXPECTED_ARCHIVE_TREE = {'files': 0}
        result = self.run_analysis()
        self.assertEqual(result['status'], 'inconclusive')
        self.assertNotIn('exactSecondQuery', result['phases'])

    def test_missing_exact_event_stops_inconclusive_without_another_query(self):
        self.raw_query = encode(event(eventMessage='unrelated private text'))
        result = self.run_analysis()
        self.assertEqual(result['status'], 'inconclusive')
        self.assertEqual(result['reason'], 'exact_event_missing_or_ambiguous')
        self.assertEqual(sum('--start' in c for c in self.calls), 1)
        self.assertNotIn('unrelated private text', json.dumps(result))


class WorkflowTests(unittest.TestCase):
    def test_new_workflow_does_not_trigger_old_diagnostic(self):
        text = (ROOT.parents[1] / '.github/workflows/picker-archive-event.yml').read_text()
        for required in ('branches: [verify/staged-pairing-native]', "github.ref == 'refs/heads/verify/staged-pairing-native'",
                         'contents: read', 'actions: read', 'persist-credentials: false',
                         'skip-decompress: true', "artifact-ids: '11341735733'", 'run-id: 37298228388',
                         'picker_archive_event_tests -v', 'picker-event-report/report.json'):
            self.assertIn(required, text)
        self.assertNotIn("- 'Integration/Diagnostics/picker_archive.py'", text)
        for forbidden in ('contents: write', 'actions: write', 'simctl', 'pull_request:', 'develop]'):
            self.assertNotIn(forbidden, text)


if __name__ == '__main__': unittest.main()
