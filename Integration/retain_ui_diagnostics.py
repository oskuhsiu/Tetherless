#!/usr/bin/env python3
"""Retain bounded app-only diagnostic excerpts; the original xcresult is kept.

An oversized log is evidence to summarize, not a product/UI failure. Excerpts
never pretend to be complete files. IO failures and unexpected types still fail.
"""
import argparse
import json
import os
from pathlib import Path
import stat


def kind(path):
    if path.name.startswith('StandardOutputAndStandardError-org.tetherless.Tetherless'):
        return 'stdout'
    if path.name.startswith('SideStore-') and path.suffix in {'.ips', '.crash'}:
        return 'crash'
    return None


def retain(root: Path, destination: Path, limit=2_097_152):
    if limit < 2 or root.is_symlink() or not root.is_dir():
        raise ValueError('Invalid diagnostic selection input')
    selected = sorted(p for p in root.rglob('*') if kind(p) and not p.is_dir())
    if len(selected) > 20:
        raise ValueError('Unexpected diagnostic count')
    destination.mkdir(exist_ok=False)
    manifest = {'schemaVersion': 1, 'originalResultRetained': 'native-ui.xcresult',
                'uiResultInferred': False, 'files': []}
    for index, path in enumerate(selected):
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError('Unexpected diagnostic file type')
            size = before.st_size
            ranges = [(0, size)] if size <= limit else [(0, limit // 2), (size - (limit - limit // 2), limit - limit // 2)]
            entry = {'kind': kind(path), 'originalBytes': size, 'truncated': size > limit,
                     'omittedBytes': max(0, size - limit), 'parts': []}
            for part, (offset, length) in enumerate(ranges):
                stream.seek(offset)
                data = stream.read(length)
                if len(data) != length:
                    raise ValueError('Diagnostic changed during selection')
                name = f'{index:02d}-{kind(path)}-{part}.txt'
                (destination / name).write_bytes(data)
                entry['parts'].append({'file': name, 'offset': offset, 'bytes': length})
            after = os.fstat(stream.fileno())
            if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
                raise ValueError('Diagnostic changed during selection')
            manifest['files'].append(entry)
    manifest['truncatedFiles'] = sum(item['truncated'] for item in manifest['files'])
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    result = retain(args.source, args.destination)
    print('Retained', len(result['files']), 'app diagnostics;', result['truncatedFiles'],
          'explicitly truncated. Original xcresult unchanged; UI result not inferred.')
