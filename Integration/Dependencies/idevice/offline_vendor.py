"""Helper-only sibling vendor preparation; no source or crate manifest edits."""
from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path, PurePosixPath

from apply_patch import VerificationError, safe_path, sha256
from build_xcframework import file_hash, locked_packages, reject_ambient_cargo_config, vendor_crates


def require_config_absent(root: Path) -> None:
    for name in ("config", "config.toml"):
        path = root / name
        if path.exists() or path.is_symlink():
            raise VerificationError("offline Cargo config destination must be new")


def prepare_offline_vendor(*, source: Path, work: Path, cache: Path, env: dict[str, str]) -> dict:
    source, work, cache = source.absolute(), work.absolute(), cache.absolute()
    if source != work / "source" or source.is_symlink() or work.is_symlink():
        raise VerificationError("expected the owned source directory beneath the fresh work root")
    home = work / "cargo-home"
    if env.get("CARGO_HOME") != str(home) or home.is_symlink() or not home.is_dir():
        raise VerificationError("CARGO_HOME must be the owned isolated cargo-home directory")
    if env.get("CARGO_NET_OFFLINE") != "true":
        raise VerificationError("nested Cargo metadata must inherit offline mode")
    require_config_absent(home)
    vendor = work / "vendor"
    if vendor.exists() or vendor.is_symlink():
        raise VerificationError("sibling vendor destination must be new")
    # Cargo metadata walks manifest ancestors to discover workspaces. The new
    # vendor directory must not be below either idevice or another Cargo root.
    for parent in vendor.parents:
        manifest = parent / "Cargo.toml"
        if manifest.exists() or manifest.is_symlink():
            raise VerificationError("vendor would be nested inside an enclosing Cargo project")
    reject_ambient_cargo_config(source)
    reject_ambient_cargo_config(vendor)
    lock_bytes = (source / "Cargo.lock").read_bytes()
    crates = vendor_crates(lock_bytes, cache, vendor)
    inputs = {}
    for package in locked_packages(lock_bytes):
        stem = f"{package['name']}-{package['version']}"
        directory = vendor / stem
        # This includes a crate-local .cargo/config or config.toml, which would
        # otherwise override the global CARGO_HOME source replacement.
        reject_ambient_cargo_config(directory)
        checksum_path = directory / ".cargo-checksum.json"
        checksums = json.loads(checksum_path.read_bytes())
        if checksums["package"] != package["checksum"]:
            raise VerificationError("vendor checksum metadata differs from authenticated archive")
        for name, expected in checksums["files"].items():
            path = safe_path(directory, name)
            if file_hash(path) != expected:
                raise VerificationError("authenticated vendor input changed during preparation")
            inputs[stem + "/" + name] = expected
        inputs[stem + "/.cargo-checksum.json"] = file_hash(checksum_path)
    config = home / "config.toml"
    # Use an absolute TOML-quoted path: nested cargo metadata may run with a cwd
    # inside a vendored crate, independent of the top-level --manifest-path.
    text = ('[source.crates-io]\nreplace-with = "tetherless-vendor"\n\n'
            '[source.tetherless-vendor]\ndirectory = ' + json.dumps(str(vendor), ensure_ascii=False) + '\n\n'
            '[net]\noffline = true\n')
    if tomllib.loads(text)["source"]["tetherless-vendor"]["directory"] != str(vendor):
        raise VerificationError("offline vendor path does not round-trip through TOML")
    with config.open("x", encoding="utf-8") as stream:
        stream.write(text)
    return {"schema": 1, "vendor_directory": str(vendor), "cargo_home": str(home),
            "cargo_config": str(config), "cargo_config_sha256": sha256(text.encode()),
            "workspace_lock_sha256": sha256(lock_bytes), "crates": crates,
            "authenticated_inputs": inputs, "top_level_frozen": True,
            "nested_metadata_offline": True, "nested_metadata_frozen": False}


