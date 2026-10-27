#!/usr/bin/env python3
"""Bounded host-only crypto regression tests for already-prepared C sources.

Never runs a device binary, downloads dependencies, or patches upstream code.
Use namespace.py first. Every compiler, linker, and executable invocation uses
the existing helper-only process-group supervisor and retains log receipts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "probes" / "host"
IDEVICE = HERE.parent / "idevice"
sys.path.insert(0, str(IDEVICE))
from bounded_process import capture_helper_command  # noqa: E402
from apply_patch import VerificationError  # noqa: E402

COMPILE_TIMEOUT_SECONDS = 120
RUN_TIMEOUT_SECONDS = 30
MAX_LOG_BYTES = 4 * 1024 * 1024
TAIL_BYTES = 64 * 1024
ED_FILES = ("sha512.c", "fe.c", "ge.c", "sc.c", "keypair.c", "sign.c",
            "verify.c", "add_scalar.c")
FIXTURE_FILES = ("main.c", "ed_sha512.c", "glue_sha512.c", "ed25519.c")
PASS_LINES = (
    "PASS Ed25519 namespaced SHA512:",
    "PASS glue public SHA512:",
    "PASS Ed25519 RFC8032 TEST 1:",
    "PASS Ed25519 add_scalar:",
    "PASS all host crypto fixtures",
)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def compiler_path(value: str | None) -> Path:
    selected = value or shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not selected:
        raise VerificationError("no installed host C compiler was found")
    path = Path(selected)
    if value and not path.is_absolute():
        raise VerificationError("--cc must be an absolute path to an installed host compiler")
    path = path.resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise VerificationError("host compiler is not an executable regular file")
    return path


def parse_success(text: str) -> dict:
    for expected in PASS_LINES:
        if sum(line.startswith(expected) for line in text.splitlines()) != 1:
            raise VerificationError(f"missing or duplicated host test result: {expected}")
    match = re.search(r"^CONTEXT_SIZES ed=(\d+) glue=(\d+) glue_num_qwords_offset=(\d+) glue_num_qwords_size=(\d+)$",
                      text, re.MULTILINE)
    if match is None:
        raise VerificationError("missing real context layout evidence")
    ed, glue, offset, member = map(int, match.groups())
    if not (0 < ed < glue and offset == ed and 0 < member <= glue - offset):
        raise VerificationError("unexpected context layout evidence")
    return {"ed_bytes": ed, "glue_bytes": glue,
            "glue_num_qwords_offset": offset, "glue_num_qwords_bytes": member}


def ordinary_probe_failure(output: Path, name: str) -> bool:
    """Cancellation, bounds, and incomplete cleanup must not become a skip."""
    receipt = json.loads((output / "logs" / (name + ".log.status.json")).read_text())
    cleanup = receipt.get("cleanup") or {}
    return (receipt.get("outcome") == "nonzero_exit" and
            cleanup.get("direct_child_reaped") is True and cleanup.get("group_empty") is True)


def run_host_tests(source: Path, output: Path, cc: str | None = None,
                   sdk: Path | None = None) -> dict:
    source = source.resolve(strict=True)
    if not source.is_dir():
        raise VerificationError("prepared source must be a directory containing root and glue")
    sdk_args = []
    if sdk is not None:
        sdk = Path(sdk)
        if not sdk.is_absolute():
            raise VerificationError("--sdk must be an absolute existing SDK directory")
        sdk = sdk.resolve(strict=True)
        if not sdk.is_dir():
            raise VerificationError("--sdk must be an absolute existing SDK directory")
        sdk_args = ["-isysroot", str(sdk)]
    # A new output directory prevents stale success evidence from surviving a rerun.
    if output.exists() or output.is_symlink():
        raise VerificationError("host test output directory must be new")
    output.mkdir(parents=True)
    output = output.resolve(strict=True)
    result = {
        "schema": 1, "kind": "host_crypto_fixtures", "outcome": "running",
        "source": str(source), "output": str(output), "sdk": str(sdk) if sdk else None,
        "commands": [],
        "plain": {"outcome": "not_run"}, "asan": {"outcome": "not_run"},
        "ubsan": {"outcome": "not_run", "reason": "ASan-only memory checks; unmodified upstream Ed25519 arithmetic may have signed-shift UB"},
        "limits": ["Host-only synthetic/public vectors; no device binary execution",
                   "No iOS build, real-device acceptance, or complete cryptographic/security audit",
                   "ASan success does not imply UBSan or all undefined-behavior safety"],
    }
    report = output / "result.json"
    write_json(report, result)

    # Do not inherit build flags, loader injection, SDK selection, or target flags.
    env = {"PATH": os.defpath, "LC_ALL": "C", "LANG": "C", "TMPDIR": str(output)}
    for key in ("SYSTEMROOT", "WINDIR"):
        if key in os.environ:
            env[key] = os.environ[key]
    env["ASAN_OPTIONS"] = "detect_leaks=0:halt_on_error=1:abort_on_error=1"

    def command(args: list[str], name: str, *, run: bool = False) -> str:
        log = output / "logs" / (name + ".log")
        result["commands"].append({"name": name, "argv": args,
                                   "log": str(log.relative_to(output)),
                                   "receipt": str(log.relative_to(output)) + ".status.json"})
        write_json(report, result)
        return capture_helper_command(args, source=source, env=env, log=log,
                                      timeout_seconds=RUN_TIMEOUT_SECONDS if run else COMPILE_TIMEOUT_SECONDS,
                                      max_log_bytes=MAX_LOG_BYTES, tail_bytes=TAIL_BYTES)

    def build(label: str, flags: list[str], compiler: Path, inputs: list[Path], includes: list[str]) -> Path:
        directory = output / label
        directory.mkdir()
        objects = []
        for index, path in enumerate(inputs):
            obj = directory / f"{index:02d}-{path.stem}.o"
            command([str(compiler), *sdk_args, "-std=c11", "-O1", "-g", "-fno-common",
                     "-fno-omit-frame-pointer", "-DED25519_NO_SEED", "-DLIMD_GLUE_STATIC",
                     "-Wall", "-Wextra", "-Werror=implicit-function-declaration",
                     *flags, *includes, "-c", str(path), "-o", str(obj)],
                    f"{label}-compile-{index:02d}-{path.stem}")
            objects.append(str(obj))
        executable = directory / "host-crypto-fixtures"
        command([str(compiler), *sdk_args, *flags, *objects, "-o", str(executable)], f"{label}-link")
        return executable

    try:
        compiler = compiler_path(cc)
        result["compiler"] = str(compiler)
        version = command([str(compiler), "--version"], "compiler-version")
        if not any(marker in version for marker in ("clang", "GCC", "gcc", "Free Software Foundation")):
            raise VerificationError("installed compiler identity is not recognized as GCC or Clang")
        result["compiler_version"] = version
        ed = source / "root" / "3rd_party" / "ed25519"
        glue = source / "glue"
        inputs = [FIXTURES / name for name in FIXTURE_FILES]
        inputs += [ed / name for name in ED_FILES] + [glue / "src" / "sha512.c"]
        required = inputs + [FIXTURES / "fixture.h", FIXTURES / "sha_suite.inc", FIXTURES / "asan_probe.c"]
        required += list(ed.glob("*.h")) + [glue / "src" / "common.h"]
        required += list((glue / "include" / "libimobiledevice-glue").glob("*.h"))
        for path in required:
            if not path.is_file() or path.is_symlink():
                raise VerificationError(f"host fixture source missing or symlinked: {path}")
        # Hash all fixture/source/header bytes used, without changing prepared source.
        result["input_sha256"] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in sorted(set(required))}
        includes = ["-I", str(FIXTURES), "-I", str(ed), "-I", str(glue / "include")]
        result["plain"] = {"outcome": "running"}
        plain = build("plain", [], compiler, inputs, includes)
        text = command([str(plain)], "plain-run", run=True)
        result["plain"] = {"outcome": "passed", "context_layout": parse_success(text)}
        write_json(report, result)

        # Availability is probed separately: a failing instrumented fixture must
        # never be downgraded to "sanitizer unavailable" or plain-test success.
        probe = output / "asan-probe"
        asan_flags = ["-fsanitize=address", "-fno-omit-frame-pointer"]
        try:
            command([str(compiler), *sdk_args, "-std=c11", *asan_flags,
                     str(FIXTURES / "asan_probe.c"), "-o", str(probe)], "asan-probe-compile")
        except VerificationError as exc:
            if not ordinary_probe_failure(output, "asan-probe-compile"):
                result["asan"] = {"outcome": "failed", "stage": "probe_compile", "reason": str(exc)}
                raise
            result["asan"] = {"outcome": "unavailable", "stage": "probe_compile", "reason": str(exc)}
        else:
            try:
                command([str(probe)], "asan-probe-run", run=True)
            except VerificationError as exc:
                if not ordinary_probe_failure(output, "asan-probe-run"):
                    result["asan"] = {"outcome": "failed", "stage": "probe_run", "reason": str(exc)}
                    raise
                result["asan"] = {"outcome": "unavailable", "stage": "probe_run", "reason": str(exc)}
            else:
                result["asan"] = {"outcome": "running", "leak_detection": False}
                sanitized = build("asan", asan_flags, compiler, inputs, includes)
                text = command([str(sanitized)], "asan-run", run=True)
                result["asan"] = {"outcome": "passed", "leak_detection": False,
                                  "context_layout": parse_success(text)}
                if result["plain"]["context_layout"] != result["asan"]["context_layout"]:
                    raise VerificationError("plain/ASan context layout mismatch")
        result["outcome"] = "passed" if result["asan"]["outcome"] == "passed" else "passed_plain_asan_unavailable"
    except (VerificationError, OSError, ValueError) as exc:
        result["outcome"] = "failed"
        result["error"] = str(exc)
        if result["plain"]["outcome"] == "running":
            result["plain"]["outcome"] = "failed"
        if result["asan"]["outcome"] == "running":
            result["asan"]["outcome"] = "failed"
    finally:
        write_json(report, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="prepared directory containing root and glue")
    parser.add_argument("--output", type=Path, required=True, help="new receipts/build output directory")
    parser.add_argument("--cc", help="absolute verified installed host GCC/Clang compiler path")
    parser.add_argument("--sdk", type=Path, help="absolute existing SDK directory for explicit compiler/linker -isysroot")
    args = parser.parse_args()
    try:
        result = run_host_tests(args.source, args.output, args.cc, args.sdk)
    except (VerificationError, OSError, ValueError) as exc:
        parser.exit(1, f"host crypto tests: {exc}\n")
    print(json.dumps({"outcome": result["outcome"], "plain": result["plain"],
                      "asan": result["asan"], "result": str(args.output / "result.json")}, sort_keys=True))
    return 1 if result["outcome"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
