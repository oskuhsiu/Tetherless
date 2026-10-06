"""Controlled Apple orchestration tests; only bounded Python children execute.

Cargo, Xcode, compiler and linker results are synthetic. Opaque output bytes and
Info.plist metadata are checked without inspecting or executing native binaries.
"""
from __future__ import annotations

from contextlib import ExitStack
import copy
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import sys
import tempfile
import tomllib
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bounded_process
import build_pairing_apple as apple
from test_pairing_result_header import generated_fixture, write_generated_fixture
from apply_patch import VerificationError, canonical_json, git_blob, sha256
from test_apple_source_bundle import make_archive, write_vendor, write_workspace

spec = importlib.util.spec_from_file_location("apple_fixture_provider", ROOT / "split-provider/provider_inputs.py")
provider = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider)
AUDITS = ("vendor-input-audit.json", "derived-vendor-input-audit.json", "workspace-input-audit.json", "provider-input-audit.json")
SYSTEM_FLAGS = ["-lSystem", "-lc++", "-lobjc", "-lz", "-liconv", "-framework", "Security", "-framework", "Foundation"]
PACKAGING_RECIPE_FILES = ("xcframework_operation.py", "tests/test_xcframework_operation.py",
                          "registration/receipts/xcframework-operation-tiny-proof.json")
PACKAGING_OPERATION_SHA256 = "98df3ef86806a707fb898dd9e59ff0a3612b330a91522d4995b793360ed0f044"
PACKAGING_PROOF_SHA256 = "a9f80c54d43cc8a84aedc81cb09cab6df48242af54e2e8052c8454b54942f7f6"


def artifact(source, target, defaults):
    return {"reason": "compiler-artifact", "package_id": "path+file://controlled#idevice-ffi@0.1.68",
            "manifest_path": str(source / "ffi/Cargo.toml"), "features": ["default", *defaults, *target["extra_features"]],
            "target": {"name": "idevice_ffi", "kind": ["staticlib"], "crate_types": ["staticlib"],
                       "src_path": str(source / "ffi/src/lib.rs")},
            "filenames": [str(source.parent / "target" / target["rust"] / "release/libidevice_ffi.a")]}


def slice_plist():
    return {"AvailableLibraries": [
        {"LibraryIdentifier": "ios-arm64", "LibraryPath": "libidevice_ffi.a", "HeadersPath": "Headers", "SupportedPlatform": "ios", "SupportedArchitectures": ["arm64"]},
        {"LibraryIdentifier": "ios-arm64-simulator", "LibraryPath": "libidevice_ffi.a", "HeadersPath": "Headers", "SupportedPlatform": "ios",
         "SupportedPlatformVariant": "simulator", "SupportedArchitectures": ["arm64"]}]}


