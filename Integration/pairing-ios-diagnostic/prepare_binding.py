#!/usr/bin/env python3
"""Prepare an owned diagnostic app copy bound to an exact local Apple artifact."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import plistlib
import shutil
import sys
from native_handoff import verify_handoff, add_handoff_arguments, context_from_args
from namespace_gateway import GATEWAY_PATH, RENAMES as GATEWAY_RENAMES, transform_gateway
from diagnostic_link_project import PROJECT_PATH, PROJECT_SHA256, PROJECT_GIT_BLOB, patch_project

HERE = Path(__file__).resolve().parent
# These are current-recipe helpers, not downloaded code. bind() authenticates
# the complete recipe before admitting artifact/header/source transformations.
sys.path.insert(0, str(HERE.parent / "Dependencies/idevice"))
try:
    import ffi_namespace
    import mixed_provider
    import retained_c_provider
    import rust_symbol_reader
    import symbol_visibility
    from apply_patch import canonical_json
finally:
    sys.path.pop(0)
MAX_RECEIPT = 64 * 1024 * 1024
OLD_TARGET = '''         .binaryTarget(
             name: "IDevice",
             url: "https://github.com/SideStore/idevice/releases/download/v0.1.68-ss-3e55c84/idevice-xcframework-v0.1.68-ss-3e55c84.zip#DeviceGateway",
             checksum: "445702d53942597deb4cdec2c4122d16a3f4ac124ce26cd75b68dab3dad92416"
         ),'''

OLD_C_TARGET = '''        .binaryTarget(
            name: "libimobiledevice",
            url: "https://github.com/SideStore/libimobiledevice-xcframework/releases/download/1.4.0-ss-0f88f7b/libimobiledevice.xcframework.zip#DeviceGateway",
            checksum: "7ccbdd56b074807461fc43d2e32ba92f20df2501a6c14cf9f64a917e7f3fe6e7"
        ),'''
C_ROOT = "provenance/retained-c-provider"
C_PRODUCT = C_ROOT + "/product/libimobiledevice.xcframework"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def safe_file(root: Path, name: str) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("diagnostic input root is missing or a symlink")
    relative = PurePosixPath(name)
    if relative.is_absolute() or not relative.parts or any(p in ("..", ".") for p in relative.parts):
        raise ValueError("unsafe diagnostic input path")
    path = root
    for part in relative.parts:
        path /= part
        if path.is_symlink():
            raise ValueError("diagnostic input is a symlink")
    if not path.is_file():
        raise ValueError("diagnostic input file is missing")
    return path


def read_json(path: Path, expected: str | None = None) -> dict:
    with path.open("rb") as stream:
        data = stream.read(MAX_RECEIPT + 1)
    if len(data) > MAX_RECEIPT or (expected is not None and digest(data) != expected):
        raise ValueError("diagnostic JSON size or identity differs")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("diagnostic JSON must be an object")
    return value


def read_contract() -> dict:
    return read_json(HERE / "input-contract.json")


def verify_recipe_inputs(recipe: Path | None, contract: dict) -> dict:
    if recipe is None:
        raise ValueError("current native recipe is required before diagnostic binding")
    index = read_json(safe_file(recipe, "apple-recipe-files.json"), contract["apple_recipe_index_sha256"])
    for name, expected in index.items():
        if file_hash(safe_file(recipe, name)) != expected:
            raise ValueError("current native recipe source differs from the Apple producer")
    return {"index_sha256": contract["apple_recipe_index_sha256"], "checked_files": len(index)}


def patched_gateway(original: bytes, contract: dict) -> bytes:
    expected = contract["gateway"]
    blob = hashlib.sha1(b"blob " + str(len(original)).encode() + b"\0" + original).hexdigest()
    if digest(original) != expected["sha256"] or blob != expected["git_blob"]:
        raise ValueError("gateway manifest does not match the pinned DeviceGateway preimage")
    source = original.decode()
    if source.count(OLD_TARGET) != 1:
        raise ValueError("exact IDevice release declaration not found once")
    replacement = ('         .binaryTarget(\n             name: "IDevice",\n'
                   '             path: "' + expected["local_binary_path"] + '"\n         ),')
    if source.count(OLD_C_TARGET) != 1:
        raise ValueError("exact libimobiledevice release declaration not found once")
    c_replacement = ('        .binaryTarget(\n            name: "libimobiledevice",\n'
                     '            path: "' + expected["local_c_binary_path"] + '"\n        ),')
    return source.replace(OLD_TARGET, replacement, 1).replace(OLD_C_TARGET, c_replacement, 1).encode()


def new_output_path(root: Path, relative: str, *, create_parents: bool = False) -> Path:
    """Reject copied symlinks and existing files at an explicitly reserved output."""
    path = PurePosixPath(relative)
    if (root.is_symlink() or not root.is_dir() or path.is_absolute() or not path.parts
            or path.as_posix() != relative or any(part in (".", "..") for part in path.parts)):
        raise ValueError("invalid owned diagnostic output path")
    current = root
    for part in path.parts[:-1]:
        current /= part
        if current.is_symlink() or (current.exists() and not current.is_dir()):
            raise ValueError("reserved diagnostic output parent is not an owned directory")
        if create_parents and not current.exists():
            current.mkdir()
    output = current / path.parts[-1]
    if output.exists() or output.is_symlink():
        raise ValueError("reserved diagnostic output already exists")
    return output


def composition_inputs(root: Path, contract: dict) -> dict:
    files = {}
    for selected in (contract["prepared_composition_sources"], contract["prepared_support_sources"]):
        for name, item in selected.items():
            actual = file_hash(safe_file(root, name))
            if actual != item["sha256"]:
                raise ValueError("prepared composition/support source differs: " + name)
            files[name] = actual
    if contract.get("diagnostic_project") != {"prepared_path": PROJECT_PATH, "sha256": PROJECT_SHA256,
            "git_blob": PROJECT_GIT_BLOB, "linker_flag_targets": ["SideStore"], "configurations": ["Debug", "Release"]}:
        raise ValueError("diagnostic project target-scope contract differs")
    project = safe_file(root, PROJECT_PATH).read_bytes()
    patch_project(project)
    files[PROJECT_PATH] = digest(project)
    package = contract["gateway"]["prepared_path"]
    original = safe_file(root, package).read_bytes()
    patched_gateway(original, contract)
    files[package] = digest(original)
    gateway_source = "Dependencies/minimuxer/DeviceGateway/idevice/IdeviceGateway.swift"
    files[gateway_source] = file_hash(safe_file(root, gateway_source))
    return files


def verify_result_header_evidence(root: Path, receipt: dict, target: str, row: dict, contract: dict, mixed: dict, archives: dict) -> dict:
    """Bind the new producer's retained header and six link receipts to its ZIP-authenticated inventory."""
    prefix = "provenance/" + target + "/"

    def retained_json(name):
        relative = prefix + name
        expected = receipt["files"].get(relative)
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError("required native header/link evidence is not in the authenticated inventory")
        return read_json(safe_file(root, relative), expected)

    checked = retained_json("pairing-result-header-check.json")
    if (checked != row.get("result_header_contract") or checked.get("schema") != 1
            or checked.get("unrelated_nonempty_lines_identical") is not True
            or checked.get("blank_item_separators_ignored") is not True
            or checked.get("native_import_or_link_established_by_this_check") is not False
            or checked.get("cpp_header_identical") is not True
            or checked.get("declarations_sha256") != contract["result_header_contract"]["declarations_sha256"]
            or checked.get("final_header_sha256") != row.get("header_namespace", {}).get("generated_header_sha256")):
        raise ValueError("native result header comparison differs from the reviewed producer")
    retained = retained_json("generated-header-retention.json")
    expected_headers = {
        "ffi/idevice.cbindgen-baseline.h": checked.get("baseline_sha256"),
        "ffi/idevice.cbindgen-scoped.h": checked.get("scoped_sha256"),
        "ffi/idevice.h": checked["final_header_sha256"],
        "cpp/include/idevice.h": checked["final_header_sha256"],
    }
    limit = contract["result_header_contract"]["per_file_byte_limit"]
    if (retained.get("schema") != 1 or retained.get("per_file_byte_limit") != limit
            or set(retained.get("files", {})) != set(expected_headers)):
        raise ValueError("native result header retention inventory differs")
    for name, expected in expected_headers.items():
        relative = prefix + "generated-headers/" + name
        item = retained["files"][name]
        path = safe_file(root, relative)
        if (item.get("status") != "retained" or item.get("sha256") != expected
                or receipt["files"].get(relative) != expected
                or type(item.get("bytes")) is not int or not 0 < item["bytes"] <= limit
                or path.stat().st_size != item["bytes"] or file_hash(path) != expected):
            raise ValueError("native result header bytes differ from retained comparison")
    from native_handoff import _success
    for group in ("pairing", "host", "result_constants"):
        for language in ("c", "swift"):
            _success(retained_json("05-link-" + group + "-" + language + ".txt.status.json"))
    namespace = ffi_namespace.load_contract(expected_sha256=contract["ffi_namespace_sha256"])
    header = safe_file(root, prefix + "generated-headers/ffi/idevice.h").read_bytes()
    expected_header = ffi_namespace.public_header(header, namespace)
    namespaced_path = prefix + "namespaced-idevice.h"
    if (receipt["files"].get(namespaced_path) != digest(expected_header)
            or safe_file(root, namespaced_path).read_bytes() != expected_header
            or row["header_sha256"] != digest(expected_header)):
        raise ValueError("native public header differs from the exact namespace transform")
    expected_header_receipt = {"schema": 1, "contract_sha256": contract["ffi_namespace_sha256"],
        "generated_header_sha256": digest(header), "public_header_sha256": digest(expected_header),
        "function_signatures_preserved": True, "parser_behavior_changed": False, "old_symbol_aliases_emitted": False}
    if retained_json("ffi-header-namespace.json") != expected_header_receipt or row.get("header_namespace") != expected_header_receipt:
        raise ValueError("native header namespace evidence differs")
    def retained_bytes(name, limit=MAX_RECEIPT):
        relative = prefix + name
        with safe_file(root, relative).open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit or receipt["files"].get(relative) != digest(data):
            raise ValueError("native export/link evidence differs from authenticated inventory")
        return data
    def retained_text(name):
        return retained_bytes(name).decode("utf-8")
    rust = retained_text("04-rust-export-symbols.txt")
    c_provider = retained_text("04-c-export-symbols.txt")
    retained_c_provider.exported(rust, unique=False)
    c_contract = retained_c_provider.check_symbols(c_provider, mixed["symbols"])
    if (retained_json("retained-c-export-contract.json") != c_contract
            or row.get("c_export_contract") != c_contract
            or row.get("retained_c_handoff_sha256") != mixed["handoff_sha256"]):
        raise ValueError("native full C export or handoff receipt differs")
    expected_exports = mixed_provider.check_symbols(rust, namespace, target)
    expected_exports.update(mixed_provider.check_mixed_symbols(rust, c_provider))
    expected_exports["contract_sha256"] = contract["ffi_namespace_sha256"]
    if retained_json("ffi-export-namespace.json") != expected_exports or row.get("export_namespace") != expected_exports:
        raise ValueError("native export namespace evidence differs")
    reader = retained_json("symbol-reader.json")
    rust_symbol_reader.validate_receipt(reader, contract.get("symbol_reader"))
    lock = read_json(safe_file(root, "provenance/toolchain-lock.json"), receipt["toolchain_lock_sha256"])
    if (reader != row.get("symbol_reader") or reader != lock.get("symbol_reader")
            or reader["rustc"]["version"] != row["toolchain_observations"].get("rustc")
            or reader["rustc"]["version"] != lock.get("observations", {}).get("rustc")
            or {key: reader["rustc"][key] for key in ("path", "sha256")} != lock.get("executables", {}).get("rustc")):
        raise ValueError("retained symbol reader differs from the compiler/toolchain lock")
    for name, command, expected in (
            ("toolchain-symbol-rustc.txt", [reader["rustc"]["path"], "--version", "--verbose"], reader["rustc"]["version"]),
            ("toolchain-symbol-sysroot.txt", [reader["rustc"]["path"], "--print", "sysroot"], reader["sysroot"]),
            ("toolchain-llvm-nm.txt", [reader["llvm_nm"]["path"], "--version"], reader["llvm_nm"]["version"])):
        status = retained_json(name + ".status.json")
        _success(status)
        if status.get("command") != command or retained_text(name).strip() != expected:
            raise ValueError("symbol-reader version observation differs from retained identity")
    for name, archive in (("04-rust-export-symbols.txt", row["library"]),
                          ("04-c-export-symbols.txt", row["mixed_provider"]["library"])):
        status = retained_json(name + ".status.json")
        _success(status)
        if status.get("command") != rust_symbol_reader.scan_command(reader, archive):
            raise ValueError("full archive symbol scan used a different reader, flags or archive")
    visibility = symbol_visibility.load_evidence(retained_bytes, target=target, reader=reader,
        archives=archives, context={"source_manifest_sha256": digest(canonical_json(row["source_manifest"])),
                                   "recipe_lock_sha256": receipt["recipe_lock_sha256"]}, links=row["link_probes"])
    for language in ("c", "swift"):
        _success(retained_json("05-link-mixed_provider-" + language + ".txt.status.json"))
        link_map = retained_bytes("05-link-mixed_provider-" + language + ".map", retained_c_provider.MAX_TEXT)
        probes = [p for p in row["link_probes"] if p["group"] == "mixed_provider" and p["language"] == language]
        if len(probes) != 1 or not link_map or probes[0].get("link_map_sha256") != digest(link_map):
            raise ValueError("native mixed-provider link map evidence differs")
        ownership = retained_c_provider.link_ownership(link_map, row["mixed_provider"]["library"], mixed["symbols"],
            row["library"], {"_" + name for name in namespace["expected_target_exports"][target]["after"]},
            visibility=visibility)
        if (retained_json("05-link-mixed_provider-" + language + "-ownership.json") != ownership
                or probes[0].get("ownership") != ownership):
            raise ValueError("native full C/required Rust live ownership receipt differs")
    if retained_json("mixed-provider-input-audit.json").get("original_inputs_unchanged") is not True:
        raise ValueError("native mixed-provider input audit failed")
    return visibility


