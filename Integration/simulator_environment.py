#!/usr/bin/env python3
"""Own one fresh CI Simulator, with bounded failure diagnostics and no retries.

Never resets/kills a shared Simulator service or touches an unowned device.
This harness changes no production entitlement, UI assertion or Apple account.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import tempfile
import time
import uuid

OWNER = Path('native-simulator-owner.json')
DIAGNOSTICS = Path('native-simulator-health')
MAX_OUTPUT = 262_144
SMOKE = Path('native-launch-evidence.json')
PICKER_TIMING = Path('native-picker-timing')
PREFLIGHT = Path('native-simulator-environment')
DEVELOPER = '/Applications/Xcode_26.3.app/Contents/Developer'
DEVICE_TYPE = 'com.apple.CoreSimulator.SimDeviceType.iPhone-SE-3rd-generation'
CONFIGURATIONS = {
    'ios-26-2': ('com.apple.CoreSimulator.SimRuntime.iOS-26-2', '26.2', '23C54'),
    'ios-18-6': ('com.apple.CoreSimulator.SimRuntime.iOS-18-6', '18.6', '22G86'),
}


def validate_configuration(values: dict, image: dict, configuration: str) -> dict:
    """Verify the observed contract, without downloading or substituting anything."""
    runtime, version, build = CONFIGURATIONS[configuration]
    expected = {'architecture': 'arm64', 'developer': DEVELOPER,
                'xcode': 'Xcode 26.3\nBuild version 17C529',
                'sdkVersion': '26.2', 'sdkBuild': '23C57'}
    if any(values.get(key) != value for key, value in expected.items()):
        raise ValueError('Observed toolchain/SDK/architecture differs from the reviewed contract')
    if (image.get('RUNNER_ARCH') != 'ARM64' or not image.get('ImageOS') or
            not image.get('ImageVersion') or
            not re.search(r'ProductVersion:\s+15\.', values.get('macOS', '')) or
            not values.get('sdkPath', '').startswith(DEVELOPER + '/')):
        raise ValueError('Runner image/macOS/SDK identity is missing or unexpected')
    runtimes = json.loads(values['runtimeInventory'])
    types = json.loads(values['deviceTypeInventory'])
    if (not isinstance(runtimes, dict) or set(runtimes) != {'runtimes'} or
            not isinstance(runtimes['runtimes'], list) or
            not all(isinstance(item, dict) for item in runtimes['runtimes']) or
            not isinstance(types, dict) or set(types) != {'devicetypes'} or
            not isinstance(types['devicetypes'], list) or
            not all(isinstance(item, dict) for item in types['devicetypes'])):
        raise ValueError('Incomplete or unexpected Simulator inventories')
    matches = [item for item in runtimes['runtimes'] if item.get('identifier') == runtime]
    devices = [item for item in types['devicetypes'] if item.get('identifier') == DEVICE_TYPE]
    if (len(matches) != 1 or matches[0].get('isAvailable') is not True or
            matches[0].get('version') != version or matches[0].get('buildversion') != build):
        raise ValueError('Required exact installed runtime is unavailable or mismatched: ' + runtime)
    if len(devices) != 1 or not devices[0].get('name'):
        raise ValueError('Required exact Simulator device type is unavailable or ambiguous')
    return {'configuration': configuration, 'runtime': runtime, 'runtimeVersion': version,
            'runtimeBuild': build, 'deviceType': DEVICE_TYPE, 'templateName': devices[0]['name'],
            'architecture': 'arm64'}


def preflight(configuration: str) -> dict:
    # Retain incomplete/failed preflight separately from product acceptance.
    # Focused inventories avoid truncating a broad devices/pairs listing.
    PREFLIGHT.mkdir(exist_ok=False)
    manifest = PREFLIGHT / 'manifest.json'
    record = {'schema': 1, 'configuration': configuration, 'status': 'incomplete',
              'sourceCommit': os.environ.get('GITHUB_SHA'), 'productAccepted': False,
              'image': {key: os.environ.get(key) for key in ('ImageOS', 'ImageVersion', 'RUNNER_ARCH')},
              'referenceImageVersion': '20260907.0337.1',
              'imageMatchesReference': os.environ.get('ImageVersion') == '20260907.0337.1',
              'commands': {}, 'values': {}}
    def save() -> None:
        manifest.write_text(json.dumps(record, indent=2) + '\n')
    save()
    try:
        if os.environ.get('DEVELOPER_DIR') != DEVELOPER:
            raise ValueError('DEVELOPER_DIR must name the reviewed installed Xcode')
        probes = {'architecture': ['uname', '-m'], 'macOS': ['sw_vers'],
                  'developer': ['xcode-select', '-p'], 'xcode': ['xcodebuild', '-version'],
                  'sdkVersion': ['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version'],
                  'sdkBuild': ['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-build-version'],
                  'sdkPath': ['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'],
                  'runtimeInventory': ['xcrun', 'simctl', 'list', 'runtimes', '--json'],
                  'deviceTypeInventory': ['xcrun', 'simctl', 'list', 'devicetypes', '--json']}
        for name, args in probes.items():
            path = PREFLIGHT / (name + '.log')
            result = capture(args, path, timeout=90 if name == 'runtimeInventory' else 30)
            record['commands'][name] = result
            save()
            if (result.get('exitCode') != 0 or result.get('timeout') or
                    result.get('errorType') or result.get('truncated')):
                raise RuntimeError('Environment probe incomplete or failed: ' + name)
            record['values'][name] = path.read_text().strip()
        selected = validate_configuration(record['values'], record['image'], configuration)
        record.update(status='verified', selected=selected)
        save()
        print('Verified exact Simulator configuration:', configuration,
              'runner image matches diagnostic:', record['imageMatchesReference'])
        return selected
    except Exception as error:
        record.update(status='failed', failureType=type(error).__name__)
        save()
        raise


def identifier(value: str) -> str:
    return str(uuid.UUID(value)).upper()


def listing(timeout: int = 30) -> dict:
    return json.loads(subprocess.check_output(
        ['xcrun', 'simctl', 'list', 'devices', 'available', '--json'], text=True, timeout=timeout))


def select_template(payload: dict) -> tuple[str, str, str]:
    candidates = []
    for runtime, devices in payload['devices'].items():
        match = re.fullmatch(r'com\.apple\.CoreSimulator\.SimRuntime\.iOS-(\d+(?:-\d+)*)', runtime)
        if not match:
            continue
        version = tuple(map(int, match[1].split('-')))
        for device in devices:
            kind = device.get('deviceTypeIdentifier', '')
            if (version[0] >= 17 and device.get('isAvailable') is True and
                    device.get('name', '').startswith('iPhone') and
                    kind.startswith('com.apple.CoreSimulator.SimDeviceType.iPhone-')):
                candidates.append((version, device['name'], runtime, kind))
    if not candidates:
        raise RuntimeError('No supported installed iPhone Simulator template')
    # Preserve the existing latest-runtime/name policy (including compact SE).
    # A larger/easier test display is not selected to evade offscreen assertions.
    _, name, runtime, kind = max(candidates)
    return name, runtime, kind


def allocate(configuration: str | None = None) -> str:
    if OWNER.exists():
        raise RuntimeError('This job already owns a Simulator; refusing a replacement')
    selected = preflight(configuration) if configuration is not None else None
    # The first request also starts CoreSimulator on a fresh runner. Give that
    # infrastructure initialization its own bound; UI/action limits stay intact.
    payload = listing(timeout=90)
    Path('native-simulator-devices.json').write_text(json.dumps(payload, indent=2) + '\n')
    if selected is None:
        template, runtime, kind = select_template(payload)
    else:
        template, runtime, kind = (selected['templateName'], selected['runtime'], selected['deviceType'])
    name = 'Tetherless-CI-' + str(uuid.uuid4()).upper()
    raw = subprocess.check_output(['xcrun', 'simctl', 'create', name, kind, runtime],
                                  text=True, timeout=60).strip()
    value = identifier(raw)
    OWNER.write_text(json.dumps({'schema': 1, 'id': value, 'name': name,
                                'runtime': runtime, 'deviceType': kind,
                                'templateName': template, 'sourceCommit': os.environ.get('GITHUB_SHA'),
                                'configuration': selected},
                               indent=2) + '\n')
    # Leave shutdown through compilation. Boot only when the built app is ready.
    with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as file:
        file.write('SIMULATOR_ID=' + value + '\n')
    print('Created owned, unbooted Simulator:', template, runtime, value)
    return value


def owned_device(payload: dict) -> dict:
    owner = json.loads(OWNER.read_text())
    if owner.get('schema') != 1 or not owner.get('name', '').startswith('Tetherless-CI-'):
        raise RuntimeError('Invalid Simulator ownership record')
    expected = identifier(owner['id'])
    matches = [(runtime, item) for runtime, devices in payload['devices'].items()
               for item in devices if item.get('udid', '').upper() == expected]
    if len(matches) != 1:
        raise RuntimeError('Owned Simulator not uniquely available')
    runtime, device = matches[0]
    if (device.get('name') != owner['name'] or runtime != owner['runtime'] or
            device.get('deviceTypeIdentifier') != owner['deviceType']):
        raise RuntimeError('Simulator ownership changed; refusing operation')
    return device


def capture(args: list[str], path: Path, timeout: int = 15) -> dict:
    """Bound retained output without a PIPE deadlock or replacing test evidence."""
    started = time.monotonic()
    result = {'command': args, 'timeoutSeconds': timeout}
    with tempfile.TemporaryFile() as output:
        try:
            process = subprocess.run(args, stdout=output, stderr=subprocess.STDOUT,
                                     timeout=timeout, check=False)
            result['exitCode'] = process.returncode
        except subprocess.TimeoutExpired:
            result['timeout'] = True
        except OSError as error:
            result['errorType'] = type(error).__name__
        length = output.seek(0, os.SEEK_END)
        output.seek(0)
        first = output.read(min(length, MAX_OUTPUT // 2))
        if length > len(first):
            tail_size = min(length - len(first), MAX_OUTPUT // 2)
            output.seek(length - tail_size)
            tail = output.read(tail_size)
        else:
            tail = b''
        path.write_bytes(first + tail)
    result.update(elapsedSeconds=round(time.monotonic() - started, 3), originalBytes=length,
                  retainedBytes=len(first) + len(tail), truncated=length > len(first) + len(tail),
                  headBytes=len(first), tailOffset=length - len(tail), file=path.name)
    return result




def paired_clock(event: str) -> dict:
    if event not in ('hostBeforeUI', 'hostAfterUI', 'hostAfterCollection'):
        raise ValueError('Unknown host clock event')
    before = time.monotonic_ns() // 1000
    wall = time.time_ns() // 1000
    after = time.monotonic_ns() // 1000
    return {'schemaVersion': 1, 'source': 'host', 'event': event, 'processID': os.getpid(),
            'monotonicBeforeUS': before, 'unixTimeUS': wall, 'monotonicAfterUS': after}


def capture_draining(args: list[str], path: Path, timeout: float = 15,
                     limit: int = MAX_OUTPUT) -> dict:
    """Drain under a deadline into bounded memory; never spool unbounded output.

    Only the process group created for this read-only command is terminated.
    No Simulator/service reset, remote kill, retry or command substitution.
    """
    if limit < 2 or limit > MAX_OUTPUT or timeout <= 0 or timeout > 30:
        raise ValueError('Unsupported collector bounds')
    if path.exists() or path.is_symlink():
        raise FileExistsError('Refusing to replace diagnostic evidence')
    started = time.monotonic()
    result = {'command': args, 'timeoutSeconds': timeout, 'outputLimitBytes': limit}
    head_limit = limit // 2
    tail_limit = limit - head_limit
    head, tail = bytearray(), bytearray()
    total = 0
    eof = False
    process = None
    stop_at = started + timeout
    killed_at = None
    try:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        assert process.stdout is not None
        os.set_blocking(process.stdout.fileno(), False)
        with selectors.DefaultSelector() as selected:
            selected.register(process.stdout, selectors.EVENT_READ)
            while not eof:
                now = time.monotonic()
                if now >= stop_at and killed_at is None:
                    result['timeout'] = True
                    killed_at = now
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                if killed_at is not None and now - killed_at >= 1:
                    result['drainIncomplete'] = True
                    break
                for key, _ in selected.select(timeout=min(0.05, max(0, stop_at - now)) if killed_at is None else 0.05):
                    try: block = os.read(key.fd, 65_536)
                    except BlockingIOError: continue
                    if not block:
                        eof = True
                        break
                    total += len(block)
                    needed = head_limit - len(head)
                    if needed > 0:
                        head.extend(block[:needed]); block = block[needed:]
                    if block:
                        tail.extend(block)
                        if len(tail) > tail_limit: del tail[:-tail_limit]
            process.stdout.close()
        try:
            result['exitCode'] = process.wait(timeout=max(0.01, stop_at - time.monotonic()))
        except subprocess.TimeoutExpired:
            result['timeout'] = True
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            try: result['exitCode'] = process.wait(timeout=1)
            except subprocess.TimeoutExpired: result['processExitUnobserved'] = True
    except OSError as error:
        result['errorType'] = type(error).__name__
    finally:
        if process is not None:
            if process.stdout is not None: process.stdout.close()
            if process.poll() is None:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                try: process.wait(timeout=1)
                except subprocess.TimeoutExpired: result['processExitUnobserved'] = True
    path.write_bytes(head + tail)
    result.update(elapsedSeconds=round(time.monotonic() - started, 3), originalBytes=total,
                  originalBytesComplete=eof and not result.get('processExitUnobserved', False),
                  retainedBytes=len(head) + len(tail), omittedBytes=total - len(head) - len(tail),
                  truncated=total > len(head) + len(tail), headBytes=len(head),
                  tailOffset=total - len(tail), file=path.name)
    return result


def capture_complete(result: dict) -> bool:
    return (result.get('exitCode') == 0 and result.get('originalBytesComplete') is True and
            not any(result.get(key) for key in ('timeout', 'truncated', 'drainIncomplete',
                                                'errorType', 'processExitUnobserved')))


def read_small_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65_536:
        raise ValueError('Unsafe evidence identity')
    value = json.loads(path.read_text())
    if not isinstance(value, dict): raise ValueError('Expected evidence object')
    return value


def picker_identity() -> dict:
    owner, smoke = read_small_json(OWNER), read_small_json(SMOKE)
    sha = os.environ.get('GITHUB_SHA', '')
    run, attempt = os.environ.get('GITHUB_RUN_ID', ''), os.environ.get('GITHUB_RUN_ATTEMPT', '')
    device = owned_device(listing())
    bundle = smoke.get('bundleID', '')
    if (not re.fullmatch(r'[0-9a-f]{40}', sha) or not run.isdecimal() or not attempt.isdecimal() or
            owner.get('sourceCommit') != sha or smoke.get('sourceCommit') != sha or
            owner['id'] != smoke.get('simulatorID') or identifier(device['udid']) != owner['id'] or
            device.get('state') != 'Booted' or smoke.get('smokePassed') is not True or
            not re.fullmatch(r'org\.tetherless\.Tetherless(?:\.[A-Za-z0-9-]+)*', bundle)):
        raise ValueError('Unbound picker timing identity')
    return {'sourceCommit': sha, 'runID': int(run), 'runAttempt': int(attempt),
            'simulatorID': owner['id'], 'runtime': owner['runtime'], 'bundleID': bundle}


def begin_picker_timing() -> None:
    identity = picker_identity()
    PICKER_TIMING.mkdir(exist_ok=False)
    record = {'schemaVersion': 1, 'identity': identity, 'clock': paired_clock('hostBeforeUI'),
              'scope': 'read-only timing baseline; no picker or service warm-up'}
    (PICKER_TIMING/'baseline.json').write_text(json.dumps(record, indent=2) + '\n')


def discover_picker_services(text: str, bundle: str) -> list[dict]:
    """Parse the actual app-bound RunningBoard monitor shape seen in artifacts.

    Never guess that a bundle/service identifier is its executable/process name.
    Unknown or conflicting identity stays a gap; no broad process fallback.
    """
    service = 'com.apple.DocumentManagerUICore.Service'
    pattern = re.compile(r'^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+\s+Df fileproviderd\[\d+:[0-9a-f]+\] '
        r'\[com\.apple\.runningboard:monitor\] Received state update for (\d+) '
        r'\(xpcservice<' + re.escape(service) + r'\(\[app<' + re.escape(bundle) +
        r'\(\(null\)\)>:(\d+)\]\)>[^\r\n]{0,512}, (?:running-active-Visible|running-active-NotVisible|none-NotVisible)$')
    identities = {}
    for line in text.splitlines():
        if 'Received state update for ' not in line or service not in line or bundle not in line: continue
        match = pattern.fullmatch(line)
        if not match: raise ValueError('Unsupported observed UI-service identity shape')
        pid, app = map(int, match.groups())
        if not (0 < pid <= 2_147_483_647 and 0 < app <= 2_147_483_647):
            raise ValueError('Invalid observed process identity')
        if pid in identities and identities[pid] != app:
            raise ValueError('Ambiguous app-bound UI-service identity')
        identities[pid] = app
    if not identities or len(identities) > 4:
        raise ValueError('Missing or excessive observed UI-service identities')
    return [{'servicePID': pid, 'appPID': app, 'serviceIdentifier': service}
            for pid, app in sorted(identities.items())]



def observed_process_rows(text: str, expected_pid: int) -> dict:
    """A header-only successful query is not observed UI-service evidence."""
    rows = []
    pattern = re.compile(r'^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+\s+\S+\s+'
                         r'([A-Za-z0-9_.-]{1,128})\[(\d+):[0-9a-fA-F]+\](?:\s|$)')
    unsupported = False
    for line in text.splitlines():
        if not re.match(r'^\d{4}-\d\d-\d\d ', line): continue
        match = pattern.match(line)
        if match is None: unsupported = True
        else: rows.append((match[1], int(match[2])))
    if unsupported: raise ValueError('Unsupported direct-process row shape')
    if not rows: raise ValueError('No direct UI-service event rows')
    if any(pid != expected_pid for _, pid in rows): raise ValueError('Direct query returned another PID')
    names = sorted({name for name, _ in rows})
    if len(names) != 1: raise ValueError('Observed PID maps to multiple process names')
    return {'matchingRows': len(rows), 'observedProcessName': names[0], 'processID': expected_pid}


def collect_picker_timing() -> None:
    record = {'schemaVersion': 1, 'status': 'incomplete', 'commands': [], 'gaps': [],
              'clocks': [paired_clock('hostAfterUI')], 'stage': 'identityValidation', 'uiResultInferred': False}
    manifest = PICKER_TIMING/'collection.json'
    if manifest.exists(): raise FileExistsError('Picker evidence already collected')
    def save(): manifest.write_text(json.dumps(record, indent=2) + '\n')
    try:
        baseline = read_small_json(PICKER_TIMING/'baseline.json')
        identity = picker_identity()
        if baseline.get('identity') != identity: raise ValueError('Timing identity changed')
        record['identity'] = identity
        record['stage'] = 'clockWindow'
        before = baseline['clock']; after = record['clocks'][0]
        elapsed = (after['monotonicBeforeUS'] - before['monotonicAfterUS']) / 1_000_000
        wall_elapsed = (after['unixTimeUS'] - before['unixTimeUS']) / 1_000_000
        if elapsed < 0 or wall_elapsed < 0 or abs(wall_elapsed - elapsed) > 1:
            raise ValueError('Host clock moved; cannot bind a service-log interval')
        end = (after['unixTimeUS'] + 999_999)//1_000_000
        start = max(before['unixTimeUS']//1_000_000, end - 600)
        clipped = start * 1_000_000 > before['unixTimeUS']
        record['window'] = {'startUnixSeconds': start, 'endUnixSeconds': end,
                            'roundingUncertaintySeconds': 1, 'maximumSeconds': 600,
                            'clipped': clipped, 'elapsedSeconds': elapsed}
        if clipped: record['gaps'].append('windowClipped')
        prefix = ['xcrun', 'simctl', 'spawn', identity['simulatorID'], 'log']
        record['stage'] = 'installedLogHelp'
        help_result = capture_draining(prefix + ['show', '--help'], PICKER_TIMING/'log-show-help.log', limit=32_768)
        record['commands'].append(help_result)
        help_text = (PICKER_TIMING/'log-show-help.log').read_text(errors='replace')
        # The retained installed-tool help uses exit64 for valid usage output.
        supported = (help_result.get('exitCode') in (0, 64) and help_result.get('originalBytesComplete') and
                     not any(help_result.get(k) for k in ('timeout','truncated','drainIncomplete','errorType')) and
                     all(token in help_text for token in ('usage: log show', '--process <pid>', '--start <date>',
                                                          '--end <date>', '--timezone', '--predicate', 'compact', '@unixtime')))
        record['installedHelpSupported'] = bool(supported)
        save()
        if not supported: raise ValueError('Installed log options not verified')
        common = prefix + ['show', '--start', '@'+str(start), '--end', '@'+str(end), '--style', 'compact', '--timezone', 'UTC']
        predicate = ('process == "fileproviderd" AND eventMessage CONTAINS "com.apple.DocumentManagerUICore.Service" '
                     'AND eventMessage CONTAINS "' + identity['bundleID'] + '"')
        record['stage'] = 'serviceDiscovery'
        discovery = capture_draining(common + ['--predicate', predicate], PICKER_TIMING/'service-discovery.log')
        record['commands'].append(discovery); save()
        if not capture_complete(discovery): raise ValueError('UI-service discovery incomplete')
        record['stage'] = 'serviceIdentity'
        identities = discover_picker_services((PICKER_TIMING/'service-discovery.log').read_text(), identity['bundleID'])
        record['observedServices'] = identities; save()
        record['stage'] = 'observedServiceQueries'
        for service in identities:
            result = capture_draining(common + ['--process', str(service['servicePID'])],
                                      PICKER_TIMING/f"ui-service-{service['servicePID']}.log")
            record['commands'].append(result)
            if not capture_complete(result): record['gaps'].append('uiServiceQueryIncomplete')
            else:
                try:
                    result['observedProcess'] = observed_process_rows(
                        (PICKER_TIMING/result['file']).read_text(), service['servicePID'])
                except ValueError:
                    record['gaps'].append('uiServiceRowsUnverified')
            save()
        record['stage'] = 'hostSnapshot'
        for args, name in ((['vm_stat'], 'host-memory.log'), (['df', '-h'], 'host-disk.log')):
            result = capture_draining(args, PICKER_TIMING/name, limit=65_536)
            record['commands'].append(result)
            if not capture_complete(result): record['gaps'].append('hostSnapshotIncomplete')
        record['clocks'].append(paired_clock('hostAfterCollection'))
        record['status'] = 'complete' if not record['gaps'] else 'gaps'
        save()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        record['status'] = 'gaps'
        record['gaps'].append(type(error).__name__)
        if PICKER_TIMING.is_dir(): save()
        raise
    if record['gaps']: raise RuntimeError('Picker timing collection has explicit gaps')


def install_failure_commands(device: dict) -> list[tuple[list[str], str]]:
    """Read back an uncertain install without retrying or accepting its result.

    Called only after owned_device has checked the live device. Bind saved smoke
    to that owner AND this job's SHA before constructing any device command.
    A timeout does not establish whether the daemon finished installation.
    """
    if not SMOKE.exists():
        return []
    with SMOKE.open('rb') as file:
        raw = file.read(65_537)
    if len(raw) > 65_536:
        raise ValueError('Oversized smoke identity')
    evidence = json.loads(raw)
    if not isinstance(evidence, dict):
        raise ValueError('Invalid smoke identity')
    if evidence.get('failedStage') != 'native-simulator-install.log':
        return []
    owner = json.loads(OWNER.read_text())
    sha = os.environ.get('GITHUB_SHA', '')
    value = identifier(device['udid'])
    bundle = evidence.get('bundleID', '')
    if (device.get('state') != 'Booted' or not re.fullmatch(r'[0-9a-f]{40}', sha) or
            owner.get('sourceCommit') != sha or evidence.get('sourceCommit') != sha or
            identifier(owner['id']) != value or evidence.get('simulatorID') != value or
            evidence.get('lastCommand') != ['xcrun', 'simctl', 'install'] or
            evidence.get('installed') is not False or evidence.get('launched') is not False or
            not isinstance(bundle, str) or not re.fullmatch(r'org\.tetherless\.Tetherless(?:\.[A-Za-z0-9-]+)*', bundle)):
        raise ValueError('Unbound failed-install evidence')
    # The old combined log mixed thousands of container records with installer
    # events and then lost its middle. Retain focused queries independently.
    # Command exit/status is evidence only; never rewrite installed/smokePassed.
    return [
        (['xcrun', 'simctl', 'get_app_container', value, bundle, 'app'],
         'install-container-readback.log'),
        (['xcrun', 'simctl', 'spawn', value, 'log', 'show', '--last', '3m',
          '--style', 'compact', '--predicate', 'process == "installd" OR process == "lsd"'],
         'install-registration.log'),
        (['xcrun', 'simctl', 'spawn', value, 'log', 'show', '--last', '3m',
          '--style', 'compact', '--predicate', 'eventMessage CONTAINS "' + bundle + '"'],
         'install-product-events.log'),
    ]


def diagnose() -> None:
    DIAGNOSTICS.mkdir(exist_ok=True)
    reports = []
    # Always retain host pressure/process identity, even if simctl is unavailable.
    # comm (not args/env) avoids dumping process command-line secrets.
    commands = [(['ps', '-axo', 'pid,ppid,stat,etime,comm'], 'host-processes.log'),
                (['vm_stat'], 'host-memory.log'),
                (['df', '-h'], 'host-disk.log')]
    try:
        payload = listing()
        (DIAGNOSTICS / 'devices.json').write_text(json.dumps(payload, indent=2) + '\n')
        device = owned_device(payload)
        value = identifier(device['udid'])
        if device.get('state') == 'Booted':
            try:
                # Query immediately, before generic logs consume the time window.
                commands = install_failure_commands(device) + commands
            except (ValueError, TypeError, KeyError, OSError):
                reports.append({'installInspection': 'rejected-unbound-evidence'})
            predicate = ('process == "installd" OR process == "containermanagerd" OR '
                         'process == "fileproviderd" OR process == "filecoordinationd" OR '
                         'process == "DocumentManager"')
            commands += [(['xcrun', 'simctl', 'spawn', value, 'launchctl', 'print', 'system'],
                          'device-services.log'),
                         (['xcrun', 'simctl', 'spawn', value, 'log', 'show', '--last', '3m',
                           '--style', 'compact', '--predicate', predicate], 'device-install-picker.log')]
    except Exception as error:
        reports.append({'ownershipOrListingFailure': type(error).__name__})
    for args, name in commands:
        reports.append(capture(args, DIAGNOSTICS / name))
    (DIAGNOSTICS / 'manifest.json').write_text(json.dumps(reports, indent=2) + '\n')
    # Diagnostic command failures are evidence, never proof of UI success. This
    # runs only after an already failed test/installation; no retry is launched.


def shutdown() -> None:
    if not OWNER.exists():
        return
    device = owned_device(listing())
    if device.get('state') == 'Shutdown':
        return
    if device.get('state') not in ('Booted', 'Booting'):
        raise RuntimeError('Unsupported owned Simulator state during cleanup')
    subprocess.run(['xcrun', 'simctl', 'shutdown', identifier(device['udid'])],
                   check=True, timeout=60)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['allocate', 'diagnose', 'shutdown', 'begin-picker-timing', 'collect-picker-timing'])
    parser.add_argument('--configuration', choices=CONFIGURATIONS)
    args = parser.parse_args()
    if args.configuration and args.action != 'allocate':
        parser.error('--configuration applies only to allocation')
    if args.action == 'allocate':
        allocate(args.configuration)
    else:
        {'diagnose': diagnose, 'shutdown': shutdown, 'begin-picker-timing': begin_picker_timing,
         'collect-picker-timing': collect_picker_timing}[args.action]()


if __name__ == '__main__':
    main()
