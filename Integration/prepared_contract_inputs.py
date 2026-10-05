#!/usr/bin/env python3
"""Retain only hash-pinned Swift preimages at their actual preparation boundaries.

These three source-only snapshots are siblings of the prepared app, never inputs
selected from the final transformed tree. No application data is enumerated.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import os
from pathlib import Path
import stat

INTEGRATION = Path(__file__).resolve().parent
DIRECTORY = 'PreparedContractInputs'
MAXIMUM_SOURCE_BYTES = 1024 * 1024
# Names are closed, and SOURCE/EXPECTED come from each unchanged transformation.
STAGES = {
    'ipa_input_safety': 'TETHERLESS_IPA_REVIEW_ROOT',
    'anisette_cache_safety': 'TETHERLESS_CACHE_REVIEW_ROOT',
    'oda_metadata_safety': 'TETHERLESS_METADATA_REVIEW_ROOT',
}


def contract(stage: str) -> tuple[Path, str]:
    if stage not in STAGES:
        raise ValueError('Unknown prepared contract stage')
    spec = importlib.util.spec_from_file_location(stage, INTEGRATION / (stage + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = Path(module.SOURCE)
    if source.is_absolute() or '..' in source.parts or source.suffix != '.swift':
        raise ValueError('Unsafe prepared contract source path')
    return source, module.EXPECTED


def blob(raw: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


@contextmanager
def directory(path: Path):
    """Anchor every component with no-follow directory descriptors."""
    path = Path(path)
    if '..' in path.parts:
        raise ValueError('Parent traversal in prepared contract path')
    path = path.absolute()
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in path.parts[1:]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


@contextmanager
def child_directory(parent: int, name: str, *, create: bool = False, exclusive: bool = False):
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
        except FileExistsError:
            if exclusive:
                raise ValueError('Prepared contract destination already exists')
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        yield fd
    finally:
        os.close(fd)


def entries(parent: int, maximum: int) -> set[str]:
    result = set()
    with os.scandir(parent) as listing:
        for entry in listing:
            result.add(entry.name)
            if len(result) > maximum:
                raise ValueError('Too many prepared contract snapshot entries')
    return result


def read_source(parent: int, path: Path, expected: str, *, exact_tree: bool = False) -> bytes:
    if exact_tree and entries(parent, 1) != {path.parts[0]}:
        raise ValueError('Unexpected prepared contract snapshot entry')
    if len(path.parts) > 1:
        with child_directory(parent, path.parts[0]) as child:
            return read_source(child, Path(*path.parts[1:]), expected, exact_tree=exact_tree)
    fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    with os.fdopen(fd, 'rb') as source:
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError('Prepared contract input must be a regular singly-linked source')
        if not 0 < metadata.st_size <= MAXIMUM_SOURCE_BYTES:
            raise ValueError('Prepared contract input exceeds source size limit')
        raw = source.read(MAXIMUM_SOURCE_BYTES + 1)
        if len(raw) != metadata.st_size or len(raw) > MAXIMUM_SOURCE_BYTES:
            raise ValueError('Prepared contract input changed or exceeded size limit')
    if blob(raw) != expected:
        raise ValueError('Unreviewed prepared contract input')
    return raw


def write_source(parent: int, path: Path, raw: bytes):
    if len(path.parts) > 1:
        with child_directory(parent, path.parts[0], create=True, exclusive=True) as child:
            write_source(child, Path(*path.parts[1:]), raw)
        return
    fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=parent)
    with os.fdopen(fd, 'wb') as target:
        target.write(raw)


def capture(root: Path, stage: str) -> Path:
    source, expected = contract(stage)
    root = Path(root)
    if '..' in root.parts:
        raise ValueError('Parent traversal in prepared contract path')
    root = root.absolute()
    if root == root.parent or root.name == DIRECTORY:
        raise ValueError('Prepared contract snapshots must be outside the application root')
    # Finish the bounded hash validation before creating any destination.
    with directory(root) as app:
        raw = read_source(app, source, expected)
    output = root.parent / DIRECTORY
    with directory(root.parent) as parent:
        with child_directory(parent, DIRECTORY, create=True) as snapshots:
            if not entries(snapshots, len(STAGES)).issubset(STAGES):
                raise ValueError('Unexpected prepared contract stage directory')
            with child_directory(snapshots, stage, create=True, exclusive=True) as destination:
                write_source(destination, source, raw)
    return output / stage


def verify(root: Path) -> dict[str, str]:
    """Reject missing, altered, oversized, linked, or extra snapshot entries."""
    roots = {}
    with directory(root) as snapshots:
        if entries(snapshots, len(STAGES)) != set(STAGES):
            raise ValueError('Prepared contract snapshots are incomplete or unexpected')
        for stage, environment in STAGES.items():
            source, expected = contract(stage)
            with child_directory(snapshots, stage) as captured:
                read_source(captured, source, expected, exact_tree=True)
            roots[environment] = str((Path(root) / stage).absolute())
    return roots


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app_root', type=Path)
    parser.add_argument('stage', choices=tuple(STAGES))
    args = parser.parse_args()
    capture(args.app_root, args.stage)


if __name__ == '__main__':
    main()
