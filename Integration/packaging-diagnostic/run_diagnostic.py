"""One toy XCFramework packaging attempt; never produces an accepted IDevice artifact.

The unchanged supervisor remains the sole packaging acceptance/cleanup authority.
The observer selects only its recorded PGID, never arguments or environment data.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import threading
import time

HELPER_PINS = {
    'Integration/Dependencies/idevice/bounded_process.py': '7724f6c3eb7d624f49a2651b30f1d6e6bb2c47d356449cd495fad28b2dd144e4',
    'Integration/Dependencies/idevice/apply_patch.py': 'a41e75b1903265c650c198bca05a2afc08ff053a01bcf0a56682cf95ce19c80a',
    'Integration/verify_pairing_composition.py': 'f5e4615e73ce2307adf575618d53d9c3537f3dececc2aa5463e884557b0706ce',
}
MAX_SAMPLES = 256
MAX_PS_BYTES = 16 * 1024
MAX_ROWS = 128
MAX_TOTAL_ROWS = 2048
SAMPLE_INTERVAL = 0.05
PACKAGE_TIMEOUT = 30


class DiagnosticError(RuntimeError):
    pass


def load_capture(root: Path):
    for relative, expected in HELPER_PINS.items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise DiagnosticError('supervisor/loader source mismatch')
    spec = importlib.util.spec_from_file_location('packaging_diagnostic_loader',
                                                root / 'Integration/verify_pairing_composition.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_supervisor(root / 'Integration/Dependencies/idevice')


def status_for(log: Path) -> Path:
    return log.with_name(log.name + '.status.json')


def packaging_environment(work: Path, developer_dir: str):
    if not developer_dir or not Path(developer_dir).is_absolute():
        raise DiagnosticError('explicit developer directory is required')
    # Match the four-key environment of the actual failed Apple packager.
    return {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'DEVELOPER_DIR': developer_dir,
            'HOME': str(work / 'aarch64-apple-ios/home'),
            'TMPDIR': str(work / 'aarch64-apple-ios/tmp')}


def read_status(path: Path):
    # The supervisor replaces this small file while running. A partial read is
    # retried, not interpreted as an empty group or a different command.
    try:
        if path.is_symlink() or path.stat().st_size > 32 * 1024:
            raise DiagnosticError('invalid status sidecar')
        return json.loads(path.read_bytes())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def owned_group(status, expected_command):
    if not isinstance(status, dict) or status.get('outcome') != 'running':
        return None
    pid = status.get('pid')
    if (type(pid) is not int or pid <= 1 or status.get('process_group') != pid
            or status.get('command') != expected_command):
        raise DiagnosticError('unexpected owned command identity')
    return pid


def ps_command(group: int):
    if type(group) is not int or group <= 1:
        raise DiagnosticError('invalid process group')
    # Darwin ps -g selects process groups; -c/comm never requests argv.
    return ['/bin/ps', '-c', '-x', '-g', str(group), '-o',
            'pid=,ppid=,pgid=,state=,lstart=,comm=']


def parse_rows(data: str, group: int):
    if len(data.encode()) > MAX_PS_BYTES:
        raise DiagnosticError('process snapshot too large')
    lines = [line for line in data.splitlines() if line.strip()]
    if len(lines) > MAX_ROWS:
        raise DiagnosticError('process snapshot has too many members')
    rows = []
    for line in lines:
        fields = line.split(None, 9)
        if len(fields) != 10:
            raise DiagnosticError('unrecognized Darwin process row')
        try:
            pid, parent, selected_group = map(int, fields[:3])
        except ValueError as error:
            raise DiagnosticError('invalid process identifier') from error
        if pid <= 0 or parent < 0 or selected_group != group:
            raise DiagnosticError('process row escaped the selected group')
        if (len(fields[3]) > 16 or len(fields[9].encode()) > 1024
                or any(len(field) > 32 for field in fields[4:9])):
            raise DiagnosticError('process identity field too large')
        rows.append({'pid': pid, 'ppid': parent, 'pgid': selected_group,
                     'state': fields[3], 'start_text': ' '.join(fields[4:9]),
                     'executable_name': fields[9]})
    return rows


def sample_group(capture, *, command, package_log, work, output, environment,
                 stop, observations, owner_pid, errors):
    group = None
    root_identity = None
    total_rows = 0
    started = time.monotonic()
    try:
        for index in range(MAX_SAMPLES):
            state = read_status(status_for(package_log))
            observed_group = owned_group(state, command)
            if observed_group is not None:
                if group not in (None, observed_group):
                    raise DiagnosticError('owned process group changed')
                group = observed_group
            if group is None:
                if stop.wait(SAMPLE_INTERVAL):
                    break
                continue
            # Stop once final cleanup has been published, avoiding later PID
            # reuse. Sampling cannot prove absence between observations.
            if state is not None and state.get('outcome') != 'running':
                break
            log = output / 'samples' / ('%03d.txt' % index)
            query_error = None
            try:
                capture(ps_command(group), source=work, env=environment, log=log,
                        timeout_seconds=0.5, max_log_bytes=MAX_PS_BYTES,
                        tail_bytes=MAX_PS_BYTES, term_grace_seconds=0.25,
                        kill_join_seconds=0.25)
            except Exception as error:
                query_error = type(error).__name__
            query = read_status(status_for(log)) or {}
            cleanup = query.get('cleanup') or {}
            if not (cleanup.get('direct_child_reaped') is True and cleanup.get('group_empty') is True):
                raise DiagnosticError('process observer command did not join')
            raw = log.read_text() if log.is_file() else ''
            if query.get('outcome') == 'nonzero_exit' and query.get('returncode') == 1 and not raw.strip():
                rows = []  # ps found no row; this is NOT supervisor ESRCH proof.
            elif query_error is None and query.get('outcome') == 'success':
                rows = parse_rows(raw, group)
            else:
                raise DiagnosticError('process observer command failed')
            total_rows += len(rows)
            if total_rows > MAX_TOTAL_ROWS:
                raise DiagnosticError('aggregate process observation limit')
            root = next((row for row in rows if row['pid'] == group), None)
            if root is not None:
                identity = (root['ppid'], root['start_text'])
                if identity[0] != owner_pid or root_identity not in (None, identity):
                    raise DiagnosticError('process group leader identity changed')
                root_identity = identity
            observations.append({'elapsed_seconds': time.monotonic() - started,
                                 'group': group, 'root_identity_observed': root_identity is not None,
                                 'members': rows})
            if stop.wait(SAMPLE_INTERVAL):
                break
        else:
            errors.append('sample_limit')
        if group is None:
            errors.append('command_pid_not_observed')
        elif root_identity is None:
            errors.append('group_leader_identity_not_observed')
    except Exception as error:
        errors.append(type(error).__name__)


def run(root: Path, work: Path, output: Path):
    if sys.platform != 'darwin':
        raise DiagnosticError('this diagnostic requires macOS; no native skip is success')
    if work.exists() or work.is_symlink() or output.exists() or output.is_symlink():
        raise DiagnosticError('diagnostic work/output paths must be new')
    work.mkdir(parents=True)
    output.mkdir(parents=True)
    work, output, root = work.resolve(), output.resolve(), root.resolve()
    capture = load_capture(root)
    own = Path(__file__).resolve().parent
    environment = packaging_environment(work, os.environ.get('DEVELOPER_DIR'))
    for name in ['HOME', 'TMPDIR']:
        Path(environment[name]).mkdir(parents=True)
    observer_environment = dict(environment, LC_ALL='C', LANG='C', TZ='UTC', COMMAND_MODE='unix2003')
    context = {'schema': 1, 'source_commit': os.environ.get('GITHUB_SHA'),
               'run_id': os.environ.get('GITHUB_RUN_ID'), 'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
               'platform': platform.platform(), 'developer_dir': environment.get('DEVELOPER_DIR'),
               'packaging_environment': environment,
               'supervisor_pins': HELPER_PINS, 'scope': 'One toy archive packaging attempt with owned-group metadata',
               'accepted_idevice_artifact': False,
               'source_hashes': {name: hashlib.sha256((own / name).read_bytes()).hexdigest()
                                 for name in ['run_diagnostic.py', 'fixture.c', 'fixture.h']}}
    (output / 'context.json').write_text(json.dumps(context, indent=2) + '\n')
    libraries, header_paths = [], []
    for sdk, target in [('iphoneos', 'arm64-apple-ios17.0'),
                        ('iphonesimulator', 'arm64-apple-ios17.0-simulator')]:
        folder = work / sdk
        folder.mkdir()
        headers = folder / 'headers'
        headers.mkdir()
        (headers / 'fixture.h').write_bytes((own / 'fixture.h').read_bytes())
        obj, library = folder / 'fixture.o', folder / 'libfixture.a'
        capture(['/usr/bin/xcrun', '--sdk', sdk, 'clang', '-target', target,
                 '-c', str(own / 'fixture.c'), '-o', str(obj)], source=work, env=environment,
                log=output / (sdk + '-compile.txt'), timeout_seconds=120, max_log_bytes=1024 * 1024)
        capture(['/usr/bin/xcrun', '--sdk', sdk, 'libtool', '-static', '-o', str(library), str(obj)],
                source=work, env=environment, log=output / (sdk + '-archive.txt'),
                timeout_seconds=30, max_log_bytes=1024 * 1024)
        libraries.append(library)
        header_paths.append(headers)
    package_log = output / 'create-xcframework.txt'
    command = ['/usr/bin/xcodebuild', '-create-xcframework',
               '-library', str(libraries[0]), '-headers', str(header_paths[0]),
               '-library', str(libraries[1]), '-headers', str(header_paths[1]),
               '-output', str(work / 'Fixture.xcframework')]
    stop = threading.Event()
    observations, observer_errors = [], []
    observer = threading.Thread(target=sample_group, kwargs={
        'capture': capture, 'command': command, 'package_log': package_log,
        'work': work, 'output': output, 'environment': observer_environment,
        'stop': stop, 'observations': observations, 'owner_pid': os.getpid(), 'errors': observer_errors},
        name='owned-packaging-observer', daemon=False)
    primary_error = None
    observer.start()
    try:
        capture(command, source=work, env=environment, log=package_log,
                timeout_seconds=PACKAGE_TIMEOUT, max_log_bytes=1024 * 1024)
    except BaseException as error:
        primary_error = error
    finally:
        stop.set()
        # Each observation invokes the unchanged supervisor with <=1 second
        # timeout+cleanup. Never treat an unjoined observer as successful.
        observer.join(timeout=5)
        joined = not observer.is_alive()
        report = {'schema': 1, 'observer_joined': joined, 'observer_errors': observer_errors,
                  'samples': observations, 'package_status': read_status(status_for(package_log)),
                  'primary_error_type': type(primary_error).__name__ if primary_error else None,
                  'accepted_idevice_artifact': False,
                  'limitations': ['Sampling may miss short-lived children or processes outside the owned group.',
                                  'output_complete=false is outcome-derived, not independent pipe-EOF evidence.',
                                  'Toy archive behavior does not establish IDevice artifact acceptance.']}
        encoded = (json.dumps(report, indent=2) + '\n').encode()
        try:
            if len(encoded) > 4 * 1024 * 1024:
                raise DiagnosticError('bounded observation report exceeded its limit')
            (output / 'owned-group-observations.json').write_bytes(encoded)
        except Exception:
            if primary_error is None:
                raise
            # The independently retained original command failure stays primary.
    if primary_error is not None:
        raise primary_error
    if not joined or observer_errors:
        raise DiagnosticError('owned process observation was inconclusive')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.repo_root, args.work_dir, args.output)
    except Exception as error:
        print('packaging diagnostic failed: ' + type(error).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
