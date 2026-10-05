"""Portable contracts/error-path tests only; no UIKit, Simulator or native acceptance."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import subprocess
import struct
import zlib
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('runtime_comparison', HERE / 'run.py')
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


def inventory():
    return {'devicetypes': [{'identifier': diag.DEVICE_TYPE}],
            'runtimes': [{'identifier': item, 'version': item.rsplit('iOS-', 1)[1].replace('-', '.'),
                          'buildversion': 'scripted-build', 'isAvailable': True} for item in diag.RUNTIMES]}


def observed():
    return {'schema': 1, 'productAccepted': False, 'selectedBytesRead': False,
            'protocolViolation': False, 'evidenceWriteFailed': False,
            'presentations': [{'outcome': outcome, 'callbackCount': 1, 'dismissed': True}
                              for outcome in ('cancelled', 'cancelled', 'selectedFileURL')]}


def attachment_fixture(directory, device='scripted-owned', passed=True):
    root = directory / 'attachments'; root.mkdir()
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(b'\x00\xff\xff\xff')) + chunk(b'IEND', b''))
    files = [('after-single-file-activation', 'shot.png', png),
             ('after-single-file-activation-hierarchy', 'hierarchy.txt', b'Application, scripted\n  Window (Main), scripted\n    Button, scripted'),
             ('runtime-selection-result', 'result.txt',
              ('waitCompleted=' + ('true' if passed else 'false') + '; outcome=' + ('selectedFileURL' if passed else 'waiting')
               + '; pickerVisible=' + ('false' if passed else 'true') + '; productAccepted=false').encode())]
    attachments = []
    for name, filename, data in files:
        (root / filename).write_bytes(data)
        attachments.append({'deviceId': device, 'exportedFileName': filename,
                            'suggestedHumanReadableName': name + '_0_scripted' + Path(filename).suffix})
    (root / 'manifest.json').write_text(json.dumps([{'testIdentifier': 'RuntimePickerTests/testCrossContainerSelection()',
                                                   'attachments': attachments}]))
    return root


class RuntimeComparisonTests(unittest.TestCase):
    def test_both_exact_installed_runtimes_and_type_are_required(self):
        self.assertEqual(tuple(diag.select_runtimes(inventory())), diag.RUNTIMES)
        cases = []
        for key, value in [('isAvailable', False), ('version', '18.5'), ('buildversion', '')]:
            altered = inventory(); altered['runtimes'][1][key] = value; cases.append(altered)
        altered = inventory(); altered['runtimes'].pop(); cases.append(altered)
        altered = inventory(); altered['runtimes'].append(altered['runtimes'][0]); cases.append(altered)
        altered = inventory(); altered['devicetypes'] = []; cases.append(altered)
        altered = inventory(); altered['devicetypes'] *= 2; cases.append(altered)
        for item in cases:
            with self.subTest(item=item), self.assertRaises(ValueError):
                diag.select_runtimes(item)

    def test_focused_inventory_ignores_oversized_unrelated_device_enumeration(self):
        full = inventory()
        full['devices'] = {'unrelated-runtime': [{'unused': 'x' * (diag.environment.MAX_OUTPUT + 1)}]}
        full['pairs'] = {}
        self.assertGreater(len(json.dumps(full).encode()), diag.environment.MAX_OUTPUT)
        calls = []
        answers = {
            ('uname', '-m'): 'arm64',
            ('sw_vers',): 'ProductName: macOS\nProductVersion: 15.7.9\nBuildVersion: 24G830',
            ('xcode-select', '-p'): diag.DEVELOPER,
            ('xcodebuild', '-version'): 'Xcode 26.3\nBuild version 17C529',
            ('xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version'): '26.2',
            ('xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'): diag.DEVELOPER + '/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator26.2.sdk',
            ('xcrun', 'simctl', 'list', '--json'): json.dumps(full),
            ('xcrun', 'simctl', 'list', 'runtimes', '--json'): json.dumps({'runtimes': full['runtimes']}),
            ('xcrun', 'simctl', 'list', 'devicetypes', '--json'): json.dumps({'devicetypes': full['devicetypes']}),
        }
        def scripted_tool(args, *, stdout, **kwargs):
            calls.append(tuple(args))
            stdout.write(answers.get(tuple(args), 'scripted informational output').encode())
            return subprocess.CompletedProcess(args, 0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(diag, 'EVIDENCE', root), patch.object(diag.subprocess, 'run', scripted_tool), \
                    patch.dict(os.environ, {'DEVELOPER_DIR': diag.DEVELOPER, 'GITHUB_SHA': 'a' * 40,
                                           'ImageOS': 'macos15', 'ImageVersion': '20260907.0337.1', 'RUNNER_ARCH': 'ARM64'}):
                result = diag.preflight()
                self.assertEqual(result['status'], 'accepted')
                self.assertEqual(tuple(result['runtimes']), diag.RUNTIMES)
                self.assertNotIn(('xcrun', 'simctl', 'list', '--json'), calls)
                for query in ('runtimeInventory', 'deviceTypeInventory'):
                    self.assertEqual(result['commands'][query]['exitCode'], 0)
                    self.assertFalse(result['commands'][query]['truncated'])
                # Exercise the unchanged real capture bound against the same
                # oversized scripted broad response, preserving the old refusal.
                broad = diag.command(['xcrun', 'simctl', 'list', '--json'], root, 'old-broad-inventory', 90, bounded=True)
                self.assertTrue(broad['truncated'])
                self.assertEqual(broad['retainedBytes'], diag.environment.MAX_OUTPUT)
                with self.assertRaises(RuntimeError): diag.require(broad)

    def test_focused_inventory_requires_both_complete_collection_schemas(self):
        good = {'runtimeInventory': json.dumps({'runtimes': inventory()['runtimes']}),
                'deviceTypeInventory': json.dumps({'devicetypes': inventory()['devicetypes']})}
        self.assertEqual(diag.selection_inventory(good), inventory())
        for key in good:
            for invalid in ('{', 'null', '[]', '{}', json.dumps({'devices': []}),
                            json.dumps({'runtimes': {}, 'devicetypes': []})):
                with self.subTest(key=key, invalid=invalid), self.assertRaises((ValueError, TypeError)):
                    diag.selection_inventory(dict(good, **{key: invalid}))
            missing = dict(good); missing.pop(key)
            with self.assertRaises(KeyError): diag.selection_inventory(missing)

    def test_toolchain_pins_and_explicit_host_identity(self):
        values = {'architecture': 'arm64', 'developer': diag.DEVELOPER,
                  'xcode': 'Xcode 26.3\nBuild version 17C529', 'sdkVersion': '26.2',
                  'macOS': 'ProductName:\tmacOS\nProductVersion:\t15.7.1\nBuildVersion:\t24G231',
                  'sdkPath': diag.DEVELOPER + '/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator26.2.sdk'}
        image = {'ImageOS': 'macos15-arm64', 'ImageVersion': 'scripted-current-image', 'RUNNER_ARCH': 'ARM64'}
        with patch.dict(os.environ, {'DEVELOPER_DIR': diag.DEVELOPER}):
            diag.validate_toolchain(values, image)
            # Historical host equality is not claimed. Both actual cases share
            # this single observed host; missing identity still rejects the run.
            diag.validate_toolchain(values, dict(image, ImageVersion='another-observed-image'))
            for key in ('architecture', 'developer', 'xcode', 'sdkVersion', 'macOS', 'sdkPath'):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    diag.validate_toolchain(dict(values, **{key: 'changed'}), image)
            for key in image:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    diag.validate_toolchain(values, dict(image, **{key: ''}))
        with patch.dict(os.environ, {'DEVELOPER_DIR': '/unreviewed'}), self.assertRaises(ValueError):
            diag.validate_toolchain(values, image)

    def test_command_failure_keeps_raw_output_status_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = diag.command([sys.executable, '-c', 'print("real retained error"); raise SystemExit(7)'],
                                  root, 'failure', 10)
            self.assertEqual(result['exitCode'], 7)
            self.assertFalse(result['truncated'])
            self.assertIn('real retained error', (root / 'failure.log').read_text())
            self.assertEqual(json.loads((root / 'commands.json').read_text())[0], result)
            self.assertIn('startedAt', result); self.assertIn('finishedAt', result)
            with self.assertRaises(RuntimeError): diag.require(result)
            with self.assertRaises(FileExistsError): diag.command(['never-executed'], root, 'failure', 1)

    def test_failed_preflight_probes_leave_complete_partial_manifests(self):
        # Scripted subprocess responses exercise retention, not macOS or native success.
        for failure in ({'exitCode': 2}, {'timeout': True}, {'errorType': 'FileNotFoundError'}):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                def capture(args, path, timeout):
                    path.write_text('scripted probe output\n')
                    return dict(failure if args == ['xcodebuild', '-version'] else {'exitCode': 0},
                                originalBytes=22, retainedBytes=22, truncated=False)
                with patch.object(diag, 'EVIDENCE', root), patch.object(diag.environment, 'capture', capture):
                    with self.assertRaises((RuntimeError, ValueError)):
                        diag.preflight()
                manifest = json.loads((root / 'preflight/manifest.json').read_text())
                self.assertEqual(manifest['status'], 'refused')
                self.assertFalse(manifest['productAccepted'])
                self.assertGreaterEqual(len(manifest['commands']), 11)
                self.assertEqual(len(json.loads((root / 'preflight/commands.json').read_text())), len(manifest['commands']))
                for key, value in failure.items():
                    self.assertEqual(manifest['commands']['xcode'][key], value)
                self.assertTrue((root / 'preflight/xcode.log').exists())

    def test_command_timeouts_are_not_zero_exit(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(diag.subprocess, 'run',
                side_effect=subprocess.TimeoutExpired(['scripted'], 1)):
            result = diag.command(['scripted'], Path(tmp), 'timeout', 1)
            self.assertTrue(result['timeout'])
            self.assertNotIn('exitCode', result)
            self.assertTrue((Path(tmp) / 'commands.json').exists())

    def test_freeze_detects_binary_resource_signature_and_xctestrun_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); app = root / 'App.app'; app.mkdir()
            for name in ('App', 'Info.plist', 'CodeResources'):
                (app / name).write_bytes(b'original')
            xctestrun = root / 'test.xctestrun'; xctestrun.write_bytes(b'original-run')
            frozen = diag.freeze({'app': app}, xctestrun)
            for path in (*app.iterdir(), xctestrun):
                original = path.read_bytes(); path.write_bytes(b'changed')
                self.assertNotEqual(diag.freeze({'app': app}, xctestrun), frozen)
                path.write_bytes(original)
            outside = root / 'outside'; outside.write_bytes(b'outside')
            (app / 'escape').symlink_to(outside)
            with self.assertRaises(ValueError): diag.freeze({'app': app}, xctestrun)

    def test_only_exact_once_delivered_and_dismissed_selection_is_observed(self):
        self.assertTrue(diag.selection_observed(observed()))
        cases = [None, {}, dict(observed(), productAccepted=True), dict(observed(), selectedBytesRead=True),
                 dict(observed(), protocolViolation=True), dict(observed(), evidenceWriteFailed=True)]
        for key, value in [('outcome', 'waiting'), ('outcome', 'cancelled'), ('outcome', 'invalidSelection'),
                           ('callbackCount', 0), ('callbackCount', 2), ('callbackCount', True), ('dismissed', False)]:
            item = observed(); item['presentations'][-1][key] = value; cases.append(item)
        item = observed(); item['presentations'][0]['callbackCount'] = 2; cases.append(item)
        item = observed(); item['presentations'].pop(0); cases.append(item)
        for item in cases:
            with self.subTest(item=item): self.assertFalse(diag.selection_observed(item))

    def test_original_public_payload_and_reviewed_producer_are_reused(self):
        self.assertEqual(len(diag.fixture.PAYLOAD), 241)
        self.assertEqual(diag.hashlib.sha256(diag.fixture.PAYLOAD).hexdigest(),
                         '8adc01ad4d6304deb1daf74335f9acc7891ed5ed442dd85c5a50a7e30b58b96b')
        script = (HERE / 'run.py').read_text()
        for value in ('producer.build_inputs(', 'producer.target(\'arm64\')', 'producer.signing_command(',
                      'producer.inspect_signature(', 'fixture.verify(', 'environment.owned_device(',
                      'environment.capture(', 'Integration/simulator_smoke.py', 'Integration/simulator_environment.py'):
            self.assertIn(value, script)
        self.assertNotIn('fixture.seed(', script)
        self.assertNotIn('producer.install(', script)
        self.assertNotIn('setattr(', script)
        self.assertNotIn('unittest.mock', script)

    def test_focused_logs_cover_omitted_processes_with_fixed_window_and_noise_exclusion(self):
        commands = diag.provider_commands('owned-uuid', '2026-10-05 01:00:00', '2026-10-05 01:03:00')
        self.assertEqual(len(commands), 6)
        joined = str(commands)
        for identity in ('ResolverService', 'LocalStorageFileProvider', 'DocumentManagerUICore',
                         'RuntimeRecipient', 'fileproviderd', 'filecoordinationd'):
            self.assertIn(identity, joined)
        for args in commands.values():
            self.assertIn('--start', args); self.assertIn('--end', args); self.assertIn('--timezone', args)
            self.assertNotIn('--last', args)
            self.assertIn('AND NOT', args[-1]); self.assertIn('com.apple.apsd', args[-1])

    def scripted_case(self, test_exit=65, collection_failure=None, missing_stdout=False, empty_stdout=False,
                      attachment_damage=None, stdout_read_error=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); runtime = diag.RUNTIMES[0]; case = root / runtime.rsplit('.', 1)[1]; case.mkdir()
            producer_data = root / 'producer-data'; producer_data.mkdir()
            diag.fixture.seed(producer_data)  # portable fixture only, never the native diagnostic
            recipient_data = root / 'recipient-data'; (recipient_data / 'Library/Caches').mkdir(parents=True)
            failed_observation = observed()
            if test_exit:
                failed_observation['presentations'][-1]['outcome'] = 'waiting'
            (recipient_data / 'Library/Caches/RuntimeObservation.json').write_text(json.dumps(failed_observation))
            bundles = {}
            for name, bundle in [('producer', diag.producer.BUNDLE), ('recipient', diag.RECIPIENT), ('runner', 'scripted.runner')]:
                app = root / (name + '.app'); app.mkdir()
                (app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': bundle}))
                bundles[name] = app
            xctestrun = root / 'test.xctestrun'; xctestrun.write_bytes(b'scripted')
            frozen = diag.freeze(bundles, xctestrun)
            called = []
            def fake_command(args, directory, name, timeout, **kwargs):
                called.append(name)
                if name == 'ui': (case / 'picker.xcresult').mkdir()
                if name == 'export-diagnostics':
                    output = case / 'diagnostics'; output.mkdir()
                    if not missing_stdout:
                        (output / ('StandardOutputAndStandardError-' + diag.RECIPIENT + '.txt')).write_text('' if empty_stdout else 'entire scripted stdout')
                if name == 'export-attachments':
                    output = attachment_fixture(case, passed=not test_exit)
                    if attachment_damage:
                        attachment_damage(output)
                result = {'exitCode': test_exit if name == 'ui' else 0, 'file': name + '.log', 'truncated': False}
                if collection_failure and name == collection_failure[0]:
                    result.update(collection_failure[1])
                return result
            def fake_container(device, bundle, kind, directory, name):
                if kind == 'data': return producer_data if bundle == diag.producer.BUNDLE else recipient_data
                return next(app for app in bundles.values() if plistlib.loads((app / 'Info.plist').read_bytes())['CFBundleIdentifier'] == bundle)
            original_digest = diag.digest
            def checked_digest(path):
                if stdout_read_error and path.name.startswith('StandardOutputAndStandardError-'):
                    raise PermissionError('scripted stdout read error')
                return original_digest(path)
            with patch.object(diag, 'EVIDENCE', root), patch.dict(os.environ, {'GITHUB_SHA': 'a' * 40}), \
                    patch.object(diag, 'digest', checked_digest), \
                    patch.object(diag, 'command', fake_command), patch.object(diag, 'container', fake_container), \
                    patch.object(diag.environment, 'listing', return_value={}), \
                    patch.object(diag.environment, 'owned_device', return_value={}):
                result = diag.inspect_case(runtime, 'scripted-owned', bundles, xctestrun, frozen)
            self.assertEqual(json.loads((case / 'result.json').read_text()), result)
            return result, called

    def test_failed_ui_still_verifies_source_and_collects_separate_result(self):
        result, called = self.scripted_case()
        self.assertEqual(result['failedStage'], 'ui')
        self.assertTrue(result['sourceVerification']['originalPreserved'])
        self.assertFalse(result['selectionObserved']); self.assertFalse(result['diagnosticPassed'])
        self.assertFalse(result['productAccepted']); self.assertTrue(result['recipientStdoutRetained'])
        self.assertTrue(result['installedArtifactsIdentical'])
        self.assertEqual(called.count('ui'), 1)
        self.assertIn('resolver', called); self.assertIn('local-provider', called)
        self.assertIn('export-diagnostics', called); self.assertIn('export-attachments', called)

    def test_collection_failure_is_distinct_from_selection_and_blocks_diagnostic_pass(self):
        complete, _ = self.scripted_case(test_exit=0)
        self.assertTrue(complete['diagnosticPassed'])  # scripted assertion, never native evidence
        for failure in [('resolver', {'exitCode': 1}), ('fileprovider', {'truncated': True}),
                        ('export-diagnostics', {'timeout': True}),
                        ('export-attachments', {'errorType': 'FileNotFoundError'})]:
            with self.subTest(failure=failure):
                result, _ = self.scripted_case(test_exit=0, collection_failure=failure)
                self.assertTrue(result['selectionObserved'])
                self.assertTrue(result['sourceVerification']['originalPreserved'])
                self.assertFalse(result['collectionComplete'])
                self.assertFalse(result['diagnosticPassed'])
                self.assertFalse(result['productAccepted'])

    def test_missing_recipient_stdout_is_an_explicit_failure(self):
        result, _ = self.scripted_case(test_exit=0, missing_stdout=True)
        self.assertTrue(result['selectionObserved'])
        self.assertFalse(result['recipientStdoutRetained'])
        self.assertFalse(result['diagnosticPassed'])
        self.assertEqual(result['stdout'], [])

    def test_empty_stdout_or_missing_empty_corrupt_attachments_cannot_pass(self):
        result, _ = self.scripted_case(test_exit=0, empty_stdout=True)
        self.assertTrue(result['selectionObserved'])
        self.assertFalse(result['recipientStdoutRetained']); self.assertFalse(result['diagnosticPassed'])
        changes = [lambda root: (root / 'manifest.json').unlink(),
                   lambda root: (root / 'shot.png').unlink(),
                   lambda root: (root / 'shot.png').write_bytes(b''),
                   lambda root: (root / 'shot.png').write_bytes(b'not a PNG'),
                   lambda root: (root / 'hierarchy.txt').write_text(''),
                   lambda root: (root / 'hierarchy.txt').write_text('not a hierarchy'),
                   lambda root: (root / 'result.txt').write_text(''),
                   lambda root: (root / 'result.txt').write_text('not a result')]
        for change in changes:
            with self.subTest(change=change):
                result, _ = self.scripted_case(test_exit=0, attachment_damage=change)
                self.assertTrue(result['selectionObserved'])
                self.assertTrue(result['sourceVerification']['originalPreserved'])
                self.assertFalse(result['collectionComplete']); self.assertFalse(result['diagnosticPassed'])
                self.assertTrue(any(item['stage'] == 'attachmentEvidence' for item in result['errors']))

    def test_attachment_identity_and_png_corruption_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); root = attachment_fixture(directory)
            self.assertTrue(diag.attachment_evidence(directory, 'scripted-owned')['complete'])
            with self.assertRaises(ValueError): diag.attachment_evidence(directory, 'different-device')
            png = (root / 'shot.png').read_bytes()
            for corrupt in (png[:-3], png[:-1] + b'X', png + b'extra'):
                with self.subTest(corrupt=corrupt), self.assertRaises(ValueError):
                    diag.verify_screenshot(corrupt)
            manifest = json.loads((root / 'manifest.json').read_text())
            manifest[0]['attachments'][0]['exportedFileName'] = '../shot.png'
            (root / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): diag.attachment_evidence(directory, 'scripted-owned')

    def test_application_hierarchy_accepts_both_observed_wrapper_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); root = attachment_fixture(directory)
            shapes = ['Application, scripted\n  Window (Main), scripted\n    Button, scripted',
                      'Attributes: Application, scripted\nElement subtree:\nApplication, scripted\n  Window, scripted\n    Button, scripted']
            for shape in shapes:
                (root / 'hierarchy.txt').write_text(shape)
                self.assertTrue(diag.attachment_evidence(directory, 'scripted-owned')['complete'])
            for incomplete in ('Application, no descendants', '  Window, no application', 'Element subtree:'):
                (root / 'hierarchy.txt').write_text(incomplete)
                with self.assertRaises(ValueError): diag.attachment_evidence(directory, 'scripted-owned')

    def test_stdout_read_error_retains_the_case_instead_of_escaping_finally(self):
        result, called = self.scripted_case(test_exit=0, stdout_read_error=True)
        self.assertTrue(result['selectionObserved'])
        self.assertTrue(result['sourceVerification']['originalPreserved'])
        self.assertTrue(result['attachmentEvidence']['complete'])
        self.assertFalse(result['diagnosticPassed'])
        self.assertFalse(result['recipientStdoutRetained'])
        self.assertEqual(result['stdout'], [])
        self.assertTrue(any(item['stage'] == 'stdout' and item['type'] == 'PermissionError' for item in result['errors']))
        self.assertEqual(result['stage'], 'finished')

    def test_one_build_and_both_cases_even_when_first_ui_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'evidence'
            def allocate(runtime):
                (root / runtime.rsplit('.', 1)[1]).mkdir()
                return runtime
            def case(runtime, *args): return {'runtime': runtime, 'diagnosticPassed': False}
            with patch.object(diag, 'EVIDENCE', root), patch.object(diag, 'preflight', return_value={}), \
                    patch.object(diag, 'allocate', side_effect=allocate), \
                    patch.object(diag, 'build', return_value=({}, Path('unchanged'), {})) as build, \
                    patch.object(diag, 'inspect_case', side_effect=case) as inspect, \
                    patch.object(diag, 'command', return_value={'exitCode': 0}) as command, \
                    patch.object(diag, 'shutdown_all'):
                self.assertEqual(diag.run(), 1)
            self.assertEqual(build.call_count, 1)
            self.assertEqual([call.args[0] for call in inspect.call_args_list], list(diag.RUNTIMES))
            self.assertEqual(json.loads((root / 'comparison.json').read_text())['status'], 'diagnostic-failed')

    def test_native_sources_preserve_cross_container_and_real_picker_contract(self):
        source = (HERE / 'RecipientApp.swift').read_text()
        ui = (HERE / 'RuntimePickerTests.swift').read_text()
        for forbidden in ('publishInvalidDocument', 'Data(contentsOf:', 'InvalidPairingFixture',
                          'UIFileSharingEnabled', 'LSSupportsOpeningDocumentsInPlace', 'PairingFileManager',
                          'TetherlessCore', 'SwiftUI', 'delegate = nil'):
            self.assertNotIn(forbidden, source)
        self.assertIn('forOpeningContentTypes: [.propertyList, .xml], asCopy: false', source)
        self.assertIn('records[index].callbackCount += 1', source)
        self.assertIn('if controller.presentingViewController == nil && presentedViewController == nil', source)
        self.assertIn('observeDismissal(controller, index: index)', source)
        self.assertIn('productAccepted = false', source)
        self.assertIn('for attempt in 1...2', ui)
        self.assertIn('recipient.buttons["Cancel"]', ui)
        self.assertEqual(ui.count('tapDocumentItem("Tetherless-Invalid-Pairing.plist"'), 1)
        self.assertIn('XCTWaiter.wait(for: [terminal], timeout: 10)', ui)
        self.assertIn('XCTAssertEqual(outcome.label, "selectedFileURL")', ui)
        self.assertIn('"1,1,1"', ui)
        for forbidden in ('sleep(', 'coordinate(', 'doubleTap(', 'swipe', 'press(forDuration', 'retry', '.documentPicker('):
            code = '\n'.join(line for line in (ui + source).splitlines() if not line.strip().startswith('//'))
            self.assertNotIn(forbidden, code)

    def test_project_scheme_and_workflow_are_isolated_and_pinned(self):
        plistlib.loads((HERE / 'Recipient.entitlements').read_bytes())
        info = plistlib.loads((HERE / 'Recipient-Info.plist').read_bytes())
        self.assertIs(info['LSSupportsOpeningDocumentsInPlace'], True)
        self.assertNotIn('UIFileSharingEnabled', info)
        scheme = ET.parse(HERE / 'RuntimePicker.xcodeproj/xcshareddata/xcschemes/RuntimePickerTests.xcscheme')
        self.assertEqual(len(scheme.findall('.//TestableReference')), 1)
        project = (HERE / 'RuntimePicker.xcodeproj/project.pbxproj').read_text()
        self.assertIn('ARCHS = arm64', project)
        self.assertIn('CURRENT_PROJECT_VERSION = 1; MARKETING_VERSION = 1.0;', project)
        self.assertNotIn('UIFileSharingEnabled', project)
        self.assertNotIn('LSSupportsOpeningDocumentsInPlace', project)
        workflow = (diag.ROOT / '.github/workflows/document-picker-runtime.yml').read_text()
        self.assertIn('branches: [develop]', workflow)
        self.assertEqual(workflow.count("      - '"), 2)
        self.assertIn("'Diagnostics/document-picker-runtime/**'", workflow)
        self.assertIn('contents: read', workflow)
        self.assertIn('group: document-picker-runtime-', workflow)
        for forbidden in ('pull_request:', 'workflow_dispatch:', 'continue-on-error', 'submodules:', 'sudo ', 'download'):
            self.assertNotIn(forbidden, workflow)
        self.assertIn('actions/checkout@11d5960a326750d5838078e36cf38b85af677262', workflow)
        self.assertIn('actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02', workflow)
        script = (HERE / 'run.py').read_text()
        self.assertEqual(script.count("['xcodebuild', 'build-for-testing'"), 1)
        self.assertEqual(script.count("['xcodebuild', 'test-without-building'"), 1)
        self.assertNotIn("'--allowProvisioningUpdates'", script)
        self.assertNotIn("'--download-platform'", script)
        self.assertNotIn('test-iterations', script)
        self.assertNotIn('retry-tests-on-failure', script)


if __name__ == '__main__': unittest.main()
