"""Compile/link probe orchestration with synthetic files; no packaged native API is executed."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('probe_pairing_link', ROOT / 'probe_pairing_link.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class FakeTools:
    """Only models process outcomes; it does not pretend to compile or link."""
    def __init__(self, fail=None, omit_output=None, resolution=None):
        self.calls = []
        self.fail = fail or (lambda _: False)
        self.omit_output = omit_output or (lambda _: False)
        self.resolution = resolution

    def __call__(self, command):
        self.calls.append(command)
        if self.fail(command):
            return {'status': 'failed', 'returncode': 1, 'stdout': '', 'stderr': 'synthetic tool failure'}
        if '--find' in command:
            stdout = (self.resolution or '/official/' + command[-1]) + '\n'
        elif '--show-sdk-path' in command:
            stdout = '/official/SDK/' + command[2] + '\n'
        elif '--version' in command:
            stdout = 'synthetic version\n'
        else:
            stdout = ''
            if '-o' in command and not self.omit_output(command):
                Path(command[command.index('-o') + 1]).write_bytes(b'synthetic output, not executable')
        return {'status': 'ok', 'returncode': 0, 'stdout': stdout, 'stderr': ''}


class PairingLinkProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.artifacts = self.base / 'artifacts'
        self.framework = self.artifacts / 'devicegateway/IDevice/IDevice.xcframework'
        self.framework.mkdir(parents=True)
        self.header = b'/* synthetic header identity only */\n'
        slices = copy.deepcopy(m.SLICES)
        libraries = []
        for key, value in slices.items():
            directory = self.framework / key
            (directory / 'Headers').mkdir(parents=True)
            (directory / 'Headers/idevice.h').write_bytes(self.header)
            archive = ('synthetic archive ' + key).encode()
            (directory / value['archive']).write_bytes(archive)
            value['sha256'] = sha(archive)
            libraries.append({'LibraryIdentifier': key, 'LibraryPath': value['archive'],
                'HeadersPath': 'Headers', 'SupportedArchitectures': ['arm64'], 'SupportedPlatform': 'ios',
                **({'SupportedPlatformVariant': value['variant']} if value['variant'] != 'device' else {})})
        (self.framework / 'Info.plist').write_bytes(plistlib.dumps({'AvailableLibraries': libraries}))
        self.patches = [patch.object(m, 'SLICES', slices), patch.object(m, 'HEADER_SHA256', sha(self.header))]
        for item in self.patches: item.start()
        self.output = self.base / 'evidence'

    def tearDown(self):
        for item in self.patches: item.stop()
        self.temp.cleanup()

    def test_both_compilers_and_platforms_are_separate_and_never_executed(self):
        tools = FakeTools()
        result = m.probe(self.artifacts, self.output, tools)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['scratch_cleanup'], 'completed_after_tool_quiescence')
        self.assertTrue(all(p.name == 'report.json' or p.name.endswith('.txt') for p in self.output.iterdir()))
        self.assertEqual(len(result['slices']), 2)
        self.assertEqual(json.loads((self.output / 'report.json').read_text()), result)
        self.assertEqual(result['runtime_abi_result'], 'not_evaluated')
        self.assertEqual(result['cancellation_result'], 'not_evaluated')
        self.assertEqual(result['handshake_result'], 'not_attempted')
        self.assertFalse(result['execution_attempted']); self.assertFalse(result['signing_requested'])
        self.assertTrue(all(c[0] in ['/usr/bin/xcrun', '/official/clang', '/official/swiftc'] for c in tools.calls))
        compile_calls = [c for c in tools.calls if '-c' in c or '-emit-object' in c]
        link_calls = [c for c in tools.calls if '-o' in c and c not in compile_calls]
        self.assertEqual(len(compile_calls), 4); self.assertEqual(len(link_calls), 4)
        for command in compile_calls + link_calls:
            generated = Path(command[command.index('-o') + 1])
            self.assertFalse(generated.exists())
            self.assertFalse(generated.is_relative_to(self.output))
        for command in link_calls:
            self.assertIn('-no_adhoc_codesign', command)
            for name in m.FUNCTIONS: self.assertIn('_' + name, command)
            self.assertNotIn('-undefined', command)
            self.assertNotIn('dynamic_lookup', command)
            self.assertNotIn('-weak_library', command)
        for command in compile_calls:
            self.assertIn('-target', command)
        swift_compile = [c for c in compile_calls if c[0].endswith('swiftc')]
        self.assertTrue(all('-import-objc-header' in c for c in swift_compile))

    def test_all_input_hashes_are_checked_before_any_tool_call(self):
        (self.framework / 'ios-arm64-simulator/Headers/idevice.h').write_bytes(b'drift')
        tools = FakeTools()
        result = m.probe(self.artifacts, self.output, tools)
        self.assertEqual(result['status'], 'unsupported_package_identity')
        self.assertEqual(tools.calls, [])
        self.assertTrue((self.output / 'report.json').is_file())

    def test_drift_after_initial_check_and_during_each_phase_invalidates_evidence(self):
        for index, when in enumerate(['version', 'c_compile', 'c_link', 'swift_compile', 'swift_link']):
            header = self.framework / 'ios-arm64/Headers/idevice.h'
            header.write_bytes(self.header)
            delegate = FakeTools()
            changed = False

            def runner(command):
                nonlocal changed
                phase = ('version' if '--version' in command else
                         'swift_compile' if '-emit-object' in command else
                         'swift_link' if '-emit-executable' in command else
                         'c_compile' if '-c' in command else
                         'c_link' if '-o' in command else 'other')
                result = delegate(command)
                if not changed and phase == when:
                    header.write_bytes(b'ordinary concurrent byte drift')
                    changed = True
                return result

            result = m.probe(self.artifacts, self.base / ('drift-' + str(index)), runner)
            self.assertTrue(changed, when)
            self.assertEqual(result['status'], 'incomplete', when)
            self.assertEqual(result['final_package_identity'], 'changed')
            entry = result['slices'][0]
            self.assertEqual(entry['status'], 'input_identity_changed', when)
            self.assertTrue(any(stage.get('reason') == 'input_identity_changed' for stage in entry['stages'].values()))
            if when == 'version':
                self.assertFalse(any('arm64-apple-ios17.0' in command and '-o' in command for command in delegate.calls))

    def test_archive_drift_and_last_phase_metadata_drift_cannot_report_success(self):
        archive = self.framework / 'ios-arm64' / m.SLICES['ios-arm64']['archive']
        delegate = FakeTools()
        mutated = False
        def runner(command):
            nonlocal mutated
            result = delegate(command)
            if not mutated and '-c' in command:
                archive.write_bytes(b'changed static archive')
                mutated = True
            return result
        report = m.probe(self.artifacts, self.output, runner)
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(report['slices'][0]['status'], 'input_identity_changed')
        # A metadata change after the final native link is caught by final check.
        archive.write_bytes(b'synthetic archive ios-arm64')
        delegate = FakeTools()
        info_path = self.framework / 'Info.plist'
        def late_runner(command):
            result = delegate(command)
            if '-emit-executable' in command and 'arm64-apple-ios17.0-simulator' in command:
                value = plistlib.loads(info_path.read_bytes())
                value['AvailableLibraries'][0]['SupportedPlatform'] = 'macos'
                info_path.write_bytes(plistlib.dumps(value))
            return result
        report = m.probe(self.artifacts, self.base / 'late-metadata', late_runner)
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(report['final_package_identity'], 'changed')

    def test_metadata_drift_and_duplicates_are_not_allowed(self):
        info_path = self.framework / 'Info.plist'
        original = plistlib.loads(info_path.read_bytes())
        for mode in ['duplicate', 'architecture', 'path', 'platform', 'missing']:
            info = copy.deepcopy(original)
            if mode == 'duplicate': info['AvailableLibraries'].append(info['AvailableLibraries'][0])
            elif mode == 'architecture': info['AvailableLibraries'][0]['SupportedArchitectures'] = ['x86_64']
            elif mode == 'path': info['AvailableLibraries'][0]['LibraryPath'] = '../escape.a'
            elif mode == 'platform': info['AvailableLibraries'][0]['SupportedPlatform'] = 'macos'
            else: info['AvailableLibraries'].pop()
            info_path.write_bytes(plistlib.dumps(info))
            tools = FakeTools()
            result = m.probe(self.artifacts, self.base / mode, tools)
            self.assertEqual(result['status'], 'unsupported_package_identity', mode)
            self.assertEqual(tools.calls, [])

    def test_compile_failure_does_not_attempt_its_link_or_hide_other_language(self):
        tools = FakeTools(fail=lambda c: '-emit-object' in c)
        result = m.probe(self.artifacts, self.output, tools)
        self.assertEqual(result['status'], 'incomplete')
        for entry in result['slices']:
            self.assertEqual(entry['status'], 'compile_failed')
            self.assertTrue(entry['stages']['c_link']['passed'])
            self.assertEqual(entry['stages']['swift_link']['status'], 'not_attempted')
        self.assertFalse(any('-emit-executable' in c for c in tools.calls))

    def test_link_failure_is_distinct_and_never_relaxes_link_settings(self):
        tools = FakeTools(fail=lambda c: '-emit-executable' in c)
        result = m.probe(self.artifacts, self.output, tools)
        self.assertEqual(result['status'], 'incomplete')
        for entry in result['slices']:
            self.assertEqual(entry['status'], 'link_failed')
            self.assertTrue(entry['stages']['swift_compile']['passed'])
            self.assertFalse(entry['stages']['swift_link']['passed'])
        self.assertEqual(sum('-emit-executable' in c for c in tools.calls), 2)

    def test_success_exit_without_outputs_is_not_success(self):
        for index, omitted in enumerate([lambda c: '-emit-object' in c, lambda c: '-emit-executable' in c]):
            result = m.probe(self.artifacts, self.base / ('no-output-' + str(index)), FakeTools(omit_output=omitted))
            self.assertEqual(result['status'], 'incomplete')
            expected = 'compile_failed' if index == 0 else 'link_failed'
            self.assertTrue(all(e['status'] == expected for e in result['slices']))

    def test_unsupported_tools_and_sdks_are_distinct(self):
        tools = FakeTools(fail=lambda c: '--find' in c)
        result = m.probe(self.artifacts, self.output, tools)
        self.assertEqual(result['status'], 'unsupported_toolchain')
        result = m.probe(self.artifacts, self.base / 'bad-resolution', FakeTools(resolution='relative/tool'))
        self.assertEqual(result['status'], 'unsupported_toolchain')
        result = m.probe(self.artifacts, self.base / 'no-sdk', FakeTools(fail=lambda c: '--show-sdk-path' in c))
        self.assertEqual(result['status'], 'incomplete')
        self.assertTrue(all(e['status'] == 'unsupported_sdk' for e in result['slices']))

    def test_refuses_output_overwrite_overlap_and_input_symlinks(self):
        self.output.mkdir()
        (self.output / 'previous').write_text('preserve')
        tools = FakeTools()
        for output in [self.output, self.artifacts / 'new-output', self.base]:
            with self.assertRaises(ValueError): m.probe(self.artifacts, output, tools)
        self.assertEqual((self.output / 'previous').read_text(), 'preserve')
        header = self.framework / 'ios-arm64/Headers/idevice.h'
        header.unlink()
        target = self.base / 'linked-header'; target.write_bytes(self.header)
        header.symlink_to(target)
        result = m.probe(self.artifacts, self.base / 'symlink-evidence', tools)
        self.assertEqual(result['status'], 'unsupported_package_identity')
        self.assertEqual(tools.calls, [])

    def test_input_packages_are_unchanged(self):
        before = {str(p.relative_to(self.artifacts)): p.read_bytes() for p in self.artifacts.rglob('*') if p.is_file()}
        m.probe(self.artifacts, self.output, FakeTools())
        after = {str(p.relative_to(self.artifacts)): p.read_bytes() for p in self.artifacts.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_sources_cover_actual_function_types_without_native_runtime_calls_from_main(self):
        c = (ROOT / 'PairingLinkProbe.c').read_text()
        swift = (ROOT / 'PairingLinkProbe.swift').read_text()
        for name in m.FUNCTIONS:
            self.assertIn(name, c); self.assertIn(name, swift)
        self.assertNotIn('pairable_host_', c.split('int main(void)')[1])
        self.assertNotIn('pairable_host_', swift.split('static func main()')[1])
        self.assertIn('UnsafeMutablePointer<RpPairingPeerDeviceC>?', swift)
        self.assertIn('@convention(c)', swift)
        self.assertNotIn('print(', swift)
        self.assertNotIn('dlopen', c + swift)
        self.assertNotIn('dlsym', c + swift)
        wrapper = (ROOT / 'pairing_safety.py').read_text()
        self.assertIn('Wireless pairing is unavailable', wrapper)
        self.assertNotIn('probe_pairing_link', wrapper)

    @unittest.skipUnless(shutil.which('cc'), 'No C compiler available for synthetic C signature contract')
    def test_c_source_compiles_links_with_exact_synthetic_types_and_rejects_drift(self):
        # This tests the C source fixture, not the real package or Apple linker.
        directory = self.base / 'synthetic-c'; directory.mkdir()
        header = '''#include <stdint.h>
struct PairableHostCancel; struct IdeviceFfiError; struct RpPairingPeerDeviceC; struct RpPairingFileHandle;
struct PairableHostCancel *pairable_host_cancel_new(void);
void pairable_host_cancel_signal(const struct PairableHostCancel *);
void pairable_host_cancel_free(struct PairableHostCancel *);
struct IdeviceFfiError *pairable_host_accept(const char *, const char *, uint16_t, void (*)(const char *, void *), void *, const struct PairableHostCancel *, uint8_t *, struct RpPairingPeerDeviceC **, struct RpPairingFileHandle **);
'''
        (directory / 'idevice.h').write_text(header)
        (directory / 'mock.c').write_text('''#include "idevice.h"
struct PairableHostCancel *pairable_host_cancel_new(void) { return 0; }
void pairable_host_cancel_signal(const struct PairableHostCancel *p) { (void)p; }
void pairable_host_cancel_free(struct PairableHostCancel *p) { (void)p; }
struct IdeviceFfiError *pairable_host_accept(const char *a, const char *b, uint16_t c, void (*d)(const char *, void *), void *e, const struct PairableHostCancel *f, uint8_t *g, struct RpPairingPeerDeviceC **h, struct RpPairingFileHandle **i) { (void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;(void)h;(void)i; return 0; }
''')
        command = [shutil.which('cc'), '-std=c11', '-Wall', '-Wextra', '-Werror', '-I', str(directory),
                   str(ROOT / 'PairingLinkProbe.c'), str(directory / 'mock.c'), '-o', str(directory / 'never-run')]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        # Deliberately no subprocess call to never-run.
        (directory / 'idevice.h').write_text(header.replace('uint16_t,', 'uint32_t,'))
        result = subprocess.run(command[:-3] + ['-c', '-o', str(directory / 'bad.o')], capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__': unittest.main()