class AppleFixture:
    def __init__(self, root):
        self.root = root
        root.mkdir()
        self.recipe = root / "recipe"
        self.profile = json.loads((ROOT / apple.PROFILE).read_bytes())
        names = [apple.PROFILE, "split-provider/header_probe.c", "overlay/ffi/pairing_result_abi.h", "namespace/contract.json"]
        names += [p["path"] for group in self.profile["probe_sets"].values() for p in group.values()]
        names += list(PACKAGING_RECIPE_FILES)
        for name in names:
            path = self.recipe / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, path)
        self.recipe_files = {name: sha256((self.recipe / name).read_bytes()) for name in names}
        index = self.recipe / "apple-recipe-files.json"
        index.write_bytes(canonical_json(self.recipe_files))
        self.cache = root / "crate-cache"
        self.lock = make_archive(self.cache)
        self.defaults = tomllib.loads((ROOT / "upstream/ffi/Cargo.toml").read_text())["features"]["default"]
        self.binaries = {name: "controlled-" + name for name in ("cargo", "rustc", "cmake", "ninja")}
        from test_rust_symbol_reader import ReaderFixture, RUST_VERSION
        self.reader_fixture = ReaderFixture(root)
        self.binaries["rustc"] = str(self.reader_fixture.rustc)
        self.reader = self.reader_fixture.observe()
        self.observations = {name: "controlled " + name + " observation" for name in apple.toolchain_commands(self.binaries)}
        self.observations.update(rustc=RUST_VERSION, xcode="Xcode 26.3\nBuild version controlled")
        self.config = {"schema": 1, "source_date_epoch": 1, "developer_dir": str(root / "developer"),
                       "rust_release": "1.98.1", "observations": self.observations, "symbol_reader": self.reader}
        self.toolchain = root / "toolchain.json"
        self.toolchain.write_bytes(canonical_json(self.config))
        self.args = SimpleNamespace(source=root / "input-source", crate_cache=self.cache, provider_inputs=root / "provider-source",
            mixed_provider=root / "mixed-provider",
            work_dir=root / "work", output=root / "published", toolchain_lock=self.toolchain,
            toolchain_lock_sha256=sha256(self.toolchain.read_bytes()), recipe_lock_sha256=sha256(index.read_bytes()))
        self.args.mixed_provider.mkdir()
        (self.args.mixed_provider / "authenticated-provider.zip").write_bytes(b"controlled opaque C provider archive fixture")
        self.sdk = root / "sdk"
        self.sdk.mkdir()
        self.tool = root / "tool"
        self.tool.write_bytes(b"opaque compiler path fixture; never executed")
        self.sysroot = self.reader_fixture.root
        for target in ("aarch64-apple-darwin", "aarch64-apple-ios", "aarch64-apple-ios-sim"):
            (self.sysroot / "lib/rustlib" / target / "lib").mkdir(parents=True)
        self.calls = []
        self.fail = None
        self.failure_kind = "nonzero_exit"
        self.mutate = None
        self.mutate_on = None
        self.bad_features = None
        self.bad_output = None
        self.large_symbol_output = False
        self.early_symbol_fault = None
        self.bad_slices = False
        self.bad_packaged_file = None
        self.mismatched_headers = False
        self.provider_libs = ""
        self.omit_provider_libs = False
        self.native_flags = list(SYSTEM_FLAGS)
        self.contract = {"commit": provider.COMMIT, "enabled": False, "product_activation": False, "entries": [], "targets": {}}
        files = {"LICENSE.txt": b"controlled OpenSSL license\n"}
        for row in apple.TARGETS:
            framework = row["sdk"] + "/OpenSSL.framework"
            self.contract["targets"][row["rust"]] = {"kind": "apple-framework", "header_root": framework + "/Headers",
                "framework_root": framework, "framework_binary": framework + "/OpenSSL", "header_count": 2,
                "native_library_input_paths": [], "environment_values": {"OPENSSL_LIBS": "", "OPENSSL_NO_VENDOR": "1"}}
            files.update({framework + "/Headers/ssl.h": b"controlled header\n",
                          framework + "/Headers/configuration.h": b"controlled configuration\n",
                          framework + "/Modules/module.modulemap": b"controlled modulemap\n",
                          framework + "/OpenSSL": b"opaque framework fixture bytes; never inspected or executed\n"})
        for name, data in files.items():
            path = self.args.provider_inputs / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o644)
            self.contract["entries"].append({"path": name, "mode": "100644", "size": len(data),
                                               "sha256": sha256(data), "git_blob": git_blob(data)})

    def environment(self, _config, work):
        for name in ("cargo-home", "home", "tmp"):
            (work / name).mkdir()
        env = {"PATH": os.defpath, "HOME": str(work / "home"), "TMPDIR": str(work / "tmp"),
               "CARGO_HOME": str(work / "cargo-home"), "CARGO_TARGET_DIR": str(work / "target"), "CARGO_NET_OFFLINE": "true",
               "OPENSSL_LIBS": "untrusted ambient ssl", "SDKROOT": "untrusted ambient sdk", "RUSTFLAGS": "untrusted flags"}
        return env, self.binaries

    def stage(self, source, destination, recipe, profile):
        if (source, recipe, profile) != (self.args.source, self.recipe, apple.PROFILE):
            raise AssertionError("unexpected source/profile staging")
        result = write_workspace(destination, self.lock, self.defaults)
        result.update(source_profile=profile, source_profile_sha256=sha256((self.recipe / profile).read_bytes()))
        return result

    def vendor(self, *, source, work, cache, env, derive_metadata, export_namespace):
        if not derive_metadata or cache != self.cache:
            raise AssertionError("expected authenticated derived vendor staging")
        return write_vendor(work, source)

    def mixed_provider(self, root, target):
        if root != self.args.mixed_provider:
            raise AssertionError("unexpected mixed provider source")
        # Honest orchestration fixture: no ZIP/native bytes are interpreted.
        return {"target": target["rust"], "library": str(root / "libimobiledevice.a"),
                "headers": str(root / "Headers"), "binary_format_inspected": False,
                "fixture_sha256": sha256((root / "authenticated-provider.zip").read_bytes())}

    def prepare_provider(self, source, destination, target):
        receipt = provider.prepare_inputs(source, destination, target)
        key = target.upper().replace("-", "_") + "_OPENSSL_LIBS"
        if self.omit_provider_libs:
            del receipt["environment"][key]
        else:
            receipt["environment"][key] = self.provider_libs
        return receipt

    def command(self, argv, *, source, env, log):
        target_name = source.parent.name if source.name == "source" else source.name
        self.calls.append({"argv": list(argv), "source": source, "env": dict(env), "log": log, "target": target_name})
        toolchain = apple.toolchain_commands(self.binaries)
        matching = [key for key, value in toolchain.items() if argv == value]
        if matching:
            output = self.observations[matching[0]] + "\n"
        elif argv == [self.binaries["rustc"], "--print", "sysroot"]:
            output = str(self.sysroot) + "\n"
        elif argv[:3] == [sys.executable, "-I", str(self.recipe / "xcframework_operation.py")]:
            if len(argv) != 8:
                raise AssertionError("unexpected packaging operation arguments")
            destination = Path(argv[7])
            destination.mkdir()
            metadata = slice_plist()
            if self.bad_slices:
                metadata["AvailableLibraries"][1]["SupportedArchitectures"] = ["x86_64"]
            (destination / "Info.plist").write_bytes(plistlib.dumps(metadata))
            libraries = [Path(argv[3]), Path(argv[5])]
            header_roots = [Path(argv[4]), Path(argv[6])]
            for number, row in enumerate(metadata["AvailableLibraries"]):
                path = destination / row["LibraryIdentifier"] / row["LibraryPath"]
                path.parent.mkdir()
                shutil.copyfile(libraries[number], path)
                headers = path.parent / row["HeadersPath"]
                headers.mkdir()
                for name in ("idevice.h", "module.modulemap"):
                    shutil.copyfile(header_roots[number] / name, headers / name)
                if number == 0 and self.bad_packaged_file:
                    changed = path if self.bad_packaged_file == "library" else headers / self.bad_packaged_file
                    changed.write_bytes(b"controlled packaged output mutation\n")
            output = "controlled XCFramework creation\n"
        elif "--show-sdk-path" in argv:
            output = str(self.sdk) + "\n"
        elif "--find" in argv:
            output = str(self.tool) + "\n"
        elif log.name == "toolchain-llvm-nm.txt":
            output = self.reader["llvm_nm"]["version"] + "\n"
        elif argv[0] == self.reader["llvm_nm"]["path"]:
            if Path(argv[-1]).name == "libidevice_ffi.a":
                namespace = json.loads((self.recipe / "namespace/contract.json").read_bytes())
                output = "\n".join("_" + n for n in namespace["expected_target_exports"][target_name]["after"]) + "\n"
            else:
                output = "\n".join("_" + n for n in ("plist_new_dict", "plist_free", "plist_array_set_item",
                    "afc_client_free", "lockdownd_client_free", "idevice_free")) + "\n"
        elif "-fsyntax-only" in argv:
            output = "controlled syntax-only header check\n"
        elif argv[:2] == [self.binaries["cargo"], "tree"]:
            output = "controlled feature graph\n"
            if self.bad_features == "graph":
                output += apple.FORBIDDEN_FEATURE + "\n"
        elif argv[:2] == [self.binaries["cargo"], "build"]:
            target = next(t for t in apple.TARGETS if t["rust"] == target_name)
            work = source.parent
            out = work / "target" / target_name / "release/build/openssl-sys-controlled/out"
            out.mkdir(parents=True)
            receipt = json.loads((work / "completed/provider-input-receipt.json").read_bytes())
            view = Path(receipt["view_root"])
            selected_output = (f"cargo:rustc-link-search=native={view}/lib\ncargo:include={view}/include\n"
                               "cargo:version_number=30600020\n").encode()
            if self.bad_output == "static-provider":
                selected_output += b"cargo:rustc-link-lib=static=ssl\n"
            if self.bad_output == "oversized":
                selected_output = b"x" * (1024 * 1024 + 1)
            (out.parent / "output").write_bytes(selected_output)
            library = work / "target" / target_name / "release/libidevice_ffi.a"
            library.write_bytes(b"opaque Rust archive fixture; never inspected or executed\n" + target_name.encode() + b"\n")
            other = "\n".join("void " + symbol + "(void);" for symbol in self.profile["required_ffi_symbols"])
            if self.mismatched_headers and target_name.endswith("-sim"):
                other += "\n// controlled simulator header difference\n"
            write_generated_fixture(source, other.encode())
            event = artifact(source, target, self.defaults)
            if self.bad_features == "artifact":
                event["features"].append(apple.FORBIDDEN_FEATURE)
            if self.bad_features == "missing-default":
                event["features"].remove("default")
            output = json.dumps(event) + "\n" + json.dumps({"reason": "build-script-executed",
                "package_id": "registry+https://github.com/rust-lang/crates.io-index#openssl-sys@0.9.112", "out_dir": str(out)}) + "\n"
        elif argv[:2] == [self.binaries["cargo"], "rustc"]:
            output = "native-static-libs: " + " ".join(self.native_flags) + "\n"
        elif argv[:3] == ["/usr/bin/xcrun", "--sdk", "iphoneos"] or argv[:3] == ["/usr/bin/xcrun", "--sdk", "iphonesimulator"]:
            if argv[3] not in ("clang", "swiftc") or "-o" not in argv:
                raise AssertionError("unexpected native command")
            Path(argv[argv.index("-o") + 1]).write_bytes(b"opaque linked probe fixture; never executed\n")
            if "-map" in argv:
                Path(argv[argv.index("-map") + 2]).write_bytes(b"controlled opaque linker map fixture\n")
            output = "controlled ordinary link result\n"
        else:
            raise AssertionError("unapproved command would execute: " + repr(argv))
        if self.large_symbol_output and log.name in ("04-rust-export-symbols.txt", "04-c-export-symbols.txt"):
            if self.early_symbol_fault == "alias" and log.name == "04-rust-export-symbols.txt":
                output = "_plist_free\n" + output
            if self.early_symbol_fault == "collision":
                output = "_early_provider_collision\n" + output
        code = "import sys,time; sys.stdout.write(" + repr(output) + "); sys.stdout.flush()"
        options = dict(timeout_seconds=2, max_log_bytes=32768, tail_bytes=32768, term_grace_seconds=.2, kill_join_seconds=.2)
        if self.large_symbol_output and log.name in ("04-rust-export-symbols.txt", "04-c-export-symbols.txt"):
            padding = "_synthetic_" + ("rust" if log.name.startswith("04-rust") else "c") + "_padding\n"
            code += "; sys.stdout.write(" + repr(padding) + " * 12000); sys.stdout.flush()"
            options.update(max_log_bytes=1024 * 1024, tail_bytes=bounded_process.SUMMARY_TAIL_BYTES)
        if self.mutate and (self.fail == (target_name, log.name) or self.mutate_on == (target_name, log.name)):
            self.mutate(self)
        if self.fail == (target_name, log.name):
            if self.failure_kind == "timeout":
                code += "; time.sleep(5)"
                options["timeout_seconds"] = .15
            else:
                code += "; sys.stderr.write('controlled native-command failure\\n'); sys.exit(7)"
        return bounded_process.capture_helper_command([sys.executable, "-u", "-c", code], source=source, env=env, log=log, **options)

    def patches(self):
        stack = ExitStack()
        stack.enter_context(patch.object(provider, "load_contract", return_value=self.contract))
        api = SimpleNamespace(prepare_inputs=self.prepare_provider, build_environment=provider.build_environment,
                              audit_inputs=provider.audit_inputs, check_build_script_output=provider.check_build_script_output)
        stack.enter_context(patch.object(apple, "HERE", self.recipe))
        for name, value in {"load_apple_profile": lambda: self.profile, "load_provider": lambda: api,
                            "verify_mixed_provider": self.mixed_provider,
                            "native_environment": self.environment, "stage": self.stage, "prepare_offline_vendor": self.vendor,
                            "capture_helper_command": self.command}.items():
            stack.enter_context(patch.object(apple, name, side_effect=value))
        return stack


