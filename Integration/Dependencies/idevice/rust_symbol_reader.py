"""Resolve and bind the official pinned Rust host LLVM archive reader.

No installation, archive filtering, source transformation or native execution.
Only the rustc/llvm-nm tools are invoked by the caller's bounded supervisor.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

CONTRACT = {"rust_release": "1.98.1", "rust_host": "aarch64-apple-darwin",
            "llvm_version": "22.1.8", "component": "llvm-tools-preview",
            "rustup_component": "llvm-tools", "tool": "llvm-nm"}
FLAGS = ["--extern-only", "--defined-only", "--format=just-symbols", "--quiet"]
MAX_METADATA = 1024 * 1024


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _regular(path: Path) -> None:
    if (not path.is_absolute() or ".." in path.parts or not path.is_file()
            or any(p.is_symlink() for p in (path, *path.parents))):
        raise ValueError("symbol-reader input must be a regular canonical absolute file")


def _metadata(path: Path) -> bytes:
    _regular(path)
    with path.open("rb") as stream:
        raw = stream.read(MAX_METADATA + 1)
    if not raw or len(raw) > MAX_METADATA:
        raise ValueError("symbol-reader component metadata is empty or oversized")
    return raw


def validate_receipt(value: dict, contract: dict = CONTRACT) -> None:
    """Validate retained identity text; never trust/execute a producer-local path."""
    if contract != CONTRACT or not isinstance(value, dict) or value.get("schema") != 1 or value.get("contract") != CONTRACT:
        raise ValueError("symbol-reader contract differs from the pinned Rust component")
    if not isinstance(value.get("sysroot"), str):
        raise ValueError("symbol-reader sysroot is missing")
    root = Path(value["sysroot"])
    if not root.is_absolute() or ".." in root.parts:
        raise ValueError("symbol-reader sysroot is not canonical absolute text")
    paths = {"rustc": root / "bin/rustc",
             "llvm_nm": root / "lib/rustlib" / CONTRACT["rust_host"] / "bin/llvm-nm",
             "component_manifest": root / "lib/rustlib" / ("manifest-" + CONTRACT["component"] + "-" + CONTRACT["rust_host"]),
             "installed_components": root / "lib/rustlib/components"}
    for key, expected in paths.items():
        row = value.get(key, {})
        if (not isinstance(row, dict) or row.get("path") != str(expected)
                or not isinstance(row.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])):
            raise ValueError("symbol-reader path/hash identity differs: " + key)
    rust = value["rustc"].get("version", "")
    if (not isinstance(rust, str) or not rust.startswith("rustc 1.98.1 (")
            or rust.splitlines().count("release: 1.98.1") != 1
            or rust.splitlines().count("host: " + CONTRACT["rust_host"]) != 1
            or rust.splitlines().count("LLVM version: " + CONTRACT["llvm_version"]) != 1):
        raise ValueError("symbol-reader Rust compiler release/host/LLVM differs")
    version = value["llvm_nm"].get("version", "")
    # Retain all output; accept LLVM's actual version line, not a prefix such as
    # 22.1.80 or an Apple reader that happens to mention another LLVM version.
    # Rust 1.98.1 bootstrap llvm.rs adds the exact -rust-1.98.1-stable suffix
    # unless the official build config clears it. No other suffix is admitted.
    if not isinstance(version, str):
        raise ValueError("symbol-reader LLVM version is missing")
    versions = re.findall(r"^\s*LLVM version ([0-9]+\.[0-9]+\.[0-9]+)(?:-rust-1\.98\.1-stable)?\s*$", version, re.M)
    if versions != [CONTRACT["llvm_version"]] or "llvm-nm" not in version.splitlines()[0]:
        raise ValueError("symbol-reader LLVM version differs from the Rust compiler")


def audit_local(value: dict) -> None:
    validate_receipt(value)
    for key in ("rustc", "llvm_nm", "component_manifest", "installed_components"):
        row = value[key]
        path = Path(row["path"])
        _regular(path)
        if digest(path) != row["sha256"]:
            raise ValueError("symbol-reader input changed after observation: " + key)


def observe(rustc: str, capture) -> dict:
    """capture(argv, log_name) must require zero exit, complete output and join."""
    compiler = Path(rustc)
    _regular(compiler)
    compiler_sha = digest(compiler)
    version = capture([str(compiler), "--version", "--verbose"], "toolchain-symbol-rustc.txt").strip()
    sysroot = Path(capture([str(compiler), "--print", "sysroot"], "toolchain-symbol-sysroot.txt").strip())
    if compiler != sysroot / "bin/rustc":
        raise ValueError("symbol reader must be inside the selected compiler's sysroot")
    manifest = sysroot / "lib/rustlib" / ("manifest-" + CONTRACT["component"] + "-" + CONTRACT["rust_host"])
    components = sysroot / "lib/rustlib/components"
    relative = "lib/rustlib/" + CONTRACT["rust_host"] + "/bin/llvm-nm"
    manifest_data, components_data = _metadata(manifest), _metadata(components)
    if (manifest_data.decode().splitlines().count("file:" + relative) != 1
            or components_data.decode().splitlines().count(CONTRACT["component"] + "-" + CONTRACT["rust_host"]) != 1):
        raise ValueError("official host llvm-tools component does not own the selected reader")
    nm = sysroot / relative
    _regular(nm)
    nm_sha = digest(nm)
    nm_version = capture([str(nm), "--version"], "toolchain-llvm-nm.txt").strip()
    result = {"schema": 1, "contract": dict(CONTRACT), "sysroot": str(sysroot),
              "rustc": {"path": str(compiler), "sha256": compiler_sha, "version": version},
              "llvm_nm": {"path": str(nm), "sha256": nm_sha, "version": nm_version},
              "component_manifest": {"path": str(manifest), "sha256": hashlib.sha256(manifest_data).hexdigest()},
              "installed_components": {"path": str(components), "sha256": hashlib.sha256(components_data).hexdigest()}}
    audit_local(result)
    return result


def scan_command(value: dict, archive: str) -> list[str]:
    validate_receipt(value)
    if not Path(archive).is_absolute():
        raise ValueError("symbol-reader archive path must be absolute")
    return [value["llvm_nm"]["path"], *FLAGS, archive]
