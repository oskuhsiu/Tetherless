#!/usr/bin/env python3
"""Package an unsigned CI app for later user-authorized signing, not installation."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import tempfile


_spec = importlib.util.spec_from_file_location('delivery_candidate', Path(__file__).with_name('delivery_candidate.py'))
delivery = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(delivery)


def validate_app(app: Path) -> dict:
    if not app.is_dir() or app.is_symlink() or app.suffix != '.app':
        raise ValueError('Expected a regular .app directory')
    info_path = app / 'Info.plist'
    if info_path.is_symlink():
        raise ValueError('Info.plist must not be a symlink')
    info = plistlib.loads(delivery.metadata_bytes(info_path))
    if not isinstance(info, dict):
        raise ValueError('Bundle Info.plist must contain a dictionary')
    executable = info.get('CFBundleExecutable')
    if not isinstance(executable, str) or executable in ('', '.', '..') or '/' in executable or '\\' in executable:
        raise ValueError('Invalid bundle executable')
    if not (app / executable).is_file() or (app / executable).is_symlink():
        raise ValueError('Bundle executable is missing or unsafe')
    if not isinstance(info.get('CFBundleIdentifier'), str) or not info['CFBundleIdentifier']:
        raise ValueError('Bundle identifier missing')
    root = app.resolve()
    budget = delivery.Budget()
    def visit(directory: Path, depth: int = 0):
        if depth > delivery.MAX_DEPTH:
            raise ValueError('App exceeds traversal depth budget')
        for path in delivery.bounded_children(directory):
            name = delivery.safe_name(path.relative_to(app).as_posix())
            if delivery.private_path(name):
                raise ValueError('App contains private/signing material')
            mode = path.lstat().st_mode
            if path.is_symlink():
                delivery.safe_link(name, str(path.readlink()))
                resolved = path.resolve(strict=True)
                if not resolved.is_relative_to(root):
                    raise ValueError('App contains a link outside its bundle')
                budget.add(len(str(path.readlink()).encode()))
            elif stat.S_ISDIR(mode):
                budget.add(0)
                visit(path, depth + 1)
            elif stat.S_ISREG(mode):
                budget.add(path.stat().st_size)
            else:
                raise ValueError('App contains a special file')
            if path.suffix.lower() in {'.p12', '.p8', '.key', '.mobileprovision', '.mobiledevicepairing'}:
                raise ValueError('Signing or provisioning material must not enter the unsigned artifact')
            if path.suffix.lower() == '.pem' and b'PRIVATE KEY' in delivery.metadata_bytes(path):
                raise ValueError('Private key must not enter the unsigned artifact')
    visit(app)
    return info


def package(app: Path, destination: Path, commit: str, configuration: str, *,
            repository: Path | None = None, prepared: Path | None = None,
            source_packages: Path | None = None) -> Path:
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('A complete source commit is required')
    if configuration not in ('Debug', 'Release'):
        raise ValueError('Unexpected build configuration')
    repository = repository or Path(__file__).resolve().parents[1]
    prepared = prepared or repository / '.generated/SideStore'
    source_packages = source_packages or repository / '.generated/DerivedData/SourcePackages'
    info = validate_app(app)
    if destination.exists() or destination.is_symlink():
        raise ValueError('Output already exists; do not overwrite an earlier artifact')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.is_symlink():
        raise ValueError('Output parent must not be a symlink')
    # Nothing appears at the final output path unless all inventories and bundles finish.
    with tempfile.TemporaryDirectory(prefix='.tetherless-package-', dir=destination.parent) as staging:
        staging = Path(staging)
        output = staging / 'candidate'
        output.mkdir()
        archive = output / 'Tetherless-unsigned.ipa'
        payload = staging / 'Payload'
        payload.mkdir()
        shutil.copytree(app, payload / 'Tetherless.app', symlinks=True)
        validate_app(payload / 'Tetherless.app')
        subprocess.run(['ditto', '-c', '-k', '--keepParent', str(payload), str(archive.resolve())], check=True)
        metadata = delivery.create_evidence(output, archive, repository, prepared, source_packages, commit)
        ipa_identity = delivery.file_identity_large(archive)
        metadata.update({
            'sourceCommit': commit, 'configuration': configuration,
            'bundleIdentifier': info['CFBundleIdentifier'],
            'version': info.get('CFBundleShortVersionString'),
            'build': info.get('CFBundleVersion'),
            'sha256': ipa_identity['sha256'],
            'ipa': {'path': archive.name, **ipa_identity},
            'requiresUserSigning': True, 'deviceValidated': False,
            'unattendedRenewalValidated': False,
            'notice': 'Experimental unsigned candidate. Not directly installable or a stable release.'
        })
        delivery.write_json(output / 'manifest.json', metadata)
        # A non-circular checksum list binds the IPA, manifest and every companion file.
        (output / 'SHA256SUMS').write_text(''.join(
            f"{delivery.file_identity_large(path)['sha256']}  {path.name}\n"
            for path in sorted(output.iterdir())), encoding='utf-8')
        output.rename(destination)
    return destination / 'Tetherless-unsigned.ipa'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--configuration', choices=['Debug', 'Release'], required=True)
    parser.add_argument('--repository', type=Path)
    parser.add_argument('--prepared', type=Path)
    parser.add_argument('--source-packages', type=Path)
    args = parser.parse_args()
    print(package(args.app, args.output, args.commit, args.configuration,
                  repository=args.repository, prepared=args.prepared, source_packages=args.source_packages))
