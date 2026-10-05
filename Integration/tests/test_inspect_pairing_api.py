"""Non-executable packaged-header and Apple tool-output fixtures only."""
import importlib.util
from pathlib import Path
import plistlib
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('inspect_pairing_api', ROOT / 'inspect_pairing_api.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

HEADER = '''#ifndef IDEVICE_H
#define IDEVICE_H
#ifdef __cplusplus
extern "C" {
#endif
struct IdeviceFfiError;
struct PairableHostCancel;
struct IdeviceFfiError *pairable_host_accept(const char *name, const char *model,
    unsigned short port, void (*pin_callback)(const char *, void *), void *context,
    const struct PairableHostCancel *cancel, unsigned char *irk, void **peer, void **record);
struct PairableHostCancel *pairable_host_cancel_new(void);
void pairable_host_cancel_signal(const struct PairableHostCancel *cancel);
void pairable_host_cancel_free(struct PairableHostCancel *cancel);
#ifdef __cplusplus
}
#endif
#endif
'''
NM = '\n'.join('_' + name + ' T 0000000000000040 0' for name in m.FUNCTIONS) + '\n'


def result(stdout='', status='ok', returncode=0, stderr=''):
    return {'status': status, 'returncode': returncode, 'stdout': stdout, 'stderr': stderr}


class FixtureTools:
    def __init__(self, outputs=None):
        self.commands = []
        self.outputs = outputs or {}

    def __call__(self, command):
        self.commands.append(command)
        if command == ['/usr/bin/xcrun', '--find', 'nm']:
            return result('/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/nm\n')
        if command[:2] == ['/usr/bin/file', '-b']:
            return result('current ar archive random library\n')
        if command[:3] == ['/usr/bin/xcrun', 'nm', '-arch']:
            assert command[4:7] == ['-g', '-U', '-P']
            return self.outputs.get(command[3], result(NM))
        raise AssertionError('Unexpected tool command: ' + repr(command))


def fixture(root, roles=('device', 'simulator')):
    framework = root / 'minimuxer' / 'IDevice' / 'IDevice.xcframework'
    libraries = []
    for role in roles:
        identifier = 'ios-arm64' if role == 'device' else 'ios-arm64_x86_64-simulator'
        folder = framework / identifier
        (folder / 'Headers').mkdir(parents=True)
        (folder / 'Headers/idevice.h').write_text(HEADER)
        # This is explicitly not a Mach-O file, archive or executable. Inspection
        # tests inject file/nm output and never run any program from the fixture.
        (folder / 'libidevice.a').write_bytes(b'NON-EXECUTABLE INSPECTION FIXTURE\n')
        value = {'LibraryIdentifier': identifier, 'LibraryPath': 'libidevice.a',
                 'HeadersPath': 'Headers', 'SupportedPlatform': 'ios',
                 'SupportedArchitectures': ['arm64'] if role == 'device' else ['arm64', 'x86_64']}
        if role == 'simulator':
            value['SupportedPlatformVariant'] = role
        libraries.append(value)
    (framework / 'Info.plist').write_bytes(plistlib.dumps({'AvailableLibraries': libraries}))
    return framework


class PackagedPairingAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_header_declarations_preserve_parameter_surface(self):
        found = m.declarations(HEADER)
        self.assertTrue(all(found[name] for name in m.FUNCTIONS))
        declaration = found['pairable_host_accept'][0]['declaration']
        self.assertIn('void (*pin_callback)(const char *, void *)', declaration)
        self.assertIn('const struct PairableHostCancel *cancel', declaration)
        self.assertEqual(found['pairable_host_accept_with_options'], [])

    def test_comments_macros_calls_and_strings_are_not_declarations(self):
        text = '''// void pairable_host_cancel_free(void *value);
/* void pairable_host_cancel_signal(void *value); */
#define pairable_host_cancel_new() imaginary
const char *example = "pairable_host_accept()";
void *another(void) { return pairable_host_cancel_new(); }
'''
        self.assertTrue(all(not matches for matches in m.declarations(text).values()))

    def test_nm_requires_exact_global_defined_text_symbols(self):
        text = '''_pairable_host_accept U
_pairable_host_cancel_new t 0 0
_pairable_host_cancel_signal D 0 0
_pairable_host_cancel_free_suffix T 0 0
Archive(_pairable_host_cancel_free):
'''
        self.assertEqual(m.defined_exports(text), set())
        self.assertEqual(m.defined_exports(NM), set(m.FUNCTIONS))

    def test_all_declared_ios_architectures_are_independently_inspected(self):
        framework = fixture(self.root)
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        tools = FixtureTools()
        report = m.inspect(self.root, tools)
        self.assertEqual(report['inspection_status'], 'complete')
        self.assertEqual(report['build_result'], 'not_evaluated')
        self.assertEqual(report['handshake_result'], 'not_attempted')
        self.assertFalse(report['provenance']['source_binary_equivalence_verified'])
        self.assertFalse(report['provenance']['expanded_archive_digest_verified'])
        commands = [c for c in tools.commands if c[:2] == ['/usr/bin/xcrun', 'nm']]
        self.assertEqual([c[3] for c in commands], ['arm64', 'arm64', 'x86_64'])
        self.assertEqual(report['slices'][0]['architectures'][0]['matching_nm_records'], NM.splitlines())
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertTrue(all(s['missing_optional_declarations'] == list(m.OPTIONAL_FUNCTIONS) for s in report['slices']))

    def test_missing_single_architecture_export_prevents_complete(self):
        fixture(self.root)
        shortened = NM.replace('_pairable_host_cancel_signal T 0000000000000040 0\n', '')
        report = m.inspect(self.root, FixtureTools({'x86_64': result(shortened)}))
        self.assertEqual(report['inspection_status'], 'incomplete')
        sim = next(s for s in report['slices'] if s['variant'] == 'simulator')
        self.assertEqual(sim['architectures'][1]['missing_exports'], ['pairable_host_cancel_signal'])
        self.assertEqual(report['slices'][0]['status'], 'complete')

    def test_missing_simulator_is_explicit(self):
        fixture(self.root, roles=('device',))
        report = m.inspect(self.root, FixtureTools())
        self.assertEqual(report['missing_platforms'], ['simulator'])
        self.assertEqual(report['inspection_status'], 'incomplete')

    def test_missing_headers_do_not_become_export_success(self):
        framework = fixture(self.root)
        for path in framework.rglob('*.h'):
            path.write_text('/* no matching APIs */')
        report = m.inspect(self.root, FixtureTools())
        self.assertEqual(report['inspection_status'], 'incomplete')
        self.assertTrue(all(s['missing_declarations'] == sorted(m.FUNCTIONS) for s in report['slices']))

    def test_failed_timed_out_and_truncated_tools_are_not_success(self):
        fixture(self.root)
        for status in ['failed', 'timeout', 'truncated', 'unavailable']:
            report = m.inspect(self.root, FixtureTools({'arm64': result(NM, status, 1)}))
            self.assertEqual(report['inspection_status'], 'incomplete')
            self.assertEqual(report['slices'][0]['architectures'][0]['defined_exports'], [])

    def test_duplicate_candidates_are_not_silently_selected(self):
        fixture(self.root / 'first')
        fixture(self.root / 'second')
        tools = FixtureTools()
        report = m.inspect(self.root, tools)
        self.assertEqual(len(report['candidates']), 2)
        self.assertEqual(tools.commands, [])
        self.assertEqual(report['inspection_status'], 'incomplete')

    def test_unrelated_framework_symlinks_are_not_traversed(self):
        fixture(self.root)
        other = self.root / 'Unrelated.xcframework'
        other.mkdir()
        (other / 'macos').symlink_to('/unavailable', target_is_directory=True)
        self.assertEqual(m.inspect(self.root, FixtureTools())['inspection_status'], 'complete')

    def test_package_header_symlink_and_traversal_are_rejected(self):
        framework = fixture(self.root)
        header = framework / 'ios-arm64/Headers/idevice.h'
        header.unlink()
        header.symlink_to(self.root / 'outside.h')
        report = m.inspect(self.root, FixtureTools())
        self.assertEqual(report['inspection_status'], 'incomplete')
        self.assertTrue(any('symlink' in issue for issue in report['slices'][0]['issues']))
        for path in ['../outside.a', '/absolute.a', 'folder/../../outside.a']:
            with self.assertRaises(ValueError):
                m.checked(framework, path)

    def test_framework_bundle_layout_uses_declared_executable(self):
        framework = fixture(self.root)
        info = plistlib.loads((framework / 'Info.plist').read_bytes())
        first = info['AvailableLibraries'][0]
        folder = framework / first['LibraryIdentifier']
        bundle = folder / 'IDevice.framework'
        bundle.mkdir()
        (folder / 'Headers').rename(bundle / 'Headers')
        (folder / 'libidevice.a').rename(bundle / 'IDevice')
        (bundle / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable': 'IDevice'}))
        first['LibraryPath'] = 'IDevice.framework'
        first.pop('HeadersPath')
        (framework / 'Info.plist').write_bytes(plistlib.dumps(info))
        self.assertEqual(m.inspect(self.root, FixtureTools())['inspection_status'], 'complete')

    def test_missing_artifact_never_runs_tools(self):
        tools = FixtureTools()
        report = m.inspect(self.root / 'absent', tools)
        self.assertEqual(report['inspection_status'], 'incomplete')
        self.assertEqual(tools.commands, [])
        self.assertIn('missing', report['issues'][0])

    def test_discovery_and_header_limits_are_explicit(self):
        fixture(self.root)
        with patch.object(m, 'MAX_ENTRIES', 1):
            report = m.inspect(self.root, FixtureTools())
        self.assertEqual(report['inspection_status'], 'incomplete')
        self.assertIn('limit exceeded', report['issues'][0])

    def test_malformed_plist_is_evidence_failure_not_build_failure(self):
        framework = fixture(self.root)
        (framework / 'Info.plist').write_bytes(b'invalid plist')
        report = m.inspect(self.root, FixtureTools())
        self.assertEqual(report['inspection_status'], 'incomplete')
        self.assertEqual(report['build_result'], 'not_evaluated')
        self.assertTrue(report['issues'])

    def test_duplicate_slice_and_unsafe_architecture_are_rejected(self):
        framework = fixture(self.root)
        info = plistlib.loads((framework / 'Info.plist').read_bytes())
        info['AvailableLibraries'].append(info['AvailableLibraries'][0].copy())
        info['AvailableLibraries'][0]['SupportedArchitectures'] = ['arm64;echo']
        (framework / 'Info.plist').write_bytes(plistlib.dumps(info))
        tools = FixtureTools()
        report = m.inspect(self.root, tools)
        self.assertEqual(report['inspection_status'], 'incomplete')
        self.assertIn('duplicate iOS slice identifiers', report['issues'])
        self.assertTrue(any('unsafe architecture' in x for x in report['slices'][0]['issues']))
        self.assertFalse(any('arm64;echo' in c for c in tools.commands))

    def test_missing_library_does_not_run_nm(self):
        framework = fixture(self.root)
        (framework / 'ios-arm64/libidevice.a').unlink()
        tools = FixtureTools()
        report = m.inspect(self.root, tools)
        self.assertEqual(report['inspection_status'], 'incomplete')
        self.assertTrue(report['slices'][0]['issues'])
        self.assertFalse(any(c[-1].endswith('ios-arm64/libidevice.a') for c in tools.commands))

    def test_root_symlink_is_rejected(self):
        actual = self.root / 'actual'
        actual.mkdir()
        fixture(actual)
        alias = self.root / 'alias'
        alias.symlink_to(actual, target_is_directory=True)
        tools = FixtureTools()
        report = m.inspect(alias, tools)
        self.assertEqual(report['inspection_status'], 'incomplete')
        self.assertEqual(tools.commands, [])

    def test_unrecognized_file_type_prevents_complete(self):
        fixture(self.root)
        delegate = FixtureTools()
        def tools(command):
            if command[:2] == ['/usr/bin/file', '-b']:
                return result('ASCII text\n')
            return delegate(command)
        report = m.inspect(self.root, tools)
        self.assertEqual(report['inspection_status'], 'incomplete')
        self.assertTrue(all('binary type could not be established with file' in s['issues'] for s in report['slices']))

    def test_live_stdout_and_stderr_are_stopped_at_their_independent_caps(self):
        # Harmless unbounded text writers, not package binaries or native tools.
        for descriptor, key, other in [(1, 'stdout', 'stderr'), (2, 'stderr', 'stdout')]:
            with self.subTest(stream=key), patch.object(m, 'MAX_TOOL_BYTES', 32768):
                started = time.monotonic()
                output = m.run_tool([sys.executable, '-c',
                    f'import os\nwhile True: os.write({descriptor}, b"X" * 4096)'])
                self.assertEqual(output['status'], 'truncated')
                self.assertEqual(len(output[key].encode()), 32768)
                self.assertEqual(output[other], '')
                self.assertLess(time.monotonic() - started, 5)
                self.assertLess(output['returncode'], 0)

    def test_live_below_cap_stdout_and_stderr_are_retained(self):
        with patch.object(m, 'MAX_TOOL_BYTES', 32768):
            output = m.run_tool([sys.executable, '-c',
                'import os; os.write(1,b"safe stdout\\n"); os.write(2,b"safe stderr\\n")'])
        self.assertEqual(output, {'returncode': 0, 'stdout': 'safe stdout\n',
                                  'stderr': 'safe stderr\n', 'status': 'ok'})

    def test_live_timeout_still_terminates_and_keeps_the_sixty_second_default(self):
        self.assertEqual(m.TOOL_TIMEOUT_SECONDS, 60)
        with patch.object(m, 'TOOL_TIMEOUT_SECONDS', 0.2):
            started = time.monotonic()
            output = m.run_tool([sys.executable, '-c', 'import time; time.sleep(30)'])
        self.assertEqual(output['status'], 'timeout')
        self.assertIsNone(output['returncode'])
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(m.TOOL_TIMEOUT_SECONDS, 60)


if __name__ == '__main__':
    unittest.main()
