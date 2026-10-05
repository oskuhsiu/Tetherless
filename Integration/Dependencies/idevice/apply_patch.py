#!/usr/bin/env python3
"""Stage a byte-verified idevice source tree and a review-locked additive patch.

No network, Git mutation, dependency resolution, or native tools are used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile

HERE = Path(__file__).resolve().parent


class VerificationError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def safe_path(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    if not parts or relative.startswith("/") or any(p in (".", "..") for p in parts) or "\\" in relative:
        raise VerificationError("unsafe relative path")
    if str(PurePosixPath(relative)) != relative:
        raise VerificationError("non-canonical relative path")
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise VerificationError(f"symlink refused: {relative}")
    return path


def safe_source_link(root: Path, name: str, target: bytes) -> Path:
    # Git records link text as the blob. Only a relative link to a committed
    # regular file inside this source tree is permitted; never follow it to read.
    text = target.decode("utf-8")
    if not text or text.startswith("/") or "\\" in text or "\0" in text:
        raise VerificationError("unsafe committed source symlink")
    destination = os.path.normpath(str(PurePosixPath(name).parent / text))
    return safe_path(root, destination)


def read_json(path: Path) -> dict | list:
    return json.loads(path.read_bytes())


def load_lock(root: Path = HERE, lock_filename: str = "source-lock.json") -> dict:
    if lock_filename not in ("source-lock.json", "helper-test-profile.json", "candidate-profiles/host-only.json", "candidate-profiles/acquisition-only.json", "candidate-profiles/combined.json", "candidate-profiles/transcript-only.json", "candidate-profiles/apple-verification.json", "candidate-profiles/host-transcript-only.json"):
        raise VerificationError("unsupported source profile")
    lock = read_json(root / lock_filename)
    if lock.get("schema") != 1:
        raise VerificationError("unsupported source lock")
    data = (root / "source-tree.json").read_bytes()
    if sha256(data) != lock["source_tree_sha256"]:
        raise VerificationError("source-tree lock mismatch")
    if lock.get("source_input_sha256") and sha256((root / "source-input.json").read_bytes()) != lock["source_input_sha256"]:
        raise VerificationError("source input contract mismatch")
    for name, digest in lock["evidence_sha256"].items():
        if sha256(safe_path(root, name).read_bytes()) != digest:
            raise VerificationError(f"upstream evidence mismatch: {name}")
    return lock


def verify_source(source: Path, entries: list[dict]) -> list[tuple[str, bytes, int]]:
    """Verify all committed blobs, never materialize Git metadata or submodules.

    Untracked files are deliberately not copied. Gitlinks are recorded in the
    source lock but unused by the FFI Cargo build; do not initialize them.
    """
    verified = []
    seen = set()
    for entry in entries:
        name = entry["path"]
        if name in seen:
            raise VerificationError("duplicate source entry")
        seen.add(name)
        if entry["mode"] == "120000":
            parent = str(PurePosixPath(name).parent)
            directory = source if parent == "." else safe_path(source, parent)
            path = directory / PurePosixPath(name).name
            data = os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
            if git_blob(data) != entry["sha"]:
                raise VerificationError(f"source symlink hash mismatch: {name}")
            target = safe_source_link(source, name, data)
            target_name = str(target.relative_to(source))
            if not any(e["path"] == target_name and e["mode"] in ("100644", "100755") for e in entries):
                raise VerificationError("source symlink target is not a committed regular file")
            verified.append((name, data, 0o120000))
            continue
        path = safe_path(source, name)
        if entry["type"] == "commit":
            continue
        if entry["type"] != "blob" or entry["mode"] not in ("100644", "100755"):
            raise VerificationError(f"unsupported source type: {name}")
        if not path.is_file():
            raise VerificationError(f"source missing: {name}")
        data = path.read_bytes()
        if git_blob(data) != entry["sha"]:
            raise VerificationError(f"source hash mismatch: {name}")
        verified.append((name, data, int(entry["mode"][-3:], 8)))
    return verified


def patched_files(root: Path, lock: dict, source_files: dict[str, bytes]) -> dict[str, bytes]:
    if not lock.get("patch_complete"):
        raise VerificationError("composite source patch review is pending")
    files = dict(source_files)
    modified = set()
    for edit in lock["edits"]:
        path = edit["path"]
        if path in modified:
            raise VerificationError("duplicate patch target")
        modified.add(path)
        original = files[path]
        if sha256(original) != edit["before_sha256"]:
            raise VerificationError(f"patch preimage mismatch: {path}")
        old, new = edit["old"].encode(), edit["new"].encode()
        if original.count(old) != 1:
            raise VerificationError(f"patch anchor not unique: {path}")
        result = original.replace(old, new, 1)
        if sha256(result) != edit["after_sha256"]:
            raise VerificationError(f"patch result mismatch: {path}")
        files[path] = result
    for overlay in lock["overlays"]:
        path, expected = overlay["path"], overlay["sha256"]
        if path in modified:
            raise VerificationError("duplicate patch target")
        modified.add(path)
        if not expected or len(expected) != 64:
            raise VerificationError("Rust overlay review/hash is pending; refusing to stage")
        if overlay.get("kind", "add") == "replace":
            expected_before = overlay.get("before_sha256")
            if not expected_before or len(expected_before) != 64 or path not in files:
                raise VerificationError("replacement overlay needs an exact original source hash")
            if sha256(files[path]) != expected_before:
                raise VerificationError(f"replacement overlay preimage mismatch: {path}")
        elif overlay.get("kind", "add") != "add":
            raise VerificationError("unknown overlay operation")
        elif path in files:
            raise VerificationError("overlay cannot replace upstream source without an explicit preimage")
        source_path = overlay.get("source_path", "overlay/" + path)
        if "source_path" in overlay:
            fixture_directory = {"registered-composite-transcript-tests": "transcript-overlay/",
                                 "registered-host-transcript-tests": "host-transcript-overlay/"}.get(lock.get("profile_kind"))
            if fixture_directory is None or source_path != fixture_directory + path:
                raise VerificationError("unsupported fixture overlay source")
        data = safe_path(root, source_path).read_bytes()
        if sha256(data) != expected:
            raise VerificationError(f"overlay hash mismatch: {path}")
        files[path] = data
    return files


def stage(source: Path, destination: Path, root: Path = HERE, lock_filename: str = "source-lock.json") -> dict:
    if destination.exists() or destination.is_symlink():
        raise VerificationError("destination must not exist")
    lock = load_lock(root, lock_filename)
    verified = verify_source(source, read_json(root / "source-tree.json"))
    before = {name: data for name, data, _ in verified}
    files = patched_files(root, lock, before)
    if files["Cargo.lock"] != before["Cargo.lock"]:
        raise VerificationError("Cargo.lock cannot change")
    # Validate everything before any output, and publish with one same-volume rename.
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".idevice-stage-", dir=destination.parent))
    try:
        modes = {name: mode for name, _, mode in verified}
        for name, data in files.items():
            path = safe_path(temporary, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            if modes.get(name) == 0o120000:
                safe_source_link(temporary, name, data)
                path.symlink_to(data.decode())
            else:
                path.write_bytes(data)
                path.chmod(modes.get(name, 0o644))
        manifest = {
            "schema": 1,
            "upstream": lock["upstream"],
            "source_lock_sha256": sha256((root / lock_filename).read_bytes()),
            "source_profile": lock_filename,
            "files": {name: sha256(data) for name, data in sorted(files.items())},
            "symlinks": {name: data.decode() for name, data, mode in verified if mode == 0o120000},
        }
        (temporary / "tetherless-source-manifest.json").write_bytes(canonical_json(manifest))
        os.rename(temporary, destination)
        return manifest
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--verify-only", action="store_true", help="verify pristine upstream bytes without applying the patch")
    args = parser.parse_args()
    if args.verify_only == (args.destination is not None):
        parser.error("choose exactly one of --verify-only or --destination")
    try:
        if args.verify_only:
            lock = load_lock()
            files = verify_source(args.source.resolve(), read_json(HERE / "source-tree.json"))
            print(json.dumps({"source_commit": lock["upstream"]["commit"], "source_only": True,
                              "verified_blobs": len(files), "verified_bytes": sum(len(data) for _, data, _ in files)}))
            return 0
        manifest = stage(args.source.resolve(), args.destination.absolute())
    except (VerificationError, OSError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(1, f"idevice source verification failed: {exc}\n")
    print(json.dumps({"source_commit": manifest["upstream"]["commit"], "files": len(manifest["files"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
