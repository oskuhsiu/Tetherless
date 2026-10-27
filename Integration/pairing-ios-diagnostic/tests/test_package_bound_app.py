"""Synthetic complete-App retention; no Xcode, native binary or signing executes."""
from contextlib import ExitStack
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import package_bound_app as bound
import run_compile as runner
from test_native_handoff import NativeHandoffFixture
from test_diagnostic_binding import put, put_json


class PackageFixture:
    def __init__(self, root, configuration='Debug'):
        self.configuration = configuration
        self.native = NativeHandoffFixture(root / 'native')
        f = self.native
        self.repository = f.repository
        f.fixture.write_contract()
        put(self.repository / '.gitignore', b'.pairing-consumer/\n')
        put(f.fixture.prepared / 'SideStore/SideStore.entitlements', plistlib.dumps({'application-identifier': 'DECLARATION.ONLY'}))
        f.source_identities()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Packaging Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('add', '.')
        self.git('commit', '-qm', 'synthetic package sources')
        commit = self.git('rev-parse', 'HEAD')
        f.context['source_commit'] = commit
        f.data['api_consumer_commit']['sha'] = commit
        f.data['api_consumer_commit']['url'] = 'https://api.github.com/repos/example/repository/git/commits/' + commit
        self.work = self.repository / '.pairing-consumer'
        handoff = self.work / 'handoff'
        handoff.mkdir(parents=True)
        for lane in f.data['artifacts']:
            shutil.copytree(f.root / lane, handoff / lane)
            shutil.copyfile(f.root / (lane + '.zip'), handoff / (lane + '.zip'))
        f.root = handoff
        f.path = handoff / 'handoff.json'
        f.fixture.artifact = handoff / 'apple-producer/apple-producer-output'
        f.fixture.output = self.work / 'diagnostic'
        f.refresh()
        self.binding = f.bind()
        self.binding_path = f.fixture.output / 'TETHERLESS_PAIRING_DIAGNOSTIC_BINDING.json'
        self.compile_root = self.work / ('compile-' + configuration.lower())
        self.evidence = self.compile_root / 'evidence'
        self.derived = self.compile_root / 'DerivedData'
        (self.derived / 'SourcePackages').mkdir(parents=True)
        self.app = self.derived / ('Build/Products/' + configuration + '-iphoneos/SideStore.app')
        self.bundle(self.app, 'SideStore', 'example.app')
        self.bundle(self.app / 'PlugIns/Widget.appex', 'Widget', 'example.widget')
        self.bundle(self.app / 'Frameworks/Support.framework', 'Support', 'example.framework')
        put(self.app / 'Resources/deep/asset.dat', b'all nested bytes retained\x00\xff')
        put(self.app / 'Resources/Empty.bundle/Info.plist', plistlib.dumps({'CFBundleIdentifier': 'example.resource'}))
        put(self.app / 'Base.lproj/Launch.storyboardc/Info.plist', plistlib.dumps({'CFBundleIdentifier': 'not.a.bundle'}))
        (self.app / 'asset-link').symlink_to('Resources/deep/asset.dat')
        nested = io.BytesIO()
        with zipfile.ZipFile(nested, 'w') as archive:
            archive.writestr('Payload/Nested.app/Info.plist', plistlib.dumps({'CFBundleIdentifier': 'example.nested'}))
            archive.writestr('Payload/Nested.app/Nested', b'nested opaque executable')
        put(self.app / 'Nested.ipa', nested.getvalue())
        self.link_map = self.evidence / 'link-maps/SideStore-arm64.map'
        map_hash = put(self.link_map, b'synthetic final linker map\n')
        self.audits = {name: {'original_inputs_unchanged': True} for name in bound.AUDITS}
        for name, value in self.audits.items():
            put_json(self.evidence / name, value)
        identity = bound.delivery.file_identity(self.app / 'SideStore')
        self.receipt = {'schema': 1, 'mode': 'diagnostic-only', 'configuration': configuration,
            'binding_receipt_sha256': bound.delivery.file_identity(self.binding_path)['sha256'],
            'native_handoff': self.binding['native_handoff'], 'input_audits': self.audits,
            'link_map_sha256': map_hash, 'app_binary_executed': False,
            'runtime_capability_gates_changed': False, 'consumer_or_product_activation': False,
            'observations': {'configuration': configuration, 'ios_binaries_executed': False,
                'consumer_or_product_activation': False,
                'link': {'output': str(self.app / 'SideStore'), 'output_size': identity['size'],
                         'output_sha256': identity['sha256']}}}
        self.compile_path = self.evidence / 'diagnostic-compile-evidence.json'
        self.write_compile()
        context, producer = f.context, f.context['producer_context']
        self.env = {'GITHUB_REPOSITORY': context['repository'], 'GITHUB_REPOSITORY_ID': str(context['repository_id']),
            'GITHUB_SHA': context['source_commit'], 'GITHUB_RUN_ID': str(context['run_id']),
            'GITHUB_RUN_ATTEMPT': str(context['consumer_attempt']),
            'PRODUCER_SOURCE_COMMIT': producer['source_commit'], 'PRODUCER_RUN_ID': str(producer['run_id']),
            'PRODUCER_RUN_ATTEMPT': str(producer['run_attempt']),
            'HANDOFF_SHA256': f.handoff_hash, 'APPLE_RECEIPT_SHA256': f.fixture.receipt_hash,
            'BINDING_RECEIPT_SHA256': self.receipt['binding_receipt_sha256'],
            'COMPONENT_FIXTURES_RESULT': 'success', 'NATIVE_PROOFS_RESULT': 'success'}
        self.output = self.work / 'packages' / configuration
        self.zip_change = None
        self.after_zip = None

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repository), *args], stderr=subprocess.DEVNULL).decode().strip()

    def bundle(self, root, executable, identifier):
        put(root / 'Info.plist', plistlib.dumps({'CFBundleExecutable': executable, 'CFBundleIdentifier': identifier,
            'CFBundleShortVersionString': '1.0', 'CFBundleVersion': '1'}))
        put(root / executable, b'synthetic opaque bytes for ' + executable.encode())
        (root / executable).chmod(0o755)

    def write_compile(self):
        put_json(self.compile_path, self.receipt)

    def zip_command(self, command, **kwargs):
        if command[0] != 'ditto':
            raise AssertionError('unexpected subprocess: ' + str(command))
        payload = Path(command[-2])
        entries = []
        for path in sorted(payload.rglob('*')):
            if path.is_symlink():
                entry = zipfile.ZipInfo(path.relative_to(payload.parent).as_posix())
                entry.create_system = 3
                entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                entries.append((entry, os.readlink(path).encode()))
            elif path.is_file():
                entry = zipfile.ZipInfo(path.relative_to(payload.parent).as_posix())
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | (path.stat().st_mode & 0o777)) << 16
                entries.append((entry, path.read_bytes()))
        if self.zip_change:
            entries = self.zip_change(entries)
        with zipfile.ZipFile(command[-1], 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries:
                archive.writestr(name, data)
        if self.after_zip:
            self.after_zip()
        return subprocess.CompletedProcess(command, 0)

    def patches(self):
        stack = ExitStack()
        stack.enter_context(patch.object(runner, 'HERE', self.native.fixture.here))
        stack.enter_context(self.native.fixture.mock_retained())
        stack.enter_context(patch.object(bound.packager.subprocess, 'run', side_effect=self.zip_command))
        stack.enter_context(patch.object(bound.delivery, 'toolchain', return_value={'fixture': True}))
        return stack

    def run(self):
        with self.patches():
            return bound.package_bound(self.configuration, self.env, repository=self.repository)


class BoundPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='bound-package-tests-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.f = PackageFixture(self.root)

    def reject(self, pattern=None):
        with self.assertRaisesRegex((ValueError, KeyError, OSError), pattern or '.'):
            self.f.run()
        self.assertFalse(self.f.output.exists())
        if self.f.output.parent.exists():
            self.assertFalse(list(self.f.output.parent.glob('.bound-package-*')))

    def test_complete_debug_package_joins_all_identities_and_preserves_nested_payloads(self):
        ipa = self.f.run()
        receipt = json.loads((ipa.parent / 'package-binding.json').read_text())
        self.assertEqual(receipt['consumer']['source_commit'], self.f.env['GITHUB_SHA'])
        self.assertEqual(receipt['consumer']['run_id'], 789)
        self.assertEqual(receipt['producer']['run_id'], 456)
        self.assertEqual(receipt['producer']['source_commit'], 'a' * 40)
        self.assertEqual(receipt['native_handoff'], self.f.binding['native_handoff'])
        self.assertEqual(receipt['evidence']['binding-receipt.json']['sha256'], self.f.env['BINDING_RECEIPT_SHA256'])
        self.assertEqual(receipt['evidence']['native-handoff.json']['sha256'], self.f.env['HANDOFF_SHA256'])
        self.assertTrue(receipt['unsigned'])
        self.assertFalse(receipt['deviceValidated'])
        self.assertFalse(receipt['releaseReady'])
        self.assertEqual(receipt['ipa']['sha256'], hashlib.sha256(ipa.read_bytes()).hexdigest())
        self.assertEqual({row['bundleIdentifier'] for row in receipt['canonicalBundles']},
                         {'example.app', 'example.widget', 'example.framework', 'example.resource', 'example.nested'})
        declarations = receipt['entitlementDeclarations']
        self.assertFalse(declarations['effectiveSigningRightsEstablished'])
        self.assertEqual(declarations['inventorySource'], 'inputs.json:files')
        self.assertEqual(declarations['generatedDerivedDataXcent'], 'not-collected')
        self.assertTrue(any(row['path'].endswith('.entitlements') for row in declarations['files']))
        for name in ('available-source.tar.gz', 'available-notices.tar.gz', 'inputs.json', 'notices.json',
                     'ipa-inventory.json', 'compiled-app-inventory.json', 'manifest.json'):
            self.assertTrue((ipa.parent / name).is_file())
        manifest = json.loads((ipa.parent / 'manifest.json').read_text())
        self.assertTrue(all(gate['status'] == 'unresolved' for gate in manifest['releaseGates']))
        for line in (ipa.parent / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ')
            self.assertEqual(digest, hashlib.sha256((ipa.parent / name).read_bytes()).hexdigest())
        self.assertEqual(len((ipa.parent / 'SHA256SUMS').read_text().splitlines()), len(list(ipa.parent.iterdir())) - 1)
        original = bound.app_inventory(self.f.app)
        self.assertEqual(bound.verify_inventory(ipa, original)['inventory'],
                         json.loads((ipa.parent / 'ipa-inventory.json').read_text()))
        self.assertIn('asset-link', [row['path'] for row in original if row['type'] == 'symlink'])

    def test_release_uses_only_its_own_paths_configuration_and_source_packages(self):
        self.f = PackageFixture(self.root / 'release', 'Release')
        with patch.object(bound.packager, 'package', wraps=bound.packager.package) as packaged:
            ipa = self.f.run()
        self.assertEqual(ipa.parent, self.f.work / 'packages/Release')
        self.assertEqual(packaged.call_args.kwargs['prepared'], self.f.work / 'diagnostic')
        self.assertEqual(packaged.call_args.kwargs['source_packages'], self.f.derived / 'SourcePackages')
        self.assertEqual(json.loads((ipa.parent / 'package-binding.json').read_text())['configuration'], 'Release')

    def test_invalid_configuration_rejected(self):
        self.f.configuration = 'AdHoc'
        self.reject('configuration')

    def test_cross_consumer_and_producer_contexts_rejected_before_packager(self):
        for key, value in {'GITHUB_REPOSITORY': 'other/repo', 'GITHUB_REPOSITORY_ID': '999',
                'GITHUB_SHA': 'd' * 40, 'GITHUB_RUN_ID': '999', 'GITHUB_RUN_ATTEMPT': '2',
                'PRODUCER_SOURCE_COMMIT': 'c' * 40, 'PRODUCER_RUN_ID': '999', 'PRODUCER_RUN_ATTEMPT': '4'}.items():
            with self.subTest(key=key), patch.dict(self.f.env, {key: value}), patch.object(bound.packager, 'package') as packaged:
                self.reject('context')
                packaged.assert_not_called()

    def test_invalid_or_missing_independent_hashes_and_needs_rejected(self):
        for key in ('BINDING_RECEIPT_SHA256', 'HANDOFF_SHA256', 'APPLE_RECEIPT_SHA256',
                    'COMPONENT_FIXTURES_RESULT', 'NATIVE_PROOFS_RESULT'):
            with self.subTest(key=key), patch.dict(self.f.env, {key: ''}):
                self.reject()
        with patch.dict(self.f.env, {'BINDING_RECEIPT_SHA256': '0' * 64}):
            self.reject('hash differs')
        with patch.dict(self.f.env, {'HANDOFF_SHA256': '0' * 64}):
            self.reject('hash differs')
        with patch.dict(self.f.env, {'APPLE_RECEIPT_SHA256': '0' * 64}):
            self.reject('handoff differs')

    def test_wrong_compile_configuration_binding_or_native_handoff_rejected(self):
        original = copy.deepcopy(self.f.receipt)
        for change in ({'configuration': 'Release'}, {'binding_receipt_sha256': '0' * 64},
                       {'native_handoff': {}}, {'app_binary_executed': True}, {'runtime_capability_gates_changed': True}):
            with self.subTest(change=change):
                self.f.receipt = dict(original, **change)
                self.f.write_compile()
                self.reject()

    def test_each_missing_false_or_nonboolean_input_audit_rejected(self):
        original = copy.deepcopy(self.f.receipt)
        for name in bound.AUDITS:
            for value in (None, False, 1, 'true'):
                with self.subTest(name=name, value=value):
                    self.f.receipt = copy.deepcopy(original)
                    if value is None:
                        del self.f.receipt['input_audits'][name]
                    else:
                        self.f.receipt['input_audits'][name]['original_inputs_unchanged'] = value
                    self.f.write_compile()
                    self.reject('audit')

    def test_changed_audit_sidecar_link_map_and_contract_rejected(self):
        for path in (self.f.evidence / bound.AUDITS[0], self.f.link_map,
                     self.f.native.fixture.here / 'input-contract.json'):
            original = path.read_bytes()
            with self.subTest(path=path):
                path.write_bytes(original + b'\n')
                # Whitespace preserves audit semantics; the link-map/contract hash is exact.
                if path.name == bound.AUDITS[0]:
                    path.write_text('{"original_inputs_unchanged":false}')
                self.reject()
                path.write_bytes(original)

    def test_missing_or_changed_executable_never_falls_back(self):
        path = self.f.app / 'SideStore'
        original = path.read_bytes()
        for data in (None, b'', original + b'changed'):
            with self.subTest(data=data):
                if data is None:
                    path.unlink()
                else:
                    path.write_bytes(data)
                self.reject()
                path.write_bytes(original)

    def test_observed_executable_path_size_and_hash_all_must_match(self):
        original = copy.deepcopy(self.f.receipt)
        for key, value in (('output', str(self.f.app / 'Other')), ('output_size', 1),
                           ('output_size', True), ('output_sha256', '0' * 64)):
            self.f.receipt = copy.deepcopy(original)
            self.f.receipt['observations']['link'][key] = value
            self.f.write_compile()
            self.reject('executable')

    def test_missing_or_changed_nested_payload_in_ipa_rejected(self):
        for suffix in ('/Widget.appex/Widget', '/Support.framework/Support', '/deep/asset.dat', '/Nested.ipa', '/asset-link'):
            for action in ('missing', 'changed'):
                def change(entries):
                    result = []
                    for name, data in entries:
                        path = name.filename if isinstance(name, zipfile.ZipInfo) else name
                        if path.endswith(suffix):
                            if action == 'missing':
                                continue
                            data = b'other safe target' if suffix == '/asset-link' else data + b'changed'
                        result.append((name, data))
                    return result
                with self.subTest(suffix=suffix, action=action):
                    self.f.zip_change = change
                    self.reject()

    def test_changed_app_extension_framework_and_resource_executable_bits_rejected(self):
        for suffix in ('/SideStore', '/Widget.appex/Widget', '/Support.framework/Support', '/deep/asset.dat'):
            for bits in ((0o100,) if suffix == '/deep/asset.dat' else (0, 0o011)):
                def change(entries):
                    for name, data in entries:
                        path = name.filename if isinstance(name, zipfile.ZipInfo) else name
                        if path.endswith(suffix):
                            mode = name.external_attr >> 16
                            name.external_attr = ((mode & ~0o111) | bits) << 16
                    return entries
                with self.subTest(suffix=suffix, bits=bits):
                    self.f.zip_change = change
                    self.reject('executable bits')

    def test_extra_outer_payload_rejected(self):
        self.f.zip_change = lambda entries: entries + [('Payload/Unexpected.app/file', b'other')]
        self.reject('outside')

    def test_input_changes_during_packaging_block_final_publication(self):
        self.f.after_zip = lambda: (self.f.app / 'Resources/deep/asset.dat').write_bytes(b'racing resource change')
        self.reject('App changed')

    def test_compile_receipt_changes_during_packaging_block_final_publication(self):
        self.f.after_zip = lambda: self.f.compile_path.write_bytes(self.f.compile_path.read_bytes() + b'\n')
        self.reject('evidence changed')

    def test_generic_package_missing_companion_is_not_admitted(self):
        real_package = bound.packager.package
        def incomplete(*args, **kwargs):
            ipa = real_package(*args, **kwargs)
            (ipa.parent / 'available-notices.tar.gz').unlink()
            return ipa
        with patch.object(bound.packager, 'package', side_effect=incomplete):
            self.reject('checksums')

    def test_ipa_changed_after_inventory_is_not_admitted(self):
        real_verify = bound.verify_inventory
        def change(ipa, original):
            result = real_verify(ipa, original)
            ipa.write_bytes(ipa.read_bytes() + b'changed after inventory')
            return result
        with patch.object(bound, 'verify_inventory', side_effect=change):
            self.reject('generic package changed')

    def test_large_valid_link_map_is_streamed_without_json_metadata_limit(self):
        self.f.link_map.write_bytes(b'm' * (bound.delivery.MAX_METADATA_BYTES + 1))
        self.f.receipt['link_map_sha256'] = bound.delivery.file_identity(self.f.link_map)['sha256']
        self.f.write_compile()
        ipa = self.f.run()
        self.assertEqual(bound.delivery.file_identity(ipa.parent / 'SideStore-arm64.map'),
                         bound.delivery.file_identity(self.f.link_map))

    def test_current_bound_source_mutation_rejected(self):
        name = next(iter(self.f.binding['bound_files']))
        (self.f.work / 'diagnostic' / name).write_bytes(b'changed bound input')
        self.reject('bound inputs changed')

    def test_native_artifact_zip_changed_after_compile_rejected(self):
        archive = self.f.work / 'handoff/apple-producer.zip'
        archive.write_bytes(archive.read_bytes() + b'changed')
        self.reject('ZIP')

    def test_existing_output_is_not_overwritten(self):
        self.f.output.mkdir(parents=True)
        marker = self.f.output / 'previous'
        marker.write_text('keep')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.f.run()
        self.assertEqual(marker.read_text(), 'keep')

    def test_racing_empty_destination_is_not_replaced(self):
        real_publish = bound.publish_directory
        def collide(source, target):
            target.mkdir()
            real_publish(source, target)
        with patch.object(bound, 'publish_directory', side_effect=collide), self.assertRaises(FileExistsError):
            self.f.run()
        self.assertEqual(list(self.f.output.iterdir()), [])
        self.assertFalse(list(self.f.output.parent.glob('.bound-package-*')))

    def test_package_failure_leaves_no_incomplete_final_output(self):
        with patch.object(bound.packager, 'package', side_effect=ValueError('controlled generic package failure')):
            self.reject('controlled')

    def test_final_publication_failure_leaves_no_incomplete_final_output(self):
        with patch.object(bound, 'publish_directory', side_effect=OSError('controlled publication failure')):
            self.reject('controlled')

    def test_symlink_output_parent_and_compile_evidence_rejected(self):
        self.f.output.parent.symlink_to(self.root, target_is_directory=True)
        self.reject('symlink')
        self.f.output.parent.unlink()
        original = self.f.compile_path.with_suffix('.saved')
        self.f.compile_path.rename(original)
        self.f.compile_path.symlink_to(original)
        self.reject()

    def test_duplicate_evidence_json_keys_rejected(self):
        self.f.compile_path.write_text('{"schema":1,"schema":1}')
        self.reject('duplicate')


class WorkflowPackageTests(unittest.TestCase):
    def test_per_configuration_gates_paths_and_partial_evidence_are_retained(self):
        workflow = (HERE.parents[1] / '.github/workflows/pairing-ios-diagnostic.yml').read_text()
        for label, configuration in (('debug', 'Debug'), ('release', 'Release')):
            self.assertIn('id: compile_' + label, workflow)
            start = workflow.index('      - name: Package bound unsigned ' + configuration)
            end = workflow.index('      - name:', start + 8)
            step = workflow[start:end]
            self.assertIn("!cancelled() && steps.compile_" + label + ".outcome == 'success'", step)
            self.assertIn('package_bound_app.py --configuration ' + configuration, step)
            for key in ('HANDOFF_SHA256', 'APPLE_RECEIPT_SHA256', 'BINDING_RECEIPT_SHA256',
                        'COMPONENT_FIXTURES_RESULT', 'NATIVE_PROOFS_RESULT'):
                self.assertIn(key + ': ${{ steps.', step)
            self.assertIn("always() && steps.package_" + label + ".outcome == 'success'", workflow)
            self.assertIn('path: .pairing-consumer/packages/' + configuration + '/', workflow)
            self.assertIn('pairing-ios-unsigned-' + label + '-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}', workflow)
        release = workflow[workflow.index('      - name: Compile unsigned Release'):]
        self.assertIn("if: ${{ !cancelled() && steps.bind.outcome == 'success' }}", release[:release.index('      - name:', 8)])
        self.assertIn('      - name: Retain authenticated handoff and bounded diagnostic evidence\n        if: always()', workflow)
        self.assertIn("paths: ['Integration/pairing-ios-diagnostic/runtime-producer.json']", workflow)
        self.assertNotIn('workflow_dispatch:', workflow)
        self.assertIn('cancel-in-progress: false', workflow)

    def test_unmodified_generic_packager_is_used_without_signing_or_upload_commands(self):
        source = (HERE / 'package_bound_app.py').read_text()
        self.assertIn("HERE.parent / 'package_unsigned.py'", source)
        self.assertIn('packager.package(app, staged', source)
        for forbidden in ('codesign', 'xcrun altool', 'xcrun devicectl', 'xcodebuild -exportArchive'):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()
