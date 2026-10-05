"""Typed production rejection and exact-runtime coverage; no native acceptance claims."""
from pathlib import Path
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('import_environment', ROOT / 'simulator_environment.py')
environment = importlib.util.module_from_spec(spec); spec.loader.exec_module(environment)


def configuration_inputs():
    values = {'architecture': 'arm64', 'developer': environment.DEVELOPER,
              'xcode': 'Xcode 26.3\nBuild version 17C529', 'sdkVersion': '26.2', 'sdkBuild': '23C57',
              'sdkPath': environment.DEVELOPER + '/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator26.2.sdk',
              'macOS': 'ProductName: macOS\nProductVersion: 15.7.9\nBuildVersion: 24G830',
              'runtimeInventory': json.dumps({'runtimes': [
                  {'identifier': runtime, 'version': version, 'buildversion': build, 'isAvailable': True}
                  for runtime, version, build in environment.CONFIGURATIONS.values()]}),
              'deviceTypeInventory': json.dumps({'devicetypes': [
                  {'identifier': environment.DEVICE_TYPE, 'name': 'iPhone SE (3rd generation)'}]})}
    image = {'RUNNER_ARCH': 'ARM64', 'ImageOS': 'macos15', 'ImageVersion': '20260907.0337.1'}
    return values, image