class ApplePolicyTests(unittest.TestCase):
    def test_packaging_operation_source_tests_and_proof_are_exact_and_recipe_indexed(self):
        recipe_files = json.loads((ROOT / "apple-recipe-files.json").read_bytes())
        for name in PACKAGING_RECIPE_FILES:
            with self.subTest(recipe_input=name):
                self.assertEqual(recipe_files[name], sha256((ROOT / name).read_bytes()))
        self.assertEqual(recipe_files[PACKAGING_RECIPE_FILES[0]], PACKAGING_OPERATION_SHA256)
        self.assertEqual(recipe_files[PACKAGING_RECIPE_FILES[2]], PACKAGING_PROOF_SHA256)

    def test_registered_apple_profile_stays_production_only_and_disabled(self):
        profile = apple.load_apple_profile()
        self.assertEqual([t["rust"] for t in profile["apple_targets"]], ["aarch64-apple-ios", "aarch64-apple-ios-sim"])
        self.assertEqual(profile["native_test_filters"], [])
        self.assertEqual(profile["forbidden_features"], ["tetherless-synthetic-peer"])
        self.assertFalse(profile["activation"]["enabled"])
        self.assertFalse(profile["activation"]["consumer_integration_allowed"])
        self.assertFalse(profile["activation"]["test_only_execution_authorized"])
        self.assertTrue(profile["activation"]["apple_verification_authorized"])

    def test_profile_scope_mutations_fail(self):
        original = apple.load_apple_profile()
        for change in (lambda p: p["activation"].update(enabled=True),
                       lambda p: p["activation"].update(consumer_integration_allowed=True),
                       lambda p: p["activation"].update(test_only_execution_authorized=True),
                       lambda p: p["activation"].update(apple_verification_authorized=False),
                       lambda p: p.update(native_test_filters=[{"filter": "fixture"}]),
                       lambda p: p["apple_targets"].reverse()):
            profile = copy.deepcopy(original)
            change(profile)
            with patch.object(apple, "load_lock", return_value=profile), self.assertRaises(VerificationError):
                apple.load_apple_profile()

    def test_release_build_and_report_preserve_defaults_with_exact_extra_features(self):
        for target in apple.TARGETS:
            for report in (False, True):
                command = apple.release_command("controlled-cargo", target, report=report)
                self.assertIn("--frozen", command)
                self.assertIn("--release", command)
                self.assertIn("--lib", command)
                self.assertNotIn("--no-default-features", command)
                self.assertEqual(command[command.index("--features") + 1], "openssl,obfuscate" if target["sdk"] == "iphoneos" else "openssl")
                if report:
                    self.assertEqual(command[-3:], ["--", "--print", "native-static-libs"])
                else:
                    self.assertIn("--message-format=json-render-diagnostics", command)

    def test_strict_static_flag_parser_preserves_system_flags_and_rejects_provider_or_injection(self):
        self.assertEqual(apple.system_link_flags("note: native-static-libs: " + " ".join(SYSTEM_FLAGS)), SYSTEM_FLAGS)
        for bad in ("-lssl", "-lcrypto", "-lcrypto.3", "-llibssl", "-lssl_static", "-lOpenSSL", "-framework OpenSSL",
                    "-framework Crypto", "-L/other", "-Wl,-force_load,/other", "/tmp/opaque.a", "-framework", "-lSystem\nnative-static-libs: -lc++"):
            with self.subTest(flags=bad), self.assertRaises(VerificationError):
                apple.system_link_flags("native-static-libs: " + bad)

    def test_each_probe_is_force_loaded_and_force_rooted_for_both_languages(self):
        for target in apple.TARGETS:
            for language in ("c", "swift"):
                command = apple.link_command(language=language, target=target, sdk="/controlled/sdk", headers=Path("/controlled/headers"),
                    library=Path("/controlled/library.a"), probe=Path("/controlled/probe." + language), symbol="controlled_probe",
                    output=Path("/controlled/output"), system_flags=SYSTEM_FLAGS,
                    framework_flags=["-F", "/controlled/frameworks", "-framework", "OpenSSL"])
                sequence = ["-Xlinker", "-force_load", "-Xlinker", "/controlled/library.a", "-Xlinker", "-u", "-Xlinker", "_controlled_probe"]
                offset = command.index("-Xlinker")
                self.assertEqual(command[offset:offset + len(sequence)], sequence)
                self.assertEqual(command[-6:], ["-F", "/controlled/frameworks", "-framework", "OpenSSL", "-o", "/controlled/output"])
                self.assertEqual(command[command.index("-target") + 1], target["clang"])

    def test_link_probe_rejects_unknown_language_symbols_framework_or_system_options(self):
        valid = dict(language="c", target=apple.TARGETS[0], sdk="/sdk", headers=Path("/headers"), library=Path("/library.a"),
                     probe=Path("/probe.c"), symbol="controlled_probe", output=Path("/output"), system_flags=SYSTEM_FLAGS,
                     framework_flags=["-F", "/frameworks", "-framework", "OpenSSL"])
        for updates in ({"language": "asm"}, {"symbol": "probe,-evil"}, {"system_flags": ["-lssl"]},
                        {"framework_flags": ["-F", "relative", "-framework", "OpenSSL"]},
                        {"framework_flags": ["-F", "/frameworks", "-framework", "Other"]}):
            with self.subTest(updates=updates), self.assertRaises(VerificationError):
                apple.link_command(**dict(valid, **updates))

    def test_feature_receipt_requires_one_staticlib_artifact_and_rejects_synthetic_anywhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            log, graph = root / "build.txt", root / "features.txt"
            graph.write_text("controlled resolved features\n")
            target = apple.TARGETS[0]
            defaults = ["house_arrest", "remote_pairing"]
            good = artifact(source, target, defaults)
            def check(events):
                log.write_text("\n".join(json.dumps(e) for e in events))
                return apple.check_production_features(log, graph, source, defaults, target)
            self.assertFalse(check([good])["synthetic_peer_selected"])
            for events in ([], [good, good], [dict(good, manifest_path="/other/Cargo.toml")],
                           [dict(good, features=["default", "openssl"])], [dict(good, target={"crate_types": ["rlib"]})],
                           [dict(good, features=[*good["features"], apple.FORBIDDEN_FEATURE])],
                           [good, dict(good, manifest_path="/other/Cargo.toml", features=[apple.FORBIDDEN_FEATURE])]):
                with self.subTest(events=events), self.assertRaises(VerificationError):
                    check(events)
            graph.write_text(apple.FORBIDDEN_FEATURE)
            with self.assertRaises(VerificationError):
                check([good])

    def test_slice_metadata_checks_only_exact_ios_arm64_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Info.plist"
            path.write_bytes(plistlib.dumps(slice_plist()))
            apple.verify_slice_metadata(path)
            for mutate in (lambda d: d["AvailableLibraries"].pop(),
                           lambda d: d["AvailableLibraries"][0].update(SupportedPlatform="macos"),
                           lambda d: d["AvailableLibraries"][1].update(SupportedArchitectures=["x86_64"]),
                           lambda d: d["AvailableLibraries"][1].pop("SupportedPlatformVariant")):
                value = slice_plist()
                mutate(value)
                path.write_bytes(plistlib.dumps(value))
                with self.assertRaises(VerificationError):
                    apple.verify_slice_metadata(path)


