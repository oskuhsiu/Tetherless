#!/usr/bin/env python3
"""Run opt-in host pairing component fixtures; no Apple artifact or product activation."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib

from apply_patch import HERE, VerificationError, canonical_json, load_lock, safe_path, sha256, stage
from build_xcframework import file_hash, inventory, native_environment, require_equal, verify_toolchain
from bounded_process import capture_helper_command, MAX_LOG_BYTES, COMMAND_TIMEOUT_SECONDS
from derived_cbindgen import derived_audit_receipt
from offline_vendor import prepare_offline_vendor, audit_vendor_inputs, audit_workspace_inputs
from run_helper_tests import verify_fixture_summary

TARGET = "aarch64-apple-darwin"
PROVIDER_RECEIPT_SHA256 = "2f4e49207716cc79c8561d517011fdc7d5bf775cfe55d612f40380de2e36302e"
OPENSSL_PACKAGE_ID = "registry+https://github.com/rust-lang/crates.io-index#openssl-sys@0.9.112"
FILTERS = [
    ("idevice-ffi", "staged_pairing::", 18), ("idevice", "bounded_rsd_tests", 25),
    ("idevice-ffi", "staged_acquisition::", 11), ("idevice", "remote_pairing::staged_contributory_tests::", 3),
    ("idevice", "remote_pairing::socket::staged_rp_socket_tests::", 2),
    ("idevice", "remote_pairing::tunnel::staged_openssl::tests::", 4),
    ("idevice", "remote_pairing::tunnel::staged_openssl_fixtures::", 4),
    ("idevice", "remote_pairing::tunnel::staged_packet_io::", 7),
]
HOST_FILTERS = [("idevice-ffi", "bounded_pairing_host::", 8), ("idevice", "bounded_host_tests", 5),
                ("idevice", "bounded_host_frame_tests", 3), ("idevice", "bounded_opack_tests", 4),
                ("idevice", "remote_pairing::responder::bounded_controller_signature_tests::", 6)]


def load_profile(name: str) -> tuple[str, dict]:
    if name not in ("acquisition-only", "combined"):
        raise VerificationError("select acquisition-only or combined explicitly")
    path = "candidate-profiles/" + name + ".json"
    registry = json.loads((HERE / "registration/registration.json").read_bytes())
    require_equal(file_hash(HERE / path), registry["profiles"][name]["sha256"], "component profile")
    profile = load_lock(HERE, path)
    expected = FILTERS + (HOST_FILTERS if name == "combined" else [])
    actual = [(e["package"], e["filter"], e["expected_passed"]) for e in profile["native_test_filters"]]
    if (actual != expected or profile.get("build_additional_features") != ["openssl"]
            or not profile["patch_complete"] or not profile["activation"].get("test_only_execution_authorized")
            or profile["activation"]["enabled"] or profile["activation"]["consumer_integration_allowed"]):
        raise VerificationError("component profile is not the exact reviewed test-only scope")
    return path, profile


def load_provider():
    path = HERE / "registration/receipts/provider-contract.json"
    require_equal(file_hash(path), PROVIDER_RECEIPT_SHA256, "provider review receipt")
    receipt = json.loads(path.read_bytes())
    for relative, expected in receipt["changed_files"].items():
        relative = str(Path(relative).relative_to("Integration/Dependencies/idevice"))
        require_equal(file_hash(safe_path(HERE, relative)), expected, "provider recipe file")
    spec = importlib.util.spec_from_file_location("pairing_component_provider", HERE / "split-provider/provider_inputs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selected_openssl_outputs(log: Path, target_root: Path, configuration: str = "debug") -> list[Path]:
    """Use Cargo's package-qualified build-script events, never a glob guess."""
    if configuration not in ("debug", "release"):
        raise VerificationError("unexpected Cargo build configuration")
    if (not target_root.is_absolute() or target_root.is_symlink() or not target_root.is_dir()
            or target_root.parent.is_symlink() or not target_root.parent.is_dir()):
        raise VerificationError("owned Cargo target root is missing or substituted")
    with log.open("rb") as stream:
        data = stream.read(MAX_LOG_BYTES + 1)
    if len(data) > MAX_LOG_BYTES:
        raise VerificationError("Cargo log exceeds its supervised bound")
    results = set()
    for line in data.splitlines():
        if not line.startswith(b"{"):
            continue
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if event.get("reason") != "build-script-executed" or event.get("package_id") != OPENSSL_PACKAGE_ID:
            continue
        out_dir = Path(event.get("out_dir", ""))
        if not out_dir.is_absolute():
            raise VerificationError("OpenSSL OUT_DIR must be absolute")
        try:
            relative = out_dir.relative_to(target_root)
        except ValueError as exc:
            raise VerificationError("OpenSSL output escaped the owned target directory") from exc
        parts = relative.parts
        if (len(parts) != 4 or parts[:2] != (configuration, "build") or parts[3] != "out"
                or not re.fullmatch(r"openssl-sys-[A-Za-z0-9_-]+", parts[2])):
            raise VerificationError("unexpected target-qualified OpenSSL build output path")
        safe_path(target_root, str(relative))
        results.add(safe_path(target_root, str(relative.parent / "output")))
    if not results:
        raise VerificationError("selected Cargo invocation did not identify openssl-sys 0.9.112 output")
    return sorted(results)


