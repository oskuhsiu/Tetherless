"""Exact build-only cbindgen adaptation; immutable registry inputs stay separate."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat

from apply_patch import VerificationError, canonical_json, safe_path, sha256
from build_xcframework import file_hash

CRATE = "cbindgen-0.29.2"
ARCHIVE_SHA256 = "befbfd072a8e81c02f8c507aefce431fe5e7d051f83d48a23ffc9b9fe5a11799"
SOURCE_PATH = "src/bindgen/cargo/cargo_metadata.rs"
SOURCE_SHA256 = "d616faea349e4e7ff5a81f944e9c25c3a7b1acc4d7cc421e437464c906d4bd8d"
PATCHED_SHA256 = "fb696646cd0ad4c47711303ac8a8cad26cde38a00923077e87b0d2e364a0b90f"
CONTEXT_VARIABLE = "TETHERLESS_CBINDGEN_WORKSPACE_MANIFEST"
README_CRATE = "nskeyedarchiver_converter-0.1.3"
README_ARCHIVE_SHA256 = "36c53158d1bf37bbbdd165f5220fda8bb5757c89eb700107992152c64c6cad7e"
README_SHA256 = "8f9d7995df53d0b3c75999fb5b253930513d761808f54f1b118c5c02cfee6f31"
README_LOGICAL = README_CRATE + "/README.md"
README_OBSERVED = README_CRATE + "/README.MD"
OLD_COMMAND = '''            let mut cmd = Command::new(cargo);
            cmd.arg("metadata");'''
NEW_COMMAND = '''            // Tetherless build-only adaptation: resolve metadata through the
            // owned, frozen workspace while retaining the binding manifest below.
            let workspace_manifest = env::var_os("TETHERLESS_CBINDGEN_WORKSPACE_MANIFEST")
                .map(std::path::PathBuf::from)
                .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput,
                    "missing owned workspace metadata context"))?;
            if !workspace_manifest.is_absolute()
                || workspace_manifest.file_name() != Some(std::ffi::OsStr::new("Cargo.toml"))
                || !workspace_manifest.is_file()
            {
                return Err(io::Error::new(io::ErrorKind::InvalidInput,
                    "invalid owned workspace metadata context").into());
            }
            let workspace_root = workspace_manifest.parent().ok_or_else(||
                io::Error::new(io::ErrorKind::InvalidInput, "missing workspace root"))?;
            let mut cmd = Command::new(cargo);
            cmd.current_dir(workspace_root);
            cmd.arg("metadata");
            cmd.arg("--frozen");'''
OLD_MANIFEST = '''            cmd.arg("--manifest-path");
            cmd.arg(manifest_path);'''
NEW_MANIFEST = '''            cmd.arg("--manifest-path");
            cmd.arg(&workspace_manifest);'''


def inventory_difference(expected: dict, actual: dict) -> dict:
    """Bounded metadata-only diagnostic; exact path/hash equality remains required."""
    missing = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys())
    changed = sorted(name for name in expected.keys() & actual.keys() if expected[name] != actual[name])
    def path_record(name: str) -> dict:
        encoded = name.encode("utf-8", errors="surrogatepass")
        return {"path": name if len(encoded) <= 512 else None,
                "path_omitted": len(encoded) > 512,
                "path_utf8_bytes": len(encoded), "path_sha256": sha256(encoded)}
    details, omitted = {}, {}
    for kind, names in (("missing", missing), ("extra", extra), ("changed", changed)):
        rows = []
        for name in names[:64]:
            row = path_record(name)
            if name in expected:
                row["expected_sha256"] = expected[name]
            if name in actual:
                row["actual_sha256"] = actual[name]
            rows.append(row)
        details[kind] = rows
        omitted[kind] = len(names) - len(rows)
    return {"schema": 1, "exact_match": expected == actual,
            "expected_files": len(expected), "observed_files": len(actual),
            "counts": {"missing": len(missing), "extra": len(extra), "changed": len(changed)},
            "details": details, "detail_limit_per_category": 64,
            "omitted_counts": omitted, "details_truncated": any(omitted.values()),
            "expected_inventory_sha256": sha256(canonical_json(expected)),
            "observed_inventory_sha256": sha256(canonical_json(actual)),
            "file_contents_retained": False}


def reconcile_reviewed_readme(vendor: Path, expected: dict, actual: dict, crates: dict) -> dict:
    """Prove the one observed spelling alias; never normalize names or file data."""
    absent = expected.keys() - actual.keys()
    if (absent != {README_LOGICAL} or actual.keys() - expected.keys()
            or any(actual[name] != expected[name] for name in actual.keys() & expected.keys())
            or crates.get(README_CRATE) != README_ARCHIVE_SHA256
            or expected.get(README_LOGICAL) != README_SHA256
            or expected.get(README_OBSERVED) != README_SHA256
            or actual.get(README_OBSERVED) != README_SHA256):
        return {"applied": False, "reason": "not_the_exact_reviewed_alias_difference"}
    try:
        logical = safe_path(vendor, README_LOGICAL)
        observed = safe_path(vendor, README_OBSERVED)
        if logical.is_symlink() or observed.is_symlink():
            return {"applied": False, "reason": "symlink_is_not_a_filename_alias"}
        left, right = logical.stat(), observed.stat()
        if (not stat.S_ISREG(left.st_mode) or not stat.S_ISREG(right.st_mode)
                or left.st_nlink != 1 or right.st_nlink != 1
                or (left.st_dev, left.st_ino) != (right.st_dev, right.st_ino)
                or not os.path.samefile(logical, observed)
                or file_hash(logical) != README_SHA256 or file_hash(observed) != README_SHA256):
            return {"applied": False, "reason": "filesystem_identity_or_exact_hash_not_proved"}
    except (VerificationError, OSError):
        return {"applied": False, "reason": "logical_lookup_not_proved"}
    return {"applied": True, "reason": "exact_logical_hashes_and_same_regular_file",
            "crate": README_CRATE, "archive_sha256": README_ARCHIVE_SHA256,
            "logical_path": README_LOGICAL, "enumerated_path": README_OBSERVED,
            "sha256": README_SHA256, "device": left.st_dev, "inode": left.st_ino,
            "link_count": left.st_nlink, "samefile": True,
            "checksum_keys_preserved": True}


def patch_metadata_source(data: bytes) -> bytes:
    if sha256(data) != SOURCE_SHA256:
        raise VerificationError("cbindgen metadata source preimage mismatch")
    text = data.decode()
    if text.count(OLD_COMMAND) != 1 or text.count(OLD_MANIFEST) != 1:
        raise VerificationError("cbindgen metadata patch anchor mismatch")
    result = text.replace(OLD_COMMAND, NEW_COMMAND).replace(OLD_MANIFEST, NEW_MANIFEST).encode()
    if sha256(result) != PATCHED_SHA256:
        raise VerificationError("cbindgen metadata patch output mismatch")
    return result


def prepare_derived_vendor(*, vendor: Path, destination: Path, source: Path,
                           originals: dict, crates: dict, env: dict,
                           export_namespace: dict | None = None) -> dict:
    if crates.get(CRATE) != ARCHIVE_SHA256:
        raise VerificationError("locked cbindgen archive identity mismatch")
    if vendor.is_symlink() or not vendor.is_dir() or destination.exists() or destination.is_symlink():
        raise VerificationError("expected pristine vendor and a fresh derived vendor destination")
    if source.is_symlink() or not source.is_dir():
        raise VerificationError("owned workspace root is missing or substituted")
    manifest = safe_path(source, "Cargo.toml")
    lock = safe_path(source, "Cargo.lock")
    if not manifest.is_file() or not lock.is_file():
        raise VerificationError("owned workspace manifest/lock missing")
    source_name = CRATE + "/" + SOURCE_PATH
    checksum_name = CRATE + "/.cargo-checksum.json"
    # Recheck the complete original inventory immediately before the copy.
    actual = {}
    for path in vendor.rglob("*"):
        if path.is_symlink():
            raise VerificationError("unexpected pristine vendor symlink")
        if path.is_file():
            if path.stat().st_nlink != 1:
                raise VerificationError("unexpected pristine vendor hardlink")
            actual[str(path.relative_to(vendor))] = file_hash(path)
    difference = inventory_difference(originals, actual)
    reconciliation = (reconcile_reviewed_readme(vendor, originals, actual, crates)
                      if actual != originals else {"applied": False, "reason": "exact_inventory_match"})
    difference["readme_reconciliation"] = reconciliation
    admitted = actual == originals or reconciliation["applied"]
    difference["admitted"] = admitted
    diagnostic = destination.parent / "vendor-derivation-inventory.json"
    encoded = canonical_json(difference)
    if len(encoded) > 1024 * 1024:
        difference["details"] = {"missing": [], "extra": [], "changed": []}
        difference["details_truncated"] = True
        difference["omitted_counts"] = dict(difference["counts"])
        difference["diagnostic_output_limit_exceeded"] = True
        encoded = canonical_json(difference)
    with diagnostic.open("xb") as stream:
        stream.write(encoded)
    if not admitted:
        counts = difference["counts"]
        raise VerificationError("pristine vendor inventory changed before derivation; "
                                f"missing={counts['missing']} extra={counts['extra']} changed={counts['changed']}; "
                                "see vendor-derivation-inventory.json")
    original_source = safe_path(vendor, source_name).read_bytes()
    patched_source = patch_metadata_source(original_source)
    original_checksum = safe_path(vendor, checksum_name).read_bytes()
    checksum = json.loads(original_checksum)
    if checksum["package"] != ARCHIVE_SHA256 or checksum["files"].get(SOURCE_PATH) != SOURCE_SHA256:
        raise VerificationError("cbindgen checksum preimage mismatch")
    checksum["files"][SOURCE_PATH] = PATCHED_SHA256
    patched_checksum = canonical_json(checksum)
    shutil.copytree(vendor, destination, symlinks=True)
    safe_path(destination, source_name).write_bytes(patched_source)
    safe_path(destination, checksum_name).write_bytes(patched_checksum)
    expected = dict(originals)
    expected[source_name] = PATCHED_SHA256
    expected[checksum_name] = sha256(patched_checksum)
    namespace_changes = {}
    if export_namespace is not None:
        from ffi_namespace import namespace_vendor
        namespace_changes = namespace_vendor(destination, originals, crates, export_namespace)
        expected.update({name: row["after_sha256"] for name, row in namespace_changes.items()})
    for name, digest in expected.items():
        if file_hash(safe_path(destination, name)) != digest:
            raise VerificationError("derived vendor input differs from exact registered result")
    env[CONTEXT_VARIABLE] = str(manifest)
    return {"schema": 1, "directory": str(destination), "input_kind": "derived_build_vendor",
            "authenticated_inputs": expected, "archive_origin_sha256": ARCHIVE_SHA256,
            "source_changes": {source_name: {"before_sha256": SOURCE_SHA256, "after_sha256": PATCHED_SHA256}},
            "export_namespace_changes": namespace_changes,
            "generated_checksum_metadata": {checksum_name: {
                "before_sha256": sha256(original_checksum), "after_sha256": sha256(patched_checksum)}},
            "metadata_context": {"environment_key": CONTEXT_VARIABLE, "manifest_path": str(manifest),
                "cwd": str(source), "workspace_lock_sha256": file_hash(lock),
                "frozen": True, "scope": "patched cbindgen metadata commands only"},
            "inventory_diagnostic": str(diagnostic), "inventory_diagnostic_sha256": file_hash(diagnostic),
            "readme_reconciliation": reconciliation,
            "pristine_registry_files_modified": False}


def derived_audit_receipt(receipt: dict) -> dict:
    result = dict(receipt)
    derived = receipt["derived_build"]
    result["vendor_directory"] = derived["directory"]
    result["authenticated_inputs"] = derived["authenticated_inputs"]
    result["input_kind"] = "derived_build_vendor"
    return result
