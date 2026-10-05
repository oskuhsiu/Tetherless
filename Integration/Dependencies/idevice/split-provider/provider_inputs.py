#!/usr/bin/env python3
"""Prepare opt-in, hash-locked OpenSSL inputs; never run a compiler or inspect binaries.

The caller owns an isolated build directory and selected toolchain. This module
does not activate an app route, modify ambient configuration, or fetch inputs.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile

HERE = Path(__file__).resolve().parent
TARGETS = ("aarch64-apple-darwin", "aarch64-apple-ios", "aarch64-apple-ios-sim")
COMMIT = "fdc9231384f37f053dffe058fd6dfc6c5072dae5"
CONTRACT_SHA256 = "20ee6e1e873cc8f6f83bf42b97e8760569a70ff95818d570a45e3966d63a9935"


class InputError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def regular_path(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    if (not parts or relative.startswith("/") or "\\" in relative
            or any(p in (".", "..") for p in parts)
            or str(PurePosixPath(relative)) != relative):
        raise InputError("unsafe input path")
    path = root
    for part in parts:
        path /= part
        if path.is_symlink():
            raise InputError("source symlink refused")
    if not stat.S_ISREG(path.stat().st_mode):
        raise InputError("input must be a regular file")
    return path


def load_contract() -> dict:
    data = (HERE / "target-inputs.json").read_bytes()
    if digest(data) != CONTRACT_SHA256:
        raise InputError("provider contract hash mismatch")
    return json.loads(data)


def verify_inputs(source: Path, contract: dict | None = None) -> dict:
    """Verify only the explicit permitted inventory, not signing/privacy resources."""
    contract = load_contract() if contract is None else contract
    # The injected contract parameter is for controlled tests only. Production
    # callers use the review-locked file through prepare_inputs.
    if (contract["commit"] != COMMIT or contract["enabled"] is not False
            or contract["product_activation"] is not False):
        raise InputError("unexpected provider contract")
    entries = contract["entries"]
    if len(entries) > 443 or sum(e["size"] for e in entries) > 40_506_667:
        raise InputError("provider inventory exceeds reviewed bounds")
    verified = {}
    for entry in entries:
        name = entry["path"]
        if name in verified or entry["mode"] not in ("100644", "100755"):
            raise InputError("duplicate or unsupported input")
        if not 0 <= entry["size"] <= 16 * 1024 * 1024:
            raise InputError("input size exceeds bound")
        path = regular_path(source, name)
        info = path.stat()
        if (info.st_size != entry["size"]
                or bool(info.st_mode & 0o111) != (entry["mode"] == "100755")):
            raise InputError("input size or executable mode mismatch")
        with path.open("rb") as stream:
            data = stream.read(entry["size"] + 1)
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if len(data) != entry["size"] or digest(data) != entry["sha256"] or blob != entry["git_blob"]:
            raise InputError("input byte identity mismatch")
        verified[name] = entry
    # Final Apple C/Swift compilation sees these original framework directories
    # through -F. Pin their complete build-relevant inventory too, so umbrella
    # discovery cannot pick up an unlisted header/module. Do not enumerate or
    # interpret the separate signing/privacy resources.
    for selected in contract["targets"].values():
        directories = [selected["header_root"]]
        if "framework_root" in selected:
            directories.append(selected["framework_root"] + "/Modules")
        for name in directories:
            prefix = name + "/"
            expected = {p[len(prefix):] for p in verified if p.startswith(prefix)}
            directory = source / name
            if (directory.is_symlink() or not expected or any("/" in p for p in expected)
                    or {p.name for p in directory.iterdir()} != expected):
                raise InputError("source header or module inventory changed")
    return verified


def _headers(verified: dict, selected: dict) -> list[dict]:
    prefix = selected["header_root"] + "/"
    headers = [entry for name, entry in verified.items() if name.startswith(prefix)]
    if len(headers) != selected["header_count"]:
        raise InputError("selected header tree is incomplete")
    if any("/" in e["path"][len(prefix):] for e in headers):
        raise InputError("unexpected nested header")
    return headers


def _copy_verified(source: Path, entry: dict, output: Path) -> None:
    with regular_path(source, entry["path"]).open("rb") as stream:
        data = stream.read(entry["size"] + 1)
    if len(data) != entry["size"] or digest(data) != entry["sha256"]:
        raise InputError("input changed during staging")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    output.chmod(0o755 if entry["mode"] == "100755" else 0o644)


def prepare_inputs(source: Path, destination: Path, target: str) -> dict:
    """Create a fresh owned include/library view and return its input receipt.

    Apple framework payloads stay in the verified source root for the final
    consumer linker. They are never copied into the Rust archive's library dir.
    """
    if target not in TARGETS:
        raise InputError("unsupported provider target")
    source = source.resolve(strict=True)
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise InputError("provider output already exists")
    destination = destination.resolve(strict=False)
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise InputError("provider source and output roots overlap")
    contract = load_contract()
    verified = verify_inputs(source, contract)
    selected = contract["targets"][target]
    headers = _headers(verified, selected)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = destination.parent.resolve(strict=True) / destination.name
    if destination.exists() or destination.is_symlink():
        raise InputError("provider output already exists")
    temporary = Path(tempfile.mkdtemp(prefix=".openssl-inputs-", dir=destination.parent))
    try:
        upper = temporary / "include/OpenSSL"
        upper.mkdir(parents=True)
        for entry in headers:
            _copy_verified(source, entry, upper / PurePosixPath(entry["path"]).name)
        lower = temporary / "include/openssl"
        if lower.exists():
            if not lower.samefile(upper):
                raise InputError("include spelling resolves to unexpected directory")
        else:
            # A physical second view works on case-sensitive volumes without
            # allowing arbitrary source/output symlinks.
            shutil.copytree(upper, lower)
        for view in (upper, lower):
            for entry in headers:
                if digest((view / PurePosixPath(entry["path"]).name).read_bytes()) != entry["sha256"]:
                    raise InputError("include view identity mismatch")
        library = temporary / "lib"
        library.mkdir()
        for name in selected["native_library_input_paths"]:
            _copy_verified(source, verified[name], library / PurePosixPath(name).name)
        _copy_verified(source, verified["LICENSE.txt"], temporary / "LICENSE.txt")
        receipt = {
            "schema": 1, "target": target, "kind": selected["kind"],
            "contract_sha256": CONTRACT_SHA256, "source_commit": COMMIT,
            "source_root": str(source), "view_root": str(destination),
            "verified_input_count": len(verified),
            "verified_input_bytes": sum(e["size"] for e in verified.values()),
            "header_count": len(headers), "include_spellings": ["OpenSSL", "openssl"],
            "native_libraries": list(selected["native_library_input_paths"]),
            "environment": {target.upper().replace("-", "_") + "_" + key: value
                            for key, value in selected["environment_values"].items()},
            "native_execution": False, "product_activation": False,
        }
        prefix = target.upper().replace("-", "_") + "_"
        receipt["environment"][prefix + "OPENSSL_INCLUDE_DIR"] = str(destination / "include")
        receipt["environment"][prefix + "OPENSSL_LIB_DIR"] = str(destination / "lib")
        if "framework_root" in selected:
            framework = source / selected["framework_root"]
            receipt["final_link_arguments"] = ["-F", str(framework.parent), "-framework", "OpenSSL"]
            receipt["framework_binary_sha256"] = verified[selected["framework_binary"]]["sha256"]
        else:
            receipt["final_link_arguments"] = []
        (temporary / "provider-input-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        os.rename(temporary, destination)
        return receipt
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def audit_inputs(receipt: dict) -> dict:
    """Recheck the owned view and source identities before/after native work."""
    contract = load_contract()
    target = receipt["target"]
    if (target not in TARGETS or receipt["contract_sha256"] != CONTRACT_SHA256
            or receipt["native_execution"] is not False or receipt["product_activation"] is not False):
        raise InputError("unexpected provider receipt")
    selected = contract["targets"][target]
    root = Path(receipt["view_root"])
    source = Path(receipt["source_root"])
    if not root.is_absolute() or not source.is_absolute():
        raise InputError("provider paths must be absolute")
    if root.is_symlink() or source.is_symlink() or root.resolve(strict=True) != root or source.resolve(strict=True) != source:
        raise InputError("provider root identity changed")
    if root.is_relative_to(source) or source.is_relative_to(root):
        raise InputError("provider source and output roots overlap")
    verified = verify_inputs(source, contract)
    if (receipt["schema"] != 1 or receipt["source_commit"] != COMMIT
            or receipt["verified_input_count"] != len(verified)
            or receipt["verified_input_bytes"] != sum(e["size"] for e in verified.values())
            or receipt["header_count"] != selected["header_count"]
            or receipt["include_spellings"] != ["OpenSSL", "openssl"]):
        raise InputError("provider receipt metadata changed")
    expected_link = []
    if "framework_root" in selected:
        expected_link = ["-F", str((source / selected["framework_root"]).parent), "-framework", "OpenSSL"]
        if receipt.get("framework_binary_sha256") != verified[selected["framework_binary"]]["sha256"]:
            raise InputError("provider framework receipt changed")
    if (receipt["kind"] != selected["kind"] or receipt["native_libraries"] != selected["native_library_input_paths"]
            or receipt["final_link_arguments"] != expected_link):
        raise InputError("provider link contract changed")
    prefix = target.upper().replace("-", "_") + "_"
    expected_env = {prefix + key: value for key, value in selected["environment_values"].items()}
    expected_env.update({prefix + "OPENSSL_INCLUDE_DIR": str(root / "include"),
                         prefix + "OPENSSL_LIB_DIR": str(root / "lib")})
    if receipt["environment"] != expected_env:
        raise InputError("provider environment changed")
    headers = _headers(verified, selected)
    names = {PurePosixPath(entry["path"]).name for entry in headers}
    include = root / "include"
    if include.is_symlink():
        raise InputError("provider include root changed")
    # One physical entry may satisfy both spellings on a case-insensitive volume.
    # Every enumerated entry must be one of the exact owned directory spellings;
    # an extra include/stdint.h would otherwise shadow the SDK header.
    for path in include.iterdir():
        if path.name not in ("OpenSSL", "openssl") or path.is_symlink() or not path.is_dir():
            raise InputError("provider include root inventory changed")
    for spelling in ("OpenSSL", "openssl"):
        view = root / "include" / spelling
        if view.is_symlink() or {p.name for p in view.iterdir()} != names:
            raise InputError("provider include inventory changed")
        for entry in headers:
            name = PurePosixPath(entry["path"]).name
            path = regular_path(root, "include/" + spelling + "/" + name)
            with path.open("rb") as stream:
                data = stream.read(entry["size"] + 1)
            if len(data) != entry["size"] or digest(data) != entry["sha256"]:
                raise InputError("provider header changed")
    library = root / "lib"
    expected_libs = selected["native_library_input_paths"]
    if library.is_symlink() or {p.name for p in library.iterdir()} != {PurePosixPath(n).name for n in expected_libs}:
        raise InputError("provider native library inventory changed")
    for name in expected_libs:
        entry = verified[name]
        path = regular_path(root, "lib/" + PurePosixPath(name).name)
        with path.open("rb") as stream:
            data = stream.read(entry["size"] + 1)
        if len(data) != entry["size"] or digest(data) != entry["sha256"]:
            raise InputError("provider library changed")
    return {"unchanged": True, "target": target, "contract_sha256": CONTRACT_SHA256,
            "verified_input_count": len(verified), "header_count": len(headers)}


def build_environment(base: dict[str, str], receipt: dict) -> dict[str, str]:
    """Extend native_environment's verified base, never os.environ.

    Keep only its explicit reproducibility/toolchain keys and the owned cbindgen
    workspace pointer. The runner sets selected SDK/CC/remap flags afterwards.
    """
    audit_inputs(receipt)
    allowed = {"PATH", "HOME", "TMPDIR", "CARGO_HOME", "CARGO_TARGET_DIR", "CARGO_NET_OFFLINE",
               "CARGO_INCREMENTAL", "RUSTUP_AUTO_INSTALL", "RUSTC", "CMAKE", "DEVELOPER_DIR",
               "LANG", "LC_ALL", "TZ", "SOURCE_DATE_EPOCH", "ZERO_AR_DATE",
               "TETHERLESS_CBINDGEN_WORKSPACE_MANIFEST"}
    result = {key: value for key, value in base.items() if key in allowed}
    result.update(receipt["environment"])
    return result


def check_build_script_output(output: bytes, receipt: dict) -> dict:
    """Check the selected openssl-sys output file, not a merged Cargo log."""
    audit_inputs(receipt)
    if len(output) > 1024 * 1024:
        raise InputError("openssl-sys output exceeds receipt bound")
    directives = []
    for line in output.decode("utf-8").splitlines():
        if line.startswith("cargo::"):
            directives.append(line[len("cargo::"):])
        elif line.startswith("cargo:"):
            directives.append(line[len("cargo:"):])
    for directive in directives:
        key = directive.split("=", 1)[0]
        if key.startswith("rustc-link-arg") or key in ("rustc-flags", "rustc-env", "metadata"):
            raise InputError("unexpected additional compiler/linker directive")
    def values(key: str) -> list[str]:
        return [line[len(key + "="):] for line in directives if line.startswith(key + "=")]
    expected = ["static=ssl", "static=crypto"] if receipt["target"] == "aarch64-apple-darwin" else []
    if values("rustc-link-lib") != expected:
        raise InputError("unexpected OpenSSL link libraries")
    if values("rustc-link-search") != ["native=" + str(Path(receipt["view_root"]) / "lib")]:
        raise InputError("unexpected OpenSSL library search")
    if values("include") != [str(Path(receipt["view_root"]) / "include")]:
        raise InputError("unexpected OpenSSL header selection")
    if values("version_number") != ["30600020"]:
        raise InputError("unexpected OpenSSL header version")
    if (any(values(key) for key in ("boringssl", "awslc", "awslc_fips", "libressl_version_number"))
            or any(value in ("boringssl", "awslc", "awslc_fips", "libressl") for value in values("rustc-cfg"))):
        raise InputError("unexpected OpenSSL provider branch")
    return {"output_sha256": digest(output), "target": receipt["target"],
            "link_libraries": expected, "header_version_hex": "30600020",
            "claim": "build-script header/link directives only; final provider/runtime proof remains pending"}
