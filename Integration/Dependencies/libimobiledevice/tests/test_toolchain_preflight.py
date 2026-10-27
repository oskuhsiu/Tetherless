"""Retained Swift bytes and mocked read-only preflight. No native tools execute."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import build_provider as b
from build_pairing_apple import SWIFT_26_3_MERGED, SWIFT_26_3_STDOUT

RAW = (HERE/'tests/fixtures/swift-26.3-merged.txt').read_bytes()


class ReadOnlyRunner:
    """Write explicitly synthetic observations without launching any process."""
    def __init__(self, work, swift=RAW):
        self.work = work
        work.mkdir(parents=True, exist_ok=True)
        self.evidence = work/'evidence'
        self.evidence.mkdir()
        self.env = {'PATH': '/synthetic/read-only/tools'}
        self.serial = 0
        self.calls = []
        self.fail_label = None
        self.values = {
            'toolchain-xcode': (b.APPLE['xcode']+'\n').encode(),
            'toolchain-macos_version': b'15.7.9\n',
            'toolchain-macos_build': b'24G830\n',
            'toolchain-clang': (b.APPLE['clang']+'\nTarget: arm64-apple-darwin24.6.0\n').encode(),
            'toolchain-swift': swift,
            'iphoneos-sdk_version': b'26.2\n',
            'iphoneos-sdk_build': b'23C57\n',
            'iphonesimulator-sdk_version': b'26.2\n',
            'iphonesimulator-sdk_build': b'23C57\n',
            'host-show-sdk-version': b'26.2\n',
            'host-show-sdk-build-version': b'25C58\n',
        }
        for name in ('autoconf','autoheader','automake','aclocal','glibtoolize','pkg-config','m4','make'):
            self.values['tool-'+name] = b'synthetic fixture version\n'
        self.values['tool-m4'] = b'm4 (GNU M4) 1.4.20\n'
        self.tool_root = work/'synthetic-tool-installation'
        (self.tool_root/'bin').mkdir(parents=True)
        for name in ('autoconf','autoheader','automake','aclocal','glibtoolize','pkg-config','m4','make'):
            (self.tool_root/'bin'/name).write_bytes(b'Not executable. Fixture bytes only.\n')
        (self.tool_root/'share/aclocal').mkdir(parents=True)
        (self.tool_root/'share/aclocal/pkg.m4').write_text('Synthetic captured macro\n')
    def resolve(self, name, command, path):
        return self.tool_root/'bin'/name
    def run(self, command, label, seconds):
        self.serial += 1
        self.calls.append([str(x) for x in command])
        if seconds != 60 or label not in self.values:
            raise AssertionError('unexpected non-preflight command')
        path = self.evidence/('%03d-%s.txt' % (self.serial,label))
        path.write_bytes(self.values[label])
        path.with_name(path.name+'.status.json').write_text(json.dumps({'synthetic_fixture':True})+'\n')
        if label == self.fail_label:
            raise ValueError('synthetic command/cleanup failure')
        return self.values[label].decode().strip()


class ToolchainPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(strict=True)
        for method,value in [('system','Darwin'),('machine','arm64')]:
            mock = patch.object(b.platform,method,return_value=value)
            mock.start(); self.addCleanup(mock.stop)
        self.count = 0
    def runner(self, swift=RAW):
        self.count += 1
        return ReadOnlyRunner(self.root/str(self.count),swift)
    def fingerprint(self, runner):
        with patch.object(b,'resolve_preinstalled_tool',side_effect=runner.resolve):
            return b.fingerprint(runner)
    def receipt(self, runner):
        return json.loads((runner.evidence/'toolchain-preflight.json').read_bytes())
    def assert_rejected(self, runner):
        with self.assertRaisesRegex(ValueError,'toolchain preflight rejected'):
            self.fingerprint(runner)
        result = self.receipt(runner)
        self.assertTrue(result['complete'])
        self.assertFalse(result['all_identity_checks_passed'])
        self.assertFalse((runner.evidence/'toolchain.json').exists())
        self.assertFalse((runner.work/'tool-macros').exists())
        return result
    def test_actual_retained_127_bytes_match_existing_reviewed_pair(self):
        self.assertEqual(len(RAW),127)
        self.assertEqual(hashlib.sha256(RAW).hexdigest(),'355986b284d60fc60e4b3c24d2bc54ff2562ee37b60ef688917cf2e531315105')
        self.assertEqual(RAW.decode().strip(),SWIFT_26_3_MERGED)
        self.assertEqual(b.APPLE['swift'],SWIFT_26_3_STDOUT)
    def test_merged_observation_reuses_validator_and_retains_raw_bytes(self):
        runner=self.runner()
        with patch.object(b,'require_toolchain_observation',wraps=b.require_toolchain_observation) as validator:
            paths,observed=self.fingerprint(runner)
        validator.assert_called_once_with(RAW.decode().strip(),SWIFT_26_3_STDOUT,'swiftc')
        self.assertEqual(observed['swift'],RAW.decode().strip())
        receipt=self.receipt(runner)
        self.assertTrue(receipt['complete']);self.assertTrue(receipt['all_identity_checks_passed'])
        self.assertEqual(len(receipt['raw_observations']),19)
        raw=receipt['raw_observations']['swift']
        self.assertEqual(raw['bytes'],127)
        self.assertEqual((runner.evidence/raw['log']).read_bytes(),RAW)
        self.assertEqual(raw['sha256'],hashlib.sha256(RAW).hexdigest())
        self.assertTrue((runner.evidence/'toolchain.json').is_file())
        self.assertEqual((Path(paths['macro_dir'])/'pkg.m4').read_bytes(),(runner.tool_root/'share/aclocal/pkg.m4').read_bytes())
    def test_original_stdout_only_exact_identity_remains_accepted(self):
        runner=self.runner((SWIFT_26_3_STDOUT+'\n').encode())
        self.fingerprint(runner)
        self.assertTrue(self.receipt(runner)['all_identity_checks_passed'])
    def test_driver_compiler_clang_target_and_extra_output_drift_rejected(self):
        for changed in [RAW.replace(b'1.127.15',b'1.127.16'),RAW.replace(b'6.2.4',b'6.2.5'),
                        RAW.replace(b'1700.6.4.2',b'1700.6.4.3'),RAW.replace(b'macosx15.0',b'macosx16.0'),
                        RAW.replace(b'arm64',b'x86_64'),b'warning: unexpected\n'+RAW,
                        RAW+b'unexpected trailing text\n',RAW.replace(b'1.127.15 ',b'1.127.15\n')]:
            with self.subTest(changed=changed):
                runner=self.runner(changed);result=self.assert_rejected(runner)
                self.assertIn('swift',{x['check'] for x in result['identity_errors']})
                self.assertEqual(len(runner.calls),19)
                self.assertIn('iphonesimulator_sdk_build',result['observations'])
                self.assertIn('tool_make',result['observations'])
    def test_all_original_apple_sdk_gates_still_fail_closed(self):
        runner=self.runner()
        runner.values['toolchain-xcode']=b'Xcode 26.4\nBuild version other\n'
        runner.values['iphoneos-sdk_build']=b'23C58\n'
        runner.values['host-show-sdk-version']=b'26.3\n'
        result=self.assert_rejected(runner)
        self.assertEqual({x['check'] for x in result['identity_errors']},{'xcode','iphoneos_sdk_build','host_show-sdk-version'})
        self.assertEqual(len(runner.calls),19)
    def test_empty_successful_clang_is_recorded_as_mismatch_and_collection_continues(self):
        runner=self.runner();runner.values['toolchain-clang']=b''
        result=self.assert_rejected(runner)
        self.assertEqual(result['identity_errors'][0]['check'],'clang')
        self.assertEqual(result['observations']['clang'],'')
        self.assertEqual(result['raw_observations']['clang']['bytes'],0)
        self.assertEqual(len(runner.calls),19)
        self.assertIn('tool_make',result['observations'])
    def test_bad_m4_still_rejected_after_other_readonly_observations(self):
        runner=self.runner();runner.values['tool-m4']=b'm4 (GNU M4) 1.4.15\n'
        result=self.assert_rejected(runner)
        self.assertEqual(result['identity_errors'][0]['check'],'m4')
    def test_missing_tool_is_reported_without_install_or_other_check_loss(self):
        runner=self.runner()
        def resolve(name,command,path):
            if name=='autoconf':raise ValueError('required preinstalled tool missing')
            return runner.resolve(name,command,path)
        with patch.object(b,'resolve_preinstalled_tool',side_effect=resolve),self.assertRaises(ValueError):
            b.fingerprint(runner)
        result=self.receipt(runner)
        self.assertTrue(result['complete']);self.assertFalse(result['all_identity_checks_passed'])
        self.assertEqual(result['identity_errors'][0]['check'],'autoconf')
        self.assertIn('tool_make',result['observations'])
        self.assertEqual(len(runner.calls),18)
    def test_missing_pkg_macro_keeps_original_gate(self):
        runner=self.runner();(runner.tool_root/'share/aclocal/pkg.m4').unlink()
        result=self.assert_rejected(runner)
        self.assertEqual(result['identity_errors'][0]['check'],'pkg_m4')
    def test_command_cleanup_failure_stops_further_processes_and_retains_partial(self):
        runner=self.runner();runner.fail_label='toolchain-swift'
        with self.assertRaisesRegex(ValueError,'synthetic command/cleanup'):
            self.fingerprint(runner)
        result=self.receipt(runner)
        self.assertFalse(result['complete']);self.assertFalse(result['all_identity_checks_passed'])
        self.assertEqual(result['collection_error']['observation'],'swift')
        self.assertEqual(len(runner.calls),5)
        self.assertEqual((runner.evidence/'005-toolchain-swift.txt').read_bytes(),RAW)
        self.assertFalse((runner.evidence/'toolchain.json').exists())
    def test_invalid_identity_stops_real_orchestrator_before_source_provider_or_host_tests(self):
        work=self.root/'orchestration'
        runner=ReadOnlyRunner(work,RAW+b'changed\n')
        # build() owns creation of work. Move the synthetic runner underneath a
        # separate path so the requested build output can still start fresh.
        requested=self.root/'owned-new-work'
        args=SimpleNamespace(work=requested,source=self.root/'absent-source',
                             openssl=self.root/'absent-openssl',old_provider=self.root/'absent-old')
        with patch.object(b,'Runner',return_value=runner),patch.object(b,'recipe_inventory',return_value={}), \
             patch.object(b,'verify_retained_sources'),patch.object(b,'resolve_preinstalled_tool',side_effect=runner.resolve), \
             patch.object(b,'load_openssl') as provider,patch.object(b,'autotools') as compile:
            with self.assertRaisesRegex(ValueError,'toolchain preflight rejected'):
                b.build(args)
        provider.assert_not_called();compile.assert_not_called()
        self.assertEqual(len(runner.calls),19)
        self.assertFalse((runner.work/'host-sources').exists())
    def test_non_arm64_macos_is_still_rejected_before_queries(self):
        runner=self.runner()
        with patch.object(b.platform,'machine',return_value='x86_64'),self.assertRaises(ValueError):
            self.fingerprint(runner)
        self.assertEqual(runner.calls,[])

if __name__=='__main__':unittest.main()
