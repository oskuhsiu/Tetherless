#!/usr/bin/env python3
"""Package an unsigned CI app for later user-authorized signing, not installation."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile


def validate_app(app: Path) -> dict:
    if not app.is_dir() or app.is_symlink() or app.suffix != '.app':
        raise ValueError('Expected a regular .app directory')
    info_path = app / 'Info.plist'
    if info_path.is_symlink():
        raise ValueError('Info.plist must not be a symlink')
    info = plistlib.loads(info_path.read_bytes())
    executable = info.get('CFBundleExecutable')
    if not isinstance(executable, str) or executable in ('', '.', '..') or '/' in executable or '\\' in executable:
        raise ValueError('Invalid bundle executable')
    if not (app / executable).is_file() or (app / executable).is_symlink():
        raise ValueError('Bundle executable is missing or unsafe')
    if not isinstance(info.get('CFBundleIdentifier'), str) or not info['CFBundleIdentifier']:
        raise ValueError('Bundle identifier missing')
    root = app.resolve()
    for path in app.rglob('*'):
        if path.is_symlink():
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise ValueError('App contains a link outside its bundle')
        if path.suffix.lower() in {'.p12', '.p8', '.key', '.mobileprovision'}:
            raise ValueError('Signing or provisioning material must not enter the unsigned artifact')
        if path.suffix.lower() == '.pem' and b'PRIVATE KEY' in path.read_bytes():
            raise ValueError('Private key must not enter the unsigned artifact')
    return info


def package(app: Path, destination: Path, commit: str, configuration: str) -> Path:
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('A complete source commit is required')
    if configuration not in ('Debug', 'Release'):
        raise ValueError('Unexpected build configuration')
    info = validate_app(app)
    if destination.exists():
        raise ValueError('Output already exists; do not overwrite an earlier artifact')
    destination.mkdir(parents=True)
    archive = destination / 'Tetherless-unsigned.ipa'
    with tempfile.TemporaryDirectory(prefix='tetherless-package-') as staging:
        payload = Path(staging) / 'Payload'
        payload.mkdir()
        shutil.copytree(app, payload / 'Tetherless.app', symlinks=True)
        subprocess.run(['ditto', '-c', '-k', '--keepParent', str(payload), str(archive.resolve())], check=True)
    metadata = {
        'sourceCommit': commit, 'configuration': configuration,
        'bundleIdentifier': info['CFBundleIdentifier'],
        'version': info.get('CFBundleShortVersionString'),
        'build': info.get('CFBundleVersion'),
        'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'requiresUserSigning': True, 'deviceValidated': False,
        'unattendedRenewalValidated': False,
        'notice': 'Experimental unsigned input for a signing/bootstrap tool. Not directly installable or a stable release.'
    }
    (destination / 'manifest.json').write_text(json.dumps(metadata, indent=2) + '\n')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--configuration', choices=['Debug', 'Release'], required=True)
    args = parser.parse_args()
    print(package(args.app, args.output, args.commit, args.configuration))
