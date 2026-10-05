#!/usr/bin/env python3
"""Compile/link the pinned packaged host API; never execute, sign or pair."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import tempfile

from inspect_pairing_api import checked, digest, find_frameworks, load_plist, run_tool

ROOT = Path(__file__).parent
FUNCTIONS = ('pairable_host_accept', 'pairable_host_cancel_new',
             'pairable_host_cancel_signal', 'pairable_host_cancel_free')
HEADER_SHA256 = '23e7ab332fc73788b67b441b0c128720f3ddbd2210672cbc4bcb1503b5ca8426'
SLICES = {
    'ios-arm64': {'sdk': 'iphoneos', 'target': 'arm64-apple-ios17.0', 'variant': 'device',
        'archive': 'libidevice_ffi.a',
        'sha256': '622e8f91aa285bf1a6076e2853da9cacb39839bfd72ad1b1b08a0902e7f33d5b'},
    'ios-arm64-simulator': {'sdk': 'iphonesimulator', 'target': 'arm64-apple-ios17.0-simulator',
        'variant': 'simulator', 'archive': 'idevice-ios-sim.a',
        'sha256': '83e94401faf680916740ba112c630e0e52bbfc98ef0d77b53967494b63858f23'},
}
# Foundation is imported by the real gateway, and -lc++ appears in the verified
# d566891 native link command. Do not add guessed third-party libraries, dynamic
# lookup, unresolved-symbol exemptions, or alternate toolchains on failure.
SYSTEM_LINK_ARGUMENTS = ['-framework', 'Foundation', '-lc++']
MAX_INPUT_BYTES = 1024 * 1024 * 1024


def ensure_plain_root(root):
    absolute = root.absolute()
    if any(p.is_symlink() for p in [absolute, *absolute.parents]):
        raise ValueError('root has a symlink component')
    if not root.is_dir():
        raise ValueError('root is not a directory')


def identity_inputs(root):
    """Validate all package identities before invoking any compiler."""
    ensure_plain_root(root)
    frameworks = find_frameworks(root)
    if len(frameworks) != 1:
        raise ValueError('expected exactly one IDevice.xcframework')
    framework = frameworks[0]
    info = load_plist(checked(framework, 'Info.plist'))
    libraries = info.get('AvailableLibraries')
    if not isinstance(libraries, list) or not 1 <= len(libraries) <= 32:
        raise ValueError('invalid XCFramework inventory')
    selected = {}
    for entry in libraries:
        if not isinstance(entry, dict):
            raise ValueError('invalid library descriptor')
        key = entry.get('LibraryIdentifier')
        if key not in SLICES:
            continue
        if key in selected:
            raise ValueError('duplicate selected library descriptor')
        expected = SLICES[key]
        if (entry.get('SupportedPlatform') != 'ios' or
            entry.get('SupportedPlatformVariant', 'device') != expected['variant'] or
            entry.get('SupportedArchitectures') != ['arm64'] or
            entry.get('LibraryPath') != expected['archive'] or
            entry.get('HeadersPath') != 'Headers'):
            raise ValueError('selected slice metadata differs from reviewed artifact')
        archive = checked(framework, key + '/' + expected['archive'])
        header = checked(framework, key + '/Headers/idevice.h')
        for path, maximum in [(archive, MAX_INPUT_BYTES), (header, 8 * 1024 * 1024)]:
            if not path.is_file() or not 0 < path.stat().st_size <= maximum:
                raise ValueError('selected input missing or exceeds limit')
        if digest(archive) != expected['sha256'] or digest(header) != HEADER_SHA256:
            raise ValueError('selected archive or header identity differs from reviewed artifact')
        selected[key] = {'archive': archive, 'header': header}
    if set(selected) != set(SLICES):
        raise ValueError('required device/simulator slices are missing')
    return selected


def run_step(label, command, output, runner):
    result = runner(command)
    # run_tool caps each pipe at 16 MiB, uses a 60-second deadline, kills the
    # process group on timeout/truncation/error, and waits to reap the leader.
    (output / (label + '.stdout.txt')).write_text(result['stdout'], encoding='utf-8')
    (output / (label + '.stderr.txt')).write_text(result['stderr'], encoding='utf-8')
    return {'command': command, 'tool_status': result['status'],
            'returncode': result['returncode'], 'passed': result['status'] == 'ok' and result['returncode'] == 0,
            'stdout_file': label + '.stdout.txt', 'stderr_file': label + '.stderr.txt'}



def check_slice_identity(paths, expected):
    """Recheck ordinary concurrent drift at each compiler/linker boundary."""
    result = {'matched': False}
    try:
        for name in ['archive', 'header']:
            path = paths[name]
            ensure_plain_root(path.parent)
            if path.is_symlink() or not path.is_file():
                raise ValueError('selected input became absent or symlinked')
            maximum = MAX_INPUT_BYTES if name == 'archive' else 8 * 1024 * 1024
            if not 0 < path.stat().st_size <= maximum:
                raise ValueError('selected input size changed outside limits')
            result[name + '_sha256'] = digest(path)
        result['matched'] = (result['archive_sha256'] == expected['sha256'] and
                             result['header_sha256'] == HEADER_SHA256)
    except (OSError, ValueError) as error:
        result['issue'] = type(error).__name__ + ': ' + str(error)
    return result


def run_verified_step(label, command, output, paths, expected, runner):
    before = check_slice_identity(paths, expected)
    if not before['matched']:
        return {'passed': False, 'tool_status': 'not_attempted', 'returncode': None,
                'reason': 'input_identity_changed', 'identity_before': before}
    result = run_step(label, command, output, runner)
    after = check_slice_identity(paths, expected)
    result['identity_before'], result['identity_after'] = before, after
    if not after['matched']:
        result['passed'] = False
        result['reason'] = 'input_identity_changed'
    return result


def tool_path(value):
    text = value.strip()
    path = Path(text)
    if not path.is_absolute() or '\n' in text or '\r' in text:
        raise ValueError('official tool/SDK resolution returned no single absolute path')
    return text


def probe(artifacts_root, output, runner=run_tool):
    artifacts_root, output = Path(artifacts_root).absolute(), Path(output).absolute()
    report = {'schema_version': 1, 'status': 'not_started', 'slices': [], 'tools': {},
        'required_functions': list(FUNCTIONS), 'issues': [],
        'provenance': {'observed_commit': 'd566891', 'observed_run': '37294413252',
                       'header_sha256': HEADER_SHA256},
        'execution_attempted': False, 'signing_requested': False,
        'runtime_abi_result': 'not_evaluated', 'cancellation_result': 'not_evaluated',
        'handshake_result': 'not_attempted', 'same_phone_result': 'not_evaluated',
        'limits': ['Compile/link success proves only these typed call sites and symbol resolution for the selected toolchain/SDK.',
                   'Executables are never launched. No runtime ABI, cancellation, discovery or real-peer behavior is tested.',
                   'No pairing gate, persistent credential, app, device, account or active record is changed.',
                   'Expanded archive/header hashes are tied to retained package observations; ZIP provenance and source/binary equivalence are not independently proved.']}
    if output.exists() or output.is_symlink():
        raise ValueError('output must be a fresh directory; prior evidence is never overwritten')
    if any(p.is_symlink() for p in output.parents):
        raise ValueError('output parent has a symlink component')
    if output.resolve().is_relative_to(artifacts_root.resolve()) or artifacts_root.resolve().is_relative_to(output.resolve()):
        raise ValueError('output and package artifact roots must be disjoint')
    output.mkdir(parents=True)

    def finish(status):
        report['status'] = status
        (output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        return report

    try:
        inputs = identity_inputs(artifacts_root)
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['issues'].append(type(error).__name__ + ': ' + str(error))
        return finish('unsupported_package_identity')
    report['sources'] = {name: digest(ROOT / name) for name in ['PairingLinkProbe.c', 'PairingLinkProbe.swift']}
    for tool in ['clang', 'swiftc']:
        lookup = run_step('resolve-' + tool, ['/usr/bin/xcrun', '--find', tool], output, runner)
        report['tools'][tool] = lookup
        if not lookup['passed']:
            return finish('unsupported_toolchain')
        try:
            lookup['path'] = tool_path((output / lookup['stdout_file']).read_text())
        except ValueError as error:
            report['issues'].append(str(error))
            return finish('unsupported_toolchain')
        report['tools'][tool + '_version'] = run_step(tool + '-version', [lookup['path'], '--version'], output, runner)
        if not report['tools'][tool + '_version']['passed']:
            return finish('unsupported_toolchain')
    with tempfile.TemporaryDirectory(prefix="tetherless-pairing-link-") as temporary:
        scratch = Path(temporary)
        for identifier, expected in SLICES.items():
            archive, header = inputs[identifier]['archive'], inputs[identifier]['header']
            entry = {'identifier': identifier, 'target': expected['target'], 'sdk': expected['sdk'],
                     'archive_sha256': digest(archive), 'header_sha256': digest(header),
                     'stages': {}, 'status': 'not_started'}
            report['slices'].append(entry)
            lookup = run_step(identifier + '-sdk', ['/usr/bin/xcrun', '--sdk', expected['sdk'], '--show-sdk-path'], output, runner)
            entry['sdk_resolution'] = lookup
            if not lookup['passed']:
                entry['status'] = 'unsupported_sdk'
                continue
            try:
                sdk = tool_path((output / lookup['stdout_file']).read_text())
            except ValueError as error:
                entry['status'] = 'unsupported_sdk'; report['issues'].append(str(error)); continue
            entry['sdk_path'] = sdk
            clang, swift = report['tools']['clang']['path'], report['tools']['swiftc']['path']
            target = expected['target']
            roots = [argument for name in FUNCTIONS for argument in ['-Xlinker', '-u', '-Xlinker', '_' + name]]
            for language in ['c', 'swift']:
                object_path = scratch / (identifier + '-' + language + '.o')
                executable = scratch / (identifier + '-' + language + '-link-only')
                if language == 'c':
                    common = [clang, '-target', target, '-isysroot', sdk]
                    compile_command = common + ['-std=c11', '-Wall', '-Wextra', '-Werror', '-O0', '-I', str(header.parent),
                        '-c', str(ROOT / 'PairingLinkProbe.c'), '-o', str(object_path)]
                    link_command = common + [str(object_path), str(archive), *SYSTEM_LINK_ARGUMENTS, *roots,
                        '-Xlinker', '-no_adhoc_codesign', '-o', str(executable)]
                else:
                    common = [swift, '-target', target, '-sdk', sdk]
                    compile_command = common + ['-swift-version', '6', '-Onone', '-parse-as-library',
                        '-import-objc-header', str(header), '-module-cache-path', str(scratch / (identifier + '-modules')),
                        '-emit-object', str(ROOT / 'PairingLinkProbe.swift'), '-o', str(object_path)]
                    link_command = common + ['-emit-executable', str(object_path), str(archive),
                        *SYSTEM_LINK_ARGUMENTS, *roots, '-Xlinker', '-u', '-Xlinker', '_tetherless_pairing_swift_link_probe',
                        '-Xlinker', '-no_adhoc_codesign', '-o', str(executable)]
                label = identifier + '-' + language
                compiled = run_verified_step(label + '-compile', compile_command, output,
                                             inputs[identifier], expected, runner)
                entry['stages'][language + '_compile'] = compiled
                if not compiled['passed']:
                    entry['stages'][language + '_link'] = {'status': 'not_attempted', 'reason': 'compile_failed'}
                    continue
                if not object_path.is_file() or object_path.stat().st_size == 0:
                    compiled['passed'] = False; compiled['output_issue'] = 'compiler produced no object'
                    entry['stages'][language + '_link'] = {'status': 'not_attempted', 'reason': 'missing_object'}
                    continue
                linked = run_verified_step(label + '-link', link_command, output,
                                           inputs[identifier], expected, runner)
                entry['stages'][language + '_link'] = linked
                if linked['passed']:
                    if not executable.is_file() or executable.stat().st_size == 0:
                        linked['passed'] = False; linked['output_issue'] = 'linker produced no executable'
                    else:
                        linked['output_sha256'] = digest(executable)
            stages = entry['stages']
            if any(value.get('reason') == 'input_identity_changed' for value in stages.values()):
                entry['status'] = 'input_identity_changed'
            elif all(stages[k + '_compile']['passed'] for k in ['c', 'swift']):
                entry['status'] = 'passed' if all(stages[k + '_link']['passed'] for k in ['c', 'swift']) else 'link_failed'
            else:
                entry['status'] = 'compile_failed'
    report['scratch_cleanup'] = 'completed_after_tool_quiescence'
    try:
        identity_inputs(artifacts_root)
        report['final_package_identity'] = 'matched'
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['final_package_identity'] = 'changed'
        report['issues'].append(type(error).__name__ + ': ' + str(error))
        return finish('incomplete')
    return finish('passed' if all(x['status'] == 'passed' for x in report['slices']) else 'incomplete')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts-root', required=True, type=Path)
    parser.add_argument('--output-root', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = probe(args.artifacts_root, args.output_root)
    except (OSError, ValueError) as error:
        print('Pairing link probe could not record evidence: ' + type(error).__name__ + ': ' + str(error), file=sys.stderr)
        return 2
    print('Pairing host compile/link probe: ' + report['status'] + '; no execution or pairing attempted.')
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
