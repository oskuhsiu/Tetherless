#!/usr/bin/env python3
"""One invalid public document for real picker testing; never seed pairing state."""
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
    file = container / 'Documents' / NAME
    if file.is_symlink() or not file.is_file() or file.read_bytes() != PAYLOAD:
        raise RuntimeError('Original fixture was changed or removed')
    return {'originalPreserved': True, 'sha256': hashlib.sha256(PAYLOAD).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['seed', 'verify'])
    args = parser.parse_args()
    device = environment.owned_device(environment.listing())
    if device.get('state') != 'Booted':
        raise RuntimeError('Owned simulator is not booted')
    evidence = json.loads(Path('native-launch-evidence.json').read_text())
    bundle = evidence['bundleID']
    if not evidence.get('installed') or not (bundle == 'org.tetherless.Tetherless' or
                                            bundle.startswith('org.tetherless.Tetherless.')):
        raise RuntimeError('Expected actually installed Tetherless')
    raw = subprocess.check_output(['xcrun', 'simctl', 'get_app_container', device['udid'], bundle, 'data'],
                                  text=True, timeout=30).strip()
    container = Path(raw)
    if args.action == 'seed':
        MANIFEST.write_text(json.dumps(seed(container), indent=2) + '\n')
    else:
        result = json.loads(MANIFEST.read_text())
        result.update(verify(container))
        # Success belongs to the actual XCTest, not a fixture setup or file read.
        MANIFEST.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
