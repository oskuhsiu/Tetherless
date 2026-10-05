#!/usr/bin/env python3
"""Offline native build of review-locked idevice sources. Installs nothing.

The native compiler/SDK observations and executable digests must match a
separately reviewed toolchain lock. A missing value is a hard failure.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import plistlib
import platform
import re
import shlex
import shutil
import subprocess
import tarfile
import tomllib
import zipfile

from apply_patch import HERE, VerificationError, canonical_json, load_lock, safe_path, sha256, stage, safe_source_link

TARGETS = (
    ("aarch64-apple-ios", "iphoneos", "IPHONEOS_DEPLOYMENT_TARGET", "17.0", ["obfuscate"]),
    ("aarch64-apple-ios-sim", "iphonesimulator", "IPHONEOS_DEPLOYMENT_TARGET", "17.0", []),
)


def run(command: list[str], *, cwd: Path, env: dict[str, str], capture: bool = True) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else ""


def locked_packages(lock_bytes: bytes) -> list[dict]:
    packages = tomllib.loads(lock_bytes.decode())["package"]
    names = set()
    result = []
    for package in packages:
        if "source" not in package:
            continue
        if package["source"] != "registry+https://github.com/rust-lang/crates.io-index":
            raise VerificationError("unreviewed non-crates.io dependency")
        name, version = package["name"], package["version"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name) or not re.fullmatch(r"[A-Za-z0-9.+_-]+", version):
            raise VerificationError("unsafe crate identity")
        if not re.fullmatch(r"[a-f0-9]{64}", package.get("checksum", "")):
            raise VerificationError("missing registry checksum")
        key = f"{name}-{version}"
        if key in names:
            raise VerificationError("duplicate registry identity")
        names.add(key)
        result.append(package)
    return result


def vendor_crates(lock_bytes: bytes, cache: Path, destination: Path) -> dict[str, str]:
    """Authenticate every .crate archive before using its content.

    This ignores unpacked Cargo caches. Only lock-authenticated regular files are
    extracted; links, path traversal, duplicate members and oversized input fail.
    """
    if destination.exists():
        raise VerificationError("vendor directory must be new")
    packages = locked_packages(lock_bytes)
    authenticated = []
    for package in packages:
        stem = f"{package['name']}-{package['version']}"
        archive = safe_path(cache, stem + ".crate")
        if not archive.is_file() or archive.stat().st_size > 256 * 1024 * 1024:
            raise VerificationError(f"missing/oversized cached crate: {stem}")
        if file_hash(archive) != package["checksum"]:
            raise VerificationError(f"crate checksum mismatch: {stem}")
        authenticated.append((package, archive))
    destination.mkdir()
    results = {}
    for package, archive in authenticated:
        stem = f"{package['name']}-{package['version']}"
        folder = destination / stem
        folder.mkdir()
        checksums, seen, total = {}, set(), 0
        archive_bytes = archive.read_bytes()
        if sha256(archive_bytes) != package["checksum"]:
            raise VerificationError(f"crate changed after authentication: {stem}")
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tf:
            for entry in tf:
                if entry.name == stem and entry.isdir():
                    continue
                if not entry.name.startswith(stem + "/"):
                    raise VerificationError(f"crate member outside root: {stem}")
                name = entry.name[len(stem) + 1:]
                path = safe_path(folder, name)
                if name in seen:
                    raise VerificationError(f"duplicate crate member: {stem}")
                seen.add(name)
                if entry.isdir():
                    path.mkdir(parents=True, exist_ok=True)
                    continue
                if not entry.isfile() or entry.size > 128 * 1024 * 1024:
                    raise VerificationError(f"unsupported crate member: {stem}")
                total += entry.size
                if total > 1024 * 1024 * 1024:
                    raise VerificationError(f"oversized expanded crate: {stem}")
                # This metadata is generated from the authenticated archive below.
                if name == ".cargo-checksum.json":
                    raise VerificationError(f"crate contains vendor metadata: {stem}")
                data = tf.extractfile(entry).read()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                path.chmod(0o755 if entry.mode & 0o111 else 0o644)
                checksums[name] = sha256(data)
        (folder / ".cargo-checksum.json").write_bytes(canonical_json({
            "package": package["checksum"], "files": checksums,
        }))
        results[stem] = package["checksum"]
    return results


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_equal(actual: str, expected: object, label: str) -> None:
    if not isinstance(expected, str) or not expected.strip() or actual != expected:
        raise VerificationError(f"toolchain mismatch or unset value: {label}")


def native_environment(config: dict, work: Path) -> tuple[dict[str, str], dict[str, str]]:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise VerificationError("native build requires the reviewed arm64 macOS host")
    binaries = {}
    for name in ("cargo", "rustc", "cmake", "ninja"):
        entry = config["executables"][name]
        if not entry.get("path"):
            raise VerificationError(f"toolchain executable is unset: {name}")
        executable = Path(entry["path"])
        if not executable.is_absolute() or executable.is_symlink() or not executable.is_file():
            raise VerificationError(f"provide actual installed executable, not a rustup proxy: {name}")
        require_equal(file_hash(executable), entry.get("sha256"), name + " sha256")
        binaries[name] = str(executable)
    # cargo resolves rustc/rustdoc next to the reviewed compiler. Never install via rustup.
    if Path(binaries["cargo"]).parent != Path(binaries["rustc"]).parent:
        raise VerificationError("cargo and rustc must belong to one installed toolchain")
    developer_dir = config.get("developer_dir")
    if not developer_dir or not Path(developer_dir).is_dir():
        raise VerificationError("reviewed Xcode DEVELOPER_DIR is missing")
    paths = list(dict.fromkeys(str(Path(p).parent) for p in binaries.values()))
    env = {
        "PATH": ":".join(paths + ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]),
        "HOME": str(work / "home"),
        "TMPDIR": str(work / "tmp"),
        "CARGO_HOME": str(work / "cargo-home"),
        "CARGO_TARGET_DIR": str(work / "target"),
        "CARGO_NET_OFFLINE": "true",
        "CARGO_INCREMENTAL": "0",
        "RUSTUP_AUTO_INSTALL": "0",
        "RUSTC": binaries["rustc"],
        "CMAKE": binaries["cmake"],
        "DEVELOPER_DIR": developer_dir,
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "TZ": "UTC",
        "SOURCE_DATE_EPOCH": str(config["source_date_epoch"]),
        "ZERO_AR_DATE": "1",
    }
    for name in ("HOME", "TMPDIR", "CARGO_HOME", "CARGO_TARGET_DIR"):
        Path(env[name]).mkdir()
    return env, binaries


def toolchain_commands(binaries: dict) -> dict[str, list[str]]:
    commands = {
        "rustc": [binaries["rustc"], "--version", "--verbose"],
        "cargo": [binaries["cargo"], "--version", "--verbose"],
        "cmake": [binaries["cmake"], "--version"],
        "ninja": [binaries["ninja"], "--version"],
        "xcode": ["/usr/bin/xcodebuild", "-version"],
        "clang": ["/usr/bin/xcrun", "clang", "--version"],
        "swiftc": ["/usr/bin/xcrun", "swiftc", "--version"],
        "macos_version": ["/usr/bin/sw_vers", "-productVersion"],
        "macos_build": ["/usr/bin/sw_vers", "-buildVersion"],
    }
    for sdk in sorted({"macosx"} | {row[1] for row in TARGETS}):
        for kind, flag in (("version", "--show-sdk-version"), ("build", "--show-sdk-build-version")):
            commands[f"sdk_{sdk}_{kind}"] = ["/usr/bin/xcrun", "--sdk", sdk, flag]
    return commands


def verify_toolchain(config: dict, work: Path, env: dict, binaries: dict) -> dict:
    observations = {}
    commands = toolchain_commands(binaries)
    if set(config["observations"]) != set(commands):
        raise VerificationError("toolchain observations are incomplete")
    for label, command in commands.items():
        value = run(command, cwd=work, env=env)
        require_equal(value, config["observations"][label], label)
        observations[label] = value
    if config.get("rust_release") != "1.98.1" or not observations["rustc"].startswith("rustc 1.98.1 ("):
        raise VerificationError("this build profile requires the Rust 1.98.1 candidate")
    if observations["xcode"].splitlines()[0] != "Xcode 26.3":
        raise VerificationError("this build profile requires Xcode 26.3")
    # Fail before Cargo if a required rust-std target is not already installed.
    sysroot = Path(run([binaries["rustc"], "--print", "sysroot"], cwd=work, env=env))
    for target in ["aarch64-apple-darwin"] + [row[0] for row in TARGETS]:
        if not (sysroot / "lib/rustlib" / target / "lib").is_dir():
            raise VerificationError(f"Rust target is not preinstalled: {target}")
    return observations


def reject_ambient_cargo_config(source: Path) -> None:
    # Cargo merges every ancestor config, even with an isolated CARGO_HOME.
    # Reject them rather than trying to override security-relevant unknown keys.
    for parent in [source] + list(source.parents):
        directory = parent / ".cargo"
        if directory.is_symlink():
            raise VerificationError("ambient Cargo configuration symlink is unsupported")
        for name in ("config", "config.toml"):
            path = directory / name
            if path.exists() or path.is_symlink():
                raise VerificationError("ambient Cargo configuration must be absent: " + str(path))


def build_command(cargo: str, target: str, features: list[str]) -> list[str]:
    command = [cargo, "build", "--frozen", "--release", "-p", "idevice-ffi", "--target", target]
    if features:
        command += ["--features", ",".join(features)]
    return command


def verify_generated_header(data: bytes, symbols: list[str]) -> None:
    text = data.decode()
    for symbol in symbols:
        if not re.search(r"\b" + re.escape(symbol) + r"\s*\(", text):
            raise VerificationError(f"generated FFI header is missing: {symbol}")


def capture_build(command: list[str], *, source: Path, env: dict, log: Path) -> str:
    result = subprocess.run(command, cwd=source, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(result.stdout)
    if result.returncode:
        raise VerificationError("native compile/link failed; see " + str(log))
    return result.stdout


def native_static_flags(output: str) -> list[str]:
    lines = re.findall(r"native-static-libs:\s*(.+)", output)
    if len(lines) != 1:
        raise VerificationError("compiler did not report exactly one native linker flag list")
    flags = shlex.split(lines[0])
    if not flags:
        raise VerificationError("empty native linker flag list")
    expect_framework = False
    for flag in flags:
        if expect_framework:
            if not re.fullmatch(r"[A-Za-z0-9_]+", flag):
                raise VerificationError("unsupported native framework name")
            expect_framework = False
        elif flag == "-framework":
            expect_framework = True
        elif not re.fullmatch(r"-l[A-Za-z0-9_+.-]+", flag):
            raise VerificationError("unreviewed native linker option: " + flag)
    if expect_framework:
        raise VerificationError("missing native framework name")
    return flags


def compile_link_probes(*, source: Path, work: Path, root: Path, lock: dict,
                        cargo: str, target: str, sdk: str, sdk_path: str,
                        deployment: str, features: list[str], env: dict,
                        headers: Path, library: Path) -> dict:
    folder = work / "link-probes" / target
    folder.mkdir(parents=True)
    # An additional cargo rustc invocation asks the reviewed compiler for its
    # actual system-library requirements. It never executes the produced code.
    command = build_command(cargo, target, features)
    command[1] = "rustc"
    output = capture_build(command + ["--", "--print", "native-static-libs"],
                           source=source, env=env, log=folder / "rust-native-libs.txt")
    flags = native_static_flags(output)
    apple_target = "arm64-apple-ios" + deployment + ("-simulator" if sdk == "iphonesimulator" else "")
    result = {"target": apple_target, "native_link_flags": flags, "commands": [], "outputs_sha256": {}}
    for language in ("c", "swift"):
        entry = lock["link_probes"][language]
        path = safe_path(root, entry["path"])
        if not entry.get("sha256") or file_hash(path) != entry["sha256"]:
            raise VerificationError("link probe source review/hash is pending or mismatched")
        binary = folder / (language + "-probe")
        if language == "c":
            command = ["/usr/bin/xcrun", "--sdk", sdk, "clang", "-target", apple_target,
                       "-isysroot", sdk_path, "-I", str(headers), "-O0", "-std=c11", "-Werror=incompatible-function-pointer-types"]
        else:
            command = ["/usr/bin/xcrun", "--sdk", sdk, "swiftc", "-target", apple_target,
                       "-sdk", sdk_path, "-I", str(headers), "-Onone"]
        command += [str(path), str(library), *flags, "-o", str(binary)]
        capture_build(command, source=source, env=env, log=folder / (language + ".txt"))
        if not binary.is_file() or not binary.stat().st_size:
            raise VerificationError("native link probe did not produce an executable")
        result["commands"].append(command)
        result["outputs_sha256"][language] = file_hash(binary)
    return result


def inventory(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise VerificationError("artifact symlinks are unsupported")
        if path.is_file():
            result[str(path.relative_to(root))] = file_hash(path)
    return result


def deterministic_zip(root: Path, output: Path, *, source_symlinks: dict[str, str] | None = None) -> None:
    source_symlinks = source_symlinks or {}
    names = []
    for path in sorted(root.rglob("*")):
        name = str(path.relative_to(root))
        if path.is_symlink():
            if source_symlinks.get(name) != os.readlink(path):
                raise VerificationError("archive contains an unreviewed symlink")
            safe_source_link(root, name, os.readlink(path).encode())
            names.append(name)
        elif path.is_file():
            names.append(name)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in names:
            path = root / name if name in source_symlinks else safe_path(root, name)
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            if name in source_symlinks:
                info.external_attr = 0o120777 << 16
                data = os.readlink(path).encode()
            else:
                info.external_attr = (0o100755 if path.stat().st_mode & 0o111 else 0o100644) << 16
                data = path.read_bytes()
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compresslevel=9)


def verify_artifact(root: Path, manifest: Path, expected_sha256: str) -> None:
    require_equal(file_hash(manifest), expected_sha256, "artifact manifest sha256")
    expected = json.loads(manifest.read_bytes())["files"]
    if inventory(root) != expected:
        raise VerificationError("artifact file inventory/hash mismatch")


def build(args: argparse.Namespace) -> dict:
    lock = load_lock()
    if not lock["required_ffi_symbols"] or not lock.get("native_test_filters_complete") or not lock.get("link_probes_complete"):
        raise VerificationError("native FFI symbol/test-filter review is pending")
    toolchain_bytes = args.toolchain_lock.read_bytes()
    require_equal(sha256(toolchain_bytes), args.toolchain_lock_sha256, "toolchain lock sha256")
    config = json.loads(toolchain_bytes)
    if config.get("schema") != 1 or not isinstance(config.get("source_date_epoch"), int):
        raise VerificationError("invalid toolchain lock")
    if args.work_dir.exists() or args.output.exists():
        raise VerificationError("work and output directories must be new; no stale native artifacts")
    # Leave failed work available for diagnosis. No output is published on failure.
    args.work_dir.mkdir(parents=True)
    env, binaries = native_environment(config, args.work_dir)
    observations = verify_toolchain(config, args.work_dir, env, binaries)
    source = args.work_dir / "source"
    source_manifest = stage(args.source, source)
    reject_ambient_cargo_config(source)
    source_lock = (source / "Cargo.lock").read_bytes()
    crates = vendor_crates(source_lock, args.crate_cache, source / "vendor")
    cargo_config = source / ".cargo/config.toml"
    if cargo_config.exists():
        raise VerificationError("upstream Cargo configuration was not reviewed")
    cargo_config.parent.mkdir(exist_ok=True)
    cargo_config.write_text('[source.crates-io]\nreplace-with = "tetherless-vendor"\n\n'
                            '[source.tetherless-vendor]\ndirectory = "vendor"\n\n'
                            '[net]\noffline = true\n')
    env["CARGO_ENCODED_RUSTFLAGS"] = "--remap-path-prefix=" + str(args.work_dir) + "=/tetherless-idevice"
    test_outputs = []
    ffi_features = tomllib.loads((source / "ffi/Cargo.toml").read_text())["features"]["default"]
    for suite in lock["native_test_filters"]:
        if suite["package"] not in ("idevice", "idevice-ffi") or not suite["filter"]:
            raise VerificationError("unsupported native fixture test selection")
        command = [binaries["cargo"], "test", "--frozen", "-p", suite["package"], "--lib",
                   "--target", "aarch64-apple-darwin"]
        if suite["package"] == "idevice":
            command += ["--features", ",".join(ffi_features)]
        command.append(suite["filter"])
        result = run(command, cwd=source, env=env)
        if not re.search(r"test result: ok\. [1-9][0-9]* passed; 0 failed;", result):
            raise VerificationError("native fixture filter did not execute and pass: " + suite["filter"])
        test_outputs.append({"command": command, "output": result})
    if not test_outputs:
        raise VerificationError("native fixture test selection must not be empty")
    test_output = canonical_json(test_outputs).decode()
    package = args.work_dir / "package"
    package.mkdir()
    headers = args.work_dir / "headers"
    headers.mkdir()
    generated_header = None
    inputs = []
    probe_results = []
    for target, sdk, deployment_key, deployment, features in TARGETS:
        sdk_path = run(["/usr/bin/xcrun", "--sdk", sdk, "--show-sdk-path"], cwd=source, env=env)
        target_env = dict(env, **{deployment_key: deployment,
                                "BINDGEN_EXTRA_CLANG_ARGS": "--sysroot=" + sdk_path,
                                "SDKROOT": sdk_path})
        run(build_command(binaries["cargo"], target, features), cwd=source, env=target_env, capture=False)
        if (source / "Cargo.lock").read_bytes() != source_lock:
            raise VerificationError("Cargo.lock changed during build")
        header = (source / "ffi/idevice.h").read_bytes()
        verify_generated_header(header, lock["required_ffi_symbols"])
        if generated_header is not None and header != generated_header:
            raise VerificationError("generated header differs across target slices")
        generated_header = header
        (headers / "idevice.h").write_bytes(header)
        shutil.copy2(source / "swift/include/module.modulemap", headers / "module.modulemap")
        library = args.work_dir / "target" / target / "release/libidevice_ffi.a"
        if not library.is_file() or not library.stat().st_size:
            raise VerificationError(f"native library missing: {target}")
        # Check names only. This is dependency ABI presence, not app admission validation.
        symbols = run(["/usr/bin/xcrun", "nm", "-gU", str(library)], cwd=source, env=env)
        for symbol in lock["required_ffi_symbols"]:
            if not re.search(r"\b_" + re.escape(symbol) + r"$", symbols, flags=re.M):
                raise VerificationError(f"native library missing exported FFI symbol: {symbol}")
        probe_results.append(compile_link_probes(
            source=source, work=args.work_dir, root=HERE, lock=lock, cargo=binaries["cargo"],
            target=target, sdk=sdk, sdk_path=sdk_path, deployment=deployment, features=features,
            env=target_env, headers=headers, library=library))
        inputs += ["-library", str(library), "-headers", str(headers)]
    for name, expected in source_manifest["files"].items():
        if name in source_manifest["symlinks"]:
            path = source / name
            actual = sha256(os.readlink(path).encode()) if path.is_symlink() else None
        else:
            actual = file_hash(safe_path(source, name))
        if actual != expected:
            raise VerificationError(f"source changed during native build: {name}")
    (headers / "idevice.h").write_bytes(generated_header)
    shutil.copy2(source / "swift/include/module.modulemap", headers / "module.modulemap")
    run(["/usr/bin/xcodebuild", "-create-xcframework", *inputs, "-output",
         str(package / "IDevice.xcframework")], cwd=source, env=env, capture=False)
    info = plistlib.loads((package / "IDevice.xcframework/Info.plist").read_bytes())
    slices = info.get("AvailableLibraries", [])
    identities = {(item.get("SupportedPlatform"), item.get("SupportedPlatformVariant", ""),
                   tuple(item.get("SupportedArchitectures", []))) for item in slices}
    if len(slices) != 2 or identities != {("ios", "", ("arm64",)), ("ios", "simulator", ("arm64",))}:
        raise VerificationError("XCFramework must contain exactly the two reviewed iOS arm64 slices")
    (package / "provenance").mkdir()
    (package / "provenance/native-tests.txt").write_text(test_output)
    (package / "provenance/link-probes.json").write_bytes(canonical_json(probe_results))
    for log in (args.work_dir / "link-probes").rglob("*.txt"):
        destination = package / "provenance/link-probe-logs" / log.relative_to(args.work_dir / "link-probes")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(log, destination)
    for name in ("source-lock.json", "source-tree.json", "source-input.json"):
        shutil.copy2(HERE / name, package / "provenance" / name)
    (package / "provenance/toolchain-lock.json").write_bytes(toolchain_bytes)
    (package / "provenance/source-manifest.json").write_bytes(canonical_json(source_manifest))
    (package / "provenance/crates.json").write_bytes(canonical_json(crates))
    shutil.copy2(source / "LICENSE.txt", package / "LICENSE-idevice.txt")
    shutil.copy2(source / "Cargo.lock", package / "provenance/Cargo.lock")
    # Full matching source including immutable vendor sources and their licenses.
    source_bundle = args.work_dir / "source-package"
    shutil.copytree(source, source_bundle, symlinks=True)
    for generated in ("ffi/idevice.h", "cpp/include/idevice.h"):
        path = source_bundle / generated
        if path.is_file():
            path.unlink()
    tooling = source_bundle / "tetherless-build-recipe"
    shutil.copytree(HERE, tooling, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    deterministic_zip(source_bundle, package / "corresponding-source.zip", source_symlinks=source_manifest["symlinks"])
    provenance = {"schema": 1, "source_commit": lock["upstream"]["commit"],
                  "source_lock_sha256": source_manifest["source_lock_sha256"],
                  "toolchain_lock_sha256": sha256(toolchain_bytes),
                  "tooling_sha256": {p.name: file_hash(p) for p in sorted(HERE.glob("*.py"))},
                  "observations": observations, "targets": TARGETS,
                  "native_tests": lock["native_test_filters"], "link_probes": probe_results, "files": inventory(package)}
    completed = args.work_dir / "completed"
    completed.mkdir()
    shutil.move(str(package), completed / "bundle")
    (completed / "artifact-manifest.json").write_bytes(canonical_json(provenance))
    deterministic_zip(completed / "bundle", completed / "IDevice-local.zip")
    checksum = {"artifact-manifest.json": file_hash(completed / "artifact-manifest.json"),
                "IDevice-local.zip": file_hash(completed / "IDevice-local.zip")}
    (completed / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in checksum.items()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    os.rename(completed, args.output)
    return checksum


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--crate-cache", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--toolchain-lock", required=True, type=Path)
    parser.add_argument("--toolchain-lock-sha256", required=True)
    args = parser.parse_args()
    for name in ("source", "crate_cache", "work_dir", "output", "toolchain_lock"):
        setattr(args, name, getattr(args, name).absolute())
    try:
        print(json.dumps(build(args), sort_keys=True))
    except (VerificationError, OSError, KeyError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"idevice native build failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
