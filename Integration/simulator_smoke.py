#!/usr/bin/env python3
"""Whole native app smoke evidence. No auth/device fixtures or UI bypasses."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import time

EVIDENCE = Path('native-launch-evidence.json')


def record(**values):
    current = json.loads(EVIDENCE.read_text()) if EVIDENCE.exists() else {
        'sourceCommit': os.environ.get('GITHUB_SHA'), 'deviceValidated': False,
        'unattendedRenewalValidated': False, 'uiFlowsTested': False,
        'installed': False, 'launched': False, 'screenshotCaptured': False,
        'scope': 'production app build, install, initial launch and screenshot only',
    }
    current.update(values)
    EVIDENCE.write_text(json.dumps(current, indent=2) + '\n')


def command(args, log: str, timeout: int):
    # A hung simctl must leave diagnostics even when communicate raises.
    record(lastCommand=args[:3])
    with open(log, 'a', encoding='utf-8') as file:
        file.write('$ ' + ' '.join(args) + '\n')
        file.flush()
        try:
            result = subprocess.run(args, stdout=file, stderr=subprocess.STDOUT,
                                    timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            file.write('\nTIMEOUT\n')
            record(failedStage=log, failure='timeout')
            raise
    if result.returncode:
        record(failedStage=log, failure='exit-' + str(result.returncode))
        raise subprocess.CalledProcessError(result.returncode, args)


def ensure_png(path: Path):
    data = path.read_bytes()
    if len(data) < 100 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise RuntimeError('No valid simulator PNG was captured')


def prepare(identifier: str):
    record(simulatorID=identifier)
    developer = subprocess.check_output(['xcode-select', '-p'], text=True, timeout=15).strip()
    gui = str(Path(developer) / 'Applications/Simulator.app')
    # simctl boot alone does not establish the GUI's screen surface.
    command(['open', '-a', gui, '--args', '-CurrentDeviceUDID', identifier],
            'native-simulator-prepare.log', 30)
    command(['xcrun', 'simctl', 'bootstatus', identifier, '-b'],
            'native-simulator-prepare.log', 300)
    # Distinguish an unavailable renderer from a failure in the product UI.
    command(['xcrun', 'simctl', 'io', identifier, 'screenshot', 'native-simulator-home.png'],
            'native-simulator-prepare.log', 120)
    ensure_png(Path('native-simulator-home.png'))
    record(simulatorReady=True)


def launch(identifier: str, app: Path):
    info = plistlib.loads((app/'Info.plist').read_bytes())
    bundle = info['CFBundleIdentifier']
    if not (bundle == 'org.tetherless.Tetherless' or bundle.startswith('org.tetherless.Tetherless.')):
        raise RuntimeError('Unexpected native product identity')
    record(bundleID=bundle)
    command(['xcrun', 'simctl', 'install', identifier, str(app)],
            'native-simulator-install.log', 120)
    record(installed=True)
    command(['xcrun', 'simctl', 'launch', '--terminate-running-process', identifier, bundle],
            'native-simulator-launch.log', 120)
    text = Path('native-simulator-launch.log').read_text()
    match = re.search(re.escape(bundle) + r':\s*(\d+)\s*$', text)
    if not match: raise RuntimeError('simctl did not report the product process ID')
    pid = int(match[1])
    record(launched=True, pid=pid)
    time.sleep(5)
    os.kill(pid, 0)
    process = subprocess.check_output(['ps', '-p', str(pid), '-o', 'comm='], text=True, timeout=15).strip()
    if '.app/' + info['CFBundleExecutable'] not in process:
        raise RuntimeError('Unexpected process after launch')
    record(launchAliveAfterSeconds=5)
    command(['xcrun', 'simctl', 'io', identifier, 'screenshot', 'native-first-launch.png'],
            'native-screenshot.log', 120)
    ensure_png(Path('native-first-launch.png'))
    os.kill(pid, 0)
    record(screenshotCaptured=True, smokePassed=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['prepare', 'launch'])
    parser.add_argument('--simulator', required=True)
    parser.add_argument('--app', type=Path)
    args = parser.parse_args()
    if not re.fullmatch('[A-Fa-f0-9-]{36}', args.simulator): parser.error('Invalid simulator identifier')
    try:
        if args.phase == 'prepare': prepare(args.simulator)
        else:
            if args.app is None: parser.error('--app is required for launch')
            launch(args.simulator, args.app)
    except Exception as error:
        record(smokePassed=False, failureType=type(error).__name__)
        raise


if __name__ == '__main__': main()