@unittest.skipUnless(os.name == "posix", "bounded Python child fixtures require POSIX")
class AppleRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='Apple runner fixture " 🌿 ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def assert_audits(self, fixture, target):
        folder = fixture.args.work_dir / target / "completed"
        for name in AUDITS:
            self.assertTrue((folder / name).is_file(), str(folder / name))
        return {name: json.loads((folder / name).read_bytes()) for name in AUDITS}

    def test_full_symbol_logs_not_summary_tails_are_validated_and_hashed(self):
        fixture = AppleFixture(self.root / "large-symbol-success")
        fixture.large_symbol_output = True
        with fixture.patches(): result = apple.build(fixture.args)
        for row in result["targets"]:
            folder = Path(row["work"]) / "completed"
            for name, key in (("04-rust-export-symbols.txt", "nm_stdout_sha256"),
                              ("04-c-export-symbols.txt", "c_nm_stdout_sha256")):
                raw = (folder / name).read_bytes()
                self.assertGreater(len(raw), bounded_process.SUMMARY_TAIL_BYTES)
                self.assertEqual(row["export_namespace"][key], sha256(raw))
            self.assertEqual(row["export_namespace"]["namespaced_export_count"], 382)
            self.assertEqual(len(row["link_probes"]), 8)

    def test_early_alias_or_collision_beyond_summary_tail_is_rejected(self):
        for fault in ("alias", "collision"):
            fixture = AppleFixture(self.root / ("large-symbol-" + fault))
            fixture.large_symbol_output = True
            fixture.early_symbol_fault = fault
            with fixture.patches(), self.assertRaises(VerificationError): apple.build(fixture.args)
            self.assertFalse(any(call["log"].name.startswith("05-link-") for call in fixture.calls))
            self.assertFalse(fixture.args.output.exists())
            self.assert_audits(fixture, "aarch64-apple-ios")

    def test_partial_symbol_output_with_complete_expected_names_still_fails(self):
        for name in ("04-rust-export-symbols.txt", "04-c-export-symbols.txt"):
            fixture = AppleFixture(self.root / name)
            fixture.fail = ("aarch64-apple-ios", name)
            with fixture.patches(), self.assertRaises(VerificationError):
                apple.build(fixture.args)
            log = fixture.args.work_dir / "aarch64-apple-ios/completed" / name
            status = json.loads(log.with_name(log.name + ".status.json").read_bytes())
            self.assertEqual(status["returncode"], 7)
            self.assertFalse(status["output_complete"])
            self.assertFalse(any(call["log"].name.startswith("05-link-") for call in fixture.calls))
            self.assertFalse(fixture.args.output.exists())
            self.assert_audits(fixture, "aarch64-apple-ios")
            if name == "04-rust-export-symbols.txt":
                self.assertEqual(len({line for line in log.read_text().splitlines()
                    if line.startswith("_tetherless_native_")}), 382)

    def test_absent_or_changed_locked_reader_stops_before_build(self):
        for change in (lambda config: config.pop("symbol_reader"),
                       lambda config: config["symbol_reader"]["llvm_nm"].update(sha256="0" * 64)):
            fixture = AppleFixture(self.root / str(len(list(self.root.iterdir()))))
            change(fixture.config)
            fixture.toolchain.write_bytes(canonical_json(fixture.config))
            fixture.args.toolchain_lock_sha256 = sha256(fixture.toolchain.read_bytes())
            with fixture.patches(), self.assertRaises(VerificationError):
                apple.build(fixture.args)
            self.assertFalse(any(call["log"].name == "03-release-build.txt" for call in fixture.calls))
            self.assertFalse(fixture.args.output.exists())

    def test_alias_parent_uses_receipt_paths_for_both_targets_without_relaxing_checks(self):
        actual = self.root / "actual-parent"
        actual.mkdir()
        alias = self.root / "alias-parent"
        alias.symlink_to(actual.resolve(), target_is_directory=True)
        fixture = AppleFixture(alias / "apple")
        with fixture.patches():
            result = apple.build(fixture.args)
            for row in result["targets"]:
                receipt = row["provider_receipt"]
                view = Path(receipt["view_root"])
                lexical_view = Path(row["work"]) / "provider"
                self.assertNotEqual(str(view), str(lexical_view))
                self.assertTrue(view.samefile(lexical_view))
                wrong = (f"cargo:rustc-link-search=native={lexical_view}/lib\n"
                         f"cargo:include={lexical_view}/include\ncargo:version_number=30600020\n").encode()
                with self.assertRaisesRegex(provider.InputError, "unexpected OpenSSL library search"):
                    provider.check_build_script_output(wrong, receipt)
                evidence = fixture.args.output / "provenance" / row["target"]["rust"]
                output = evidence / row["openssl_outputs"][0]["retained_file"]
                self.assertEqual(output.read_bytes(),
                    (f"cargo:rustc-link-search=native={view}/lib\ncargo:include={view}/include\n"
                     "cargo:version_number=30600020\n").encode())
                for name in AUDITS:
                    self.assertTrue((evidence / name).is_file())
        self.assertEqual(len(result["targets"]), 2)
        self.assertFalse(result["ios_binaries_executed"])

    def test_two_target_success_wires_release_empty_libs_compile_and_link_only(self):
        fixture = AppleFixture(self.root / "success")
        with fixture.patches():
            result = apple.build(fixture.args)
        self.assertEqual([r["target"]["rust"] for r in result["targets"]], [r["rust"] for r in apple.TARGETS])
        self.assertNotEqual(result["targets"][0]["library_sha256"], result["targets"][1]["library_sha256"])
        for flag in ("framework_provider_bundled", "ios_binaries_executed", "source_binary_equivalence_claimed", "consumer_or_product_activation"):
            self.assertFalse(result[flag])
        self.assertEqual(result["process_limits"], {"command_seconds": bounded_process.COMMAND_TIMEOUT_SECONDS, "log_bytes": bounded_process.MAX_LOG_BYTES})
        for row in result["targets"]:
            target = row["target"]["rust"]
            self.assert_audits(fixture, target)
            self.assertEqual(row["source_manifest"]["source_profile"], apple.PROFILE)
            self.assertEqual(row["system_link_flags"], SYSTEM_FLAGS)
            self.assertEqual(len(row["link_probes"]), 8)
            self.assertEqual(row["symbol_reader"], fixture.reader)
            for scan in ("04-rust-export-symbols.txt", "04-c-export-symbols.txt"):
                call = next(c for c in fixture.calls if c["target"] == target and c["log"].name == scan)
                archive = row["library"] if scan.startswith("04-rust") else row["mixed_provider"]["library"]
                self.assertEqual(call["argv"], apple.rust_symbol_reader.scan_command(fixture.reader, archive))
            self.assertFalse(row["header_probe_linked_or_executed"])
            self.assertIn("-fsyntax-only", row["header_probe_command"])
            self.assertNotIn("-o", row["header_probe_command"])
            self.assertTrue(all(not p["executed"] for p in row["link_probes"]))
            self.assertEqual(row["library_sha256"], sha256(Path(row["library"]).read_bytes()))
            for probe in row["link_probes"]:
                symbol = fixture.profile["probe_entry_symbols"][probe["group"]][probe["language"]]
                self.assertIn("_" + symbol, probe["command"])
                self.assertIn("-force_load", probe["command"])
            self.assertEqual(len(row["openssl_outputs"]), 1)
            self.assertIn("/release/build/openssl-sys-", row["openssl_outputs"][0]["source_path"])
            target_calls = [c for c in fixture.calls if c["target"] == target]
            self.assertEqual(len({c["log"].name for c in target_calls}), len(target_calls))
            for call in target_calls:
                argv, env = call["argv"], call["env"]
                status = json.loads(call["log"].with_name(call["log"].name + ".status.json").read_bytes())
                self.assertEqual(status["outcome"], "success")
                self.assertTrue(status["cleanup"]["direct_child_reaped"])
                if call["source"].name == "source":
                    key = target.upper().replace("-", "_") + "_OPENSSL_LIBS"
                    self.assertIn(key, env)
                    self.assertEqual(env[key], "")
                    self.assertNotIn("OPENSSL_LIBS", env)
                    self.assertNotIn("RUSTFLAGS", env)
                    self.assertEqual(env["IPHONEOS_DEPLOYMENT_TARGET"], "17.0")
                if argv[0] == "controlled-cargo" and argv[1] in ("build", "rustc", "tree"):
                    self.assertNotIn("--no-default-features", argv)
                    self.assertIn("--frozen", argv)
                    self.assertNotIn("test", argv)
            self.assertTrue((fixture.args.output / "provenance" / target / "target-evidence.json").is_file())
        self.assertEqual(result["xcframework_command"][:2], ["/usr/bin/xcodebuild", "-create-xcframework"])
        self.assertEqual(result["xcframework_command"].count("-library"), 2)
        package_output = str(fixture.args.work_dir / "package/IDevice.xcframework")
        device, simulator = result["targets"]
        self.assertEqual(result["xcframework_command"], ["/usr/bin/xcodebuild", "-create-xcframework",
            "-library", device["library"], "-headers", device["headers"],
            "-library", simulator["library"], "-headers", simulator["headers"], "-output", package_output])
        operation_command = [sys.executable, "-I", str(fixture.recipe / "xcframework_operation.py"),
            device["library"], device["headers"], simulator["library"], simulator["headers"], package_output]
        self.assertEqual(result["xcframework_operation_command"], operation_command)
        self.assertEqual(result["xcframework_operation_sha256"], PACKAGING_OPERATION_SHA256)
        package_calls = [call for call in fixture.calls if call["log"].name == "create-xcframework.txt"]
        self.assertEqual(len(package_calls), 1)
        self.assertEqual(package_calls[0]["argv"], operation_command)
        self.assertEqual(package_calls[0]["source"], fixture.args.work_dir)
        self.assertEqual(package_calls[0]["env"], {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "DEVELOPER_DIR": fixture.config["developer_dir"],
            "HOME": str(fixture.args.work_dir / "aarch64-apple-ios/home"),
            "TMPDIR": str(fixture.args.work_dir / "aarch64-apple-ios/tmp")})
        self.assertTrue((fixture.args.output / "LICENSE-idevice.txt").is_file())
        self.assertTrue((fixture.args.output / "LICENSE-OpenSSL.txt").is_file())
        self.assertTrue((fixture.args.output / "SHA256SUMS").is_file())
        with zipfile.ZipFile(fixture.args.output / "corresponding-source.zip") as archive:
            self.assertIn("crate-archives/fixture-1.0.0.crate", archive.namelist())
            metadata = json.loads(archive.read("source-provenance.json"))
            self.assertEqual(metadata["recipe_files"], fixture.recipe_files)
            for name in PACKAGING_RECIPE_FILES:
                self.assertEqual(archive.read("recipe/" + name), (ROOT / name).read_bytes())
                self.assertEqual(sha256(archive.read("recipe/" + name)), fixture.recipe_files[name])
            self.assertFalse(any("opaque Rust archive" in archive.read(name).decode(errors="ignore") for name in archive.namelist()))
            self.assertFalse(any("opaque framework fixture" in archive.read(name).decode(errors="ignore") for name in archive.namelist()))

    def test_early_and_late_native_failures_leave_target_audits_logs_and_no_publication(self):
        for index, (target, log) in enumerate([
            ("aarch64-apple-ios", "toolchain-rustc.txt"), ("aarch64-apple-ios", "01-provider-header.txt"),
            ("aarch64-apple-ios", "03-release-build.txt"), ("aarch64-apple-ios", "04-native-static-libs.txt"),
            ("aarch64-apple-ios", "05-link-host-swift.txt"), ("aarch64-apple-ios-sim", "05-link-pairing-swift.txt")]):
            with self.subTest(target=target, log=log):
                fixture = AppleFixture(self.root / str(index))
                fixture.fail = (target, log)
                with fixture.patches(), self.assertRaisesRegex(VerificationError, "nonzero_exit"):
                    apple.build(fixture.args)
                self.assertFalse(fixture.args.output.exists())
                self.assert_audits(fixture, target)
                folder = fixture.args.work_dir / target / "completed"
                self.assertIn("controlled native-command failure", (folder / log).read_text())
                self.assertFalse((folder / "target-evidence.json").exists())

    def test_second_target_failure_reaudits_successful_first_target_mutation(self):
        fixture = AppleFixture(self.root / "global-reaudit")
        fixture.fail = ("aarch64-apple-ios-sim", "03-release-build.txt")
        fixture.mutate = lambda f: (f.args.work_dir / "aarch64-apple-ios/source/Cargo.lock").write_bytes(b"changed after first target success\n")
        with fixture.patches(), self.assertRaisesRegex(VerificationError, "nonzero_exit"):
            apple.build(fixture.args)
        self.assertFalse(fixture.args.output.exists())
        audits = self.assert_audits(fixture, "aarch64-apple-ios")
        self.assertFalse(audits["workspace-input-audit.json"]["original_inputs_unchanged"])
        self.assert_audits(fixture, "aarch64-apple-ios-sim")

    def test_missing_or_nonempty_apple_libs_stop_before_header_or_build(self):
        for name in ("missing", "nonempty"):
            with self.subTest(libs=name):
                fixture = AppleFixture(self.root / name)
                fixture.omit_provider_libs = name == "missing"
                fixture.provider_libs = "ssl:crypto" if name == "nonempty" else ""
                with fixture.patches(), self.assertRaises(VerificationError):
                    apple.build(fixture.args)
                self.assertFalse(fixture.args.output.exists())
                self.assert_audits(fixture, "aarch64-apple-ios")
                self.assertFalse(any(c["log"].name == "01-provider-header.txt" for c in fixture.calls))

    def test_feature_graph_or_compiler_artifact_synthetic_feature_blocks_link_and_package(self):
        for bad in ("graph", "artifact", "missing-default"):
            with self.subTest(features=bad):
                fixture = AppleFixture(self.root / bad)
                fixture.bad_features = bad
                with fixture.patches(), self.assertRaises(VerificationError):
                    apple.build(fixture.args)
                self.assertFalse(fixture.args.output.exists())
                self.assert_audits(fixture, "aarch64-apple-ios")
                self.assertFalse(any(c["log"].name.startswith("05-link-") for c in fixture.calls))

    def test_selected_release_output_provider_directives_and_size_fail_before_link(self):
        for bad in ("static-provider", "oversized"):
            with self.subTest(output=bad):
                fixture = AppleFixture(self.root / bad)
                fixture.bad_output = bad
                with fixture.patches(), self.assertRaises(ValueError):
                    apple.build(fixture.args)
                self.assertFalse(fixture.args.output.exists())
                self.assert_audits(fixture, "aarch64-apple-ios")
                folder = fixture.args.work_dir / "aarch64-apple-ios/completed"
                retained = list(folder.glob("03-release-build-openssl-sys-*.txt"))
                self.assertEqual(len(retained), 1 if bad == "static-provider" else 0)
                self.assertFalse(any(c["log"].name.startswith("05-link-") for c in fixture.calls))

    def test_reported_extra_provider_blocks_all_c_and_swift_links(self):
        fixture = AppleFixture(self.root / "report-provider")
        fixture.native_flags += ["-lcrypto"]
        with fixture.patches(), self.assertRaisesRegex(VerificationError, "provider"):
            apple.build(fixture.args)
        self.assert_audits(fixture, "aarch64-apple-ios")
        self.assertFalse(fixture.args.output.exists())
        self.assertFalse(any(c["log"].name.startswith("05-link-") for c in fixture.calls))

    def test_bounded_link_timeout_retains_diagnostics_and_all_audits(self):
        fixture = AppleFixture(self.root / "timeout")
        fixture.fail = ("aarch64-apple-ios", "05-link-host-c.txt")
        fixture.failure_kind = "timeout"
        with fixture.patches(), self.assertRaisesRegex(VerificationError, "timeout"):
            apple.build(fixture.args)
        self.assert_audits(fixture, "aarch64-apple-ios")
        self.assertFalse(fixture.args.output.exists())
        status = json.loads((fixture.args.work_dir / "aarch64-apple-ios/completed/05-link-host-c.txt.status.json").read_bytes())
        self.assertEqual(status["outcome"], "timeout")
        self.assertTrue(status["cleanup"]["direct_child_reaped"])

    def test_wrong_xcframework_slice_metadata_prevents_publication(self):
        fixture = AppleFixture(self.root / "wrong-slices")
        fixture.bad_slices = True
        with fixture.patches(), self.assertRaisesRegex(VerificationError, "slice metadata"):
            apple.build(fixture.args)
        self.assertFalse(fixture.args.output.exists())
        for target in apple.TARGETS:
            self.assert_audits(fixture, target["rust"])

    def test_packaged_library_header_or_module_mutation_prevents_publication(self):
        for name in ("library", "idevice.h", "module.modulemap"):
            with self.subTest(file=name):
                fixture = AppleFixture(self.root / name)
                fixture.bad_packaged_file = name
                with fixture.patches(), self.assertRaisesRegex(VerificationError, "packaged"):
                    apple.build(fixture.args)
                self.assertFalse(fixture.args.output.exists())
                for target in apple.TARGETS:
                    self.assert_audits(fixture, target["rust"])

    def test_packaging_command_failure_retains_both_targets_and_package_diagnostics(self):
        fixture = AppleFixture(self.root / "package-failure")
        fixture.fail = ("work", "create-xcframework.txt")
        with fixture.patches(), self.assertRaisesRegex(VerificationError, "nonzero_exit"):
            apple.build(fixture.args)
        self.assertFalse(fixture.args.output.exists())
        for target in apple.TARGETS:
            self.assert_audits(fixture, target["rust"])
            self.assertTrue((fixture.args.work_dir / target["rust"] / "completed/target-evidence.json").is_file())
        status = json.loads((fixture.args.work_dir / "create-xcframework.txt.status.json").read_bytes())
        self.assertEqual(status["outcome"], "nonzero_exit")
        self.assertEqual(status["returncode"], 7)

    def test_packaging_operation_timeout_retains_both_targets_audits_and_diagnostics(self):
        fixture = AppleFixture(self.root / "package-timeout")
        fixture.fail = ("work", "create-xcframework.txt")
        fixture.failure_kind = "timeout"
        with fixture.patches(), self.assertRaisesRegex(VerificationError, "timeout"):
            apple.build(fixture.args)
        self.assertFalse(fixture.args.output.exists())
        for target in apple.TARGETS:
            self.assert_audits(fixture, target["rust"])
            self.assertTrue((fixture.args.work_dir / target["rust"] / "completed/target-evidence.json").is_file())
        log = fixture.args.work_dir / "create-xcframework.txt"
        self.assertIn("controlled XCFramework creation", log.read_text())
        status = json.loads(log.with_name(log.name + ".status.json").read_bytes())
        self.assertEqual(status["outcome"], "timeout")
        self.assertTrue(status["cleanup"]["direct_child_reaped"])
        self.assertTrue(status["cleanup"]["group_empty"])

    def test_packaging_operation_mutation_fails_before_native_commands(self):
        fixture = AppleFixture(self.root / "package-module-mutation")
        (fixture.recipe / "xcframework_operation.py").write_bytes(b"controlled operation module mutation\n")
        with fixture.patches(), self.assertRaisesRegex(VerificationError, "Apple recipe input"):
            apple.build(fixture.args)
        self.assertFalse(fixture.args.output.exists())
        self.assertFalse(fixture.args.work_dir.exists())
        self.assertEqual(fixture.calls, [])

    def test_provider_mutation_after_both_targets_success_blocks_final_publication(self):
        fixture = AppleFixture(self.root / "late-provider")
        fixture.mutate_on = ("work", "create-xcframework.txt")
        fixture.mutate = lambda f: (f.args.provider_inputs / "iphoneos/OpenSSL.framework/Headers/ssl.h").write_bytes(b"late mutation\n")
        with fixture.patches(), self.assertRaisesRegex(VerificationError, "packaging input audit"):
            apple.build(fixture.args)
        self.assertFalse(fixture.args.output.exists())
        for target in apple.TARGETS:
            audits = self.assert_audits(fixture, target["rust"])
            self.assertFalse(audits["provider-input-audit.json"]["unchanged"])
            self.assertTrue((fixture.args.work_dir / target["rust"] / "completed/target-evidence.json").is_file())

    def test_different_target_headers_fail_before_xcframework_creation(self):
        fixture = AppleFixture(self.root / "headers-differ")
        fixture.mismatched_headers = True
        with fixture.patches(), self.assertRaisesRegex(VerificationError, "headers differ"):
            apple.build(fixture.args)
        self.assertFalse(fixture.args.output.exists())
        self.assertFalse(any(call["log"].name == "create-xcframework.txt" for call in fixture.calls))
        for target in apple.TARGETS:
            self.assert_audits(fixture, target["rust"])

    def test_external_recipe_hash_mismatch_fails_before_native_commands(self):
        fixture = AppleFixture(self.root / "bad-index")
        fixture.args.recipe_lock_sha256 = "0" * 64
        with fixture.patches(), self.assertRaises(VerificationError):
            apple.build(fixture.args)
        self.assertFalse(fixture.args.output.exists())
        self.assertEqual(fixture.calls, [])


if __name__ == "__main__":
    unittest.main()
