#!/usr/bin/env python3
"""Run the actual manager/store and pinned parser in separate synthetic writer/readers."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

LOCK = 'Integration/fixtures/ColdPairingParser/source-lock.json'
LOCK_SHA256 = '31b3b5d88dfd22bbc2a272ebce076417bb438e2b8d14477c1b9f1ccac307039f'
SCENARIOS = ('remote_identity', 'binary_normalization', 'xml_representation',
             'selection_precedence', 'missing_selected', 'corrupt_or_wrong_selected',
             'invalid_preference', 'reset_suppression', 'strict_ordinary_parser')
MAX_BYTES = 4 * 1024 * 1024
MAX_LOG = 16 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def plain(path, *, directory=False):
    path = Path(path).absolute()
    if any(item.is_symlink() for item in [path, *path.parents]):
        raise ValueError('symlink input or output')
    if directory:
        if not path.is_dir(): raise ValueError('directory missing')
        return path
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError('source missing or oversized')
    with path.open('rb') as stream: data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES: raise ValueError('source oversized')
    return data


def inputs(root):
    root = plain(root, directory=True)
    lock_bytes = plain(root / LOCK)
    if sha(lock_bytes) != LOCK_SHA256: raise ValueError('source lock identity mismatch')
    lock = json.loads(lock_bytes)
    result = {LOCK: lock_bytes}
    for path, expected in lock['sha256'].items():
        data = plain(root / path)
        if sha(data) != expected: raise ValueError('source identity mismatch: ' + path)
        result[path] = data
    return lock, result


def verify(source_root, output_root, *, runner=None, platform=None):
    output = Path(output_root).absolute()
    plain(output.parent, directory=True)
    if output.exists() or output.is_symlink(): raise ValueError('output directory must be new')
    output.mkdir(mode=0o700)
    report = {'schema_version': 1, 'status': 'pending', 'native_execution': False,
              'runner': 'Apple_toolchain' if runner is None else 'injected_test_double',
              'evidence': 'Actual manager/store and pinned ordinary parser; synthetic persistent preferences, app and gateway-input seams. No native gateway, startup or device proof.',
              'scenarios': list(SCENARIOS), 'phases': {}}
    scratch = None
    joined = True
    try:
        lock, frozen = inputs(source_root)
        report['source_hashes'] = lock['sha256']
        report['source_lock_sha256'] = LOCK_SHA256
        if (sys.platform if platform is None else platform) != 'darwin':
            report['status'] = 'unsupported_platform'
            return report
        scratch = Path(tempfile.mkdtemp(prefix='tetherless-cold-pairing-')).resolve()
        staged = scratch / 'source'; staged.mkdir()
        for path, data in frozen.items():
            destination = staged / path; destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        spec = importlib.util.spec_from_file_location('cold_pairing_supervisor_loader', staged / 'Integration/verify_pairing_composition.py')
        loader = importlib.util.module_from_spec(spec); spec.loader.exec_module(loader)
        invoke = runner if runner is not None else loader.load_supervisor(staged / 'Integration/Dependencies/idevice')
        home = scratch / 'home'; home.mkdir()
        environment = os.environ.copy()
        environment['HOME'] = environment['CFFIXED_USER_HOME'] = str(home)

        def run(name, command, *, timeout=120, expected=None):
            nonlocal joined
            inputs(source_root); inputs(staged)
            log = output / (name + '.log')
            joined = False
            caught = None
            try:
                invoke(command, source=scratch, env=environment, log=log, timeout_seconds=timeout,
                       max_log_bytes=MAX_LOG, tail_bytes=128 * 1024,
                       term_grace_seconds=5, kill_join_seconds=5)
            except BaseException as error:
                caught = error
            status_path = log.with_name(log.name + '.status.json')
            status = json.loads(status_path.read_bytes()) if status_path.is_file() else {}
            cleanup = status.get('cleanup') or {}
            joined = cleanup.get('direct_child_reaped') is True and cleanup.get('group_empty') is True
            raw = log.read_bytes() if log.is_file() else b''
            if len(raw) > MAX_LOG: raise ValueError('supervisor log exceeds cap')
            passed = caught is None and joined and status.get('outcome') == 'success' and status.get('returncode') == 0 and status.get('output_complete') is True
            if expected is not None: passed = passed and raw.decode('utf-8', 'replace').splitlines() == [expected]
            report['phases'][name] = {'passed': passed, 'command': command, 'supervisor_status': status,
                                     'log': log.name, 'sha256': sha(raw), 'expected_line': expected,
                                     'caught_exception_class': type(caught).__name__ if caught else None}
            inputs(source_root); inputs(staged)
            if isinstance(caught, (KeyboardInterrupt, SystemExit)): raise caught
            if not passed: raise ValueError('fixture phase failed: ' + name)

        common = [str(staged / path) for path in lock['fixtures'] if '/ColdPairingParser/' in path]
        compile_prefix = ['/usr/bin/xcrun', '--sdk', 'macosx', 'swiftc', '-swift-version', '5', '-parse-as-library']
        for configuration, optimization in [('debug', '-Onone'), ('optimized', '-O')]:
            build = scratch / configuration; build.mkdir()
            run(configuration + '-parser-compile', [*compile_prefix, optimization, '-emit-library', '-emit-module',
                '-module-name', 'MinimuxerCommon', '-emit-module-path', str(build / 'MinimuxerCommon.swiftmodule'),
                *common, '-o', str(build / 'libMinimuxerCommon.dylib')])
            binary = build / 'cold-pairing'
            run(configuration + '-manager-compile', [*compile_prefix, optimization,
                '-I', str(build), '-L', str(build), '-lMinimuxerCommon', '-Xlinker', '-rpath', '-Xlinker', str(build),
                *[str(staged / path) for path in lock['production']],
                str(staged / 'Integration/fixtures/PairingColdReadSupport.swift'),
                str(staged / 'Integration/fixtures/PairingColdReadMain.swift'), '-o', str(binary)])
            for scenario in SCENARIOS:
                root = build / scenario; root.mkdir(mode=0o700)
                environment['TETHERLESS_COLD_PAIRING_ROOT'] = str(root)
                run(configuration + '-' + scenario + '-write', [str(binary), 'write', scenario], timeout=30,
                    expected='pairing_cold_fixture written=' + scenario)
                # Supervisor confirms the complete writer process group exited
                # before the distinct reader is allowed to observe those files.
                run(configuration + '-' + scenario + '-read', [str(binary), 'read', scenario], timeout=30,
                    expected='pairing_cold_fixture passed=' + scenario)
        report['status'] = 'passed' if runner is None else 'injected_runner_passed'
        report['native_execution'] = runner is None
        return report
    except (KeyboardInterrupt, SystemExit):
        report['status'] = 'interrupted' if joined else 'cleanup_incomplete'
        return report
    except (ValueError, OSError) as error:
        report['status'] = 'fixture_or_input_failure' if joined else 'cleanup_incomplete'
        report['failure_class'] = type(error).__name__
        return report
    finally:
        if scratch is not None:
            if joined:
                try:
                    shutil.rmtree(scratch)
                    report['scratch_removed_after_join'] = True
                except OSError:
                    report['scratch_removed_after_join'] = False
                    report['retained_scratch'] = str(scratch)
                    report['status'] = 'scratch_cleanup_failure'
            else:
                report['scratch_removed_after_join'] = False
                report['retained_scratch'] = str(scratch)
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--output-root', required=True, type=Path)
    args = parser.parse_args()
    report = verify(args.source_root, args.output_root)
    print(json.dumps({'status': report['status'], 'report': str(args.output_root / 'report.json')}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
