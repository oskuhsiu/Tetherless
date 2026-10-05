#!/usr/bin/env python3
"""Capture exact public OpenSSL input bytes; never execute or interpret binaries."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile

HERE = Path(__file__).resolve().parent
MANIFEST = HERE/'openssl-candidate/capture-inputs.json'
MANIFEST_SHA256 = '6c0feae4db570ca99b730a19a0415f6c649ab612dd91d159b878ca0066234271'


def load_manifest() -> dict:
    raw = MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError('OpenSSL capture manifest changed')
    return json.loads(raw)


def capture(source: Path, output: Path, manifest: dict) -> dict:
    source = source.resolve(strict=True)
    output = output.absolute()
    staging = output.with_name(output.name+'.partial')
    if output.exists() or staging.exists():
        raise ValueError('OpenSSL capture output must be new')
    entries = manifest['entries']
    seen = set()
    for entry in entries:
        path = PurePosixPath(entry['path'])
        if path.is_absolute() or '..' in path.parts or str(path) != entry['path'] or entry['path'] in seen:
            raise ValueError('Invalid OpenSSL capture path')
        if entry['mode'] not in ('100644','100755') or entry['size'] < 0:
            raise ValueError('Invalid OpenSSL capture entry')
        seen.add(entry['path'])
    staging.mkdir(parents=True)
    observed = []
    for entry in entries:
        path = source/entry['path']
        for candidate in [path, *path.parents]:
            if candidate == source:
                break
            if candidate.is_symlink():
                raise ValueError('OpenSSL input symlink is not in the selected inventory')
        before = path.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_size != entry['size']:
            raise ValueError('OpenSSL input size/type mismatch: '+entry['path'])
        executable = bool(before.st_mode & 0o111)
        if executable != (entry['mode'] == '100755'):
            raise ValueError('OpenSSL input Git mode mismatch: '+entry['path'])
        sha = hashlib.sha256()
        blob = hashlib.sha1(b'blob '+str(entry['size']).encode()+b'\0')
        destination = staging/'inputs'/entry['path']
        destination.parent.mkdir(parents=True,exist_ok=True)
        count = 0
        with path.open('rb') as src, destination.open('xb') as dst:
            while chunk := src.read(1024*1024):
                count += len(chunk)
                if count > entry['size']:
                    raise ValueError('OpenSSL input grew: '+entry['path'])
                sha.update(chunk); blob.update(chunk); dst.write(chunk)
        after = path.stat()
        if count != entry['size'] or blob.hexdigest() != entry['git_blob']:
            raise ValueError('OpenSSL input Git blob mismatch: '+entry['path'])
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns) != (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
            raise ValueError('OpenSSL input changed while capturing: '+entry['path'])
        destination.chmod(0o755 if executable else 0o644)
        observed.append({**entry,'sha256':sha.hexdigest()})
    receipt = {'schema':1,'repository':manifest['repository'],'commit':manifest['commit'],
               'tree':manifest['tree'],'scope':manifest['scope'],'entries':observed,
               'files':len(observed),'bytes':sum(x['size'] for x in observed),
               'binary_execution':False,'signature_admission':False,
               'binary_source_equivalence':False,'product_activation':False}
    (staging/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    os.rename(staging,output)
    return receipt



def archive_capture(root: Path, archive: Path, receipt: dict) -> None:
    """Preserve recorded modes across upload-artifact's permission normalization."""
    partial = archive.with_name(archive.name+'.partial')
    if archive.exists() or partial.exists():
        raise ValueError('OpenSSL archive output must be new')
    rows = [('inputs/'+entry['path'], int(entry['mode'][-3:],8)) for entry in receipt['entries']]
    rows.append(('receipt.json',0o644))
    with tarfile.open(partial,'x:') as tar:
        for name,mode in rows:
            path = root/name
            info = tarfile.TarInfo(name)
            info.size = path.stat().st_size
            info.mode = mode
            info.mtime = 0
            with path.open('rb') as src:
                tar.addfile(info,src)
    os.rename(partial,archive)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args()
    receipt = capture(args.source,args.output,load_manifest())
    archive_capture(args.output,args.output.with_suffix('.tar'),receipt)
    print(json.dumps({'commit':receipt['commit'],'files':receipt['files'],'bytes':receipt['bytes']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
