"""Helper-only sibling vendor preparation; no source or crate manifest edits."""
from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path, PurePosixPath

from apply_patch import VerificationError, canonical_json, safe_path, sha256
from build_xcframework import file_hash, locked_packages, reject_ambient_cargo_config, vendor_crates


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


def inventory_packaged_configs(vendor: Path, records: list[tuple[dict, dict]], output: Path,
                               cargo_cwds: list[Path]) -> dict:
    """Inventory sibling vendor configs outside the owned Cargo discovery chains.

    Archive extraction/authentication has already finished. Reads and emitted
    key metadata are bounded; file contents and values never enter this report.
    """
    rows, bytes_read, count_exceeded = [], 0, False
    discovered = {str(parent / ".cargo" / name)
                  for cwd in cargo_cwds for parent in [cwd.absolute(), *cwd.absolute().parents]
                  for name in ("config", "config.toml")}
    budget = {"keys": MAX_CONFIG_KEYS, "key_bytes": MAX_CONFIG_KEY_TOTAL_BYTES}
    for package, checksums in records:
        stem = package["name"] + "-" + package["version"]
        directory = vendor / stem
        cargo_dir = directory / ".cargo"
        if directory.is_symlink() or cargo_dir.is_symlink():
            if len(rows) >= MAX_CONFIG_FILES:
                count_exceeded = True
                break
            rows.append({"crate": stem, "path": ".cargo", "status": "unsafe_symlink", "setting_names": []})
            continue
        for name in ("config", "config.toml"):
            path, relative = cargo_dir / name, ".cargo/" + name
            if not path.exists() and not path.is_symlink():
                continue
            if len(rows) >= MAX_CONFIG_FILES:
                # The pinned lock has at most 726 root config paths. Retain a
                # bounded failure receipt if a different input exceeds the cap.
                count_exceeded = True
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
                            row["status"] = "parsed"
            row["effective_for_owned_cargo"] = str(path.absolute()) in discovered
            row["discovery_class"] = "effective" if row["effective_for_owned_cargo"] else "inactive_sibling"
        if count_exceeded:
            break
    result = {"schema": 1, "scope": "authenticated crate-root Cargo config metadata only",
              "all_packages_examined": not count_exceeded,
              "config_count_budget_exceeded": count_exceeded,
              "package_count": len(records), "configs": rows,
              "blocked": any(row.get("effective_for_owned_cargo", False) for row in rows),
              "owned_cargo_cwds": [str(cwd.absolute()) for cwd in cargo_cwds],
              "admission_scope": "config content is diagnostic; only owned cwd discovery chains are effective",
              "values_retained": False, "limits": {"files": MAX_CONFIG_FILES,
                  "file_bytes": MAX_CONFIG_FILE_BYTES, "total_read_bytes": MAX_CONFIG_TOTAL_BYTES,
                  "keys": MAX_CONFIG_KEYS, "key_bytes": MAX_CONFIG_KEY_BYTES,
                  "total_key_bytes": MAX_CONFIG_KEY_TOTAL_BYTES, "key_depth": MAX_CONFIG_DEPTH,
                  "inventory_bytes": MAX_CONFIG_INVENTORY_BYTES}}
    encoded = canonical_json(result)
    if len(encoded) > MAX_CONFIG_INVENTORY_BYTES:
        # Preserve bounded diagnostic uncertainty; inactive contents are not admission gates.
        result = {"schema": 1, "blocked": False, "all_packages_examined": False,
                  "values_retained": False, "error": "inventory_byte_budget_exceeded"}
        encoded = canonical_json(result)
    with output.open("xb") as stream:
        stream.write(encoded)
    return result


def require_config_absent(root: Path) -> None:
    for name in ("config", "config.toml"):
        path = root / name
        if path.exists() or path.is_symlink():
            raise VerificationError("offline Cargo config destination must be new")