def artifact_inputs(root: Path, expected_receipt: str, contract: dict) -> dict:
    receipt = read_json(safe_file(root, "apple-build-evidence.json"), expected_receipt)
    if (receipt["profile_sha256"] != contract["apple_profile_sha256"]
            or receipt["recipe_lock_sha256"] != contract["apple_recipe_index_sha256"]
            or receipt["framework_provider_bundled"] is not False
            or receipt["ios_binaries_executed"] is not False
            or receipt["consumer_or_product_activation"] is not False):
        raise ValueError("Apple artifact is outside the diagnostic production recipe")
    if (receipt.get("mixed_c_provider_link_probes_only") is not True
            or receipt.get("mixed_c_provider_embedded_in_IDevice") is not False):
        raise ValueError("Apple artifact lacks the isolated mixed-provider verification")
    c_handoff_sha256 = receipt.get("retained_c_handoff_sha256")
    if (not isinstance(c_handoff_sha256, str) or len(c_handoff_sha256) != 64
            or any(c not in "0123456789abcdef" for c in c_handoff_sha256)):
        raise ValueError("Apple artifact lacks the caller-bound retained C handoff")
    # Authenticate the entire nested C handoff. It travels inside the existing
    # Apple lane; the consumer never fetches a sixth artifact or executes its code.
    nested_files = {name: expected for name, expected in receipt["files"].items()
                    if name.startswith(C_ROOT + "/")}
    actual_nested = {}
    nested_root = root / C_ROOT
    if nested_root.is_symlink() or not nested_root.is_dir():
        raise ValueError("retained C handoff tree is missing")
    for path in sorted(nested_root.rglob("*")):
        if path.is_symlink():
            raise ValueError("retained C handoff tree contains a symlink")
        if path.is_file():
            actual_nested[path.relative_to(root).as_posix()] = file_hash(path)
    if (not nested_files or nested_files != actual_nested
            or receipt.get("retained_c_provider_files") != {
                name.removeprefix(C_ROOT + "/"): value for name, value in nested_files.items()}):
        raise ValueError("retained C handoff bytes differ from Apple artifact inventory")
    c_targets, rust_symbols, visibility = {}, {}, {}
    targets = {row["target"]["rust"]: row for row in receipt["targets"]}
    if len(receipt["targets"]) != 2 or set(targets) != {"aarch64-apple-ios", "aarch64-apple-ios-sim"}:
        raise ValueError("both exact Apple target receipts are required")
    expected = {name: value for name, value in receipt["files"].items() if name.startswith("IDevice.xcframework/")}
    directory = root / "IDevice.xcframework"
    actual = {}
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("local Rust XCFramework is missing")
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("local Rust XCFramework contains a symlink")
        if path.is_file():
            actual[path.relative_to(root).as_posix()] = file_hash(path)
    if not expected or actual != expected:
        raise ValueError("local XCFramework bytes differ from its native build receipt")
    info = plistlib.loads(safe_file(root, "IDevice.xcframework/Info.plist").read_bytes())
    rows = info["AvailableLibraries"]
    if len(rows) != 2:
        raise ValueError("expected two XCFramework slices")
    identities = set()
    device_slice, rust_archives = {}, {}
    for row in rows:
        variant = row.get("SupportedPlatformVariant", "")
        identities.add((row["SupportedPlatform"], variant, tuple(row["SupportedArchitectures"])))
        target = targets["aarch64-apple-ios-sim" if variant == "simulator" else "aarch64-apple-ios"]
        prefix = "IDevice.xcframework/" + row["LibraryIdentifier"] + "/"
        if (file_hash(safe_file(root, prefix + row["LibraryPath"])) != target["library_sha256"]
                or file_hash(safe_file(root, prefix + row["HeadersPath"] + "/idevice.h")) != target["header_sha256"]):
            raise ValueError("packaged native library/header identity differs")
        library_path = safe_file(root, prefix + row["LibraryPath"])
        rust_archives[target["target"]["rust"]] = {
            "source": target["library"], "sha256": target["library_sha256"], "bytes": library_path.stat().st_size}
        if variant == "":
            device_slice = {"archive": prefix + row["LibraryPath"],
                            "header": prefix + row["HeadersPath"] + "/idevice.h",
                            "module_map": prefix + row["HeadersPath"] + "/module.modulemap"}
            for name in device_slice.values():
                if name not in expected:
                    raise ValueError("device module/header/archive is absent from the artifact inventory")
    if identities != {("ios", "", ("arm64",)), ("ios", "simulator", ("arm64",))}:
        raise ValueError("diagnostic requires device and Simulator arm64 slice metadata")
    for target, row in targets.items():
        mixed = retained_c_provider.verify(nested_root, row["target"],
                                           expected_handoff_sha256=c_handoff_sha256)
        # Absolute producer paths identify retained commands/maps, not local
        # input locations. Every non-path identity must match the nested proof.
        original = row.get("mixed_provider", {})
        if ({key: value for key, value in original.items() if key not in ("library", "headers")}
                != {key: value for key, value in mixed.items() if key not in ("library", "headers")}
                or not all(isinstance(original.get(key), str) and Path(original[key]).is_absolute()
                           for key in ("library", "headers"))):
            raise ValueError("Rust mixed-provider identity differs from the retained C handoff")
        c_targets[target] = mixed
        provider = row["provider_receipt"]
        observations = row.get("toolchain_observations", {})
        if any(not isinstance(observations.get(name), str) or not observations[name] for name in
               ("xcode", "clang", "swiftc", "sdk_iphoneos_version", "sdk_iphoneos_build")):
            raise ValueError("Apple target has no complete retained compiler/SDK identity")
        prefix = target.upper().replace("-", "_") + "_"
        probes = {(p["group"], p["language"]) for p in row["link_probes"]}
        if (probes != {(group, language) for group in ("pairing", "host", "result_constants", "mixed_provider") for language in ("c", "swift")}
                or len(row["link_probes"]) != 8 or any(p["executed"] is not False for p in row["link_probes"])
                or provider["kind"] != "apple-framework-consumer" or provider["native_libraries"]
                or provider["environment"].get(prefix + "OPENSSL_LIBS") != ""
                or row["production_features"]["synthetic_peer_selected"] is not False
                or row["header_probe_linked_or_executed"] is not False):
            raise ValueError("native composition/provider probe receipt is incomplete")
        retained_c_provider.verify_provider(mixed, provider)
        retained_c_provider.verify_sdk(mixed, observations)
        c_library = safe_file(nested_root / "product", mixed["library_relative"])
        if file_hash(c_library) != mixed["library_sha256"]:
            raise ValueError("retained C archive identity changed before visibility validation")
        archives = {"rust": rust_archives[target], "c": {"source": row["mixed_provider"]["library"],
            "sha256": mixed["library_sha256"], "bytes": c_library.stat().st_size}}
        visibility[target] = verify_result_header_evidence(root, receipt, target, row, contract, mixed, archives)
        rust_symbols[target] = list(visibility[target]["archives"]["rust"]["external_symbols"])
    c_files = {name.removeprefix(C_ROOT + "/product/"): value
               for name, value in nested_files.items() if name.startswith(C_PRODUCT + "/")}
    c_device = c_targets["aarch64-apple-ios"]
    c_device_slice = {"archive": c_device["library_relative"],
                      "header": c_device["headers_relative"] + "/plist/plist.h",
                      "module_map": c_device["headers_relative"] + "/libimobiledevice/module.modulemap"}
    return {"receipt_sha256": expected_receipt, "files": expected,
            "c_files": c_files, "c_targets": c_targets, "c_device_slice": c_device_slice, "rust_symbols": rust_symbols,
            "retained_c_handoff_sha256": c_handoff_sha256, "symbol_visibility": visibility,
            "recipe_index_sha256": receipt["recipe_lock_sha256"], "targets": targets,
            "toolchain_lock_sha256": receipt["toolchain_lock_sha256"], "device_slice": device_slice,
            "binary_format_inspected": False}


