"""Check and retain the two-result cbindgen ABI adaptation, without rewriting output."""
from __future__ import annotations

from pathlib import Path
import re

from apply_patch import VerificationError, canonical_json, safe_path, sha256

MAX_HEADER_BYTES = 2 * 1024 * 1024
RESULTS = {
    "TetherlessPairingValidationResult": [
        ("Ok", 0), ("InvalidArgument", 1), ("Cancelled", 2), ("TimedOut", 3),
        ("Protocol", 4), ("Io", 5), ("Mismatch", 6), ("AlreadyUsed", 7), ("Budget", 8)],
    "TetherlessPairingHostResult": [
        ("Ok", 0), ("InvalidArgument", 1), ("Cancelled", 2), ("TimedOut", 3),
        ("Protocol", 4), ("Io", 5), ("AlreadyUsed", 7), ("Budget", 8)],
}
GENERATED = ("ffi/idevice.cbindgen-baseline.h", "ffi/idevice.cbindgen-scoped.h",
             "ffi/idevice.h", "cpp/include/idevice.h")
VALIDATION_DOC = "A fixed result code; no peer-provided text, challenge or record is returned."


def read_header(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise VerificationError("generated header is not a regular file")
    with path.open("rb") as stream:
        data = stream.read(MAX_HEADER_BYTES + 1)
    if len(data) > MAX_HEADER_BYTES:
        raise VerificationError("generated header exceeds retained byte limit")
    return data


def declarations() -> bytes:
    lines = ["/* Tetherless fixed-width pairing result declarations. */", "#include <stdint.h>"]
    for name, variants in RESULTS.items():
        lines.append("typedef uint32_t " + name + ";")
        prefix = name.removesuffix("Result")
        lines += [f"#define {prefix}{variant} ((uint32_t){value})" for variant, value in variants]
    lines.append("/* End Tetherless fixed-width pairing result declarations. */")
    return ("\n".join(lines) + "\n").encode()


def remove_generated_result(text: str, name: str, variants: list[tuple[str, int]]) -> str:
    # Only the measured C fixed-width enum form is accepted. Numeric values must
    # match the Rust-derived baseline before replacing its declaration in C.
    pattern = re.compile(r"(?m)^enum " + name + r" \{\n([^{}]*)\n\};\s*typedef uint32_t " + name + r";\n")
    found = list(pattern.finditer(text))
    if len(found) != 1:
        raise VerificationError("expected one baseline fixed-width result enum and alias")
    match = found[0]
    expected = [(name.removesuffix("Result") + label, str(value)) for label, value in variants]
    actual = []
    for line in match.group(1).splitlines():
        entry = re.fullmatch(r"\s*(\w+) = ([0-9]+),\s*", line)
        if entry is None:
            raise VerificationError("unexpected baseline result enumerator syntax")
        actual.append(entry.groups())
    if actual != expected:
        raise VerificationError("baseline result discriminants differ from the reviewed ABI")
    start = match.start()
    if name == "TetherlessPairingValidationResult":
        before = text[:start]
        doc = re.search(r"/\*\*\n((?:[^*]|\*(?!/))*)\*/\s*$", before)
        if doc is None:
            raise VerificationError("baseline validation result documentation is missing")
        content = " ".join(line.strip().removeprefix("*").strip() for line in doc.group(1).splitlines()).strip()
        if content != VALIDATION_DOC:
            raise VerificationError("baseline validation result documentation changed")
        start = doc.start()
    return text[:start] + text[match.end():]


def compare_generated(baseline: bytes, scoped: bytes, fragment: bytes) -> dict:
    if fragment != declarations():
        raise VerificationError("injected result declarations differ from reviewed scalar ABI")
    try:
        old, new = baseline.decode("utf-8"), scoped.decode("utf-8")
        injected = fragment.decode("utf-8")
    except UnicodeError as error:
        raise VerificationError("generated header is not UTF-8") from error
    for name, variants in RESULTS.items():
        old = remove_generated_result(old, name, variants)
        if re.search(r"\benum\s+" + name + r"\b", new):
            raise VerificationError("scoped header still has a colliding enum tag")
    if new.count(injected) != 1:
        raise VerificationError("expected one exact injected result declaration block")
    new = new.replace(injected, "", 1)
    # cbindgen separates emitted items with blank lines. Excluding an item may
    # remove its separator; every other nonempty line, including indentation,
    # documentation, includes and function declarations, must remain identical.
    old_lines = [line for line in old.splitlines() if line.strip()]
    new_lines = [line for line in new.splitlines() if line.strip()]
    if old_lines != new_lines:
        raise VerificationError("unrelated generated header content changed")
    return {"baseline_sha256": sha256(baseline), "scoped_sha256": sha256(scoped),
            "declarations_sha256": sha256(fragment), "unrelated_nonempty_lines_identical": True,
            "blank_item_separators_ignored": True, "result_discriminants": RESULTS,
            "native_import_or_link_established_by_this_check": False}


def verify_headers(source: Path, declaration_path: Path) -> dict:
    baseline, scoped, final, cpp = [read_header(safe_path(source, name)) for name in GENERATED]
    result = compare_generated(baseline, scoped, read_header(declaration_path))
    if final != scoped + b"\n\n\n" + read_header(safe_path(source, "ffi/plist.h")):
        raise VerificationError("final header does not preserve the original plist append contract")
    if final != cpp:
        raise VerificationError("copied C++ include header differs from the FFI header")
    return {"schema": 1, **result, "final_header_sha256": sha256(final), "cpp_header_identical": True}


def retain_headers(source: Path, evidence: Path) -> dict:
    """Keep bounded generated bytes, including on a failed Cargo/link command."""
    destination = evidence / "generated-headers"
    receipt_path = evidence / "generated-header-retention.json"
    if destination.is_symlink() or receipt_path.is_symlink():
        raise VerificationError("generated header evidence destination is a symlink")
    destination.mkdir(exist_ok=True)
    rows = {}
    for name in GENERATED:
        try:
            path = safe_path(source, name)
            if not path.exists() and not path.is_symlink():
                rows[name] = {"status": "missing"}
                continue
            data = read_header(path)
            output = safe_path(destination, name)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
            rows[name] = {"status": "retained", "bytes": len(data), "sha256": sha256(data)}
        except (OSError, VerificationError):
            rows[name] = {"status": "unreadable_or_outside_bound"}
    receipt = {"schema": 1, "per_file_byte_limit": MAX_HEADER_BYTES, "files": rows}
    receipt_path.write_bytes(canonical_json(receipt))
    return receipt
