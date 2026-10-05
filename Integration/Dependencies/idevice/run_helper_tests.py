#!/usr/bin/env python3
"""Run only reviewed helper/RSD fixture tests on the locked macOS host.

Never builds an XCFramework, activates OpenSSL, adds composite acquisition code,
executes device/account work, modifies app routes, or changes main patch gates.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tomllib

from apply_patch import HERE, VerificationError, canonical_json, load_lock, sha256, stage
from build_xcframework import (file_hash, inventory, native_environment,
    reject_ambient_cargo_config, require_equal, vendor_crates, verify_toolchain)

from bounded_process import (capture_helper_command, COMMAND_TIMEOUT_SECONDS, MAX_LOG_BYTES,
    SUMMARY_TAIL_BYTES, TERM_GRACE_SECONDS, KILL_JOIN_SECONDS)

PROFILE = "helper-test-profile.json"
EXPECTED_FILTERS = [{"package": "idevice-ffi", "filter": "staged_pairing::", "expected_passed": 18},
                    {"package": "idevice", "filter": "bounded_rsd_tests", "expected_passed": 25}]


def load_helper_profile() -> dict:
    profile = load_lock(HERE, PROFILE)
    if profile.get("profile_kind") != "helper-only-native-tests" or profile["native_test_filters"] != EXPECTED_FILTERS:
        raise VerificationError("unexpected helper-only test scope")
    expected = {"ffi/src/staged_pairing.rs", "idevice/src/xpc/mod.rs", "idevice/src/xpc/format.rs",
                "idevice/src/xpc/http2/mod.rs", "idevice/src/xpc/http2/frame.rs", "idevice/src/services/rsd.rs"}
    if {entry["path"] for entry in profile["overlays"]} != expected:
        raise VerificationError("helper-only profile contains an unexpected source overlay")
    for edit in profile["edits"]:
        if "staged_acquisition" in edit["new"] or "openssl" in edit["new"]:
            raise VerificationError("helper-only profile cannot activate composite acquisition or OpenSSL")
    if {entry["path"] for entry in profile["edits"]} != {"ffi/src/lib.rs", "ffi/Cargo.toml"}:
        raise VerificationError("helper-only source edit scope changed")
    return profile


def verify_fixture_summary(output: str, suite: dict) -> int:
    summaries = re.findall(
        r"(?m)^test result: (ok|FAILED)\. ([0-9]+) passed; ([0-9]+) failed; "
        r"([0-9]+) ignored; ([0-9]+) measured; ([0-9]+) filtered out;", output)
    if len(summaries) != 1:
        raise VerificationError("fixture filter lacks one unambiguous final summary: " + suite["filter"])
    state, passed, failed, ignored, measured, _filtered = summaries[0]
    if state != "ok" or int(passed) != suite["expected_passed"] or any(int(value) for value in (failed, ignored, measured)):
        raise VerificationError("fixture filter did not pass its exact reviewed test count: " + suite["filter"])
    return int(passed)


def execute(args: argparse.Namespace) -> dict:
    profile = load_helper_profile()
    toolchain_bytes = args.toolchain_lock.read_bytes()
    require_equal(sha256(toolchain_bytes), args.toolchain_lock_sha256, "toolchain lock sha256")
    config = json.loads(toolchain_bytes)
    if config.get("schema") != 1 or not isinstance(config.get("source_date_epoch"), int):
        raise VerificationError("invalid toolchain lock")
    if args.work_dir.exists() or args.output.exists():
        raise VerificationError("work/output directories must be new")
    args.work_dir.mkdir(parents=True)
    env, binaries = native_environment(config, args.work_dir)
    observations = verify_toolchain(config, args.work_dir, env, binaries)
    source = args.work_dir / "source"
    source_manifest = stage(args.source, source, HERE, PROFILE)
    reject_ambient_cargo_config(source)
    if (source / "ffi/src/staged_acquisition.rs").exists():
        raise VerificationError("composite acquisition must be absent from helper-only source")
    before = (source / "Cargo.lock").read_bytes()
    crates = vendor_crates(before, args.crate_cache, source / "vendor")
    (source / ".cargo").mkdir()
    (source / ".cargo/config.toml").write_text('[source.crates-io]\nreplace-with = "tetherless-vendor"\n\n'
        '[source.tetherless-vendor]\ndirectory = "vendor"\n\n[net]\noffline = true\n')
    env["CARGO_ENCODED_RUSTFLAGS"] = "--remap-path-prefix=" + str(args.work_dir) + "=/tetherless-helper-test"
    defaults = tomllib.loads((source / "ffi/Cargo.toml").read_text())["features"]["default"]
    if "openssl" in defaults:
        raise VerificationError("helper-only tests must preserve the upstream AWS-LC defaults")
    completed = args.work_dir / "completed"
    completed.mkdir()
    outcomes = []
    for suite in profile["native_test_filters"]:
        command = [binaries["cargo"], "test", "--frozen", "-p", suite["package"], "--lib",
                   "--target", "aarch64-apple-darwin"]
        if suite["package"] == "idevice":
            command += ["--features", ",".join(defaults)]
        command.append(suite["filter"])
        log = completed / (suite["package"] + ".txt")
        output = capture_helper_command(command, source=source, env=env, log=log)
        passed = verify_fixture_summary(output, suite)
        outcomes.append({"package": suite["package"], "filter": suite["filter"],
                         "passed": passed, "command": command})
    if (source / "Cargo.lock").read_bytes() != before:
        raise VerificationError("Cargo.lock changed during native tests")
    for name, expected in source_manifest["files"].items():
        path = source / name
        actual = sha256(os.readlink(path).encode()) if name in source_manifest["symlinks"] and path.is_symlink() else file_hash(path)
        if actual != expected:
            raise VerificationError("source changed during fixture tests: " + name)
    evidence = {"schema": 1, "profile_kind": "helper-only-native-tests", "tests": outcomes,
                "source_commit": profile["upstream"]["commit"],
                "profile_sha256": file_hash(HERE / PROFILE),
                "toolchain_sha256": sha256(toolchain_bytes), "toolchain_observations": observations,
                "tooling_sha256": {p.name: file_hash(p) for p in (HERE / "apply_patch.py", HERE / "build_xcframework.py", HERE / "bounded_process.py", Path(__file__))},
                "process_limits": {"command_seconds": COMMAND_TIMEOUT_SECONDS, "log_bytes": MAX_LOG_BYTES,
                    "tail_bytes": SUMMARY_TAIL_BYTES, "term_grace_seconds": TERM_GRACE_SECONDS,
                    "kill_join_seconds": KILL_JOIN_SECONDS},
                "evidence_scope": "host fixture tests only; no iOS build/link, composite TLS, app integration or device acceptance"}
    (completed / "test-evidence.json").write_bytes(canonical_json(evidence))
    (completed / "source-manifest.json").write_bytes(canonical_json(source_manifest))
    (completed / "crates.json").write_bytes(canonical_json(crates))
    (completed / "toolchain-lock.json").write_bytes(toolchain_bytes)
    shutil.copy2(HERE / PROFILE, completed / PROFILE)
    (completed / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in inventory(completed).items()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    os.rename(completed, args.output)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "crate-cache", "work-dir", "output", "toolchain-lock"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--toolchain-lock-sha256", required=True)
    args = parser.parse_args()
    for name in ("source", "crate_cache", "work_dir", "output", "toolchain_lock"):
        setattr(args, name, getattr(args, name).absolute())
    try:
        evidence = execute(args)
    except (VerificationError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"helper-only native test failed: {exc}\n")
    print(json.dumps({"scope": evidence["profile_kind"], "tests": evidence["tests"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