class ExactProductEnvironmentTests(unittest.TestCase):
    def test_both_configs_select_exact_installed_runtime_build_and_device(self):
        values, image = configuration_inputs()
        for configuration, (runtime, version, build) in environment.CONFIGURATIONS.items():
            with self.subTest(configuration=configuration):
                selected = environment.validate_configuration(values, image, configuration)
                self.assertEqual(selected['runtime'], runtime)
                self.assertEqual(selected['runtimeVersion'], version)
                self.assertEqual(selected['runtimeBuild'], build)
                self.assertEqual(selected['deviceType'], environment.DEVICE_TYPE)
                self.assertEqual(selected['architecture'], 'arm64')

    def test_requested_runtime_missing_unavailable_duplicated_or_build_drift_fails(self):
        for mutation in ('missing', 'unavailable', 'duplicate', 'build', 'version'):
            with self.subTest(mutation=mutation):
                values, image = configuration_inputs()
                runtimes = json.loads(values['runtimeInventory'])['runtimes']
                target = runtimes[1]
                if mutation == 'missing': runtimes.remove(target)
                elif mutation == 'duplicate': runtimes.append(target)
                elif mutation == 'unavailable': target['isAvailable'] = False
                elif mutation == 'build': target['buildversion'] = 'different'
                elif mutation == 'version': target['version'] = '18.5'
                values['runtimeInventory'] = json.dumps({'runtimes': runtimes})
                with self.assertRaisesRegex(ValueError, 'Required exact installed runtime'):
                    environment.validate_configuration(values, image, 'ios-18-6')

    def test_missing_exact_device_never_uses_other_size(self):
        values, image = configuration_inputs()
        for devices in ([], [{'identifier': 'com.apple.CoreSimulator.SimDeviceType.iPhone-17', 'name': 'iPhone 17'}],
                        [{'identifier': environment.DEVICE_TYPE, 'name': 'SE'}] * 2):
            values['deviceTypeInventory'] = json.dumps({'devicetypes': devices})
            with self.assertRaises(ValueError):
                environment.validate_configuration(values, image, 'ios-18-6')

    def test_actual_architecture_toolchain_sdk_are_required(self):
        for key in ('architecture', 'developer', 'xcode', 'sdkVersion', 'sdkBuild', 'sdkPath', 'macOS'):
            with self.subTest(key=key):
                values, image = configuration_inputs(); values[key] = 'different'
                with self.assertRaises(ValueError):
                    environment.validate_configuration(values, image, 'ios-18-6')
        for key in ('RUNNER_ARCH', 'ImageOS', 'ImageVersion'):
            values, image = configuration_inputs(); image[key] = ''
            with self.assertRaises(ValueError):
                environment.validate_configuration(values, image, 'ios-18-6')

    def test_incomplete_inventories_fail_closed(self):
        for key, bad in [('runtimeInventory', '{}'), ('runtimeInventory', '{'),
                         ('runtimeInventory', '{"runtimes": [null]}'),
                         ('deviceTypeInventory', '{"devicetypes": [] ,"devices": []}')]:
            values, image = configuration_inputs(); values[key] = bad
            with self.assertRaises(ValueError):
                environment.validate_configuration(values, image, 'ios-18-6')

    def test_failed_preflight_cannot_allocate_or_fallback(self):
        with patch.object(environment, 'OWNER') as owner, \
             patch.object(environment, 'preflight', side_effect=ValueError('missing runtime')) as preflight, \
             patch.object(environment, 'listing') as listing, \
             patch.object(environment.subprocess, 'check_output') as create:
            owner.exists.return_value = False
            with self.assertRaises(ValueError): environment.allocate('ios-18-6')
            preflight.assert_called_once_with('ios-18-6')
            listing.assert_not_called(); create.assert_not_called()

    def test_exact_allocation_uses_new_owned_uuid_even_without_template_device(self):
        values, image = configuration_inputs()
        selected = environment.validate_configuration(values, image, 'ios-18-6')
        identifier = 'F7D98FC7-1590-4A40-B6B7-B67E1EA2C910'
        with tempfile.TemporaryDirectory() as temporary:
            old = Path.cwd(); os.chdir(temporary)
            try:
                with patch.object(environment, 'preflight', return_value=selected), \
                     patch.object(environment, 'listing', return_value={'devices': {}}), \
                     patch.object(environment.subprocess, 'check_output', return_value=identifier) as create, \
                     patch.dict(os.environ, {'GITHUB_ENV': str(Path(temporary)/'env'), 'GITHUB_SHA': 'a' * 40}):
                    self.assertEqual(environment.allocate('ios-18-6'), identifier)
                    create.assert_called_once()
                    self.assertEqual(create.call_args.args[0][:3], ['xcrun', 'simctl', 'create'])
                    self.assertEqual(create.call_args.args[0][-2:], [environment.DEVICE_TYPE, selected['runtime']])
                    owner = json.loads(environment.OWNER.read_text())
                    self.assertEqual(owner['configuration'], selected)
                    self.assertEqual(owner['sourceCommit'], 'a' * 40)
                    self.assertEqual(owner['id'], identifier)
                    self.assertTrue(owner['name'].startswith('Tetherless-CI-'))
                    with self.assertRaises(RuntimeError): environment.allocate('ios-18-6')
                    create.assert_called_once()
            finally:
                os.chdir(old)

    def test_preflight_records_probes_and_image_drift_without_claiming_acceptance(self):
        values, image = configuration_inputs()
        image['ImageVersion'] = 'new-image-identity'
        def capture(args, path, timeout):
            path.write_text(values[path.stem] + '\n')
            return {'exitCode': 0, 'truncated': False, 'timeoutSeconds': timeout}
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(environment, 'PREFLIGHT', Path(temporary)/'environment'), \
             patch.dict(os.environ, dict(image, DEVELOPER_DIR=environment.DEVELOPER)), \
             patch.object(environment, 'capture', side_effect=capture) as probe:
            selected = environment.preflight('ios-18-6')
            record = json.loads((environment.PREFLIGHT/'manifest.json').read_text())
            self.assertEqual(record['status'], 'verified')
            self.assertEqual(record['selected'], selected)
            self.assertFalse(record['productAccepted'])
            self.assertFalse(record['imageMatchesReference'])
            self.assertEqual(record['image']['ImageVersion'], 'new-image-identity')
            self.assertEqual(set(record['commands']), set(values))
            self.assertEqual(probe.call_count, len(values))
            with self.assertRaises(FileExistsError): environment.preflight('ios-18-6')

    def test_probe_timeout_error_and_truncation_remain_failed_evidence(self):
        for result in ({'exitCode': 1}, {'timeout': True}, {'errorType': 'OSError'},
                       {'exitCode': 0, 'truncated': True}):
            with self.subTest(result=result), tempfile.TemporaryDirectory() as temporary, \
                 patch.object(environment, 'PREFLIGHT', Path(temporary)/'environment'), \
                 patch.dict(os.environ, {'DEVELOPER_DIR': environment.DEVELOPER}), \
                 patch.object(environment, 'capture', return_value=result) as probe:
                with self.assertRaises(RuntimeError): environment.preflight('ios-18-6')
                record = json.loads((environment.PREFLIGHT/'manifest.json').read_text())
                self.assertEqual(record['status'], 'failed')
                self.assertFalse(record['productAccepted'])
                self.assertEqual(record['commands']['architecture'], result)
                probe.assert_called_once()

    def test_cli_configuration_is_allocation_only(self):
        for args in (['diagnose', '--configuration', 'ios-18-6'],
                     ['allocate', '--configuration', 'latest']):
            result = subprocess.run([sys.executable, str(ROOT/'simulator_environment.py'), *args],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2, result.stderr)

    def test_separate_full_product_lanes_keep_all_acceptance_and_artifacts(self):
        workflow = (ROOT.parent/'.github/workflows/native-simulator.yml').read_text()
        self.assertIn('configuration: ios-26-2', workflow)
        self.assertIn('configuration: ios-18-6', workflow)
        self.assertIn('coverage: Normal full product (iOS 26.2)', workflow)
        self.assertIn('coverage: Supplemental full product (iOS 18.6)', workflow)
        self.assertIn('fail-fast: false', workflow)
        self.assertIn('DEVELOPER_DIR: ' + environment.DEVELOPER, workflow)
        self.assertIn('allocate --configuration "${{ matrix.configuration }}"', workflow)
        self.assertIn('name: native-launch-${{ matrix.configuration }}-${{ github.sha }}', workflow)
        self.assertIn('native-simulator-environment', workflow)
        for unchanged in ('simulator_signing.py', 'simulator_smoke.py prepare', 'simulator_smoke.py launch',
                          'document_fixture_app.py', 'prepare_ui_tests.py', 'xcodebuild test',
                          'ui_document_fixture.py verify', 'simulator_environment.py shutdown'):
            self.assertIn(unchanged, workflow)
        for forbidden in ('continue-on-error', '-skip-testing:', '-only-testing:', 'downloadPlatform',
                          'sudo', 'xcode-select -s', '-retry-tests-on-failure', 'generic/platform'):
            self.assertNotIn(forbidden, workflow)


