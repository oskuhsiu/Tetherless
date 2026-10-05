#!/usr/bin/env python3
"""Run exactly three opt-in synthetic composite tests; no artifact/app activation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from apply_patch import HERE, VerificationError, canonical_json, load_lock, safe_path, sha256, stage
from bounded_process import capture_helper_command, COMMAND_TIMEOUT_SECONDS, MAX_LOG_BYTES
from build_xcframework import file_hash, inventory, native_environment, require_equal, verify_toolchain
from offline_vendor import prepare_offline_vendor
from run_helper_tests import verify_fixture_summary
from run_pairing_component_tests import load_provider, retain_input_audits, retain_openssl_outputs

PROFILE = "candidate-profiles/transcript-only.json"
PROFILE_SHA256 = "fb644be9b24726f58d7820bd52d5c551d62feb5a3c490c0afa7cb887cac1f300"
TARGET = "aarch64-apple-darwin"
FEATURES = ["openssl", "tetherless-synthetic-peer"]
SUITE = {"package": "idevice-ffi", "filter": "staged_acquisition::composite_transcript::", "expected_passed": 3}
RECEIPTS = {
    'registration/receipts/acquisition-stack-repair.json': '2bb6b71abc3e4876390c814705e665ef9b7ca83bc7dd3d3b5b85d35840cf2554',
    'registration/receipts/acquisition-stack-independent-review.json': 'e36166d16d94e648000e82b3064240f565305cea1b931d81dc477f100c5291cc',
    "registration/receipts/composite-transcript-source.json": "d3d85a874879e29021635ba4753121413b36749951d6cc4450b80cac050a8d04",
    "registration/receipts/composite-transcript-review.md": "5478c01376017e4c1e63d95f7a8925215fa64e87ec50df44b179254b2868eec1",
}


def load_transcript_profile(root: Path = HERE) -> dict:
    require_equal(file_hash(root / PROFILE), PROFILE_SHA256, "transcript profile")
    profile = load_lock(root, PROFILE)
    if (profile["native_test_filters"] != [SUITE] or profile["build_additional_features"] != FEATURES
            or profile["fixture_inventory"]["authored_count"] != 3 or profile["fixture_inventory"]["executed"]
            or profile["profile_kind"] != "registered-composite-transcript-tests"
            or not profile["patch_complete"] or not profile["activation"]["test_only_execution_authorized"]
            or profile["activation"]["enabled"] or profile["activation"]["consumer_integration_allowed"]):
        raise VerificationError("transcript profile differs from the exact reviewed test-only scope")
    for name, digest in RECEIPTS.items():
        require_equal(file_hash(safe_path(root, name)), digest, "transcript source/review receipt")
    return profile


def execute(args: argparse.Namespace) -> dict:
    profile = load_transcript_profile()
    provider = load_provider()
    toolchain = args.toolchain_lock.read_bytes()
    require_equal(sha256(toolchain), args.toolchain_lock_sha256, "toolchain lock")
    config = json.loads(toolchain)
    if config.get("schema") != 1 or not isinstance(config.get("source_date_epoch"), int):
        raise VerificationError("invalid toolchain lock")
    if args.work_dir.exists() or args.output.exists():
        raise VerificationError("transcript work/output directories must be fresh")
    args.work_dir.mkdir(parents=True)
    env, binaries = native_environment(config, args.work_dir)
    observations = verify_toolchain(config, args.work_dir, env, binaries)
    source = args.work_dir / "source"
    source_manifest = stage(args.source, source, HERE, PROFILE)
    vendor = prepare_offline_vendor(source=source, work=args.work_dir, cache=args.crate_cache,
                                    env=env, derive_metadata=True)
    completed = args.work_dir / "completed"
    completed.mkdir()
    (completed / "source-manifest.json").write_bytes(canonical_json(source_manifest))
    (completed / "vendor-layout.json").write_bytes(canonical_json(vendor))
    receipt = None
    try:
        receipt = provider.prepare_inputs(args.provider_inputs, args.work_dir / "host-provider", TARGET)
        (completed / "provider-input-receipt.json").write_bytes(canonical_json(receipt))
        if receipt["target"] != TARGET or receipt["final_link_arguments"]:
            raise VerificationError("transcript fixtures require the standalone host provider")
        env = provider.build_environment(env, receipt)
        env["DEVELOPER_DIR"] = config["developer_dir"]
        env["CARGO_ENCODED_RUSTFLAGS"] = "--remap-path-prefix=" + str(args.work_dir) + "=/tetherless-transcript-test"

        def command(argv, name):
            return capture_helper_command(argv, source=source, env=env, log=completed / name)

        sdk = command(["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"], "00-sdk-path.txt").strip()
        if not Path(sdk).is_absolute() or not Path(sdk).is_dir():
            raise VerificationError("selected SDK path is not an existing absolute directory")
        env["SDKROOT"] = sdk
        tools = {}
        for tool, key in (("clang", "CC_aarch64_apple_darwin"), ("clang++", "CXX_aarch64_apple_darwin"),
                          ("ar", "AR_aarch64_apple_darwin")):
            path = command(["/usr/bin/xcrun", "--sdk", "macosx", "--find", tool], "00-tool-" + tool + ".txt").strip()
            if not Path(path).is_absolute() or not Path(path).is_file():
                raise VerificationError("selected target tool is not an existing absolute file")
            env[key], tools[key] = path, path
        header = ["/usr/bin/xcrun", "--sdk", "macosx", "clang", "-arch", "arm64", "-isysroot", sdk,
                  "-I", str(Path(receipt["view_root"]) / "include"), "-fsyntax-only",
                  "-Werror=incompatible-function-pointer-types", str(HERE / "split-provider/header_probe.c")]
        command(header, "00-header-compile.txt")
        graph = [binaries["cargo"], "tree", "--frozen", "-p", "idevice-ffi", "--target", TARGET,
                 "--edges", "features", "--features", ",".join(FEATURES)]
        command(graph, "00-features-idevice-ffi.txt")
        argv = [binaries["cargo"], "test", "--frozen", "-p", "idevice-ffi", "--lib", "--target", TARGET,
                "--features", ",".join(FEATURES), "--message-format=json-render-diagnostics", SUITE["filter"]]
        passed = verify_fixture_summary(command(argv, "01-transcript.txt"), SUITE)
        outputs = retain_openssl_outputs(provider, receipt, completed / "01-transcript.txt",
                                         args.work_dir / "target" / TARGET, completed)
    finally:
        primary_failure = sys.exc_info()[0] is not None
        audits = retain_input_audits(source=source, source_manifest=source_manifest, vendor_receipt=vendor,
                                    provider=provider, provider_receipt=receipt, completed=completed)
        unchanged = all(audits[key]["original_inputs_unchanged"] for key in ("vendor", "derived_vendor", "workspace"))
        if (not unchanged or not audits["provider"]["unchanged"]) and not primary_failure:
            raise VerificationError("transcript input audit failed; all four receipts retained")
    evidence = {"schema": 1, "scope": "synthetic full composite transcript only", "profile_sha256": PROFILE_SHA256,
                "passed": passed, "suite": SUITE, "features": FEATURES, "command": argv,
                "log_file": "01-transcript.txt", "status_file": "01-transcript.txt.status.json",
                "source_commit": profile["upstream"]["commit"], "feature_graph_command": graph,
                "feature_graph_log": "00-features-idevice-ffi.txt", "header_probe_command": header,
                "header_probe_linked_or_executed": False, "openssl_outputs": outputs,
                "provider_receipt": receipt, "sdk_root": sdk, "compiler_paths": tools,
                "toolchain_sha256": sha256(toolchain), "toolchain_observations": observations,
                "process_limits": {"command_seconds": COMMAND_TIMEOUT_SECONDS, "log_bytes": MAX_LOG_BYTES},
                "artifact_or_product_activation": False, "apple_or_device_compatibility": False,
                "tooling_sha256": {name: file_hash(HERE / name) for name in (
                    "run_pairing_transcript_tests.py", "run_pairing_component_tests.py", "apply_patch.py",
                    "offline_vendor.py", "derived_cbindgen.py", "bounded_process.py", "run_helper_tests.py")}}
    (completed / "test-evidence.json").write_bytes(canonical_json(evidence))
    (completed / "toolchain-lock.json").write_bytes(toolchain)
    (completed / "transcript-profile.json").write_bytes((HERE / PROFILE).read_bytes())
    (completed / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in inventory(completed).items()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    os.rename(completed, args.output)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "crate-cache", "provider-inputs", "work-dir", "output", "toolchain-lock"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--toolchain-lock-sha256", required=True)
    args = parser.parse_args()
    for name in ("source", "crate_cache", "provider_inputs", "work_dir", "output", "toolchain_lock"):
        setattr(args, name, getattr(args, name).absolute())
    try:
        evidence = execute(args)
    except (VerificationError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"transcript test failed: {exc}\n")
    print(json.dumps({"passed": evidence["passed"], "scope": evidence["scope"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
