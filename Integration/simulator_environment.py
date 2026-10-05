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
import subprocess
import tempfile
import time
import uuid

OWNER = Path('native-simulator-owner.json')
DIAGNOSTICS = Path('native-simulator-health')
MAX_OUTPUT = 262_144
SMOKE = Path('native-launch-evidence.json')


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


def allocate() -> str:
    if OWNER.exists():
        raise RuntimeError('This job already owns a Simulator; refusing a replacement')
    # The first request also starts CoreSimulator on a fresh runner. Give that
    # infrastructure initialization its own bound; UI/action limits stay intact.
    payload = listing(timeout=90)
    Path('native-simulator-devices.json').write_text(json.dumps(payload, indent=2) + '\n')
    template, runtime, kind = select_template(payload)
    name = 'Tetherless-CI-' + str(uuid.uuid4()).upper()
    raw = subprocess.check_output(['xcrun', 'simctl', 'create', name, kind, runtime],
                                  text=True, timeout=60).strip()
    value = identifier(raw)
    OWNER.write_text(json.dumps({'schema': 1, 'id': value, 'name': name,
                                'runtime': runtime, 'deviceType': kind,
                                'templateName': template, 'sourceCommit': os.environ.get('GITHUB_SHA')},
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
    parser.add_argument('action', choices=['allocate', 'diagnose', 'shutdown'])
    args = parser.parse_args()
    {'allocate': allocate, 'diagnose': diagnose, 'shutdown': shutdown}[args.action]()


if __name__ == '__main__':
    main()
