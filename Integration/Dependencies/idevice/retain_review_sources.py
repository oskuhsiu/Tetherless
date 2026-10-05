#!/usr/bin/env python3
"""Retain bounded, checksum-authenticated public crate sources for review only."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tomllib

PACKAGES = {
    'idevice-srp-0.6.0': ['Cargo.toml', '.cargo_vcs_info.json', 'src/lib.rs', 'src/server.rs', 'src/client.rs', 'src/groups.rs'],
    'dialoguer-0.12.0': ['Cargo.toml', '.cargo/config.toml', '.cargo_vcs_info.json'],
    'cbindgen-0.29.2': ['Cargo.toml', 'Cargo.lock', '.cargo_vcs_info.json', 'src/bindgen/cargo/cargo_metadata.rs', 'src/bindgen/cargo/cargo.rs'],
    'plist_ffi-0.1.6': ['Cargo.toml', 'Cargo.toml.orig', 'Cargo.lock', 'build.rs', 'cbindgen.toml', 'plist.h', '.cargo_vcs_info.json'],
    'tokio-openssl-0.6.5': ['Cargo.toml', 'src/lib.rs'],
    'openssl-sys-0.9.112': ['Cargo.toml', 'build/main.rs', 'build/find_normal.rs', 'build/cfgs.rs', 'build/expando.c', 'src/lib.rs'],
    'openssl-0.10.76': ['Cargo.toml', 'src/lib.rs', 'src/ssl/mod.rs', 'src/ssl/connector.rs', 'src/ssl/bio.rs', 'src/ssl/callbacks.rs', 'src/ssl/error.rs'],
    'jktcp-0.1.7': ['Cargo.toml', 'src/lib.rs', 'src/adapter.rs', 'src/stream.rs', 'src/packets.rs', 'src/handle.rs'],
}
# Preserve available crate notices alongside the selected public source.
for names in PACKAGES.values():
    names += ['LICENSE', 'LICENSE.txt', 'LICENSE-MIT', 'LICENSE-APACHE', 'NOTICE', 'COPYING']

MAX_ARCHIVE = 32 * 1024 * 1024
MAX_FILE = 1024 * 1024
MAX_TOTAL = 4 * 1024 * 1024

def digest(data):
    return hashlib.sha256(data).hexdigest()

def selected_archive(data: bytes, stem: str, checksum: str, selected: list[str]) -> dict[str, bytes]:
    if len(data) > MAX_ARCHIVE or digest(data) != checksum:
        raise ValueError('archive size/checksum mismatch: ' + stem)
    retained, seen, expanded = {}, set(), 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for entry in archive:
            name = entry.name
            parts = name.split('/')
            if len(seen) >= 10000 or name in seen or any(p in ('', '.', '..') for p in parts) or '\\' in name or any(ord(c) < 32 for c in name):
                raise ValueError('unsafe/duplicate archive member: ' + stem)
            seen.add(name)
            if parts[0] != stem or (len(parts) == 1 and not entry.isdir()):
                raise ValueError('archive root mismatch: ' + stem)
            if entry.size < 0 or entry.size > 128 * 1024 * 1024:
                raise ValueError('oversized archive member: ' + stem)
            expanded += entry.size
            if expanded > 256 * 1024 * 1024:
                raise ValueError('expanded archive budget exceeded: ' + stem)
            relative = '/'.join(parts[1:])
            if relative not in selected:
                continue
            if not entry.isfile() or entry.size > MAX_FILE:
                raise ValueError('selected member is not a bounded regular file: ' + relative)
            value = archive.extractfile(entry).read(MAX_FILE + 1)
            if len(value) != entry.size:
                raise ValueError('selected member length mismatch: ' + relative)
            retained[relative] = value
    return retained

def execute(lock: Path, cache: Path, output: Path):
    if output.exists() or output.is_symlink():
        raise ValueError('review output must be new')
    packages = tomllib.loads(lock.read_text())['package']
    expected = {}
    for package in packages:
        stem = package['name'] + '-' + package['version']
        if stem in PACKAGES:
            if stem in expected or package.get('source') != 'registry+https://github.com/rust-lang/crates.io-index':
                raise ValueError('unexpected locked package source')
            expected[stem] = package['checksum']
    if set(expected) != set(PACKAGES):
        raise ValueError('exact review crate versions are absent from Cargo.lock')
    payloads, rows, total = {}, {}, 0
    for stem, selected in PACKAGES.items():
        archive = cache / (stem + '.crate')
        if archive.is_symlink() or not archive.is_file() or archive.stat().st_size > MAX_ARCHIVE:
            raise ValueError('missing/nonregular/oversized archive: ' + stem)
        with archive.open('rb') as stream:
            data = stream.read(MAX_ARCHIVE + 1)
        values = selected_archive(data, stem, expected[stem], selected)
        total += sum(map(len, values.values()))
        if total > MAX_TOTAL:
            raise ValueError('review source aggregate budget exceeded')
        rows[stem] = {'archive_sha256': expected[stem], 'files': {n: digest(b) for n, b in values.items()},
                      'requested_absent': sorted(set(selected) - set(values))}
        payloads[stem] = values
    # All inputs are validated before publishing this fresh, workflow-owned directory.
    output.mkdir(parents=True)
    for stem, values in payloads.items():
        (output / stem).mkdir()
        for name, data in values.items():
            destination = output / stem / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        # Deliberately a subset, not a substitute for Cargo's complete vendor metadata.
        (output / stem / 'review-checksums.json').write_text(json.dumps(rows[stem], sort_keys=True, indent=2) + '\n')
    manifest = {'schema': 1, 'scope': 'selected public source review only; no native or TLS correctness claim',
                'cargo_lock_sha256': digest(lock.read_bytes()), 'retained_bytes': total, 'packages': rows}
    (output / 'review-source-manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    return manifest

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('lock', 'cache', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(execute(args.lock, args.cache, args.output)))
    except (OSError, ValueError, KeyError, tarfile.TarError) as exc:
        parser.exit(1, 'public review-source retention failed: ' + str(exc) + '\n')

if __name__ == '__main__':
    main()
