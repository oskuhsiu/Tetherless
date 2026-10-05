"""Helper-only sibling vendor preparation; no source or crate manifest edits."""
from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path, PurePosixPath

from apply_patch import VerificationError, canonical_json, safe_path, sha256
from build_xcframework import file_hash, locked_packages, reject_ambient_cargo_config, vendor_crates


PACKAGED_CONFIG_RULE = {
    "name": "dialoguer", "version": "0.12.0",
    "source": "registry+https://github.com/rust-lang/crates.io-index",
    "archive_sha256": "25f104b501bf2364e78d0d3974cbc774f738f5865306ed128e1e0d7499c0ad96",
    "path": ".cargo/config.toml",
    "file_sha256": "362771141e605c79a39783cb704a5736c746688c4ec9c20c9c448c75e2e8d2fa",
}
REVIEWED_ALIASES = {"format": "fmt", "format-check": "fmt --check",
                    "lint": "clippy --all-targets --all-features -- -D warnings",
                    "test-cover": "llvm-cov --all-features --lcov --output-path lcov.info"}
MAX_CONFIG_FILES = 1024
MAX_CONFIG_FILE_BYTES = 64 * 1024
MAX_CONFIG_TOTAL_BYTES = 256 * 1024
MAX_CONFIG_KEYS = 4096
MAX_CONFIG_KEY_BYTES = 128
MAX_CONFIG_KEY_TOTAL_BYTES = 64 * 1024
MAX_CONFIG_DEPTH = 16
MAX_CONFIG_INVENTORY_BYTES = 1024 * 1024


def setting_names(data: bytes, budget: dict) -> list[list[str]]:
    """Return TOML key paths only; never serialize values or parser exceptions."""
    parsed = tomllib.loads(data.decode("utf-8"))
    result = []
    def walk(value: object, prefix: list[str]) -> None:
        if len(prefix) > MAX_CONFIG_DEPTH:
            raise ValueError("key depth budget exceeded")
        if isinstance(value, dict):
            for key, child in value.items():
                length = len(key.encode("utf-8"))
                if length > MAX_CONFIG_KEY_BYTES or budget["keys"] <= 0 or budget["key_bytes"] < length:
                    raise ValueError("key budget exceeded")
                budget["keys"] -= 1
                budget["key_bytes"] -= length
                path = prefix + [key]
                result.append(path)
                walk(child, path)
        elif isinstance(value, list):
            for child in value:
                if isinstance(child, (list, dict)):
                    walk(child, prefix + ["[]"])
    walk(parsed, [])
    return result


def inventory_packaged_configs(vendor: Path, records: list[tuple[dict, dict]], output: Path) -> dict:
    """Inspect all authenticated crate-root configs before rejecting any one.

    Archive extraction/authentication has already finished. Reads and emitted
    key metadata are bounded; file contents and values never enter this report.
    """
    rows, blocked, bytes_read, count_exceeded = [], False, 0, False
    budget = {"keys": MAX_CONFIG_KEYS, "key_bytes": MAX_CONFIG_KEY_TOTAL_BYTES}
    for package, checksums in records:
        stem = package["name"] + "-" + package["version"]
        directory = vendor / stem
        cargo_dir = directory / ".cargo"
        if directory.is_symlink() or cargo_dir.is_symlink():
            if len(rows) >= MAX_CONFIG_FILES:
                blocked, count_exceeded = True, True
                break
            rows.append({"crate": stem, "path": ".cargo", "status": "unsafe_symlink", "setting_names": []})
            blocked = True
            continue
        for name in ("config", "config.toml"):
            path, relative = cargo_dir / name, ".cargo/" + name
            if not path.exists() and not path.is_symlink():
                continue
            if len(rows) >= MAX_CONFIG_FILES:
                # The pinned lock has at most 726 root config paths. Retain a
                # bounded failure receipt if a different input exceeds the cap.
                blocked, count_exceeded = True, True
                break
            row = {"crate": stem, "path": relative, "archive_sha256": package["checksum"],
                   "file_sha256": checksums["files"].get(relative), "setting_names": [], "status": "unreviewed"}
            rows.append(row)
            if path.is_symlink() or not path.is_file():
                row["status"] = "unsafe_nonregular_path"
            else:
                size = path.stat().st_size
                row["bytes"] = size
                if size > MAX_CONFIG_FILE_BYTES:
                    row["status"] = "file_byte_budget_exceeded"
                elif bytes_read + size > MAX_CONFIG_TOTAL_BYTES:
                    row["status"] = "total_byte_budget_exceeded"
                else:
                    with path.open("rb") as stream:
                        data = stream.read(MAX_CONFIG_FILE_BYTES + 1)
                    bytes_read += len(data)
                    if len(data) != size or sha256(data) != row["file_sha256"]:
                        row["status"] = "authenticated_file_changed"
                    else:
                        try:
                            row["setting_names"] = setting_names(data, budget)
                        except (ValueError, RecursionError, UnicodeError):
                            row["status"] = "invalid_or_over_budget_setting_names"
                        else:
                            rule = PACKAGED_CONFIG_RULE
                            if (all(package.get(key) == rule[key] for key in ("name", "version", "source"))
                                    and package["checksum"] == rule["archive_sha256"]
                                    and checksums["package"] == rule["archive_sha256"]
                                    and relative == rule["path"] and row["file_sha256"] == rule["file_sha256"]
                                    and tomllib.loads(data.decode()) == {"alias": REVIEWED_ALIASES}):
                                row["status"] = "reviewed_exact_match"
            blocked |= row["status"] != "reviewed_exact_match"
        if count_exceeded:
            break
    result = {"schema": 1, "scope": "authenticated crate-root Cargo config metadata only",
              "all_packages_examined": not count_exceeded,
              "config_count_budget_exceeded": count_exceeded,
              "package_count": len(records), "configs": rows, "blocked": blocked,
              "values_retained": False, "limits": {"files": MAX_CONFIG_FILES,
                  "file_bytes": MAX_CONFIG_FILE_BYTES, "total_read_bytes": MAX_CONFIG_TOTAL_BYTES,
                  "keys": MAX_CONFIG_KEYS, "key_bytes": MAX_CONFIG_KEY_BYTES,
                  "total_key_bytes": MAX_CONFIG_KEY_TOTAL_BYTES, "key_depth": MAX_CONFIG_DEPTH,
                  "inventory_bytes": MAX_CONFIG_INVENTORY_BYTES}}
    encoded = canonical_json(result)
    if len(encoded) > MAX_CONFIG_INVENTORY_BYTES:
        # Preserve a bounded failure receipt; never print configuration values.
        result = {"schema": 1, "blocked": True, "all_packages_examined": False,
                  "values_retained": False, "error": "inventory_byte_budget_exceeded"}
        encoded = canonical_json(result)
    with output.open("xb") as stream:
        stream.write(encoded)
    return result