def retain_openssl_outputs(provider, receipt: dict, log: Path, target_root: Path, evidence: Path,
                           configuration: str = "debug") -> list[dict]:
    results = []
    for index, path in enumerate(selected_openssl_outputs(log, target_root, configuration), 1):
        with path.open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise VerificationError("selected openssl-sys output exceeds 1 MiB")
        destination = evidence / f"{log.stem}-openssl-sys-{index:02d}.txt"
        with destination.open("xb") as stream:
            stream.write(data)
        result = provider.check_build_script_output(data, receipt)
        results.append(dict(result, source_path=str(path), retained_file=destination.name))
    return results


def features(package: str, defaults: list[str]) -> list[str]:
    return ["openssl"] if package == "idevice-ffi" else [*defaults, "openssl"]


def retain_input_audits(*, source: Path, source_manifest: dict, vendor_receipt: dict,
                        provider, provider_receipt: dict | None, completed: Path) -> dict:
    """One audit error must not suppress the other independent receipts."""
    operations = (
        ("vendor", "vendor-input-audit.json", lambda: audit_vendor_inputs(vendor_receipt)),
        ("derived_vendor", "derived-vendor-input-audit.json", lambda: audit_vendor_inputs(derived_audit_receipt(vendor_receipt))),
        ("workspace", "workspace-input-audit.json", lambda: audit_workspace_inputs(source, source_manifest, vendor_receipt["workspace_lock_sha256"])),
        ("provider", "provider-input-audit.json", lambda: provider.audit_inputs(provider_receipt)
            if provider_receipt is not None else {"unchanged": False, "status": "preparation_not_completed"}),
    )
    results = {}
    for key, filename, operation in operations:
        try:
            result = operation()
        except (OSError, ValueError, KeyError) as exc:
            result = {"original_inputs_unchanged": False, "unchanged": False,
                      "status": "audit_failed", "error_type": type(exc).__name__}
        results[key] = result
        (completed / filename).write_bytes(canonical_json(result))
    return results


