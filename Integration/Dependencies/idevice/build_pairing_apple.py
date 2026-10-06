#!/usr/bin/env python3
"""Bounded opt-in Apple dependency build/link verification. No app or iOS execution."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import sys
import tomllib

from apply_patch import HERE, VerificationError, canonical_json, load_lock, safe_path, sha256, stage
from build_xcframework import (file_hash, inventory, native_environment, require_equal, toolchain_commands,
    native_static_flags, verify_generated_header, deterministic_zip)
from bounded_process import capture_helper_command, MAX_LOG_BYTES, COMMAND_TIMEOUT_SECONDS
from offline_vendor import prepare_offline_vendor
from run_pairing_component_tests import load_provider, retain_openssl_outputs, retain_input_audits
from apple_source_bundle import create_source_bundle
from pairing_result_header import retain_headers, verify_headers
from ffi_namespace import load_contract as namespace_contract, public_header
from mixed_provider import verify as verify_mixed_provider, audit as audit_mixed_provider, check_symbols, check_mixed_symbols

PROFILE = "candidate-profiles/apple-verification.json"
PROFILE_SHA256 = "384bbd1554e0148c7d8289b6d3a214dd82819a580c8d418ded55ff06b219c27f"
FORBIDDEN_FEATURE = "tetherless-synthetic-peer"
TARGETS = [
    {"rust": "aarch64-apple-ios", "sdk": "iphoneos", "clang": "arm64-apple-ios17.0", "deployment": "17.0", "extra_features": ["openssl", "obfuscate"]},
    {"rust": "aarch64-apple-ios-sim", "sdk": "iphonesimulator", "clang": "arm64-apple-ios17.0-simulator", "deployment": "17.0", "extra_features": ["openssl"]},
]
SWIFT_26_3_STDOUT = ("Apple Swift version 6.2.4 (swiftlang-6.2.4.1.4 clang-1700.6.4.2)\n"
                     "Target: arm64-apple-macosx15.0")
SWIFT_26_3_MERGED = "swift-driver version: 1.127.15 " + SWIFT_26_3_STDOUT


def require_toolchain_observation(value: str, expected: str, label: str) -> None:
    # The lock observer records stdout. The bounded supervisor retains both
    # streams. Xcode 26.3's swiftc --version also emits this exact driver identity
    # on stderr, preceding stdout (observed in producer run 37375339856).
    # Accept that complete measured pair; do not strip or ignore arbitrary text.
    if label == "swiftc" and expected == SWIFT_26_3_STDOUT and value == SWIFT_26_3_MERGED:
        return
    require_equal(value, expected, label)


def load_apple_profile() -> dict:
    require_equal(file_hash(HERE / PROFILE), PROFILE_SHA256, "Apple verification profile")
    profile = load_lock(HERE, PROFILE)
    if (profile["profile_kind"] != "apple-pairing-production-verification" or profile["apple_targets"] != TARGETS
            or not profile["patch_complete"] or not profile["activation"].get("apple_verification_authorized")
            or profile["activation"]["enabled"] or profile["activation"]["consumer_integration_allowed"]
            or profile["activation"].get("test_only_execution_authorized") or profile["native_test_filters"]
            or profile["forbidden_features"] != [FORBIDDEN_FEATURE]):
        raise VerificationError("Apple production verification profile differs from reviewed scope")
    return profile


def bounded_toolchain(config: dict, work: Path, env: dict, binaries: dict, evidence: Path) -> dict:
    commands = toolchain_commands(binaries)
    if set(config["observations"]) != set(commands):
        raise VerificationError("toolchain observations are incomplete")
    observations = {}
    for label, argv in commands.items():
        value = capture_helper_command(argv, source=work, env=env, log=evidence / ("toolchain-" + label + ".txt")).strip()
        require_toolchain_observation(value, config["observations"][label], label)
        observations[label] = value
    if config.get("rust_release") != "1.98.1" or not observations["rustc"].startswith("rustc 1.98.1 ("):
        raise VerificationError("Apple recipe requires Rust 1.98.1")
    if observations["xcode"].splitlines()[0] != "Xcode 26.3":
        raise VerificationError("Apple recipe requires Xcode 26.3")
    sysroot = Path(capture_helper_command([binaries["rustc"], "--print", "sysroot"], source=work,
        env=env, log=evidence / "toolchain-sysroot.txt").strip())
    for target in ["aarch64-apple-darwin", *[row["rust"] for row in TARGETS]]:
        if not (sysroot / "lib/rustlib" / target / "lib").is_dir():
            raise VerificationError("required exact Rust target is not preinstalled")
    return observations


def release_command(cargo: str, target: dict, *, report: bool = False) -> list[str]:
    command = [cargo, "rustc" if report else "build", "--frozen", "--release", "--lib", "-p", "idevice-ffi",
               "--target", target["rust"], "--features", ",".join(target["extra_features"])]
    if report:
        command += ["--", "--print", "native-static-libs"]
    else:
        command += ["--message-format=json-render-diagnostics"]
    return command


def read_bounded_log(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(MAX_LOG_BYTES + 1)
    if len(data) > MAX_LOG_BYTES:
        raise VerificationError("native log exceeded its supervised bound")
    return data


def check_production_features(build_log: Path, graph_log: Path, source: Path, defaults: list[str], target: dict) -> dict:
    if FORBIDDEN_FEATURE in defaults or FORBIDDEN_FEATURE in target["extra_features"]:
        raise VerificationError("synthetic-peer feature cannot be selected for Apple output")
    if FORBIDDEN_FEATURE.encode() in read_bounded_log(graph_log):
        raise VerificationError("synthetic-peer feature appears in resolved Apple feature graph")
    matched = []
    for line in read_bounded_log(build_log).splitlines():
        if not line.startswith(b"{"):
            continue
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if event.get("reason") != "compiler-artifact":
            continue
        enabled = event.get("features", [])
        if FORBIDDEN_FEATURE in enabled:
            raise VerificationError("synthetic-peer feature appears in compiler artifact")
        if event.get("manifest_path") == str(source / "ffi/Cargo.toml"):
            if not set(defaults + target["extra_features"]).issubset(set(enabled)) or "default" not in enabled:
                raise VerificationError("Apple FFI artifact did not preserve default/selected features")
            selected_target = event.get("target", {})
            # Cargo reports the package's build script under the same manifest
            # before its library. It is a host executable, not the FFI archive.
            if (selected_target.get("kind") == ["custom-build"]
                    and selected_target.get("crate_types") == ["bin"]
                    and selected_target.get("name") == "build-script-build"
                    and selected_target.get("src_path") == str(source / "ffi/build.rs")):
                continue
            if (selected_target.get("kind") != ["staticlib"]
                    or selected_target.get("crate_types") != ["staticlib"]
                    or selected_target.get("name") != "idevice_ffi"
                    or selected_target.get("src_path") != str(source / "ffi/src/lib.rs")):
                raise VerificationError("selected FFI compiler artifact is not the staticlib target")
            library = source.parent / "target" / target["rust"] / "release/libidevice_ffi.a"
            if str(library) not in event.get("filenames", []):
                raise VerificationError("selected FFI compiler artifact does not identify the target release archive")
            matched.append({"package_id": event.get("package_id"), "features": enabled, "filenames": event.get("filenames", [])})
    if len(matched) != 1:
        raise VerificationError("need exactly one selected FFI compiler artifact feature receipt")
    return {"target": target["rust"], "ffi_artifact": matched[0], "synthetic_peer_selected": False,
            "feature_graph_sha256": file_hash(graph_log), "build_log_sha256": file_hash(build_log)}


def system_link_flags(output: str) -> list[str]:
    flags = native_static_flags(output)
    framework = False
    for flag in flags:
        if framework:
            name, framework = flag, False
        elif flag == "-framework":
            framework = True
            continue
        else:
            name = flag[2:]
        lower = name.lower()
        if (lower == "openssl" or lower.startswith("openssl")
                or re.fullmatch(r"(?:lib)?(?:ssl|crypto)(?:[._-].*)?", lower)):
            raise VerificationError("additional OpenSSL provider conflicts with Apple empty-LIBS contract")
    return flags


def link_command(*, language: str, target: dict, sdk: str, headers: Path, library: Path,
                 probe: Path, symbol: str, output: Path, system_flags: list[str], framework_flags: list[str]) -> list[str]:
    if (len(framework_flags) != 4 or framework_flags[0] != "-F" or framework_flags[2:] != ["-framework", "OpenSSL"]
            or not Path(framework_flags[1]).is_absolute()):
        raise VerificationError("exact selected OpenSSL framework arguments required")
    # Reuse the strict compiler-report parser to reject injected options/providers.
    system_link_flags("native-static-libs: " + " ".join(system_flags))
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", symbol):
        raise VerificationError("unreviewed probe root symbol")
    if language == "c":
        args = ["/usr/bin/xcrun", "--sdk", target["sdk"], "clang", "-target", target["clang"],
                "-isysroot", sdk, "-I", str(headers), "-O0", "-std=c11", "-Werror=incompatible-function-pointer-types"]
    elif language == "swift":
        args = ["/usr/bin/xcrun", "--sdk", target["sdk"], "swiftc", "-target", target["clang"],
                "-sdk", sdk, "-I", str(headers), "-Onone"]
    else:
        raise VerificationError("unsupported link-probe language")
    return args + [str(probe), "-Xlinker", "-force_load", "-Xlinker", str(library),
                   "-Xlinker", "-u", "-Xlinker", "_" + symbol, *system_flags, *framework_flags, "-o", str(output)]


def verify_slice_metadata(path: Path, targets: list[dict] | None = None) -> dict:
    data = plistlib.loads(path.read_bytes())
    slices = data.get("AvailableLibraries", [])
    actual = {(row.get("SupportedPlatform"), row.get("SupportedPlatformVariant", ""),
               tuple(row.get("SupportedArchitectures", []))) for row in slices}
    if len(slices) != 2 or actual != {("ios", "", ("arm64",)), ("ios", "simulator", ("arm64",))}:
        raise VerificationError("generated XCFramework slice metadata differs from the two requested targets")
    verified = []
    if targets is not None:
        for item in slices:
            variant = item.get("SupportedPlatformVariant", "")
            target = next(row for row in targets if (row["target"]["sdk"] == "iphonesimulator") == (variant == "simulator"))
            directory = safe_path(path.parent, item["LibraryIdentifier"])
            library = safe_path(directory, item["LibraryPath"])
            headers = safe_path(directory, item["HeadersPath"])
            if file_hash(library) != target["library_sha256"] or file_hash(headers / "idevice.h") != target["header_sha256"]:
                raise VerificationError("packaged slice bytes differ from verified compiler outputs")
            if file_hash(safe_path(headers, "module.modulemap")) != file_hash(Path(target["headers"]) / "module.modulemap"):
                raise VerificationError("packaged module map changed")
            verified.append({"identifier": item["LibraryIdentifier"], "library_sha256": file_hash(library),
                             "header_sha256": target["header_sha256"]})
    return {"slices": verified, "metadata_sha256": file_hash(path), "binary_format_inspected": False}


def build_target(args, profile: dict, config: dict, provider, target: dict) -> dict:
    work = args.work_dir / target["rust"]
    work.mkdir()
    evidence = work / "completed"
    evidence.mkdir()
    source = work / "source"
    source_manifest, vendor_receipt, provider_receipt = {}, {}, None
    env, binaries = {}, {}
    header_evidence = None
    mixed = None
    header_retention_attempted = False
    try:
        env, binaries = native_environment(config, work)
        observations = bounded_toolchain(config, work, env, binaries, evidence)
        source_manifest = stage(args.source, source, HERE, PROFILE)
        (evidence / "source-manifest.json").write_bytes(canonical_json(source_manifest))
        namespace = namespace_contract(HERE, profile["export_namespace_sha256"])
        mixed = verify_mixed_provider(args.mixed_provider, target)
        (evidence / "mixed-provider-inputs.json").write_bytes(canonical_json(mixed))
        vendor_receipt = prepare_offline_vendor(source=source, work=work, cache=args.crate_cache, env=env,
                                               derive_metadata=True, export_namespace=namespace)
        (evidence / "vendor-layout.json").write_bytes(canonical_json(vendor_receipt))
        provider_receipt = provider.prepare_inputs(args.provider_inputs, work / "provider", target["rust"])
        (evidence / "provider-input-receipt.json").write_bytes(canonical_json(provider_receipt))
        prefix = target["rust"].upper().replace("-", "_") + "_"
        if provider_receipt["environment"].get(prefix + "OPENSSL_LIBS") != "" or provider_receipt["native_libraries"]:
            raise VerificationError("Apple Rust build requires present-empty LIBS and no native archives")
        env = provider.build_environment(env, provider_receipt)
        env.update({"DEVELOPER_DIR": config["developer_dir"], "IPHONEOS_DEPLOYMENT_TARGET": target["deployment"],
                    "CARGO_ENCODED_RUSTFLAGS": "--remap-path-prefix=" + str(work) + "=/tetherless-apple-build"})
        def run(argv, name):
            return capture_helper_command(argv, source=source, env=env, log=evidence / name)
        sdk = run(["/usr/bin/xcrun", "--sdk", target["sdk"], "--show-sdk-path"], "00-sdk-path.txt").strip()
        if not Path(sdk).is_absolute() or not Path(sdk).is_dir():
            raise VerificationError("selected SDK path missing")
        env["SDKROOT"] = sdk
        tools = {}
        suffix = target["rust"].replace("-", "_")
        for tool, key in (("clang", "CC_"), ("clang++", "CXX_"), ("ar", "AR_")):
            value = run(["/usr/bin/xcrun", "--sdk", target["sdk"], "--find", tool], "00-tool-" + tool + ".txt").strip()
            if not Path(value).is_absolute() or not Path(value).is_file():
                raise VerificationError("selected compiler/tool path missing")
            env[key + suffix], tools[key + suffix] = value, value
        header_probe = ["/usr/bin/xcrun", "--sdk", target["sdk"], "clang", "-target", target["clang"],
                        "-isysroot", sdk, "-I", str(Path(provider_receipt["view_root"]) / "include"),
                        "-fsyntax-only", "-Werror=incompatible-function-pointer-types", str(HERE / "split-provider/header_probe.c")]
        run(header_probe, "01-provider-header.txt")
        defaults = tomllib.loads((source / "ffi/Cargo.toml").read_text())["features"]["default"]
        graph = [binaries["cargo"], "tree", "--frozen", "-p", "idevice-ffi", "--target", target["rust"],
                 "--edges", "features", "--features", ",".join(target["extra_features"])]
        run(graph, "02-feature-graph.txt")
        if FORBIDDEN_FEATURE.encode() in read_bounded_log(evidence / "02-feature-graph.txt"):
            raise VerificationError("synthetic-peer feature is not permitted in Apple verification")
        cargo_command = release_command(binaries["cargo"], target)
        run(cargo_command, "03-release-build.txt")
        features = check_production_features(evidence / "03-release-build.txt", evidence / "02-feature-graph.txt", source, defaults, target)
        outputs = retain_openssl_outputs(provider, provider_receipt, evidence / "03-release-build.txt", work / "target" / target["rust"], evidence, "release")
        report = release_command(binaries["cargo"], target, report=True)
        run(report, "04-native-static-libs.txt")
        system_flags = system_link_flags(read_bounded_log(evidence / "04-native-static-libs.txt").decode())
        header_retention_attempted = True
        header_evidence = retain_headers(source, evidence)
        if any(row["status"] != "retained" for row in header_evidence["files"].values()):
            raise VerificationError("required generated header evidence was not retained")
        header_contract = verify_headers(source, HERE / "overlay/ffi/pairing_result_abi.h")
        (evidence / "pairing-result-header-check.json").write_bytes(canonical_json(header_contract))
        header = safe_path(source, "ffi/idevice.h").read_bytes()
        verify_generated_header(header, profile["required_ffi_symbols"])
        namespaced = public_header(header, namespace)
        header_namespace = {"schema": 1, "contract_sha256": profile["export_namespace_sha256"],
                            "generated_header_sha256": sha256(header), "public_header_sha256": sha256(namespaced),
                            "function_signatures_preserved": True, "parser_behavior_changed": False,
                            "old_symbol_aliases_emitted": False}
        (evidence / "ffi-header-namespace.json").write_bytes(canonical_json(header_namespace))
        (evidence / "namespaced-idevice.h").write_bytes(namespaced)
        headers = work / "headers"
        headers.mkdir()
        (headers / "idevice.h").write_bytes(namespaced)
        shutil.copyfile(source / "swift/include/module.modulemap", headers / "module.modulemap")
        library = safe_path(work / "target", target["rust"] + "/release/libidevice_ffi.a")
        if not library.is_file() or not library.stat().st_size:
            raise VerificationError("Rust static archive is missing")
        if str(library) not in features["ffi_artifact"]["filenames"]:
            raise VerificationError("selected Rust archive lacks its compiler-artifact identity")
        nm = ["/usr/bin/xcrun", "--sdk", target["sdk"], "nm", "-g", "-U", "-j"]
        rust_symbols = run(nm + [str(library)], "04-rust-export-symbols.txt")
        c_symbols = run(nm + [mixed["library"]], "04-c-export-symbols.txt")
        export_namespace = check_symbols(rust_symbols, namespace, target["rust"])
        export_namespace.update(check_mixed_symbols(rust_symbols, c_symbols))
        export_namespace["contract_sha256"] = profile["export_namespace_sha256"]
        (evidence / "ffi-export-namespace.json").write_bytes(canonical_json(export_namespace))
        links = []
        for group, probes in profile["probe_sets"].items():
            for language, probe in probes.items():
                path = safe_path(HERE, probe["path"])
                require_equal(file_hash(path), probe["sha256"], "link-probe source")
                binary = work / (group + "-" + language + "-probe")
                command = link_command(language=language, target=target, sdk=sdk, headers=headers, library=library,
                    probe=path, symbol=profile["probe_entry_symbols"][group][language], output=binary,
                    system_flags=system_flags, framework_flags=provider_receipt["final_link_arguments"])
                if group == "mixed_provider":
                    link_map = evidence / ("05-link-mixed_provider-" + language + ".map")
                    command += ["-I", mixed["headers"], "-I", str(Path(mixed["headers"]) / "libimobiledevice"),
                                "-Xlinker", "-force_load", "-Xlinker", mixed["library"],
                                "-Xlinker", "-map", "-Xlinker", str(link_map)]
                run(command, "05-link-" + group + "-" + language + ".txt")
                if binary.is_symlink() or not binary.is_file() or not binary.stat().st_size:
                    raise VerificationError("ordinary native link did not create its output")
                entry = {"group": group, "language": language, "command": command,
                         "output_sha256": file_hash(binary), "executed": False}
                if group == "mixed_provider":
                    if link_map.is_symlink() or not link_map.is_file() or not 0 < link_map.stat().st_size <= MAX_LOG_BYTES:
                        raise VerificationError("bounded mixed-provider linker map was not retained")
                    entry["link_map_sha256"] = file_hash(link_map)
                links.append(entry)
        result = {"target": target, "work": str(work), "source": str(source), "source_manifest": source_manifest,
                  "vendor_receipt": vendor_receipt, "provider_receipt": provider_receipt, "library": str(library),
                  "library_sha256": file_hash(library), "headers": str(headers), "header_sha256": file_hash(headers / "idevice.h"),
                  "toolchain_observations": observations, "sdk_root": sdk, "compiler_paths": tools,
                  "header_probe_command": header_probe, "header_probe_linked_or_executed": False,
                  "feature_graph_command": graph, "production_features": features, "build_command": cargo_command,
                  "result_header_contract": header_contract, "header_namespace": header_namespace,
                  "export_namespace": export_namespace, "mixed_provider": mixed,
                  "native_static_libs_command": report, "system_link_flags": system_flags, "openssl_outputs": outputs, "link_probes": links}
    finally:
        primary_failure = sys.exc_info()[0] is not None
        retention_error = None
        if not header_retention_attempted:
            try:
                retain_headers(source, evidence)
            except (OSError, VerificationError) as error:
                retention_error = error
        # Retaining header evidence must never bypass the four input audits or
        # replace an existing Cargo/import/link failure with a cleanup error.
        checks = retain_input_audits(source=source, source_manifest=source_manifest, vendor_receipt=vendor_receipt,
                                    provider=provider, provider_receipt=provider_receipt, completed=evidence)
        unchanged = all(checks[key]["original_inputs_unchanged"] for key in ("vendor", "derived_vendor", "workspace"))
        if mixed is not None:
            mixed_check = audit_mixed_provider(args.mixed_provider, target, mixed, verifier=verify_mixed_provider)
            try:
                (evidence / "mixed-provider-input-audit.json").write_bytes(canonical_json(mixed_check))
            except (OSError, ValueError) as error:
                mixed_check["original_inputs_unchanged"] = False
                if retention_error is None:
                    retention_error = error
            unchanged &= mixed_check["original_inputs_unchanged"]
        if retention_error is not None and not primary_failure:
            raise retention_error
        if (not unchanged or not checks["provider"]["unchanged"]) and not primary_failure:
            raise VerificationError("Apple target input audit failed; all four receipts retained")
    (evidence / "target-evidence.json").write_bytes(canonical_json(result))
    return result


def build(args) -> dict:
    profile = load_apple_profile()
    provider = load_provider()
    toolchain_bytes = args.toolchain_lock.read_bytes()
    require_equal(sha256(toolchain_bytes), args.toolchain_lock_sha256, "toolchain lock")
    config = json.loads(toolchain_bytes)
    if config.get("schema") != 1 or not isinstance(config.get("source_date_epoch"), int):
        raise VerificationError("invalid toolchain lock")
    recipe_bytes = (HERE / "apple-recipe-files.json").read_bytes()
    require_equal(sha256(recipe_bytes), args.recipe_lock_sha256, "Apple recipe inventory")
    recipe_files = json.loads(recipe_bytes)
    for name, digest in recipe_files.items():
        require_equal(file_hash(safe_path(HERE, name)), digest, "Apple recipe input")
    operation = safe_path(HERE, "xcframework_operation.py")
    operation_sha256 = recipe_files["xcframework_operation.py"]
    require_equal(file_hash(operation), operation_sha256, "XCFramework operation source")
    if args.work_dir.exists() or args.work_dir.is_symlink() or args.output.exists() or args.output.is_symlink():
        raise VerificationError("Apple work/output roots must be fresh")
    args.work_dir.mkdir(parents=True)
    targets = []
    package = args.work_dir / "package"
    provenance = package / "provenance"
    try:
        for target in TARGETS:
            targets.append(build_target(args, profile, config, provider, target))
        if (targets[0]["source_manifest"]["files"] != targets[1]["source_manifest"]["files"]
                or targets[0]["source_manifest"]["symlinks"] != targets[1]["source_manifest"]["symlinks"]):
            raise VerificationError("production source inputs differ between Apple targets")
        if targets[0]["header_sha256"] != targets[1]["header_sha256"]:
            raise VerificationError("generated FFI headers differ between Apple targets")
        package.mkdir()
        provenance.mkdir()
        command = ["/usr/bin/xcodebuild", "-create-xcframework"]
        for target in targets:
            command += ["-library", target["library"], "-headers", target["headers"]]
        command += ["-output", str(package / "IDevice.xcframework")]
        package_env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "DEVELOPER_DIR": config["developer_dir"],
                       "HOME": str(args.work_dir / TARGETS[0]["rust"] / "home"), "TMPDIR": str(args.work_dir / TARGETS[0]["rust"] / "tmp")}
        # Keep the supervised leader alive until its fixed xcodebuild child and
        # that child's natural helper tail have left the owned process group.
        operation_command = [sys.executable, "-I", str(operation)]
        for target in targets:
            operation_command += [target["library"], target["headers"]]
        operation_command += [str(package / "IDevice.xcframework")]
        capture_helper_command(operation_command, source=args.work_dir, env=package_env, log=args.work_dir / "create-xcframework.txt")
        slice_receipt = verify_slice_metadata(package / "IDevice.xcframework/Info.plist", targets)
        shutil.copyfile(HERE / PROFILE, provenance / "apple-verification.json")
        shutil.copyfile(args.mixed_provider / "authenticated-provider.zip", provenance / "mixed-provider-archive.zip")
        (provenance / "toolchain-lock.json").write_bytes(toolchain_bytes)
        (provenance / "recipe-files.json").write_bytes(recipe_bytes)
        shutil.copyfile(Path(targets[0]["source"]) / "LICENSE.txt", package / "LICENSE-idevice.txt")
        shutil.copyfile(Path(targets[0]["provider_receipt"]["view_root"]) / "LICENSE.txt", package / "LICENSE-OpenSSL.txt")
        source_receipt = create_source_bundle(source=Path(targets[0]["source"]), source_manifest=targets[0]["source_manifest"],
            vendor_receipt=targets[0]["vendor_receipt"], crate_cache=args.crate_cache, recipe_root=HERE,
            recipe_files=recipe_files, output=package / "corresponding-source.zip", staging=args.work_dir / "source-bundle")
        (provenance / "source-bundle.json").write_bytes(canonical_json(source_receipt))
    finally:
        primary_failure = sys.exc_info()[0] is not None
        clean = True
        for row in targets:
            checks = retain_input_audits(source=Path(row["source"]), source_manifest=row["source_manifest"], vendor_receipt=row["vendor_receipt"],
                provider=provider, provider_receipt=row["provider_receipt"], completed=Path(row["work"]) / "completed")
            clean &= all(checks[k]["original_inputs_unchanged"] for k in ("vendor", "derived_vendor", "workspace")) and checks["provider"]["unchanged"]
            mixed_check = audit_mixed_provider(args.mixed_provider, row["target"], row["mixed_provider"], verifier=verify_mixed_provider)
            try:
                (Path(row["work"]) / "completed/mixed-provider-packaging-audit.json").write_bytes(canonical_json(mixed_check))
            except (OSError, ValueError):
                mixed_check["original_inputs_unchanged"] = False
            clean &= mixed_check["original_inputs_unchanged"]
        if not clean and not primary_failure:
            raise VerificationError("Apple packaging input audit failed")
    for row in targets:
        destination = provenance / row["target"]["rust"]
        shutil.copytree(Path(row["work"]) / "completed", destination)
    shutil.copyfile(args.work_dir / "create-xcframework.txt", package / "provenance/create-xcframework.txt")
    shutil.copyfile(args.work_dir / "create-xcframework.txt.status.json", package / "provenance/create-xcframework.txt.status.json")
    receipt = {"schema": 1, "profile_sha256": PROFILE_SHA256, "targets": targets, "xcframework_command": command,
               "mixed_c_provider_link_probes_only": True, "mixed_c_provider_embedded_in_IDevice": False,
               "xcframework_operation_command": operation_command, "xcframework_operation_sha256": operation_sha256,
               "xcframework_slice_receipt": slice_receipt,
               "toolchain_lock_sha256": sha256(toolchain_bytes), "recipe_lock_sha256": sha256(recipe_bytes),
               "source_bundle": source_receipt, "framework_provider_bundled": False, "ios_binaries_executed": False,
               "source_binary_equivalence_claimed": False, "consumer_or_product_activation": False,
               "process_limits": {"command_seconds": COMMAND_TIMEOUT_SECONDS, "log_bytes": MAX_LOG_BYTES}, "files": inventory(package)}
    (package / "apple-build-evidence.json").write_bytes(canonical_json(receipt))
    (package / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in inventory(package).items()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    os.rename(package, args.output)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "crate-cache", "provider-inputs", "mixed-provider", "work-dir", "output", "toolchain-lock"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--toolchain-lock-sha256", required=True)
    parser.add_argument("--recipe-lock-sha256", required=True)
    args = parser.parse_args()
    for name in ("source", "crate_cache", "provider_inputs", "mixed_provider", "work_dir", "output", "toolchain_lock"):
        setattr(args, name, getattr(args, name).absolute())
    try:
        result = build(args)
    except (VerificationError, OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Apple dependency verification failed: {exc}\n")
    print(json.dumps({"targets": [t["target"]["rust"] for t in result["targets"]], "output": str(args.output)}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
