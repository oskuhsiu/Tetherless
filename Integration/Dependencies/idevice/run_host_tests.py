#!/usr/bin/env python3
"""Run only the three reviewed host-generation overlays and their fixture tests on the locked macOS host.

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

from offline_vendor import prepare_offline_vendor, audit_vendor_inputs, audit_workspace_inputs
from derived_cbindgen import derived_audit_receipt
from bounded_process import (capture_helper_command, COMMAND_TIMEOUT_SECONDS, MAX_LOG_BYTES,
    SUMMARY_TAIL_BYTES, TERM_GRACE_SECONDS, KILL_JOIN_SECONDS)

PROFILE = "candidate-profiles/host-only.json"
EXPECTED_FILTERS = [{"package": "idevice-ffi", "filter": "bounded_pairing_host::", "expected_passed": 8},
                    {"package": "idevice", "filter": "bounded_host_tests", "expected_passed": 5},
                    {"package": "idevice", "filter": "bounded_host_frame_tests", "expected_passed": 3},
                    {"package": "idevice", "filter": "bounded_opack_tests", "expected_passed": 4},
                    {"package": "idevice", "filter": "remote_pairing::responder::bounded_controller_signature_tests::", "expected_passed": 6}]


def load_host_profile() -> dict:
    profile = load_lock(HERE, PROFILE)
    if profile.get("profile_kind") != "registered-host-only-candidate" or profile["native_test_filters"] != EXPECTED_FILTERS:
        raise VerificationError("unexpected host-only test scope")
    expected = {"ffi/src/bounded_pairing_host.rs", "idevice/src/remote_pairing/opack.rs",
                "idevice/src/remote_pairing/responder.rs"}
    if {entry["path"] for entry in profile["overlays"]} != expected:
        raise VerificationError("host-only profile contains an unexpected source overlay")
    if len(profile["edits"]) != 1 or profile["edits"][0]["path"] != "ffi/src/lib.rs":
        raise VerificationError("host-only profile must have only its module declaration")
    declaration = '#[cfg(all(unix, feature = "remote_pairing"))]\npub mod bounded_pairing_host;\n'
    edit = profile["edits"][0]
    if edit["new"] != edit["old"] + declaration:
        raise VerificationError("host-only guarded module declaration differs")
    if profile.get("build_additional_features") or profile["activation"]["enabled"]:
        raise VerificationError("host-only tests cannot activate new features or artifacts")
    if not profile["patch_complete"] or not profile["activation"].get("test_only_execution_authorized"):
        raise VerificationError("host-only source/fixture authorization is incomplete")
    for name, expected_hash in profile["registration_receipts"].items():
        if file_hash(HERE / name) != expected_hash:
            raise VerificationError("host-only source receipt identity mismatch")
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
    profile = load_host_profile()
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
    for excluded in ("ffi/src/staged_pairing.rs", "ffi/src/staged_acquisition.rs", "idevice/src/remote_pairing/tunnel/staged_packet_io.rs"):
        if (source / excluded).exists():
            raise VerificationError("unrelated validation/acquisition source must be absent from host-only source")
    before = (source / "Cargo.lock").read_bytes()
    vendor_receipt = prepare_offline_vendor(source=source, work=args.work_dir, cache=args.crate_cache, env=env, derive_metadata=True)
    crates = vendor_receipt["crates"]
    env["CARGO_ENCODED_RUSTFLAGS"] = "--remap-path-prefix=" + str(args.work_dir) + "=/tetherless-host-test"
    defaults = tomllib.loads((source / "ffi/Cargo.toml").read_text())["features"]["default"]
    if "openssl" in defaults:
        raise VerificationError("host-only tests must preserve the upstream AWS-LC defaults")
    completed = args.work_dir / "completed"
    completed.mkdir()
    (completed / "vendor-layout.json").write_bytes(canonical_json(vendor_receipt))
    (completed / "source-manifest.json").write_bytes(canonical_json(source_manifest))
    outcomes = []
    try:
        for suite_index, suite in enumerate(profile["native_test_filters"], start=1):
            command = [binaries["cargo"], "test", "--frozen", "-p", suite["package"], "--lib",
                       "--target", "aarch64-apple-darwin"]
            if suite["package"] == "idevice":
                command += ["--features", ",".join(defaults)]
            command.append(suite["filter"])
            log = completed / f"{suite_index:02d}-{suite['package']}.txt"
            output = capture_helper_command(command, source=source, env=env, log=log)
            passed = verify_fixture_summary(output, suite)
            outcomes.append({"package": suite["package"], "filter": suite["filter"],
                             "passed": passed, "command": command, "log_file": log.name,
                             "status_file": log.name + ".status.json"})
    finally:
        audit = audit_vendor_inputs(vendor_receipt)
        derived_audit = audit_vendor_inputs(derived_audit_receipt(vendor_receipt))
        workspace_audit = audit_workspace_inputs(source, source_manifest, vendor_receipt["workspace_lock_sha256"])
        (completed / "vendor-input-audit.json").write_bytes(canonical_json(audit))
        (completed / "derived-vendor-input-audit.json").write_bytes(canonical_json(derived_audit))
        (completed / "workspace-input-audit.json").write_bytes(canonical_json(workspace_audit))
        if (not audit["original_inputs_unchanged"] or not derived_audit["original_inputs_unchanged"]
                or not workspace_audit["original_inputs_unchanged"]):
            raise VerificationError("authenticated workspace/vendor input changed; retained input-audit JSON files")
    total_passed = sum(suite["passed"] for suite in outcomes)
    if total_passed != 26 or len(outcomes) != 5:
        raise VerificationError("host-only profile must execute all five suites and exactly 26 fixtures")
    evidence = {"schema": 1, "profile_kind": "host-only-native-tests", "tests": outcomes,
                "expected_fixture_count": 26, "observed_fixture_count": total_passed,
                "source_commit": profile["upstream"]["commit"],
                "profile_sha256": file_hash(HERE / PROFILE),
                "toolchain_sha256": sha256(toolchain_bytes), "toolchain_observations": observations,
                "tooling_sha256": {p.name: file_hash(p) for p in (HERE / "apply_patch.py", HERE / "build_xcframework.py", HERE / "bounded_process.py", HERE / "offline_vendor.py", HERE / "derived_cbindgen.py", Path(__file__))},
                "vendor_layout": {key: value for key, value in vendor_receipt.items() if key != "authenticated_inputs"},
                "process_limits": {"command_seconds": COMMAND_TIMEOUT_SECONDS, "log_bytes": MAX_LOG_BYTES,
                    "tail_bytes": SUMMARY_TAIL_BYTES, "term_grace_seconds": TERM_GRACE_SECONDS,
                    "kill_join_seconds": KILL_JOIN_SECONDS},
                "evidence_scope": "host-generation fixture tests only; no helper/RSD/acquisition overlay, iOS build/link, OpenSSL, app integration or device acceptance"}
    (completed / "test-evidence.json").write_bytes(canonical_json(evidence))
    (completed / "source-manifest.json").write_bytes(canonical_json(source_manifest))
    (completed / "crates.json").write_bytes(canonical_json(crates))
    (completed / "toolchain-lock.json").write_bytes(toolchain_bytes)
    shutil.copy2(HERE / PROFILE, completed / "host-test-profile.json")
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
        parser.exit(1, f"host-only native test failed: {exc}\n")
    print(json.dumps({"scope": evidence["profile_kind"], "tests": evidence["tests"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
