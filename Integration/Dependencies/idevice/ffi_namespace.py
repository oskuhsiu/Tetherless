"""Exact Apple-only export namespace; never change Rust function bodies or names.

The pristine registry/workspace inputs remain authenticated independently. This
adapter owns a separately recorded source postimage and public-header postimage.
It is not a parser, ABI shim, symbol alias, or a declaration of new capabilities.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from apply_patch import VerificationError, canonical_json, safe_path, sha256

HERE = Path(__file__).resolve().parent
CONTRACT_PATH = "namespace/contract.json"
EXPORT = re.compile(r'#\[unsafe\(no_mangle\)\]((?:\s*#\[[^\n]+\])?\s*)pub(?: unsafe)? extern "C" fn (\w+)')
# Preserve comments and quoted literals verbatim. This handles the frozen C
# headers/shim, not general C preprocessing or arbitrary untrusted programs.
C_TOKEN = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_][A-Za-z_0-9]*', re.S)


def load_contract(root: Path = HERE, expected_sha256: str | None = None) -> dict:
    data = safe_path(root, CONTRACT_PATH).read_bytes()
    if expected_sha256 is not None and sha256(data) != expected_sha256:
        raise VerificationError("FFI namespace contract identity differs")
    value = json.loads(data)
    if value.get("schema") != 1 or value.get("prefix") != "tetherless_native_" or value.get("preserved_prefix") != "tetherless_":
        raise VerificationError("unsupported FFI namespace contract")
    return value


def rename_c_identifiers(data: bytes, names: dict[str, str]) -> bytes:
    text = data.decode("utf-8")
    return C_TOKEN.sub(lambda m: names.get(m[0], m[0]), text).encode("utf-8")


def source_postimage(data: bytes, row: dict) -> bytes:
    if sha256(data) != row["before_sha256"]:
        raise VerificationError("FFI namespace source preimage differs")
    if "exports" in row:
        names = row["exports"]
        text = data.decode("utf-8")
        matches = list(EXPORT.finditer(text))
        selected = [m[2] for m in matches if not m[2].startswith("tetherless_")]
        if (text.count("#[unsafe(no_mangle)]") != len(matches)
                or len(selected) != len(set(selected)) or set(selected) != set(names)
                or any(new != "tetherless_native_" + old for old, new in names.items())):
            raise VerificationError("FFI namespace export inventory differs")
        def replacement(match):
            if match[2] not in names:
                return match[0]
            return '#[unsafe(export_name = "' + names[match[2]] + '")]' + match[0][len("#[unsafe(no_mangle)]"):]
        result = EXPORT.sub(replacement, text).encode("utf-8")
        # Explicit inverse establishes that all function bodies, internal Rust
        # names, cfg attributes, argument/return types and data layouts survived.
        inverse = result
        for new in names.values():
            inverse = inverse.replace(('#[unsafe(export_name = "' + new + '")]').encode(), b"#[unsafe(no_mangle)]")
        if inverse != data:
            raise VerificationError("FFI namespace modified content outside export attributes")
    else:
        names = row["c_identifiers"]
        if set(names) != {"plist_access_path", "plist_access_pathv", "plist_access_path_shim"}:
            raise VerificationError("FFI namespace C shim inventory differs")
        result = rename_c_identifiers(data, names)
        if rename_c_identifiers(result, {new: old for old, new in names.items()}) != data:
            raise VerificationError("FFI namespace changed C shim behavior")
    if sha256(result) != row["after_sha256"]:
        raise VerificationError("FFI namespace source postimage differs")
    return result


def namespace_workspace(files: dict[str, bytes], root: Path, expected: str) -> dict[str, bytes]:
    contract = load_contract(root, expected)
    result = dict(files)
    for name, row in contract["workspace"].items():
        result[name] = source_postimage(files[name], row)
    preserved = contract.get("preserved_workspace_exports", {})
    for name, row in preserved.items():
        if sha256(files[name]) != row["sha256"]:
            raise VerificationError("preserved pairing export source differs")
    # No no_mangle function is silently omitted when a source profile changes.
    for name, data in result.items():
        if name.startswith("ffi/src/") and name.endswith(".rs"):
            text = data.decode()
            found = [m[2] for m in EXPORT.finditer(text)]
            renamed = re.findall(r'#\[unsafe\(export_name = "(\w+)"\)\]', text)
            expected_names = list(contract["workspace"].get(name, {}).get("exports", {}).values())
            if (text.count("no_mangle") != len(found)
                    or text.count("export_name") != len(renamed)
                    or sorted(found) != sorted(preserved.get(name, {}).get("exports", []))
                    or sorted(renamed) != sorted(expected_names)):
                raise VerificationError("unregistered unnamespaced workspace export")
    return result


def namespace_vendor(destination: Path, originals: dict, crates: dict, contract: dict) -> dict:
    crate = "plist_ffi-0.1.6"
    if crates.get(crate) != contract["plist_crate_sha256"]:
        raise VerificationError("FFI namespace requires the exact plist_ffi crate archive")
    postimages = {}
    for name, row in contract["vendor"].items():
        if originals.get(name) != row["before_sha256"]:
            raise VerificationError("FFI namespace vendor inventory preimage differs")
        postimages[name] = source_postimage(safe_path(destination, name).read_bytes(), row)
    checksum_name = crate + "/.cargo-checksum.json"
    checksum_data = safe_path(destination, checksum_name).read_bytes()
    if originals.get(checksum_name) != sha256(checksum_data):
        raise VerificationError("FFI namespace vendor checksum preimage differs")
    checksum = json.loads(checksum_data)
    if checksum["package"] != contract["plist_crate_sha256"]:
        raise VerificationError("FFI namespace original archive identity differs")
    for name, data in postimages.items():
        relative = name.removeprefix(crate + "/")
        if checksum["files"].get(relative) != contract["vendor"][name]["before_sha256"]:
            raise VerificationError("FFI namespace vendor file checksum differs")
        checksum["files"][relative] = sha256(data)
    postimages[checksum_name] = canonical_json(checksum)
    # All inputs are checked before the owned derived files are changed.
    for name, data in postimages.items():
        safe_path(destination, name).write_bytes(data)
    return {name: {"before_sha256": originals[name], "after_sha256": sha256(data)}
            for name, data in postimages.items()}


def public_header(data: bytes, contract: dict) -> bytes:
    """Namespace old appended plist declarations, preserving every signature."""
    names = contract["header_identifiers"]
    result = rename_c_identifiers(data, names)
    # Compare paired lexical spans rather than reversing names globally:
    # cbindgen may already have emitted an identifier's namespaced spelling.
    old_tokens = list(C_TOKEN.finditer(data.decode()))
    new_tokens = list(C_TOKEN.finditer(result.decode()))
    if (len(old_tokens) != len(new_tokens)
            or any(new[0] != names.get(old[0], old[0]) for old, new in zip(old_tokens, new_tokens))
            or C_TOKEN.sub("", data.decode()) != C_TOKEN.sub("", result.decode())):
        raise VerificationError("FFI public header changed outside identifier tokens")
    identifiers = {m[0] for m in C_TOKEN.finditer(result.decode())}
    if identifiers & set(names):
        raise VerificationError("FFI public header contains unnamespaced identifiers")
    if identifiers & {"PLIST_OPT_COERCE", "TETHERLESS_NATIVE_PLIST_OPT_COERCE"}:
        raise VerificationError("FFI public header must not invent COERCE support")
    return result
