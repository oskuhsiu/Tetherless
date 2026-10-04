#!/usr/bin/env python3
"""Verify the real external fixture; seed() remains a local unit-test helper only."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import subprocess

import simulator_environment as environment

NAME = 'Tetherless-Invalid-Pairing.plist'
PAYLOAD = plistlib.dumps({'TetherlessInvalidPairingFixture': True}, fmt=plistlib.FMT_XML)
MANIFEST = Path('native-ui-document-fixture.json')


def seed(container: Path) -> dict:
    if not container.is_absolute() or container.is_symlink() or not container.is_dir():
        raise ValueError('Not an existing simulator app container')
    documents = container / 'Documents'
    if documents.is_symlink():
        raise ValueError('Unsafe Documents directory')
    documents.mkdir(exist_ok=True)
    file = documents / NAME
    # Exclusive creation: do not overwrite even this named test document.
    with file.open('xb') as stream:
        stream.write(PAYLOAD)
    if file.read_bytes() != PAYLOAD:
        raise RuntimeError('Fixture readback failed')
    return {'schema': 1, 'name': NAME, 'bytes': len(PAYLOAD),
            'sha256': hashlib.sha256(PAYLOAD).hexdigest(),
            'scope': 'invalid plist document only; no pairing/account/backend state',
            'uiResult': 'not-observed'}


def verify(container: Path) -> dict:
    if (not container.is_absolute() or container.is_symlink() or not container.is_dir() or
            (container / 'Documents').is_symlink()):
        raise ValueError('Unsafe fixture container')
    file = container / 'Documents' / NAME
    if (file.is_symlink() or not file.is_file() or file.stat().st_size != len(PAYLOAD) or
            file.read_bytes() != PAYLOAD):
        raise RuntimeError('Original fixture was changed or removed')
    return {'originalPreserved': True, 'sha256': hashlib.sha256(PAYLOAD).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['verify'])
    args = parser.parse_args()
    device = environment.owned_device(environment.listing())
    if device.get('state') != 'Booted':
        raise RuntimeError('Owned simulator is not booted')
    evidence = json.loads(Path('native-launch-evidence.json').read_text())
    saved = json.loads(MANIFEST.read_text())
    bundle = saved.get('sourceBundleID')
    if (bundle != 'org.tetherless.testdocuments' or saved.get('schema') != 2 or
            saved.get('simulatorID') != device['udid'] or
            saved.get('sourceCommit') != evidence.get('sourceCommit') or
            not saved.get('sourceAppInstalled')):
        raise RuntimeError('Expected the independently installed document fixture')
    raw = subprocess.check_output(['xcrun', 'simctl', 'get_app_container', device['udid'], bundle, 'data'],
                                  text=True, timeout=30).strip()
    result = verify(Path(raw))
    saved.update(result)
    # No UI or callback success is inferred, even on a failed test run.
    MANIFEST.write_text(json.dumps(saved, indent=2) + '\n')


if __name__ == '__main__':
    main()
