"""Authenticate the exact existing C provider for mixed-provider link probes.

Only archive paths/opaque bytes/XCFramework metadata and ordinary nm text are
handled. No Mach-O parser, parser changes, device calls or binary execution.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import plistlib
import shutil
import stat
import zipfile

from apply_patch import VerificationError, canonical_json, safe_path, sha256
from build_xcframework import file_hash

ARCHIVE_SHA256 = "7ccbdd56b074807461fc43d2e32ba92f20df2501a6c14cf9f64a917e7f3fe6e7"
ARCHIVE_URL = "https://github.com/SideStore/libimobiledevice-xcframework/releases/download/1.4.0-ss-0f88f7b/libimobiledevice.xcframework.zip"
MAX_ARCHIVE = 8 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
MAX_FILES = 2048


def authenticated_files(archive: Path) -> dict[str, bytes]:
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size > MAX_ARCHIVE:
        raise VerificationError("mixed-provider archive must be a bounded regular file")
    if file_hash(archive) != ARCHIVE_SHA256:
        raise VerificationError("mixed-provider archive is not the pinned consumer release")
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if len(entries) > MAX_FILES or sum(row.file_size for row in entries) > MAX_EXPANDED:
            raise VerificationError("mixed-provider extraction budget exceeded")
        names = set()
        for row in entries:
            name = row.filename.rstrip("/")
            pure = PurePosixPath(name)
            mode = row.external_attr >> 16
            if (name in names or not pure.parts or pure.is_absolute() or pure.as_posix() != name
                    or any(part in (".", "..") for part in pure.parts) or "\\" in name
                    or pure.parts[0] != "libimobiledevice.xcframework"
                    or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR))):
                raise VerificationError("mixed-provider archive has an unsafe entry")
            names.add(name)
        files = {}
        for row in entries:
            if row.is_dir():
                continue
            files[row.filename] = source.read(row)
    return files


def prepare(archive: Path, output: Path) -> dict:
    files = authenticated_files(archive)
    if output.exists() or output.is_symlink():
        raise VerificationError("mixed-provider output must be fresh")
    output.mkdir(parents=True)
    for name, data in files.items():
        path = safe_path(output, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    shutil.copyfile(archive, output / "authenticated-provider.zip")
    receipt = {"schema": 1, "archive_sha256": ARCHIVE_SHA256, "archive_url": ARCHIVE_URL,
               "files": {name: sha256(data) for name, data in files.items()},
               "binary_format_inspected": False, "binaries_executed": False}
    (output / "mixed-provider-inputs.json").write_bytes(canonical_json(receipt))
    return receipt


def verify(root: Path, target: dict) -> dict:
    if root.is_symlink() or not root.is_dir():
        raise VerificationError("mixed-provider root is not a regular directory")
    with safe_path(root, "mixed-provider-inputs.json").open("rb") as stream:
        receipt_data = stream.read(4 * 1024 * 1024 + 1)
    if len(receipt_data) > 4 * 1024 * 1024:
        raise VerificationError("mixed-provider receipt exceeds its byte bound")
    receipt = json.loads(receipt_data)
    if (not isinstance(receipt, dict) or receipt.get("schema") != 1 or receipt.get("archive_sha256") != ARCHIVE_SHA256
            or receipt.get("binary_format_inspected") is not False or receipt.get("binaries_executed") is not False):
        raise VerificationError("mixed-provider receipt identity differs")
    original = authenticated_files(safe_path(root, "authenticated-provider.zip"))
    expected_files = {name: sha256(data) for name, data in original.items()}
    if receipt["files"] != expected_files:
        raise VerificationError("mixed-provider inventory differs from authenticated archive")
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise VerificationError("mixed-provider tree contains a symlink")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != set(expected_files) | {"authenticated-provider.zip", "mixed-provider-inputs.json"}:
        raise VerificationError("mixed-provider tree has missing or extra files")
    for name, expected in expected_files.items():
        if file_hash(safe_path(root, name)) != expected:
            raise VerificationError("mixed-provider authenticated bytes changed")
    xc = root / "libimobiledevice.xcframework"
    info = plistlib.loads(safe_path(xc, "Info.plist").read_bytes())
    variant = "simulator" if target["sdk"] == "iphonesimulator" else ""
    rows = [row for row in info["AvailableLibraries"] if row.get("SupportedPlatform") == "ios"
            and row.get("SupportedPlatformVariant", "") == variant and "arm64" in row["SupportedArchitectures"]]
    if len(rows) != 1:
        raise VerificationError("expected one matching arm64 C-provider slice")
    row = rows[0]
    base = safe_path(xc, row["LibraryIdentifier"])
    library = safe_path(base, row["LibraryPath"])
    headers = safe_path(base, row["HeadersPath"])
    selected = (library, headers / "plist/plist.h", headers / "libimobiledevice/module.modulemap")
    if any(path.relative_to(root).as_posix() not in receipt["files"] for path in selected):
        raise VerificationError("mixed-provider slice/header/module absent from authenticated inventory")
    return {"archive_sha256": ARCHIVE_SHA256, "receipt_sha256": file_hash(root / "mixed-provider-inputs.json"),
            "library": str(library), "library_sha256": file_hash(library), "headers": str(headers),
            "header_sha256": file_hash(selected[1]), "module_map_sha256": file_hash(selected[2]),
            "target": target["rust"], "binary_format_inspected": False}


def exported_symbols(text: str) -> set[str]:
    return {line.strip() for line in text.splitlines() if line.strip() and not line.rstrip().endswith(":")}


def audit(root: Path, target: dict, expected: dict, verifier=verify) -> dict:
    try:
        return {"original_inputs_unchanged": verifier(root, target) == expected}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, zipfile.BadZipFile) as error:
        return {"original_inputs_unchanged": False, "error_kind": type(error).__name__}


def check_symbols(text: str, contract: dict, target: str) -> dict:
    symbols = exported_symbols(text)
    expected = {"_" + name for name in contract["expected_target_exports"][target]["after"]}
    observed = {name for name in symbols if name.startswith("_tetherless_native_")}
    old = {"_" + name for role in ("workspace", "vendor") for row in contract[role].values()
           for name in row.get("exports", row.get("c_identifiers", {}))}
    if observed != expected or symbols & old:
        raise VerificationError("native export namespace is incomplete or retains old global aliases")
    return {"schema": 1, "target": target, "namespaced_export_count": len(expected),
            "old_exports_absent": True, "expected_exports_present": True,
            "nm_stdout_sha256": sha256(text.encode())}


def check_mixed_symbols(rust: str, c_provider: str) -> dict:
    left, right = exported_symbols(rust), exported_symbols(c_provider)
    required = {"_plist_new_dict", "_plist_free", "_plist_array_set_item", "_afc_client_free",
                "_lockdownd_client_free", "_idevice_free"}
    if left & right or not required <= right:
        raise VerificationError("mixed native providers overlap or required C exports are missing")
    return {"schema": 1, "provider_export_sets_disjoint": True,
            "required_c_exports_present": True, "c_nm_stdout_sha256": sha256(c_provider.encode())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        prepare(args.archive, args.output)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, str(error) + "\n")