def audit_vendor_inputs(receipt: dict) -> dict:
    """Do not restore/mutate input bytes; report original changes and new outputs."""
    vendor = Path(receipt["vendor_directory"])
    changed, missing, generated, unsafe = {}, [], {}, []
    if vendor.is_symlink() or not vendor.is_dir():
        return {"schema": 1, "original_inputs_unchanged": False, "vendor_root_valid": False,
                "changed_authenticated_inputs": {}, "missing_authenticated_inputs": [],
                "unsafe_paths": ["."], "generated_files": {}, "cargo_config_unchanged": None,
                "nested_metadata_frozen": False}
    originals = receipt["authenticated_inputs"]
    for name, expected in originals.items():
        try:
            path = safe_path(vendor, name)
            if not path.is_file():
                missing.append(name)
            else:
                actual = file_hash(path)
                if actual != expected:
                    changed[name] = {"expected_sha256": expected, "actual_sha256": actual}
        except (VerificationError, OSError):
            unsafe.append(name)
    for path in sorted(vendor.rglob("*")):
        name = str(path.relative_to(vendor))
        if path.is_symlink():
            unsafe.append(name)
        elif path.is_file() and name not in originals:
            generated[name] = file_hash(path)
            if path.name in ("config", "config.toml") and path.parent.name == ".cargo":
                unsafe.append(name)
    config = Path(receipt["cargo_config"])
    home = Path(receipt["cargo_home"])
    legacy_config = home / "config"
    if legacy_config.exists() or legacy_config.is_symlink():
        unsafe.append("$CARGO_HOME/config")
    try:
        config_unchanged = (not home.is_symlink() and not config.is_symlink() and config.is_file()
                            and file_hash(config) == receipt["cargo_config_sha256"])
    except OSError:
        config_unchanged = False
    return {"schema": 1, "original_inputs_unchanged": not(changed or missing or unsafe) and config_unchanged,
            "vendor_root_valid": True,
            "changed_authenticated_inputs": changed, "missing_authenticated_inputs": missing,
            "unsafe_paths": sorted(set(unsafe)), "generated_files": generated,
            "cargo_config_unchanged": config_unchanged, "nested_metadata_frozen": False}


def audit_workspace_inputs(source: Path, source_manifest: dict, lock_sha256: str) -> dict:
    """Verify all staged original inputs on success and on command failure."""
    changed, missing, unsafe = {}, [], []
    if source.is_symlink() or not source.is_dir():
        return {"schema": 1, "original_inputs_unchanged": False, "source_root_valid": False,
                "workspace_lock_unchanged": False, "changed_inputs": {}, "missing_inputs": [],
                "unsafe_paths": ["."]}
    for name, expected in source_manifest["files"].items():
        try:
            if name in source_manifest["symlinks"]:
                parent = str(PurePosixPath(name).parent)
                directory = source if parent == "." else safe_path(source, parent)
                path = directory / PurePosixPath(name).name
                if not path.is_symlink():
                    unsafe.append(name)
                    continue
                actual = sha256(os.readlink(path).encode())
            else:
                path = safe_path(source, name)
                if not path.is_file():
                    missing.append(name)
                    continue
                actual = file_hash(path)
            if actual != expected:
                changed[name] = {"expected_sha256": expected, "actual_sha256": actual}
        except (VerificationError, OSError):
            unsafe.append(name)
    try:
        path = safe_path(source, "Cargo.lock")
        lock_unchanged = path.is_file() and file_hash(path) == lock_sha256
    except (VerificationError, OSError):
        lock_unchanged = False
    return {"schema": 1, "source_root_valid": True,
            "original_inputs_unchanged": not(changed or missing or unsafe) and lock_unchanged,
            "workspace_lock_unchanged": lock_unchanged, "changed_inputs": changed,
            "missing_inputs": missing, "unsafe_paths": sorted(set(unsafe))}
