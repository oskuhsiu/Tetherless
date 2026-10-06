#!/usr/bin/env python3
"""New bounded diagnostic compiler adapter after explicit source recovery loss.

Only the owned diagnostic copy is compiled. No app/probe binary is run.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

import prepare_binding as prepare
from native_handoff import add_handoff_arguments, context_from_args, verify_handoff
from observe_compile import observe_compile

HERE = Path(__file__).resolve().parent
COMPILE_TIMEOUT_SECONDS = 1800
MAX_LOG_BYTES = 32 * 1024 * 1024
TOOL_TIMEOUT_SECONDS = 60
TOOL_COMMANDS = {
    "xcode": ["/usr/bin/xcodebuild", "-version"],
    "clang": ["/usr/bin/xcrun", "clang", "--version"],
    "swiftc": ["/usr/bin/xcrun", "swiftc", "--version"],
    "sdk_iphoneos_version": ["/usr/bin/xcrun", "--sdk", "iphoneos", "--show-sdk-version"],
    "sdk_iphoneos_build": ["/usr/bin/xcrun", "--sdk", "iphoneos", "--show-sdk-build-version"],
}


def write_json(path: Path, value: dict) -> None:
    selected = prepare.new_output_path(path.parent, path.name)
    with selected.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2) + "\n")


def load_supervisor(recipe: Path, contract: dict):
    # Execute only the exact already-reviewed Python supervisor from the complete
    # recipe verified against the producer's authenticated source identity.
    prepare.verify_recipe_inputs(recipe, contract)
    sys.path.insert(0, str(recipe))
    try:
        spec = importlib.util.spec_from_file_location("tetherless_diagnostic_supervisor", recipe / "bounded_process.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def audit_bound_inputs(binding: dict, contract: dict) -> dict:
    root = Path(binding["diagnostic_root"])
    changed = []
    for name, expected in binding["bound_files"].items():
        try:
            valid = prepare.file_hash(prepare.safe_file(root, name)) == expected
        except (OSError, ValueError):
            valid = False
        if not valid:
            changed.append(name)
    gate = HERE.parent / contract["preparation_gate"]["path"]
    try:
        gate_valid = (binding["preparation_gate"] == {"path": str(gate), "sha256": contract["preparation_gate"]["sha256"]}
                      and prepare.file_hash(prepare.safe_file(HERE.parent, contract["preparation_gate"]["path"])) == contract["preparation_gate"]["sha256"])
    except (OSError, ValueError):
        gate_valid = False
    if not gate_valid:
        changed.append("preparation-gate:pairing_safety.py")
    if binding.get("contract_sha256") != prepare.file_hash(HERE / "input-contract.json"):
        changed.append("input-contract.json")
    return {"schema": 1, "original_inputs_unchanged": not changed, "changed": changed,
            "checked_files": len(binding["bound_files"]), "runtime_capability_gates_changed": False}


def command(root: Path, work: Path, configuration: str, sdk: str, contract: dict) -> list[str]:
    if configuration not in contract["configurations"] or configuration not in ("Debug", "Release"):
        raise ValueError("unsupported diagnostic configuration")
    return ["/usr/bin/xcodebuild", "build", "-project", str(root / "AltStore.xcodeproj"),
            "-scheme", "SideStore", "-configuration", configuration,
            "-destination", "generic/platform=iOS", "-sdk", sdk,
            "-derivedDataPath", str(work / "DerivedData"), "-onlyUsePackageVersionsFromResolvedFile",
            "CODE_SIGNING_ALLOWED=NO", "CODE_SIGNING_REQUIRED=NO", "AD_HOC_CODE_SIGNING_ALLOWED=YES",
            "DEVELOPMENT_TEAM=XYZ0123456", "ORG_IDENTIFIER=com.SideStore", "ENABLE_DEBUG_DYLIB=NO",
            "LD_GENERATE_MAP_FILE=YES",
            "LD_MAP_FILE_PATH=" + str(work / "evidence/link-maps/$(TARGET_NAME)-$(CURRENT_ARCH).map"),
            "SWIFT_ACTIVE_COMPILATION_CONDITIONS=$(inherited) " + " ".join(contract["required_conditions"])]


def run(args) -> dict:
    contract = prepare.read_contract()
    if args.configuration not in ("Debug", "Release"):
        raise ValueError("unsupported diagnostic configuration")
    if args.diagnostic_root.is_symlink():
        raise ValueError("diagnostic root is a symlink")
    root = args.diagnostic_root.resolve(strict=True)
    binding = prepare.read_json(prepare.safe_file(root, "TETHERLESS_PAIRING_DIAGNOSTIC_BINDING.json"), args.binding_receipt_sha256)
    if (binding.get("diagnostic_root") != str(root) or binding.get("mode") != "diagnostic-only"
            or binding.get("runtime_capability_gates_changed") is not False
            or binding.get("consumer_or_product_activation") is not False
            or binding.get("native_or_app_build_executed") is not False):
        raise ValueError("binding is outside the closed diagnostic contract")
    context = context_from_args(args)
    artifact = Path(binding["native_handoff"]["apple_artifact_root"])
    artifact_sha = binding["native_handoff"]["apple_receipt_sha256"]

    def handoff():
        return verify_handoff(contract, args.native_handoff, args.native_handoff_sha256, context,
                              artifact, artifact_sha, args.native_recipe)

    if handoff() != binding["native_handoff"]:
        raise ValueError("binding differs from current authenticated native handoff")
    if prepare.artifact_inputs(artifact, artifact_sha, contract) != binding["native_artifact"]:
        raise ValueError("binding native artifact evidence changed")
    if prepare.verify_recipe_inputs(args.native_recipe, contract) != binding["native_recipe"]:
        raise ValueError("binding current native recipe changed")
    if not audit_bound_inputs(binding, contract)["original_inputs_unchanged"]:
        raise ValueError("bound inputs changed before diagnostic compilation")
    toolchain = prepare.read_json(prepare.safe_file(args.toolchain_lock.parent, args.toolchain_lock.name),
                                  binding["native_artifact"]["toolchain_lock_sha256"])
    developer = toolchain.get("developer_dir")
    if developer != "/Applications/Xcode_26.3.app/Contents/Developer" or not Path(developer).is_dir():
        raise ValueError("exact reviewed Xcode developer directory is required")
    work = args.work_dir
    if (work.exists() or work.is_symlink() or work.resolve().is_relative_to(root)
            or root.is_relative_to(work.resolve())):
        raise ValueError("diagnostic compile work must be fresh and separate")
    work = work.resolve(strict=False)
    work.mkdir(parents=True)
    evidence = work / "evidence"
    evidence.mkdir()
    (evidence / "link-maps").mkdir()
    for name in ("home", "tmp"):
        (work / name).mkdir()
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(work / "home"), "TMPDIR": str(work / "tmp"),
           "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8", "DEVELOPER_DIR": developer}
    supervisor = load_supervisor(args.native_recipe, contract)
    expected = binding["native_artifact"]["targets"]["aarch64-apple-ios"]["toolchain_observations"]
    primary = None
    audits = {}
    result = None
    try:
        observations = {}
        for label, argv in TOOL_COMMANDS.items():
            value = supervisor.capture_helper_command(argv, source=root, env=env, log=evidence / ("toolchain-" + label + ".txt"),
                timeout_seconds=TOOL_TIMEOUT_SECONDS, max_log_bytes=1024 * 1024).strip()
            if not expected.get(label) or value != expected[label]:
                raise ValueError("compiler/SDK observation differs from authenticated producer: " + label)
            observations[label] = value
        sdk = supervisor.capture_helper_command(["/usr/bin/xcrun", "--sdk", "iphoneos", "--show-sdk-path"],
            source=root, env=env, log=evidence / "sdk-path.txt", timeout_seconds=TOOL_TIMEOUT_SECONDS,
            max_log_bytes=1024 * 1024).strip()
        if (not Path(sdk).is_absolute() or not Path(sdk).is_dir()
                or sdk != binding["native_artifact"]["targets"]["aarch64-apple-ios"]["sdk_root"]):
            raise ValueError("selected SDK path differs from authenticated producer")
        argv = command(root, work, args.configuration, sdk, contract)
        write_json(evidence / "invocation.json", {"command": argv, "environment": env, "executed_output": False})
        supervisor.capture_helper_command(argv, source=root, env=env, log=evidence / "xcodebuild.txt",
            timeout_seconds=COMPILE_TIMEOUT_SECONDS, max_log_bytes=MAX_LOG_BYTES)
        observed = observe_compile(evidence / "xcodebuild.txt", root, work / "DerivedData", contract,
                                   dict(binding, sdk_path=sdk), args.configuration,
                                   evidence_directory=evidence / "compiler-inputs")
        link_map = prepare.safe_file(evidence, "link-maps/SideStore-arm64.map")
        if not 0 < link_map.stat().st_size <= MAX_LOG_BYTES:
            raise ValueError("final app linker map is missing or outside the retained bound")
        result = {"schema": 1, "configuration": args.configuration, "mode": "diagnostic-only",
                  "binding_receipt_sha256": args.binding_receipt_sha256, "native_handoff": binding["native_handoff"],
                  "link_map_sha256": prepare.file_hash(link_map),
                  "observations": observed, "toolchain_observations": observations, "command": argv,
                  "compile_process_limits": {"seconds": COMPILE_TIMEOUT_SECONDS, "log_bytes": MAX_LOG_BYTES},
                  "app_binary_executed": False, "runtime_capability_gates_changed": False,
                  "consumer_or_product_activation": False}
    except BaseException as error:
        primary = error
    finally:
        checks = {
            "bound-input-audit.json": lambda: audit_bound_inputs(binding, contract),
            "recipe-input-audit.json": lambda: {"original_inputs_unchanged": prepare.verify_recipe_inputs(args.native_recipe, contract) == binding["native_recipe"]},
            "native-handoff-audit.json": lambda: {"original_inputs_unchanged": handoff() == binding["native_handoff"] and prepare.artifact_inputs(artifact, artifact_sha, contract) == binding["native_artifact"]},
        }
        for name, check in checks.items():
            try:
                audit = check()
            except (OSError, ValueError, KeyError) as error:
                audit = {"original_inputs_unchanged": False, "error_kind": type(error).__name__}
            audits[name] = audit
            try:
                write_json(evidence / name, audit)
            except (OSError, ValueError) as error:
                audits[name] = dict(audit, evidence_write_error=type(error).__name__, original_inputs_unchanged=False)
        if primary is not None:
            raise primary
        if not all(row["original_inputs_unchanged"] for row in audits.values()):
            raise ValueError("diagnostic input audit failed; success not published")
    result["input_audits"] = audits
    write_json(evidence / "diagnostic-compile-evidence.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("diagnostic-root", "work-dir", "toolchain-lock", "native-recipe"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--configuration", required=True, choices=("Debug", "Release"))
    parser.add_argument("--binding-receipt-sha256", required=True)
    add_handoff_arguments(parser)
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, str(error) + "\n")
    print(json.dumps({"configuration": result["configuration"], "app_binary_executed": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