def check_packaged_cargo_config(directory: Path, package: dict, checksums: dict) -> list[dict]:
    """One reviewed alias-only config; authentication remains mandatory.

    The expected file came from immutable upstream source. Only an actual
    lock-authenticated registry archive containing those exact bytes can pass.
    Nothing is removed, rewritten, or allowed by maintainer/version name alone.
    """
    reject_ambient_cargo_config(directory.parent)
    cargo_dir = directory / ".cargo"
    if directory.is_symlink() or cargo_dir.is_symlink():
        raise VerificationError("ambient Cargo configuration symlink is unsupported")
    accepted = []
    for name in ("config", "config.toml"):
        path = cargo_dir / name
        if not path.exists() and not path.is_symlink():
            continue
        rule = PACKAGED_CONFIG_RULE
        relative = ".cargo/" + name
        identity_matches = (directory.name == rule["name"] + "-" + rule["version"]
                            and all(package.get(key) == rule[key] for key in ("name", "version", "source")))
        if (not identity_matches or package.get("checksum") != rule["archive_sha256"]
                or checksums.get("package") != rule["archive_sha256"]
                or relative != rule["path"] or path.is_symlink() or not path.is_file()
                or checksums.get("files", {}).get(relative) != rule["file_sha256"]
                or file_hash(path) != rule["file_sha256"]
                or tomllib.loads(path.read_text()) != {"alias": REVIEWED_ALIASES}):
            raise VerificationError("ambient Cargo configuration must be absent: " + str(path))
        accepted.append({"crate": package["name"] + "-" + package["version"],
                         "path": relative, "archive_sha256": rule["archive_sha256"],
                         "file_sha256": rule["file_sha256"],
                         "scope": "exact reviewed alias-only packaged config"})
    return accepted


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
    inputs, packaged_configs, records = {}, [], []
    for package in locked_packages(lock_bytes):
        stem = f"{package['name']}-{package['version']}"
        directory = vendor / stem
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
        records.append((package, checksums))
    inventory_path = work / "vendor-config-inventory.json"
    inventory = inventory_packaged_configs(vendor, records, inventory_path)
    if inventory["blocked"]:
        raise VerificationError("ambient Cargo configuration rejected; see vendor-config-inventory.json (metadata only)")
    for package, checksums in records:
        directory = vendor / (package["name"] + "-" + package["version"])
        packaged_configs += check_packaged_cargo_config(directory, package, checksums)
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
            "reviewed_packaged_configs": packaged_configs,
            "config_inventory": str(inventory_path), "config_inventory_sha256": file_hash(inventory_path),
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
