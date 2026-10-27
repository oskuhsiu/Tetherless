"""Derived host-runner wiring with controlled archives/Python; never Cargo or Xcode."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import derived_cbindgen as derived
import run_host_tests as host
from apply_patch import VerificationError
from bounded_process import capture_helper_command

EXPECTED_COUNTS = [8, 5, 3, 4, 6]
EXPECTED_LOGS = ['01-idevice-ffi.txt', '02-idevice.txt', '03-idevice.txt', '04-idevice.txt', '05-idevice.txt']
AUDITS = ['vendor-input-audit.json', 'derived-vendor-input-audit.json', 'workspace-input-audit.json']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summary(passed):
    return f'test result: ok. {passed} passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s'


class HostVendorWiringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='host-derived-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'input'
        (self.source / 'ffi/src').mkdir(parents=True)
        (self.source / 'Cargo.toml').write_text('[workspace]\nmembers=["ffi"]\n')
        (self.source / 'ffi/Cargo.toml').write_text('[features]\ndefault=["remote_pairing"]\n')
        (self.source / 'ffi/src/bounded_pairing_host.rs').write_text('// controlled stage fixture\n')
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        self.original = (ROOT / 'upstream/registry-build' / derived.CRATE / derived.SOURCE_PATH).read_bytes()
        self.cbindgen_digest = self.archive('cbindgen', '0.29.2', {
            'Cargo.toml': b'[package]\nname="cbindgen"\nversion="0.29.2"\n',
            derived.SOURCE_PATH: self.original, 'Cargo.lock': b'version=4\n'})
        self.plist_files = {name: (ROOT / 'upstream/registry-build/plist_ffi-0.1.6' / name).read_bytes()
                            for name in ('Cargo.toml', 'Cargo.lock', 'build.rs')}
        plist_digest = self.archive('plist_ffi', '0.1.6', self.plist_files)
        (self.source / 'Cargo.lock').write_text('version=4\n' + ''.join(
            f'[[package]]\nname="{name}"\nversion="{version}"\n'
            'source="registry+https://github.com/rust-lang/crates.io-index"\n'
            f'checksum="{value}"\n' for name, version, value in
            [('cbindgen', '0.29.2', self.cbindgen_digest), ('plist_ffi', '0.1.6', plist_digest)]))
        self.toolchain = self.root / 'toolchain.json'
        self.toolchain.write_text('{"schema":1,"source_date_epoch":1}')
        self.commands = []

    def archive(self, name, version, files):
        stem = name + '-' + version
        archive = self.cache / (stem + '.crate')
        with tarfile.open(archive, 'w:gz') as tf:
            for relative, data in files.items():
                entry = tarfile.TarInfo(stem + '/' + relative)
                entry.size = len(data)
                tf.addfile(entry, io.BytesIO(data))
        return digest(archive)

    def args(self, label):
        return SimpleNamespace(source=self.source, crate_cache=self.cache,
            work_dir=self.root / (label + '-work'), output=self.root / (label + '-evidence'),
            toolchain_lock=self.toolchain, toolchain_lock_sha256=digest(self.toolchain))

    def environment(self, _config, owned):
        (owned / 'cargo-home').mkdir()
        return {'CARGO_HOME': str(owned / 'cargo-home'), 'CARGO_NET_OFFLINE': 'true'}, {'cargo': 'never-executed'}

    def stage(self, source, destination, _recipe, profile):
        self.assertEqual(profile, 'candidate-profiles/host-only.json')
        shutil.copytree(source, destination)
        return {'files': {str(p.relative_to(destination)): digest(p)
                          for p in destination.rglob('*') if p.is_file()}, 'symlinks': {}}

    def execute(self, args, command):
        # Only the synthetic archive checksum is substituted inside this fixture.
        # The production cbindgen source preimage/output and patch logic stay exact.
        with patch.object(derived, 'ARCHIVE_SHA256', self.cbindgen_digest), \
             patch.object(host, 'native_environment', side_effect=self.environment), \
             patch.object(host, 'verify_toolchain', return_value={}), \
             patch.object(host, 'stage', side_effect=self.stage), \
             patch.object(host, 'capture_helper_command', side_effect=command):
            return host.execute(args)

    def controlled_command(self, command, *, source, env, log, failed=False, passed=None):
        self.commands.append(command)
        self.assertEqual(command[0], 'never-executed')
        self.assertIn('--frozen', command)
        self.assertEqual(command[command.index('--target') + 1], 'aarch64-apple-darwin')
        self.assertEqual(env[derived.CONTEXT_VARIABLE], str(source / 'Cargo.toml'))
        self.assertEqual(env['CARGO_HOME'], str(source.parent / 'cargo-home'))
        config = tomllib.loads((source.parent / 'cargo-home/config.toml').read_text())
        self.assertEqual(config['source']['tetherless-vendor']['directory'], str(source.parent / 'build-vendor'))
        self.assertTrue(config['net']['offline'])
        self.assertFalse((source / 'vendor').exists())
        self.assertFalse((source / '.cargo').exists())
        suite = next(item for item in host.EXPECTED_FILTERS if item['filter'] == command[-1])
        text = summary(suite['expected_passed'] if passed is None else passed)
        code = 'import sys; print(' + repr(text) + '); sys.exit(' + ('7' if failed else '0') + ')'
        return capture_helper_command([sys.executable, '-u', '-c', code],
            source=source, env=dict(os.environ, **env), log=log,
            timeout_seconds=3, max_log_bytes=4096, tail_bytes=1024,
            term_grace_seconds=.2, kill_join_seconds=.2)

    def read_audits(self, directory):
        return {name: json.loads((directory / name).read_bytes()) for name in AUDITS}

    def write_generated_headers(self, source):
        for path in (source.parent / 'build-vendor/plist_ffi-0.1.6/plist.h',
                     source / 'ffi/idevice.h', source / 'cpp/include/idevice.h'):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('// controlled generated header\n')

    def assert_logs(self, directory, count, failing=None):
        self.assertEqual({p.name for p in directory.glob('*.txt')}, set(EXPECTED_LOGS[:count]))
        for index, name in enumerate(EXPECTED_LOGS[:count], start=1):
            status = json.loads((directory / (name + '.status.json')).read_bytes())
            self.assertEqual(status['outcome'], 'nonzero_exit' if index == failing else 'success')
            self.assertTrue(status['cleanup']['direct_child_reaped'])
            self.assertTrue(status['cleanup']['group_empty'])

    def test_all_five_suites_use_derived_vendor_and_exclusive_logs_with_twenty_six_fixtures(self):
        args = self.args('success')
        evidence = self.execute(args, self.controlled_command)
        self.assertEqual([command[-1] for command in self.commands], [s['filter'] for s in host.EXPECTED_FILTERS])
        self.assertEqual([s['passed'] for s in evidence['tests']], EXPECTED_COUNTS)
        self.assertEqual([s['log_file'] for s in evidence['tests']], EXPECTED_LOGS)
        self.assertEqual([s['status_file'] for s in evidence['tests']], [name + '.status.json' for name in EXPECTED_LOGS])
        self.assertEqual(evidence['expected_fixture_count'], 26)
        self.assertEqual(evidence['observed_fixture_count'], 26)
        self.assert_logs(args.output, 5)
        self.assertTrue(all(a['original_inputs_unchanged'] for a in self.read_audits(args.output).values()))
        layout = evidence['vendor_layout']
        self.assertTrue(layout['nested_metadata_frozen'])
        self.assertEqual(layout['derived_build']['metadata_context']['manifest_path'], str(args.work_dir / 'source/Cargo.toml'))
        self.assertEqual(layout['derived_build']['metadata_context']['cwd'], str(args.work_dir / 'source'))
        self.assertEqual(evidence['tooling_sha256']['derived_cbindgen.py'], digest(ROOT / 'derived_cbindgen.py'))
        self.assertEqual(json.loads((args.output / 'test-evidence.json').read_bytes()), evidence)
        for line in (args.output / 'SHA256SUMS').read_text().splitlines():
            value, name = line.split('  ', 1)
            self.assertEqual(digest(args.output / name), value)

    def test_each_suite_failure_retains_three_audits_generated_headers_and_unique_statuses(self):
        for failing in range(1, 6):
            with self.subTest(suite=failing):
                args = self.args('failure-' + str(failing))
                calls = []
                def command(command, *, source, env, log):
                    calls.append(command)
                    if len(calls) == failing:
                        self.write_generated_headers(source)
                    return self.controlled_command(command, source=source, env=env, log=log,
                                                   failed=len(calls) == failing)
                with self.assertRaisesRegex(VerificationError, 'nonzero_exit'):
                    self.execute(args, command)
                completed = args.work_dir / 'completed'
                self.assert_logs(completed, failing, failing=failing)
                self.assertEqual(len(calls), failing)
                audits = self.read_audits(completed)
                self.assertTrue(all(a['original_inputs_unchanged'] for a in audits.values()))
                self.assertEqual(audits['vendor-input-audit.json']['generated_files'], {})
                header = args.work_dir / 'build-vendor/plist_ffi-0.1.6/plist.h'
                self.assertEqual(audits['derived-vendor-input-audit.json']['generated_files']['plist_ffi-0.1.6/plist.h'], digest(header))
                for name in ('ffi/idevice.h', 'cpp/include/idevice.h'):
                    observed = audits['workspace-input-audit.json']['known_generated_headers'][name]
                    self.assertEqual(observed['status'], 'generated')
                    self.assertEqual(observed['sha256'], digest(args.work_dir / 'source' / name))
                    self.assertEqual(observed['bytes'], (args.work_dir / 'source' / name).stat().st_size)
                for folder in ('vendor', 'build-vendor'):
                    for name, data in self.plist_files.items():
                        self.assertEqual((args.work_dir / folder / 'plist_ffi-0.1.6' / name).read_bytes(), data)
                self.assertEqual((args.work_dir / 'vendor' / derived.CRATE / derived.SOURCE_PATH).read_bytes(), self.original)
                self.assertTrue((completed / 'source-manifest.json').is_file())
                self.assertTrue(json.loads((completed / 'vendor-layout.json').read_bytes())['nested_metadata_frozen'])
                self.assertFalse((completed / 'test-evidence.json').exists())
                self.assertFalse(args.output.exists())

    def test_any_changed_pristine_derived_workspace_or_owned_config_input_blocks_publication(self):
        cases = [('pristine', 'vendor/plist_ffi-0.1.6/Cargo.lock', 'vendor-input-audit.json'),
                 ('derived', 'build-vendor/plist_ffi-0.1.6/Cargo.lock', 'derived-vendor-input-audit.json'),
                 ('workspace', 'source/Cargo.lock', 'workspace-input-audit.json'),
                 ('config', 'cargo-home/config.toml', 'vendor-input-audit.json')]
        for label, relative, failed_audit in cases:
            with self.subTest(input=label):
                args = self.args(label)
                def command(_command, **_kwargs):
                    (args.work_dir / relative).write_text('controlled changed input')
                    raise VerificationError('controlled command failure')
                with self.assertRaisesRegex(VerificationError, 'authenticated workspace/vendor input changed'):
                    self.execute(args, command)
                audits = self.read_audits(args.work_dir / 'completed')
                self.assertFalse(audits[failed_audit]['original_inputs_unchanged'])
                self.assertEqual((args.work_dir / relative).read_text(), 'controlled changed input')
                self.assertFalse(args.output.exists())

    def test_wrong_suite_count_is_rejected_after_status_and_audits_are_retained(self):
        args = self.args('wrong-count')
        def command(command, **kwargs):
            return self.controlled_command(command, **kwargs, passed=20)
        with self.assertRaisesRegex(VerificationError, 'exact reviewed test count'):
            self.execute(args, command)
        self.assert_logs(args.work_dir / 'completed', 1)
        self.assertTrue(all(a['original_inputs_unchanged'] for a in self.read_audits(args.work_dir / 'completed').values()))
        self.assertFalse(args.output.exists())

    def test_helper_and_acquisition_sources_are_rejected_before_vendor_or_commands(self):
        for index, path in enumerate(('ffi/src/staged_pairing.rs', 'ffi/src/staged_acquisition.rs',
                                      'idevice/src/remote_pairing/tunnel/staged_packet_io.rs')):
            with self.subTest(path=path):
                fixture = self.source / path
                fixture.parent.mkdir(parents=True, exist_ok=True)
                fixture.write_text('// excluded controlled fixture\n')
                args = self.args('excluded-' + str(index))
                with self.assertRaisesRegex(VerificationError, 'unrelated validation/acquisition source'):
                    self.execute(args, self.controlled_command)
                self.assertFalse((args.work_dir / 'vendor').exists())
                self.assertFalse(args.output.exists())
                fixture.unlink()
        self.assertEqual(self.commands, [])


if __name__ == '__main__':
    unittest.main()
