"""Matching-source bundle adapter over the reviewed deterministic ZIP helper."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

from apply_patch import VerificationError, canonical_json, safe_path, safe_source_link, sha256
from build_xcframework import deterministic_zip, file_hash, inventory, locked_packages
from derived_cbindgen import derived_audit_receipt
from offline_vendor import audit_vendor_inputs, audit_workspace_inputs


def copy_selected_inputs(source: Path, destination: Path, files: dict[str, str], links: dict[str, str] | None = None) -> None:
    """Copy only registered source/known header entries, never arbitrary build extras."""
    links = links or {}
    destination.mkdir(parents=True)
    for name, expected in sorted(files.items()):
        output = safe_path(destination, name)
        output.parent.mkdir(parents=True, exist_ok=True)
        if name in links:
            path = source / name
            if not path.is_symlink() or os.readlink(path) != links[name] or sha256(links[name].encode()) != expected:
                raise VerificationError("matching-source committed symlink changed")
            safe_source_link(destination, name, links[name].encode())
            output.symlink_to(links[name])
        else:
            path = safe_path(source, name)
            if file_hash(path) != expected:
                raise VerificationError("matching-source selected input changed")
            shutil.copy2(path, output)
            if file_hash(output) != expected:
                raise VerificationError("matching-source copied selected input changed")


def create_source_bundle(*, source: Path, source_manifest: dict, vendor_receipt: dict,
                         crate_cache: Path, recipe_root: Path, recipe_files: dict[str, str],
                         output: Path, staging: Path) -> dict:
    if staging.exists() or staging.is_symlink() or output.exists() or output.is_symlink():
        raise VerificationError("source bundle staging/output must be fresh")
    audits = {"workspace": audit_workspace_inputs(source, source_manifest, vendor_receipt["workspace_lock_sha256"]),
              "pristine_vendor": audit_vendor_inputs(vendor_receipt),
              "derived_vendor": audit_vendor_inputs(derived_audit_receipt(vendor_receipt))}
    if not all(row["original_inputs_unchanged"] for row in audits.values()):
        raise VerificationError("matching-source inputs failed their existing audits")
    archives = {}
    for package in locked_packages((source / "Cargo.lock").read_bytes()):
        name = package["name"] + "-" + package["version"] + ".crate"
        path = safe_path(crate_cache, name)
        if not path.is_file() or file_hash(path) != package["checksum"]:
            raise VerificationError("matching-source crate archive mismatch")
        archives[name] = package["checksum"]
    if not recipe_files:
        raise VerificationError("matching-source recipe inventory must be explicit")
    for name, digest in recipe_files.items():
        if file_hash(safe_path(recipe_root, name)) != digest:
            raise VerificationError("matching-source recipe file changed")
    staging.mkdir(parents=True)
    workspace_files = dict(source_manifest["files"])
    for name, evidence in audits["workspace"].get("known_generated_headers", {}).items():
        if name in ("ffi/idevice.h", "cpp/include/idevice.h") and evidence.get("status") == "generated":
            workspace_files[name] = evidence["sha256"]
    derived_files = dict(vendor_receipt["derived_build"]["authenticated_inputs"])
    generated_header = "plist_ffi-0.1.6/plist.h"
    if generated_header in audits["derived_vendor"]["generated_files"]:
        derived_files[generated_header] = audits["derived_vendor"]["generated_files"][generated_header]
    copy_selected_inputs(source, staging / "workspace", workspace_files, source_manifest["symlinks"])
    copy_selected_inputs(Path(vendor_receipt["vendor_directory"]), staging / "vendor/pristine", vendor_receipt["authenticated_inputs"])
    copy_selected_inputs(Path(vendor_receipt["derived_build"]["directory"]), staging / "vendor/derived", derived_files)
    for name, digest in archives.items():
        destination = staging / "crate-archives" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(safe_path(crate_cache, name), destination)
        if file_hash(destination) != digest:
            raise VerificationError("matching-source archive changed during copy")
    for name, digest in recipe_files.items():
        destination = safe_path(staging / "recipe", name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(safe_path(recipe_root, name), destination)
        if file_hash(destination) != digest:
            raise VerificationError("matching-source recipe changed during copy")
    # Logical checksum keys can alias on the native volume. Keep those exact keys
    # in the receipts, and retain the original authenticated .crate bytes too.
    for label, directory, expected in (
        ("workspace", staging / "workspace", source_manifest["files"]),
        ("pristine", staging / "vendor/pristine", vendor_receipt["authenticated_inputs"]),
        ("derived", staging / "vendor/derived", vendor_receipt["derived_build"]["authenticated_inputs"]),
    ):
        for name, digest in expected.items():
            if label == "workspace" and name in source_manifest["symlinks"]:
                continue
            if file_hash(safe_path(directory, name)) != digest:
                raise VerificationError("matching-source copied input mismatch")
    metadata = {"schema": 1, "source_manifest": source_manifest, "vendor_layout": vendor_receipt,
                "input_audits": audits, "crate_archives": archives, "recipe_files": recipe_files,
                "included_roots": ["workspace", "vendor/pristine", "vendor/derived", "crate-archives", "recipe"],
                "bundled_workspace_files": workspace_files, "bundled_derived_vendor_files": derived_files,
                "unregistered_build_outputs_copied": False,
                "external_inputs": ["The selected OpenSSL framework payloads remain external, identified by the provider receipts.",
                    "Provider source/binary equivalence is unproved; this bundle does not contain a reconstructed provider source build.",
                    "The separately locked Rust/Xcode/SDK toolchain must be supplied for a rebuild."],
                "target_or_probe_binaries_included": False}
    (staging / "source-provenance.json").write_bytes(canonical_json(metadata))
    links = {"workspace/" + name: target for name, target in source_manifest["symlinks"].items()}
    output.parent.mkdir(parents=True, exist_ok=True)
    deterministic_zip(staging, output, source_symlinks=links)
    return {"schema": 1, "sha256": file_hash(output), "bytes": output.stat().st_size,
            "crate_archive_count": len(archives), "recipe_file_count": len(recipe_files),
            "source_manifest_sha256": file_hash(staging / "source-provenance.json"),
            "logical_vendor_keys_preserved": True, "opaque_provider_payloads_included": False,
            "input_audits": audits, "external_inputs": metadata["external_inputs"]}