def prepare_offline_vendor(*, source: Path, work: Path, cache: Path, env: dict[str, str],
                           derive_metadata: bool = False) -> dict:
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
    reject_ambient_cargo_config(source)
    lock_bytes = (source / "Cargo.lock").read_bytes()
    crates = vendor_crates(lock_bytes, cache, vendor)
    inputs, records = {}, []
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
    inventory = inventory_packaged_configs(vendor, records, inventory_path, [source])
    if inventory["blocked"]:
        raise VerificationError("ambient Cargo configuration rejected; see vendor-config-inventory.json (metadata only)")
    derived, build_vendor = None, vendor
    if derive_metadata:
        from derived_cbindgen import prepare_derived_vendor
        build_vendor = work / "build-vendor"
        derived = prepare_derived_vendor(vendor=vendor, destination=build_vendor, source=source,
                                         originals=inputs, crates=crates, env=env)
    config = home / "config.toml"
    # Use an absolute TOML-quoted path: nested cargo metadata may run with a cwd
    # inside a vendored crate, independent of the top-level --manifest-path.
    text = ('[source.crates-io]\nreplace-with = "tetherless-vendor"\n\n'
            '[source.tetherless-vendor]\ndirectory = ' + json.dumps(str(build_vendor), ensure_ascii=False) + '\n\n'
            '[net]\noffline = true\n')
    if tomllib.loads(text)["source"]["tetherless-vendor"]["directory"] != str(build_vendor):
        raise VerificationError("offline vendor path does not round-trip through TOML")
    with config.open("x", encoding="utf-8") as stream:
        stream.write(text)
    return {"schema": 1, "vendor_directory": str(vendor), "cargo_home": str(home),
            "cargo_config": str(config), "cargo_config_sha256": sha256(text.encode()),
            "workspace_lock_sha256": sha256(lock_bytes), "crates": crates,
            "derived_build": derived,
            "effective_cargo_cwds": [str(source)],
            "config_inventory": str(inventory_path), "config_inventory_sha256": file_hash(inventory_path),
            "authenticated_inputs": inputs, "top_level_frozen": True,
            "nested_metadata_offline": True, "nested_metadata_frozen": bool(derived)}


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
                if path.stat().st_nlink != 1:
                    unsafe.append(name)
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
            if path.stat().st_nlink != 1:
                unsafe.append(name)
            generated[name] = file_hash(path)
            # New sibling-vendor configs are recorded outputs, outside owned Cargo cwd chains.
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
    pristine_extra = bool(receipt.get("derived_build")) and receipt.get("input_kind") != "derived_build_vendor" and bool(generated)
    return {"schema": 1, "original_inputs_unchanged": not(changed or missing or unsafe or pristine_extra) and config_unchanged,
            "unexpected_pristine_outputs": pristine_extra,
            "vendor_root_valid": True,
            "changed_authenticated_inputs": changed, "missing_authenticated_inputs": missing,
            "unsafe_paths": sorted(set(unsafe)), "generated_files": generated,
            "cargo_config_unchanged": config_unchanged,
            "nested_metadata_frozen": receipt.get("nested_metadata_frozen", False)}


def audit_workspace_inputs(source: Path, source_manifest: dict, lock_sha256: str) -> dict:
    """Verify all staged original inputs on success and on command failure."""
    changed, missing, unsafe, generated_headers = {}, [], [], {}
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
        reject_ambient_cargo_config(source)
    except (VerificationError, OSError):
        unsafe.append("effective_workspace_or_ancestor_cargo_config")
    try:
        path = safe_path(source, "Cargo.lock")
        lock_unchanged = path.is_file() and file_hash(path) == lock_sha256
    except (VerificationError, OSError):
        lock_unchanged = False
    for name in ("ffi/idevice.h", "cpp/include/idevice.h"):
        try:
            path = safe_path(source, name)
            if name in source_manifest["files"]:
                generated_headers[name] = {"status": "registered_input_audited_above"}
            elif path.is_file():
                generated_headers[name] = {"status": "generated", "sha256": file_hash(path),
                                           "bytes": path.stat().st_size}
            elif path.exists():
                generated_headers[name] = {"status": "unsafe_nonregular_output"}
                unsafe.append(name)
            else:
                generated_headers[name] = {"status": "not_generated"}
        except (VerificationError, OSError):
            generated_headers[name] = {"status": "unsafe_or_unreadable_output"}
            unsafe.append(name)
    return {"schema": 1, "source_root_valid": True,
            "original_inputs_unchanged": not(changed or missing or unsafe) and lock_unchanged,
            "workspace_lock_unchanged": lock_unchanged, "changed_inputs": changed,
            "missing_inputs": missing, "unsafe_paths": sorted(set(unsafe)),
            "known_generated_headers": generated_headers}