def execute(args: argparse.Namespace) -> dict:
    profile_path, profile = load_profile(args.profile)
    provider = load_provider()
    toolchain_bytes = args.toolchain_lock.read_bytes()
    require_equal(sha256(toolchain_bytes), args.toolchain_lock_sha256, "toolchain lock")
    config = json.loads(toolchain_bytes)
    if config.get("schema") != 1 or not isinstance(config.get("source_date_epoch"), int):
        raise VerificationError("invalid toolchain lock")
    if args.work_dir.exists() or args.output.exists():
        raise VerificationError("component work/output directories must be fresh")
    args.work_dir.mkdir(parents=True)
    env, binaries = native_environment(config, args.work_dir)
    observations = verify_toolchain(config, args.work_dir, env, binaries)
    source = args.work_dir / "source"
    source_manifest = stage(args.source, source, HERE, profile_path)
    vendor_receipt = prepare_offline_vendor(source=source, work=args.work_dir, cache=args.crate_cache,
                                           env=env, derive_metadata=True)
    completed = args.work_dir / "completed"
    completed.mkdir()
    (completed / "vendor-layout.json").write_bytes(canonical_json(vendor_receipt))
    (completed / "source-manifest.json").write_bytes(canonical_json(source_manifest))
    provider_receipt, outcomes, feature_graphs, output_receipts = None, [], [], []
    try:
        provider_receipt = provider.prepare_inputs(args.provider_inputs, args.work_dir / "host-provider", TARGET)
        (completed / "provider-input-receipt.json").write_bytes(canonical_json(provider_receipt))
        if provider_receipt["target"] != TARGET or provider_receipt["final_link_arguments"]:
            raise VerificationError("host component tests require standalone host static inputs")
        env = provider.build_environment(env, provider_receipt)
        env["DEVELOPER_DIR"] = config["developer_dir"]
        env["CARGO_ENCODED_RUSTFLAGS"] = "--remap-path-prefix=" + str(args.work_dir) + "=/tetherless-component-test"
        def command(command, name):
            return capture_helper_command(command, source=source, env=env, log=completed / name)
        sdk = command(["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"], "00-sdk-path.txt").strip()
        if not Path(sdk).is_absolute() or not Path(sdk).is_dir():
            raise VerificationError("selected SDK path is not an existing absolute directory")
        env["SDKROOT"] = sdk
        compiler_paths = {}
        for tool, key in (("clang", "CC_aarch64_apple_darwin"), ("clang++", "CXX_aarch64_apple_darwin"), ("ar", "AR_aarch64_apple_darwin")):
            value = command(["/usr/bin/xcrun", "--sdk", "macosx", "--find", tool], "00-tool-" + tool + ".txt").strip()
            if not Path(value).is_absolute() or not Path(value).is_file():
                raise VerificationError("selected compiler/tool path is not an existing absolute file")
            env[key], compiler_paths[key] = value, value
        header_command = ["/usr/bin/xcrun", "--sdk", "macosx", "clang", "-arch", "arm64", "-isysroot", sdk,
                          "-I", str(Path(provider_receipt["view_root"]) / "include"), "-fsyntax-only",
                          "-Werror=incompatible-function-pointer-types", str(HERE / "split-provider/header_probe.c")]
        command(header_command, "00-header-compile.txt")
        defaults = tomllib.loads((source / "ffi/Cargo.toml").read_text())["features"]["default"]
        if "openssl" in defaults:
            raise VerificationError("OpenSSL must remain an explicit component-test feature")
        for package in ("idevice-ffi", "idevice"):
            graph = [binaries["cargo"], "tree", "--frozen", "-p", package, "--target", TARGET,
                     "--edges", "features", "--features", ",".join(features(package, defaults))]
            name = "00-features-" + package + ".txt"
            command(graph, name)
            feature_graphs.append({"package": package, "command": graph, "log_file": name})
        for index, suite in enumerate(profile["native_test_filters"], 1):
            argv = [binaries["cargo"], "test", "--frozen", "-p", suite["package"], "--lib", "--target", TARGET,
                    "--features", ",".join(features(suite["package"], defaults)),
                    "--message-format=json-render-diagnostics", suite["filter"]]
            if suite["filter"] == "staged_acquisition::":
                argv += ["--", "--nocapture"]
            name = f"{index:02d}-{suite['package']}.txt"
            output = command(argv, name)
            passed = verify_fixture_summary(output, suite)
            outputs = retain_openssl_outputs(provider, provider_receipt, completed / name,
                                             args.work_dir / "target" / TARGET, completed)
            output_receipts.extend(outputs)
            outcomes.append({"package": suite["package"], "filter": suite["filter"], "passed": passed,
                             "command": argv, "log_file": name, "status_file": name + ".status.json",
                             "openssl_outputs": outputs})
    finally:
        primary_failure = sys.exc_info()[0] is not None
        checks = retain_input_audits(source=source, source_manifest=source_manifest, vendor_receipt=vendor_receipt,
                                    provider=provider, provider_receipt=provider_receipt, completed=completed)
        unchanged = all(checks[key]["original_inputs_unchanged"] for key in ("vendor", "derived_vendor", "workspace"))
        if (not unchanged or not checks["provider"]["unchanged"]) and not primary_failure:
            raise VerificationError("component input audit failed; retained original/derived/workspace/provider evidence")
    expected_count = 74 if args.profile == "acquisition-only" else 100
    if sum(row["passed"] for row in outcomes) != expected_count or len(outcomes) != len(profile["native_test_filters"]):
        raise VerificationError("component fixture aggregate differs from the reviewed selection")
    evidence = {"schema": 1, "scope": "host pairing component fixtures only", "profile": args.profile,
                "profile_sha256": file_hash(HERE / profile_path), "tests": outcomes, "passed": expected_count,
                "feature_graphs": feature_graphs, "openssl_outputs": output_receipts,
                "header_probe_command": header_command, "header_probe_linked_or_executed": False,
                "provider_receipt": provider_receipt, "sdk_root": sdk, "compiler_paths": compiler_paths,
                "provider_recipe_manifest_sha256": PROVIDER_RECEIPT_SHA256,
                "provider_module_sha256": file_hash(HERE / "split-provider/provider_inputs.py"),
                "toolchain_sha256": sha256(toolchain_bytes), "toolchain_observations": observations,
                "process_limits": {"command_seconds": COMMAND_TIMEOUT_SECONDS, "log_bytes": MAX_LOG_BYTES},
                "artifact_or_product_activation": False,
                "tooling_sha256": {name: file_hash(HERE / name) for name in
                    ("run_pairing_component_tests.py", "apply_patch.py", "offline_vendor.py", "derived_cbindgen.py",
                     "bounded_process.py", "build_xcframework.py", "run_helper_tests.py")}}
    (completed / "test-evidence.json").write_bytes(canonical_json(evidence))
    (completed / "toolchain-lock.json").write_bytes(toolchain_bytes)
    (completed / "component-profile.json").write_bytes((HERE / profile_path).read_bytes())
    (completed / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in inventory(completed).items()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    os.rename(completed, args.output)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "crate-cache", "provider-inputs", "work-dir", "output", "toolchain-lock"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--toolchain-lock-sha256", required=True)
    parser.add_argument("--profile", choices=("acquisition-only", "combined"), required=True)
    args = parser.parse_args()
    for name in ("source", "crate_cache", "provider_inputs", "work_dir", "output", "toolchain_lock"):
        setattr(args, name, getattr(args, name).absolute())
    try:
        evidence = execute(args)
    except (VerificationError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"component test failed: {exc}\n")
    print(json.dumps({"profile": evidence["profile"], "passed": evidence["passed"]}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