def bind(prepared: Path, artifact: Path, expected_artifact_receipt: str, output: Path, *,
         handoff_path: Path | None = None, handoff_sha256: str | None = None,
         context: dict | None = None, native_recipe: Path | None = None) -> dict:
    contract = read_contract()
    handoff = verify_handoff(contract, handoff_path, handoff_sha256, context, artifact, expected_artifact_receipt, native_recipe)
    recipe = verify_recipe_inputs(native_recipe, contract)
    gate = safe_file(HERE.parent, contract["preparation_gate"]["path"])
    if file_hash(gate) != contract["preparation_gate"]["sha256"]:
        raise ValueError("reviewed preparation capability gate changed")
    prepared, artifact = prepared.resolve(strict=True), artifact.resolve(strict=True)
    if output.is_symlink():
        raise ValueError("diagnostic output is a symlink")
    output = output.resolve(strict=False)
    if (output.exists() or output.is_relative_to(prepared) or prepared.is_relative_to(output)
            or output.is_relative_to(artifact) or artifact.is_relative_to(output)):
        raise ValueError("diagnostic copy must be fresh and separate from its prepared source")
    source_inputs = composition_inputs(prepared, contract)
    namespace = ffi_namespace.load_contract(expected_sha256=contract["ffi_namespace_sha256"])
    if any(namespace["header_identifiers"].get(old) != new for old, new in GATEWAY_RENAMES.items()):
        raise ValueError("gateway identifiers differ from the authenticated producer namespace")
    gateway_postimage = transform_gateway(safe_file(prepared, GATEWAY_PATH).read_bytes())
    native = artifact_inputs(artifact, expected_artifact_receipt, contract)
    local_relative = (Path(contract["gateway"]["prepared_path"]).parent / contract["gateway"]["local_binary_path"]).as_posix()
    local_c_relative = (Path(contract["gateway"]["prepared_path"]).parent / contract["gateway"]["local_c_binary_path"]).as_posix()
    receipt_relative = "TETHERLESS_PAIRING_DIAGNOSTIC_BINDING.json"
    new_output_path(prepared, local_relative)
    new_output_path(prepared, local_c_relative)
    new_output_path(prepared, receipt_relative)
    sentinel = (HERE / "PairingCompositionCompileSentinel.swift").read_bytes()
    if digest(sentinel) != contract["sentinel"]["sha256"]:
        raise ValueError("compile sentinel changed")
    # Preserve the prepared app/dependency tree; only the explicit diagnostic
    # manifest, Rust gateway, sentinel and local artifact postimages differ. Git administration is not needed by xcodebuild.
    shutil.copytree(prepared, output, symlinks=True, ignore=shutil.ignore_patterns(".git"))
    composition_inputs(output, contract)
    package = safe_file(output, contract["gateway"]["prepared_path"])
    local = new_output_path(output, local_relative, create_parents=True)
    new_output_path(output, receipt_relative)
    local_c = new_output_path(output, local_c_relative, create_parents=True)
    shutil.copytree(artifact / "IDevice.xcframework", local)
    shutil.copytree(artifact / C_PRODUCT, local_c)
    bound_files = dict(source_inputs)
    project = safe_file(output, PROJECT_PATH)
    project.write_bytes(patch_project(project.read_bytes()))
    bound_files[PROJECT_PATH] = file_hash(project)
    safe_file(output, GATEWAY_PATH).write_bytes(gateway_postimage)
    bound_files[GATEWAY_PATH] = digest(gateway_postimage)
    package.write_bytes(patched_gateway(package.read_bytes(), contract))
    bound_files[contract["gateway"]["prepared_path"]] = file_hash(package)
    onboarding = safe_file(output, contract["sentinel"]["prepared_path"])
    onboarding.write_bytes(onboarding.read_bytes() + b"\n" + sentinel)
    bound_files[contract["sentinel"]["prepared_path"]] = file_hash(onboarding)
    for name, expected in {**native["files"], **native["c_files"]}.items():
        copied = local.parent / name
        if file_hash(safe_file(local.parent, name)) != expected:
            raise ValueError("copied local XCFramework changed")
        bound_files[copied.relative_to(output).as_posix()] = expected
    if composition_inputs(prepared, contract) != source_inputs:
        raise ValueError("prepared input changed during diagnostic copying")
    artifact_inputs(artifact, expected_artifact_receipt, contract)
    if verify_handoff(contract, handoff_path, handoff_sha256, context, artifact, expected_artifact_receipt, native_recipe) != handoff:
        raise ValueError("native handoff changed during diagnostic copying")
    if verify_recipe_inputs(native_recipe, contract) != recipe:
        raise ValueError("current native recipe changed during diagnostic copying")
    if file_hash(gate) != contract["preparation_gate"]["sha256"]:
        raise ValueError("reviewed preparation capability gate changed during copying")
    receipt = {"schema": 1, "mode": "diagnostic-only", "prepared_source": str(prepared),
               "diagnostic_root": str(output), "source_inputs": source_inputs, "bound_files": bound_files,
               "native_artifact": native, "native_handoff": handoff, "native_recipe": recipe,
               "sentinel_sha256": digest(sentinel),
               "contract_sha256": file_hash(HERE / "input-contract.json"),
               "runtime_capability_gates_changed": False, "consumer_or_product_activation": False,
               "native_or_app_build_executed": False}
    receipt["local_device_files"] = {key: (local.parent / name).relative_to(output).as_posix()
                                     for key, name in native["device_slice"].items()}
    receipt["local_c_device_files"] = {key: (local_c.parent / name).relative_to(output).as_posix()
                                       for key, name in native["c_device_slice"].items()}
    receipt["preparation_gate"] = {"path": str(gate), "sha256": contract["preparation_gate"]["sha256"]}
    receipt_path = new_output_path(output, receipt_relative)
    with receipt_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("prepared-source", "apple-artifact", "diagnostic-output", "native-recipe"):
        parser.add_argument("--" + option, required=True, type=Path)
    parser.add_argument("--apple-artifact-receipt-sha256", required=True)
    add_handoff_arguments(parser)
    args = parser.parse_args()
    try:
        receipt = bind(args.prepared_source, args.apple_artifact, args.apple_artifact_receipt_sha256, args.diagnostic_output,
                       handoff_path=args.native_handoff, handoff_sha256=args.native_handoff_sha256,
                       context=context_from_args(args), native_recipe=args.native_recipe)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, str(error) + "\n")
    print(json.dumps({"diagnostic_root": receipt["diagnostic_root"], "native_build_executed": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