class TypedProductImportTests(unittest.TestCase):
    def setUp(self):
        self.view = (ROOT/'Overrides/OnboardingView.swift').read_text()
        self.ui = (ROOT/'UITests/TetherlessUITests.swift').read_text()

    def test_real_catch_exposes_only_closed_category_and_rethrows_unchanged(self):
        selected = self.view.split('case .selected(let url):', 1)[1].split('@ViewBuilder', 1)[0]
        self.assertIn('try PairingFileManager.shared.importPairingFile(from: url)', selected)
        self.assertIn('pairingImportFailure = PairingImportFailure(error)\n                    PairingImportDiagnostic.importFailed.record()\n                    throw error', selected)
        self.assertIn('.accessibilityValue(pairingImportFailure?.rawValue ?? "")', self.view)
        self.assertEqual(self.view.count('pairingImportFailure = PairingImportFailure(error)'), 1)
        for scope in ('choosePairingFile()', 'perform(_ operation:', 'move(_ delta:'):
            part = self.view.split('private func ' + scope, 1)[1].split('\n    }', 1)[0]
            self.assertIn('pairingImportFailure = nil', part)
        classifier = self.view.split('private enum PairingImportFailure:', 1)[1].split('@State private var pairingImportFailure', 1)[0]
        self.assertNotIn('localizedDescription', classifier)
        self.assertNotIn('String(describing:', classifier)
        self.assertNotIn('url', classifier)
        self.assertIn('"pairing/invalidContent"', classifier)
        self.assertIn('"pairing/otherFailure"', classifier)

    def test_invalid_content_is_parser_category_not_coordinated_file_io(self):
        manager = (ROOT/'Overrides/PairingFileManager.swift').read_text()
        inspect = manager.split('func inspectPairingFile(from url: URL)', 1)[1].split('func importPairingFile(', 1)[0]
        self.assertIn('let record = try PairingRecord(data: captured.get())', inspect)
        self.assertIn('guard coordinationError == nil, let captured else { throw PrivateFileError.unavailable }', inspect)
        self.assertIn('PrivateFileStore.readExternal(coordinatedURL)', inspect)
        self.assertNotIn('throw PrivateFileError.invalidContent', inspect)
        self.assertLess(inspect.index('captured.get()'), inspect.index('try parse(content: record.content)'))
        store = (ROOT.parent/'Sources/TetherlessCore/PrivateFileStore.swift').read_text()
        # No filesystem operation maps its errors to the parser's invalidContent.
        self.assertNotIn('throw PrivateFileError.invalidContent', store)
        self.assertNotIn('PrivateFileError.invalidContent', store.split('public struct PrivateFileStore:', 1)[1])
        imported = manager.split('func importPairingFile(from url:', 1)[1].split('func deletePairingFile(', 1)[0]
        self.assertLess(imported.index('inspectPairingFile(from: url)'), imported.index('savePairingFile(contents: content'))

    def test_outcome_deadline_single_selection_and_fresh_storage_observation_remain_required(self):
        self.assertIn('for attempt in 1...2', self.ui)
        self.assertEqual(self.ui.count('tapDocumentItem("Tetherless-Invalid-Pairing.plist", in: app, documentCell: true)'), 1)
        self.assertIn('let outcomeAppeared = rejected.waitForExistence(timeout: 10)', self.ui)
        self.assertIn('XCTAssertFalse(pickerStillVisible', self.ui)
        self.assertIn('XCTAssertEqual(rejected.value as? String, "pairing/invalidContent"', self.ui)
        self.assertIn('The operation did not complete.', self.ui)
        self.assertEqual(self.ui.count('assertPairingObservedMissing(app)'), 3)
        self.assertIn('app.terminate(); app.launch()', self.ui)
        self.assertIn('Protected pairing record: missing', self.ui)
        self.assertIn('Protected pairing record: unavailable', self.ui)
        self.assertIn('Protected pairing record: present', self.ui)
        self.assertIn('not retention of an existing valid pairing', self.ui)
        self.assertNotIn('coordinate(', self.ui)
        self.assertNotIn('sleep(', self.ui)
        self.assertNotIn('launchEnvironment', self.ui)

    def test_real_parser_and_exact_presentation_classifier_compile_and_run(self):
        # Exercise the production enum unchanged, together with the real parser
        # and external reader; no synthetic successful native/backend route.
        classifier = 'enum PairingImportFailure:' + self.view.split('private enum PairingImportFailure:', 1)[1].split('    @State private var pairingImportFailure', 1)[0]
        harness = '''import Foundation
CLASSIFIER
let payload = try PropertyListSerialization.data(fromPropertyList: ["TetherlessInvalidPairingFixture": true], format: .xml, options: 0)
let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
defer { try? FileManager.default.removeItem(at: directory) }
let original = directory.appendingPathComponent("public-fixture.plist")
try payload.write(to: original)
let bytes = try PrivateFileStore.readExternal(original)!
precondition(bytes == payload)
do { _ = try PairingRecord(data: bytes); fatalError("invalid fixture was accepted") }
catch { precondition(PairingImportFailure(error).rawValue == "pairing/invalidContent") }
precondition(try Data(contentsOf: original) == payload)
for error in [PrivateFileError.invalidName, .unavailable, .unsafeFile, .tooLarge, .changedDuringRead, .conflict] {
    precondition(PairingImportFailure(error).rawValue == "pairing/otherFailure")
}
precondition(PairingImportFailure(NSError(domain: "pairing/invalidContent", code: 0,
    userInfo: [NSLocalizedDescriptionKey: "private path and record must not escape"])).rawValue == "pairing/otherFailure")
precondition(PairingImportFailure(CancellationError()).rawValue == "pairing/otherFailure")
print("typed-parser-rejection-and-value-free-classification-passed")
'''.replace('CLASSIFIER', classifier)
        # Swift's precondition autoclosure cannot throw.
        harness = harness.replace('precondition(try Data(contentsOf: original) == payload)',
                                  'let unchanged = try Data(contentsOf: original)\nprecondition(unchanged == payload)')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary); source = path/'main.swift'; source.write_text(harness)
            result = subprocess.run(['swiftc', str(ROOT.parent/'Sources/TetherlessCore/PrivateFileStore.swift'),
                                     str(ROOT.parent/'Sources/TetherlessCore/PairingRecord.swift'),
                                     str(source), '-o', str(path/'check')],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(path/'check')], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'typed-parser-rejection-and-value-free-classification-passed')


if __name__ == '__main__': unittest.main()
