"""Timing-only invariants and bounded read-only collectors; not Simulator acceptance."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
def load(name):
    spec = importlib.util.spec_from_file_location('timing_' + name, ROOT/(name+'.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
ENV = load('simulator_environment')
DIAG = load('retain_ui_diagnostics')
BUNDLE = 'org.tetherless.Tetherless.XYZ0123456'
DEVICE = 'F7D98FC7-1590-4A40-B6B7-B67E1EA2C910'
IDENTITY = {'sourceCommit': 'a'*40, 'runID': 123, 'runAttempt': 1,
            'simulatorID': DEVICE, 'runtime': 'com.apple.CoreSimulator.SimRuntime.iOS-26-2', 'bundleID': BUNDLE}
# This is the exact monitor grammar retained in the verified26.2 artifact;
# process numbers are synthetic. No executable name is inferred from this ID.
SERVICE = ('2026-10-05 09:03:03.325 Df fileproviderd[123:11e47] [com.apple.runningboard:monitor] '
           'Received state update for 456 (xpcservice<com.apple.DocumentManagerUICore.Service('
           '[app<org.tetherless.Tetherless.XYZ0123456((null))>:789])>{vt hash: 0}'
           '{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-Visible\n')
# Exact 32 app-bound monitor rows from run 37298228388, attempt 1,
# job 111724485744, source 3d97ef75a224a76f84ba6741da8d9a6b89f99217.
# Artifact 11341735733 ZIP SHA256:
# ac79e699970ebf98f07277855ffd824529fb826b6aba01583da4538433b742e2
# Member: native-picker-timing/service-discovery.log. Only monitor rows are
# included; source document paths, contents and credentials are absent.
# https://github.com/oskuhsiu/Tetherless/actions/runs/37298228388/artifacts/11341735733
OBSERVED_SERVICE_ROWS = '''2026-10-05 10:55:28.018 Df fileproviderd[12472:e802] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:28.019 Df fileproviderd[12472:9c9e] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:28.038 Df fileproviderd[12472:f3f4] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:28.040 Df fileproviderd[12472:e802] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:28.050 Df fileproviderd[12472:e802] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:30.139 Df fileproviderd[12472:10224] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-Visible
2026-10-05 10:55:30.833 Df fileproviderd[12472:8ef6] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-Visible
2026-10-05 10:55:31.412 Df fileproviderd[12472:8ef6] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-Visible
2026-10-05 10:55:33.782 Df fileproviderd[12472:8ef6] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-Visible
2026-10-05 10:55:33.846 Df fileproviderd[12472:9496] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:33.987 Df fileproviderd[12472:f3f4] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:34.314 Df fileproviderd[12472:f3f4] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:34.803 Df fileproviderd[12472:f3f4] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-suspended-NotVisible
2026-10-05 10:55:35.292 Df fileproviderd[12472:f3f4] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:35.351 Df fileproviderd[12472:8ef6] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:35.510 Df fileproviderd[12472:f3f5] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:35.512 Df fileproviderd[12472:f3f4] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:35.831 Df fileproviderd[12472:f3f4] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-Visible
2026-10-05 10:55:38.896 Df fileproviderd[12472:f3f5] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-Visible
2026-10-05 10:55:38.927 Df fileproviderd[12472:9496] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:39.069 Df fileproviderd[12472:f3f5] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:39.417 Df fileproviderd[12472:f3f4] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:39.509 Df fileproviderd[12472:f3f4] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-suspended-NotVisible
2026-10-05 10:55:40.471 Df fileproviderd[12472:f3f4] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:40.486 Df fileproviderd[12472:f3f4] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:40.550 Df fileproviderd[12472:8ef6] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:40.552 Df fileproviderd[12472:f3f5] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:40.802 Df fileproviderd[12472:f3f5] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:55:40.881 Df fileproviderd[12472:8ef6] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-Visible
2026-10-05 10:55:43.298 Df fileproviderd[12472:8ef6] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-Visible
2026-10-05 10:56:18.937 Df fileproviderd[12472:9496] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, running-active-NotVisible
2026-10-05 10:56:18.987 Df fileproviderd[12472:9bca] [com.apple.runningboard:monitor] Received state update for 22858 (xpcservice<com.apple.DocumentManagerUICore.Service([app<org.tetherless.Tetherless.XYZ0123456((null))>:21855])>{vt hash: 0}{definition:com.apple.DocumentManagerUICore.Service[extension][client]}, none-NotVisible
'''
OBSERVED_SERVICE_ROWS_SHA256 = '5b9fcc880ca96963e64126987ad1cfeefa11375f8975adc1547f2a28dd0770be'

HELP = '''usage: log show [options]
--process <pid> | <process>   Filter events using the specified process
--start <date> Display events from the given start date
--end <date> Display events up to the given end date
--timezone local | <tz>
--predicate <predicate>
--style <style> (valid: default, syslog, json, ndjson, compact)
valid time formats: '@unixtime'
'''
WALL = 1_791_190_000_000_000

def record(source='app', event='hostDidAppear', mono=100_000, offset=WALL, pid=789):
    value = {'schemaVersion': 1, 'source': source, 'event': event, 'processID': pid,
             'monotonicBeforeUS': mono, 'unixTimeUS': mono+5+offset, 'monotonicAfterUS': mono+10}
    choices = {'app': DIAG.APP_TIMING_FIELDS, 'uiTest': DIAG.UI_TIMING_FIELDS, 'host': DIAG.HOST_TIMING_FIELDS}
    value.update({key: False for key in choices[source][event]})
    return value


def capture_result(path, text='', exit_code=0):
    path.write_text(text)
    return {'exitCode': exit_code, 'originalBytesComplete': True, 'truncated': False,
            'originalBytes': len(text.encode()), 'file': path.name}


class TimingSchemaTests(unittest.TestCase):
    def test_only_closed_typed_clock_fields_are_accepted(self):
        for source, choices in [('app', DIAG.APP_TIMING_FIELDS), ('uiTest', DIAG.UI_TIMING_FIELDS), ('host', DIAG.HOST_TIMING_FIELDS)]:
            for event in choices:
                value = record(source, event)
                self.assertEqual(DIAG.clock_record(value, source), value)
        for mutate in [lambda r:r.update(path='/private/SECRET'), lambda r:r.update(requestUUID='SECRET'),
                       lambda r:r.update(event='SECRET'), lambda r:r.update(processID=True),
                       lambda r:r.update(unixTimeUS=float('nan')), lambda r:r.update(monotonicBeforeUS=999_999),
                       lambda r:r.update(hostWindowAttached='SECRET')]:
            value = record(); mutate(value)
            with self.assertRaises(ValueError): DIAG.clock_record(value, 'app')

    def test_timing_scan_rejects_payloads_and_retains_bounds(self):
        good = DIAG.PICKER_PREFIX + json.dumps(record()).encode() + b'\n'
        bad = DIAG.PICKER_PREFIX + b'{"path":"PRIVATE_SECRET"}\n'
        source = good + bad + good
        scanned = DIAG.picker_timing(io.BytesIO(source), len(source), event_limit=1)
        self.assertEqual(scanned['observedRecordCount'], 2)
        self.assertEqual(scanned['invalidRecordCount'], 1)
        self.assertTrue(scanned['recordsTruncated'] and scanned['scanComplete'])
        self.assertNotIn('PRIVATE_SECRET', repr(scanned))
        truncated = DIAG.picker_timing(io.BytesIO(source), len(source), scan_limit=len(good)-1)
        self.assertFalse(truncated['scanComplete']); self.assertEqual(truncated['records'], [])
        oversized = b'x'*2048 + good
        self.assertEqual(DIAG.picker_timing(io.BytesIO(oversized),len(oversized))['records'], [])

    def test_existing_fixed_event_scanner_is_unchanged(self):
        source = (ROOT/'retain_ui_diagnostics.py').read_text()
        function = source[source.index('def pairing_lifecycle('):source.index('\nPICKER_PREFIX')].rstrip()
        # Separately verify original event behavior, even when both channels occur.
        data = b'[Tetherless.PairingImport] selectionReceived\n' + DIAG.PICKER_PREFIX + json.dumps(record()).encode()+b'\n'
        result = DIAG.pairing_lifecycle(io.BytesIO(data),len(data))
        self.assertEqual(result['events'], ['selectionReceived'])
        self.assertTrue(result['scanComplete']); self.assertFalse(result['uiResultInferred'])
        self.assertNotIn('PickerTiming', function)

    def test_correlation_brackets_agreement_and_drift_without_mapping_video(self):
        clocks = [record('app','hostDidAppear'), record('uiTest','beforeFirstPickerTap',mono=500_000,pid=321)]
        result = DIAG.clock_correlation(clocks)
        self.assertEqual(result['crossSourceOffsetCompatibility'], 'compatible')
        self.assertFalse(result['videoPTSMappingPerformed']); self.assertFalse(result['rootCauseInferred'])
        clocks.append(record('app','hostDidAppear',mono=1_000_000,offset=WALL+1000))
        result=DIAG.clock_correlation(clocks)
        self.assertEqual(result['crossSourceOffsetCompatibility'], 'disagrees')
        self.assertGreater(result['minimumCrossSourceDisagreementUS'], 0)
        self.assertFalse(result['groups'][0]['constantOffsetCompatible'])
        self.assertEqual(DIAG.clock_correlation([clocks[0]])['crossSourceOffsetCompatibility'], 'insufficient')

    def make_correlation_inputs(self, root):
        timing, diag, attachments = [root/x for x in ('timing','diag','attachments')]
        for path in (timing,diag,attachments):path.mkdir()
        (timing/'baseline.json').write_text(json.dumps({'identity':IDENTITY,'clock':record('host','hostBeforeUI',pid=100)}))
        (timing/'collection.json').write_text(json.dumps({'identity':IDENTITY,'status':'complete',
            'clocks':[record('host','hostAfterUI',mono=500_000,pid=101),record('host','hostAfterCollection',mono=600_000,pid=101)],
            'observedServices':[{'servicePID':456,'appPID':789,'serviceIdentifier':'com.apple.DocumentManagerUICore.Service'}]}))
        app=record();scan={'records':[app],'scanComplete':True,'recordsTruncated':False,'invalidRecordCount':0}
        (diag/'manifest.json').write_text(json.dumps({'files':[{'kind':'stdout','pickerTiming':scan}]}))
        (attachments/'manifest.json').write_text(json.dumps([{'testIdentifier':'TetherlessUITests/testFirstSetupAndLocalNavigation()',
            'attachments':[{'suggestedHumanReadableName':'picker-clock-first-presentation_0_example.json',
                            'exportedFileName':'clock.json','deviceId':DEVICE}]}]))
        clocks=[record('uiTest',event,mono=100_000+i*100_000,pid=321) for i,event in enumerate(DIAG.UI_TIMING_FIELDS)]
        (attachments/'clock.json').write_text(json.dumps(clocks))
        return timing,diag,attachments

    def test_correlation_binds_attachment_identity_and_preserves_wait_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);paths=self.make_correlation_inputs(root)
            result=DIAG.correlate_picker_timing(*paths,root/'result.json')
            self.assertEqual(result['status'],'complete')
            self.assertFalse(result['originalCancelWait']['found'])
            self.assertEqual(result['originalCancelWait']['configuredTimeoutSeconds'],10)
            self.assertEqual(result['originalCancelWait']['durationLowerUS'],99_990)
            self.assertFalse(result['uiResultInferred'])
            with self.assertRaises(FileExistsError):DIAG.correlate_picker_timing(*paths,root/'result.json')

    def test_final_clock_on_failed_collection_does_not_make_correlation_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);paths=self.make_correlation_inputs(root)
            path=paths[0]/'collection.json';value=json.loads(path.read_text())
            value.update(status='gaps',gaps=['ValueError'],stage='serviceIdentity',
                         finalClockStage='serviceIdentity',finalClockScope='afterCollectionAttempt')
            path.write_text(json.dumps(value))
            result=DIAG.correlate_picker_timing(*paths,root/'result.json')
            self.assertTrue(result['temporalEnclosure']['valid'])
            self.assertEqual(result['status'],'gaps');self.assertIn('collectorIncomplete',result['gaps'])
            self.assertFalse(result['uiResultInferred']);self.assertFalse(result['videoPTSMappingPerformed'])

    def test_samples_outside_ui_window_never_report_complete_even_with_matching_offsets(self):
        for source,shift in [('uiTest',10_000_000),('uiTest',-10_000_000),('app',10_000_000),('app',-10_000_000)]:
            with self.subTest(source=source,shift=shift),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);timing,diag,attachments=self.make_correlation_inputs(root)
                path=attachments/'clock.json' if source=='uiTest' else diag/'manifest.json'
                value=json.loads(path.read_text())
                samples=value if source=='uiTest' else value['files'][0]['pickerTiming']['records']
                # Move a whole same-origin fixture into the future/past without
                # introducing negative monotonic fields; keep offset compatibility.
                for data_path in [timing/'baseline.json',timing/'collection.json',diag/'manifest.json',attachments/'clock.json']:
                    data=json.loads(data_path.read_text())
                    def move(obj):
                        if isinstance(obj,dict):
                            if 'monotonicBeforeUS' in obj:
                                for key in ('monotonicBeforeUS','monotonicAfterUS','unixTimeUS'):obj[key]+=20_000_000
                            for child in obj.values():move(child)
                        elif isinstance(obj,list):
                            for child in obj:move(child)
                    move(data);data_path.write_text(json.dumps(data))
                value=json.loads(path.read_text())
                samples=value if source=='uiTest' else value['files'][0]['pickerTiming']['records']
                for item in samples:
                    for key in ('monotonicBeforeUS','monotonicAfterUS','unixTimeUS'):item[key]+=shift
                path.write_text(json.dumps(value))
                result=DIAG.correlate_picker_timing(timing,diag,attachments,root/'result.json')
                self.assertEqual(result['status'],'gaps')
                self.assertIn('sampleOutsideHostUIWindow',result['gaps'])
                self.assertEqual(result['correlation']['crossSourceOffsetCompatibility'],'compatible')
                self.assertFalse(result['temporalEnclosure']['valid'])
                self.assertFalse(result['videoPTSMappingPerformed'])

    def test_missing_reordered_and_time_reversed_host_stages_are_gaps(self):
        for problem in ('missing','reordered','time','collectorPID'):
            with self.subTest(problem=problem),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);timing,diag,attachments=self.make_correlation_inputs(root)
                path=timing/'collection.json';value=json.loads(path.read_text())
                if problem=='missing':value['clocks'].pop()
                elif problem=='reordered':value['clocks'].reverse()
                elif problem=='collectorPID':value['clocks'][1]['processID']=102
                else:value['clocks'][0]=record('host','hostAfterUI',mono=1,pid=101)
                path.write_text(json.dumps(value))
                result=DIAG.correlate_picker_timing(timing,diag,attachments,root/'result.json')
                self.assertEqual(result['status'],'gaps');self.assertFalse(result['temporalEnclosure']['valid'])

    def test_wrong_device_payload_and_clock_order_stay_explicit_gaps(self):
        for problem in ('device','payload','order','identity'):
            with self.subTest(problem=problem),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);timing,diag,attachments=self.make_correlation_inputs(root)
                if problem=='device':
                    p=attachments/'manifest.json';value=json.loads(p.read_text());value[0]['attachments'][0]['deviceId']='different';p.write_text(json.dumps(value))
                elif problem=='identity':
                    p=timing/'collection.json';value=json.loads(p.read_text());value['identity']['sourceCommit']='b'*40;p.write_text(json.dumps(value))
                else:
                    p=attachments/'clock.json';value=json.loads(p.read_text())
                    if problem=='payload':value[0]['secret']='PRIVATE_SECRET'
                    else:value.reverse()
                    p.write_text(json.dumps(value))
                result=DIAG.correlate_picker_timing(timing,diag,attachments,root/'result.json')
                self.assertEqual(result['status'],'gaps');self.assertFalse(result['uiResultInferred'])
                self.assertNotIn('PRIVATE_SECRET',json.dumps(result))


class BoundedCollectorTests(unittest.TestCase):
    def test_large_output_is_drained_with_fixed_retained_memory_and_no_spool(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'output.log'
            tracemalloc.start()
            result=ENV.capture_draining([sys.executable,'-c',
                'import os; os.write(1,b"BEGIN"); [os.write(1,b"x"*65536) for _ in range(160)]; os.write(1,b"END")'],path,timeout=10,limit=4096)
            _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            self.assertEqual(result['exitCode'],0);self.assertTrue(result['originalBytesComplete'])
            self.assertEqual(result['originalBytes'],160*65536+8)
            self.assertEqual(path.stat().st_size,4096);self.assertTrue(result['truncated'])
            self.assertTrue(path.read_bytes().startswith(b'BEGIN') and path.read_bytes().endswith(b'END'))
            self.assertLess(peak,2_000_000)
            self.assertEqual(result['omittedBytes'],result['originalBytes']-4096)
            self.assertNotIn('TemporaryFile',__import__('inspect').getsource(ENV.capture_draining))

    def test_timeout_is_bounded_and_partial_output_is_not_called_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'output.log'
            result=ENV.capture_draining([sys.executable,'-c','import time;print("before",flush=True);time.sleep(10)'],path,timeout=0.2,limit=128)
            self.assertTrue(result['timeout']);self.assertLess(result['elapsedSeconds'],2.5)
            self.assertFalse(ENV.capture_complete(result));self.assertIn(b'before',path.read_bytes())
            with self.assertRaises(FileExistsError):ENV.capture_draining(['unused'],path)

    def test_spawn_failure_and_invalid_bounds_remain_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'output.log'
            result=ENV.capture_draining(['/definitely-no-such-command'],path)
            self.assertEqual(result['errorType'],'FileNotFoundError')
            self.assertFalse(ENV.capture_complete(result));self.assertFalse(result['originalBytesComplete'])
            for kwargs in ({'limit':1},{'limit':ENV.MAX_OUTPUT+1},{'timeout':0},{'timeout':31}):
                with self.assertRaises(ValueError):ENV.capture_draining(['unused'],path,**kwargs)

    def test_service_identity_uses_observed_binding_not_guessed_process_name(self):
        expected=[{'servicePID':456,'appPID':789,'serviceIdentifier':'com.apple.DocumentManagerUICore.Service'}]
        self.assertEqual(ENV.discover_picker_services(SERVICE+SERVICE,BUNDLE),expected)
        for bad in ('', SERVICE.replace(BUNDLE,'org.someone.else'), SERVICE.replace('((null))','new-format'),
                    SERVICE+SERVICE.replace('>:789]', '>:790]')):
            with self.assertRaises(ValueError):ENV.discover_picker_services(bad,BUNDLE)
        too_many=''.join(SERVICE.replace('for 456 ',f'for {456+i} ') for i in range(5))
        with self.assertRaises(ValueError):ENV.discover_picker_services(too_many,BUNDLE)

    def test_exact_retained_32_monitor_rows_accept_only_observed_app_bound_identity(self):
        self.assertEqual(hashlib.sha256(OBSERVED_SERVICE_ROWS.encode()).hexdigest(),
                         OBSERVED_SERVICE_ROWS_SHA256)
        self.assertEqual(len(OBSERVED_SERVICE_ROWS.splitlines()), 32)
        self.assertEqual(OBSERVED_SERVICE_ROWS.count('running-suspended-NotVisible'), 2)
        expected = [{'servicePID':22858, 'appPID':21855,
                     'serviceIdentifier':'com.apple.DocumentManagerUICore.Service'}]
        self.assertEqual(ENV.discover_picker_services(OBSERVED_SERVICE_ROWS, BUNDLE), expected)
        for bad in (OBSERVED_SERVICE_ROWS.replace('running-suspended-NotVisible', 'unknown-state'),
                    OBSERVED_SERVICE_ROWS.replace('((null))', 'unverified-format'),
                    OBSERVED_SERVICE_ROWS.replace('for 22858 ', 'for 0 '),
                    OBSERVED_SERVICE_ROWS.replace(BUNDLE, 'org.foreign.application'),
                    OBSERVED_SERVICE_ROWS.replace('DocumentManagerUICore.Service', 'Other.Service'),
                    OBSERVED_SERVICE_ROWS + OBSERVED_SERVICE_ROWS.replace('>:21855]', '>:999]')):
            with self.subTest(bad=bad[-80:]), self.assertRaises(ValueError):
                ENV.discover_picker_services(bad, BUNDLE)
        # Foreign rows never authorize querying their PID, even beside a valid row.
        foreign = OBSERVED_SERVICE_ROWS.replace(BUNDLE, 'org.foreign.application').replace('for 22858 ', 'for 999 ')
        self.assertEqual(ENV.discover_picker_services(OBSERVED_SERVICE_ROWS + foreign, BUNDLE), expected)

    def make_collection(self, directory):
        path=Path(directory)/'timing';path.mkdir()
        baseline={'identity':IDENTITY,'clock':record('host','hostBeforeUI',mono=100_000,pid=100)}
        (path/'baseline.json').write_text(json.dumps(baseline))
        return path

    def test_direct_process_rows_reject_headers_wrong_pid_and_ambiguous_names(self):
        row='2026-10-05 09:03:03.325 Df ObservedPickerService[456:abc] [observed:subsystem] event\n'
        self.assertEqual(ENV.observed_process_rows(row,456)['matchingRows'],1)
        for invalid in ['Timestamp Type Process Message\n', row.replace('[456:', '[999:'),
                        row+row.replace('ObservedPickerService','OtherProcess'),
                        '2026-10-05 09:03:03 unsupported-format\n']:
            with self.assertRaises(ValueError):ENV.observed_process_rows(invalid,456)

    def test_collection_only_queries_observed_pid_and_exact_owned_window(self):
        def capture(args,path,timeout=15,limit=ENV.MAX_OUTPUT):
            if path.name=='log-show-help.log':return capture_result(path,HELP,64)
            if path.name=='service-discovery.log':return capture_result(path,SERVICE)
            return capture_result(path,'2026-10-05 09:03:03.325 Df ObservedPickerService[456:abc] [observed:subsystem] event\n' if path.name.startswith('ui-service-') else 'host snapshot\n')
        with tempfile.TemporaryDirectory() as directory:
            target=self.make_collection(directory)
            with patch.object(ENV,'PICKER_TIMING',target),patch.object(ENV,'picker_identity',return_value=IDENTITY), \
                 patch.object(ENV,'paired_clock',side_effect=lambda e:record('host',e,mono=500_000,pid=101)), \
                 patch.object(ENV,'capture_draining',side_effect=capture) as commands:
                ENV.collect_picker_timing()
            result=json.loads((target/'collection.json').read_text())
            self.assertEqual(result['status'],'complete');self.assertTrue(result['installedHelpSupported'])
            self.assertEqual(result['commands'][0]['exitCode'],64) # preserve actual help status
            calls=[c.args[0] for c in commands.call_args_list]
            self.assertEqual([args for args in calls if '--process' in args][0][-2:],['--process','456'])
            self.assertTrue(all(args[3]==DEVICE for args in calls if args[0]=='xcrun'))
            self.assertTrue(all('--start' in args and '--end' in args for args in calls if '--process' in args or '--predicate' in args))
            self.assertFalse(any('DocumentManagerUICore.Service'==arg for args in calls for arg in args))
            self.assertLessEqual(result['window']['endUnixSeconds']-result['window']['startUnixSeconds'],600)
            self.assertFalse(result['uiResultInferred'])
            self.assertEqual([x['event'] for x in result['clocks']], ['hostAfterUI','hostAfterCollection'])
            self.assertEqual(result['finalClockStage'], 'hostSnapshot')
            self.assertEqual(result['finalClockScope'], 'afterCollectionAttempt')

    def test_unsupported_help_or_missing_discovery_has_no_fallback_query(self):
        for problem in ('help','discovery','truncation','ownership','identityShape'):
            with self.subTest(problem=problem),tempfile.TemporaryDirectory() as directory:
                target=self.make_collection(directory)
                def capture(args,path,timeout=15,limit=ENV.MAX_OUTPUT):
                    if path.name=='log-show-help.log':return capture_result(path,'unsupported' if problem=='help' else HELP,64)
                    value=capture_result(path,'' if problem=='discovery' else SERVICE.replace('running-active-Visible','unknown-state') if problem=='identityShape' else SERVICE)
                    if problem=='truncation':value['truncated']=True
                    return value
                with patch.object(ENV,'PICKER_TIMING',target), \
                     patch.object(ENV,'picker_identity',side_effect=ValueError('unbound') if problem=='ownership' else None,return_value=IDENTITY), \
                     patch.object(ENV,'paired_clock',side_effect=lambda e:record('host',e,mono=500_000,pid=101)), \
                     patch.object(ENV,'capture_draining',side_effect=capture) as commands:
                    with self.assertRaises(ValueError):ENV.collect_picker_timing()
                result=json.loads((target/'collection.json').read_text())
                self.assertEqual(result['status'],'gaps')
                self.assertFalse(any('--process' in c.args[0] for c in commands.call_args_list))
                self.assertEqual([x['event'] for x in result['clocks']], ['hostAfterUI','hostAfterCollection'])
                self.assertEqual(result['finalClockScope'], 'afterCollectionAttempt')
                self.assertEqual(result['finalClockStage'], result['stage'])
                self.assertEqual(result['stage'], {'help':'installedLogHelp','discovery':'serviceIdentity',
                    'truncation':'serviceDiscovery','ownership':'identityValidation','identityShape':'serviceIdentity'}[problem])
                if problem=='ownership':commands.assert_not_called()

    def test_final_clock_follows_failed_command_without_query_retry_or_gap_erasure(self):
        for failed_name,stage in [('ui-service-456.log','observedServiceQueries'),
                                  ('host-memory.log','hostSnapshot')]:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                target=self.make_collection(directory); events=[]
                failure=OSError('test command failed')
                def capture(args,path,timeout=15,limit=ENV.MAX_OUTPUT):
                    events.append(path.name)
                    if path.name==failed_name: raise failure
                    if path.name=='log-show-help.log':return capture_result(path,HELP,64)
                    if path.name=='service-discovery.log':return capture_result(path,SERVICE)
                    return capture_result(path,'2026-10-05 09:03:03.325 Df ObservedPickerService[456:abc] [observed:subsystem] event\n')
                def clock(event):
                    events.append(event)
                    return record('host',event,mono=500_000+len(events)*100,pid=101)
                with patch.object(ENV,'PICKER_TIMING',target),patch.object(ENV,'picker_identity',return_value=IDENTITY), \
                     patch.object(ENV,'paired_clock',side_effect=clock),patch.object(ENV,'capture_draining',side_effect=capture):
                    with self.assertRaises(OSError) as caught:ENV.collect_picker_timing()
                self.assertIs(caught.exception,failure)
                saved=json.loads((target/'collection.json').read_text())
                self.assertEqual(saved['status'],'gaps');self.assertEqual(saved['gaps'],['OSError'])
                self.assertEqual(saved['stage'],stage);self.assertEqual(saved['finalClockStage'],stage)
                self.assertEqual(saved['finalClockScope'],'afterCollectionAttempt')
                self.assertEqual(events[-2:],[failed_name,'hostAfterCollection'])
                self.assertEqual(events.count(failed_name),1)
                self.assertEqual([x['event'] for x in saved['clocks']],['hostAfterUI','hostAfterCollection'])
                self.assertGreater(saved['clocks'][1]['monotonicBeforeUS'],saved['clocks'][0]['monotonicAfterUS'])
                self.assertNotIn('test command failed',json.dumps(saved))

    def test_missing_final_clock_does_not_mask_original_identity_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            target=self.make_collection(directory);failure=ValueError('identity rejected')
            def clock(event):
                if event=='hostAfterCollection':raise OSError('clock unavailable')
                return record('host',event,mono=500_000,pid=101)
            with patch.object(ENV,'PICKER_TIMING',target),patch.object(ENV,'picker_identity',side_effect=failure), \
                 patch.object(ENV,'paired_clock',side_effect=clock),patch.object(ENV,'capture_draining') as commands:
                with self.assertRaises(ValueError) as caught:ENV.collect_picker_timing()
            commands.assert_not_called();self.assertIs(caught.exception,failure)
            saved=json.loads((target/'collection.json').read_text())
            self.assertEqual(saved['status'],'gaps')
            self.assertEqual(saved['gaps'],['ValueError','finalClockUnavailable'])
            self.assertEqual(saved['finalClockStage'],'identityValidation')
            self.assertEqual([x['event'] for x in saved['clocks']],['hostAfterUI'])

    def test_identity_rejects_other_source_device_or_run_before_collection(self):
        owner={'schema':1,'id':DEVICE,'name':'Tetherless-CI-owned','runtime':IDENTITY['runtime'],
               'deviceType':'com.apple.CoreSimulator.SimDeviceType.iPhone-SE-3rd-generation','sourceCommit':'a'*40}
        smoke={'sourceCommit':'a'*40,'simulatorID':DEVICE,'bundleID':BUNDLE,'smokePassed':True}
        device={'udid':DEVICE,'name':owner['name'],'state':'Booted','deviceTypeIdentifier':owner['deviceType']}
        listing={'devices':{owner['runtime']:[device]}}
        for problem in ('valid','source','device','notBooted','bundle','run'):
            with self.subTest(problem=problem),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);saved_owner=dict(owner);saved_smoke=dict(smoke)
                active={'GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}
                if problem=='source':saved_owner['sourceCommit']='b'*40
                elif problem=='device':saved_smoke['simulatorID']='different'
                elif problem=='bundle':saved_smoke['bundleID']='org.other.application'
                elif problem=='run':active['GITHUB_RUN_ID']='unknown'
                data=json.loads(json.dumps(listing))
                if problem=='notBooted':data['devices'][owner['runtime']][0]['state']='Shutdown'
                (root/'owner.json').write_text(json.dumps(saved_owner));(root/'smoke.json').write_text(json.dumps(saved_smoke))
                with patch.object(ENV,'OWNER',root/'owner.json'),patch.object(ENV,'SMOKE',root/'smoke.json'), \
                     patch.object(ENV,'listing',return_value=data),patch.dict(os.environ,active):
                    if problem=='valid':self.assertEqual(ENV.picker_identity(),IDENTITY)
                    else:
                        with self.assertRaises(ValueError):ENV.picker_identity()

    def test_clock_jump_and_window_clipping_never_masquerade_as_complete(self):
        for problem in ('jump','clipped'):
            with self.subTest(problem=problem),tempfile.TemporaryDirectory() as directory:
                target=self.make_collection(directory)
                after=record('host','hostAfterUI',mono=700_000_000 if problem=='clipped' else 500_000,pid=101)
                if problem=='jump':after['unixTimeUS']+=2_000_000
                def capture(args,path,timeout=15,limit=ENV.MAX_OUTPUT):
                    if path.name=='log-show-help.log':return capture_result(path,HELP,64)
                    if path.name=='service-discovery.log':return capture_result(path,SERVICE)
                    return capture_result(path,'2026-10-05 09:03:03.325 Df ObservedPickerService[456:abc] [observed:subsystem] event\n' if path.name.startswith('ui-service-') else 'host snapshot\n')
                with patch.object(ENV,'PICKER_TIMING',target),patch.object(ENV,'picker_identity',return_value=IDENTITY), \
                     patch.object(ENV,'paired_clock',return_value=after),patch.object(ENV,'capture_draining',side_effect=capture) as commands:
                    with self.assertRaises((ValueError,RuntimeError)):ENV.collect_picker_timing()
                saved=json.loads((target/'collection.json').read_text());self.assertEqual(saved['status'],'gaps')
                if problem=='jump':commands.assert_not_called()
                else:
                    self.assertTrue(saved['window']['clipped'])
                    self.assertLessEqual(saved['window']['endUnixSeconds']-saved['window']['startUnixSeconds'],600)

    def test_begin_is_read_only_and_refuses_replacement(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(ENV,'PICKER_TIMING',Path(directory)/'timing'), \
             patch.object(ENV,'picker_identity',return_value=IDENTITY),patch.object(ENV,'capture_draining') as capture:
            ENV.begin_picker_timing();capture.assert_not_called()
            value=json.loads((ENV.PICKER_TIMING/'baseline.json').read_text())
            self.assertEqual(value['identity'],IDENTITY);self.assertEqual(value['clock']['event'],'hostBeforeUI')
            with self.assertRaises(FileExistsError):ENV.begin_picker_timing()


class TimingOnlySourceTests(unittest.TestCase):
    def test_ui_logic_is_byte_identical_after_removing_only_reviewed_clock_instrumentation(self):
        source=(ROOT/'UITests/TetherlessUITests.swift').read_text()
        start=source.index('    private enum PickerClockEvent:');end=source.index('    @MainActor private func capture(')
        helper=source[start:end]
        self.assertEqual(hashlib.sha256(helper.encode()).hexdigest(),'f6b145fa82e0a5e9218fe1e86464c33a633bde78232b13beb81113c8c85591b4')
        self.assertNotIn('XCUIApplication',helper);self.assertNotIn('waitForExistence',helper)
        self.assertNotIn('tap()',helper);self.assertNotIn('screenshot',helper)
        source=source[:start]+source[end:]
        source=source.replace('''            // Clock samples stay in memory until the SAME existing wait ends.
            // No attachment IO, additional AX query or action can warm the picker.
            let beforeTap = attempt == 1 ? pickerClock(.beforeFirstPickerTap) : nil
''','',1)
        source=source.replace('''            let waitStart = attempt == 1 ? pickerClock(.firstCancelWaitStart) : nil
            let cancelAppeared = cancelImport.waitForExistence(timeout: 10)
            let waitEnd = attempt == 1 ? pickerClock(.firstCancelWaitEnd, found: cancelAppeared) : nil
            if let beforeTap, let waitStart, let waitEnd {
                attachPickerClocks([beforeTap, waitStart, waitEnd])
            }
            XCTAssertTrue(cancelAppeared,''','''            XCTAssertTrue(cancelImport.waitForExistence(timeout: 10),''',1)
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),'ad0a414f76778932b00ff373e07c26cb60c3532d93a247ac24456e6f848daee2')
        original=(ROOT/'UITests/TetherlessUITests.swift').read_text()
        self.assertLess(original.index('let cancelAppeared = cancelImport.waitForExistence(timeout: 10)'),original.index('attachPickerClocks([beforeTap'))
        self.assertEqual(original.count('cancelImport.waitForExistence(timeout: 10)'),1)

    def test_presenter_behavior_is_byte_identical_after_removing_only_timing_calls(self):
        source=(ROOT/'Native/PairingDocumentPicker.swift').read_text()
        start=source.index('\n\n/// A second, strictly allowlisted diagnostic channel.');end=source.rfind('\n#endif')
        helper=source[start:end]
        self.assertEqual(hashlib.sha256(helper.encode()).hexdigest(),'c4253a95aba0b9863a505c56fd795e89b7c643d2a27937f147fd97ea9ed2fc7e')
        source=source[:start]+source[end:]
        completion='''            present(picker, animated: true) { [weak self, weak picker] in
                guard let self, let picker else { return }
                PickerTiming.emit(.presentationCompleted, hostWindowAttached: self.viewIfLoaded?.window != nil,
                                  pickerWindowAttached: picker.viewIfLoaded?.window != nil,
                                  presentedControllerMatches: self.presentedViewController === picker,
                                  alreadyPresented: self.presentedPicker)
            }'''
        self.assertIn(completion,source);source=source.replace(completion,'            present(picker, animated: true)',1)
        reviewed_calls = ['        PickerTiming.emit(.dismantle, hostWindowAttached: host.viewIfLoaded?.window != nil)\n', '            PickerTiming.emit(.hostDidAppear, hostWindowAttached: viewIfLoaded?.window != nil,\n                              pickerWindowAttached: picker.viewIfLoaded?.window != nil,\n                              presentedControllerMatches: presentedViewController === picker,\n                              alreadyPresented: presentedPicker)\n', '            PickerTiming.emit(.presentationAttempt, hostWindowAttached: viewIfLoaded?.window != nil,\n                              pickerWindowAttached: picker.viewIfLoaded?.window != nil,\n                              presentedControllerMatches: presentedViewController === picker,\n                              alreadyPresented: presentedPicker)\n', '            PickerTiming.emit(.delegateSelection, pickerWindowAttached: controller.viewIfLoaded?.window != nil)\n', '            PickerTiming.emit(.delegateCancellation, pickerWindowAttached: controller.viewIfLoaded?.window != nil)\n', '            PickerTiming.emit(.interactiveDismissal, pickerWindowAttached: picker?.viewIfLoaded?.window != nil)\n']
        for call in reviewed_calls:
            self.assertEqual(source.count(call),1)
            source=source.replace(call,'',1)
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),'b31a0176bfe50a22ed8af6f0944cd2e685088917c827879b76120b494ffe7c9d')

    def test_workflow_collection_is_read_only_owned_and_after_original_wait_source_check(self):
        text=(ROOT.parent/'.github/workflows/native-simulator.yml').read_text()
        self.assertLess(text.index('begin-picker-timing'),text.index('xcodebuild test'))
        self.assertLess(text.index('ui_document_fixture.py verify'),text.index('collect-picker-timing'))
        self.assertLess(text.index('xcresulttool export attachments'),text.index('--correlate-picker'))
        self.assertIn('native-picker-timing',text)
        self.assertNotIn('continue-on-error',text)
        self.assertNotIn('-retry-tests-on-failure',text)
        self.assertNotIn('downloadPlatform',text)

    def test_actual_app_trace_helper_compiles_and_emits_only_closed_records(self):
        text=(ROOT/'Native/PairingDocumentPicker.swift').read_text()
        helper=text[text.index('@MainActor private enum PickerTiming'):text.rfind('\n#endif')]
        source='import Foundation\n'+helper+'''\n@main struct Main {
 @MainActor static func main() {
  PickerTiming.emit(.presentationAttempt, hostWindowAttached: true, pickerWindowAttached: false,
                    presentedControllerMatches: false, alreadyPresented: true)
  PickerTiming.emit(.delegateCancellation, pickerWindowAttached: false)
 }
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            p=Path(temporary);(p/'Main.swift').write_text(source)
            for mode in ['-Onone','-O']:
                result=subprocess.run(['swiftc','-swift-version','6','-parse-as-library',mode,str(p/'Main.swift'),'-o',str(p/'check')],capture_output=True,text=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stderr)
                ran=subprocess.run([str(p/'check')],capture_output=True,timeout=10)
                self.assertEqual(ran.returncode,0,ran.stderr)
                scanned=DIAG.picker_timing(io.BytesIO(ran.stdout),len(ran.stdout))
                self.assertEqual([x['event'] for x in scanned['records']],['presentationAttempt','delegateCancellation'])
                self.assertEqual(scanned['invalidRecordCount'],0)


if __name__=='__main__':unittest.main()
