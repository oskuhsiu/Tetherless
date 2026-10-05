"""Controlled component-runner wiring; only bounded Python children execute.

The provider, workspace and both vendor audits use synthetic authenticated files.
No Rust, Cargo, compiler, Xcode, binary inspection or app/device work runs here.
Successful fixture summaries below are synthetic, never native success evidence.
"""
from __future__ import annotations

from contextlib import ExitStack
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import tomllib
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bounded_process
import run_pairing_component_tests as runner
from apply_patch import VerificationError, canonical_json, git_blob, sha256

spec = importlib.util.spec_from_file_location("component_fixture_provider", ROOT / "split-provider/provider_inputs.py")
provider = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider)

AUDIT_FILES = ("vendor-input-audit.json", "derived-vendor-input-audit.json",
               "workspace-input-audit.json", "provider-input-audit.json")
ACQUISITION_SUITES = [
    ("idevice-ffi", "staged_pairing::", 18), ("idevice", "bounded_rsd_tests", 25),
    ("idevice-ffi", "staged_acquisition::", 11),
    ("idevice", "remote_pairing::staged_contributory_tests::", 3),
    ("idevice", "remote_pairing::socket::staged_rp_socket_tests::", 2),
    ("idevice", "remote_pairing::tunnel::staged_openssl::tests::", 4),
    ("idevice", "remote_pairing::tunnel::staged_openssl_fixtures::", 4),
    ("idevice", "remote_pairing::tunnel::staged_packet_io::", 7),
]
HOST_SUITES = [("idevice-ffi", "bounded_pairing_host::", 8), ("idevice", "bounded_host_tests", 5),
               ("idevice", "bounded_host_frame_tests", 3), ("idevice", "bounded_opack_tests", 4)]


def build_event(out_dir, **overrides):
    event = dict(reason="build-script-executed", package_id=runner.OPENSSL_PACKAGE_ID, out_dir=str(out_dir))
    event.update(overrides)
    return event


def write_events(log, events):
    log.write_bytes(b"".join(json.dumps(event).encode() + b"\n" for event in events))


def directives(view):
    return (f"cargo:rustc-link-search=native={view}/lib\ncargo:include={view}/include\n"
            "cargo:version_number=30600020\ncargo:rustc-link-lib=static=ssl\n"
            "cargo:rustc-link-lib=static=crypto\n").encode()


class RunnerFixture:
    """Replace tool invocation/staging, retain actual provider and audit behavior."""
    def __init__(self, root, profile="acquisition-only"):
        self.root = root
        self.root.mkdir()
        self.profile_path = "candidate-profiles/" + profile + ".json"
        self.profile = json.loads((ROOT / self.profile_path).read_bytes())
        self.defaults = tomllib.loads((ROOT / "upstream/ffi/Cargo.toml").read_text())["features"]["default"]
        self.calls = []
        self.failure_log = None
        self.failure_kind = "nonzero_exit"
        self.summary_offset = 0
        self.output_fault = None
        self.mutation = None
        self.check_count = 0
        self.sdk = root / "selected-sdk"
        self.sdk.mkdir()
        self.compiler = root / "selected-tool"
        self.compiler.write_text("opaque tool path fixture; never executed\n")
        toolchain = root / "toolchain.json"
        toolchain.write_bytes(canonical_json({"schema": 1, "source_date_epoch": 1,
                                               "developer_dir": str(root / "developer")}))
        self.args = SimpleNamespace(profile=profile, source=root / "input-source", crate_cache=root / "cache",
            provider_inputs=root / "provider-source", work_dir=root / "work", output=root / "published",
            toolchain_lock=toolchain, toolchain_lock_sha256=sha256(toolchain.read_bytes()))
        self.contract = {"commit": provider.COMMIT, "enabled": False, "product_activation": False,
            "entries": [], "targets": {runner.TARGET: {"kind": "standalone-static", "header_root": "headers",
                "header_count": 2, "native_library_input_paths": ["lib/libssl.a", "lib/libcrypto.a"],
                "environment_values": {"OPENSSL_LIBS": "ssl:crypto", "OPENSSL_STATIC": "1", "OPENSSL_NO_VENDOR": "1"}}}}
        for name, data in {"LICENSE.txt": b"synthetic license\n", "headers/ssl.h": b"synthetic header\n",
                           "headers/configuration.h": b"synthetic configuration\n",
                           "lib/libssl.a": b"opaque fixture ssl bytes\n", "lib/libcrypto.a": b"opaque fixture crypto bytes\n"}.items():
            path = self.args.provider_inputs / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o644)
            self.contract["entries"].append({"path": name, "mode": "100644", "size": len(data),
                                              "sha256": sha256(data), "git_blob": git_blob(data)})

    @property
    def completed(self):
        return self.args.work_dir / "completed"

    def environment(self, _config, work):
        (work / "cargo-home").mkdir()
        env = {"PATH": os.defpath, "CARGO_HOME": str(work / "cargo-home"), "CARGO_NET_OFFLINE": "true",
               "CARGO_TARGET_DIR": str(work / "target"), "LANG": "C", "LC_ALL": "C",
               "OPENSSL_DIR": "ambient-must-be-removed", "RUSTFLAGS": "ambient-must-be-removed"}
        return env, {"cargo": "controlled-cargo-never-executed"}

    def stage(self, source, destination, recipe, profile_path):
        if (source, recipe, profile_path) != (self.args.source, ROOT, self.profile_path):
            raise AssertionError("runner selected the wrong source/profile")
        (destination / "ffi").mkdir(parents=True)
        (destination / "ffi/Cargo.toml").write_text("[features]\ndefault = " + json.dumps(self.defaults) + "\n")
        (destination / "Cargo.toml").write_text('[workspace]\nmembers = ["ffi"]\n')
        (destination / "Cargo.lock").write_text("version = 4\n")
        return {"files": {str(p.relative_to(destination)): sha256(p.read_bytes())
                           for p in destination.rglob("*") if p.is_file()}, "symlinks": {},
                "source_profile": profile_path, "source_profile_sha256": sha256((recipe / profile_path).read_bytes())}

    def vendor(self, *, source, work, cache, env, derive_metadata):
        if not derive_metadata or cache != self.args.crate_cache:
            raise AssertionError("component runner must request owned derived vendor metadata")
        inputs = {"fixture-1/src/lib.rs": sha256(b"synthetic authenticated source\n")}
        for name in ("vendor", "build-vendor"):
            path = work / name / "fixture-1/src/lib.rs"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"synthetic authenticated source\n")
        config = work / "cargo-home/config.toml"
        config.write_text("[net]\noffline = true\n")
        return {"vendor_directory": str(work / "vendor"), "authenticated_inputs": inputs,
                "cargo_home": str(config.parent), "cargo_config": str(config), "cargo_config_sha256": sha256(config.read_bytes()),
                "workspace_lock_sha256": sha256((source / "Cargo.lock").read_bytes()), "nested_metadata_frozen": True,
                "derived_build": {"directory": str(work / "build-vendor"), "authenticated_inputs": dict(inputs)}}

    def check_output(self, output, receipt):
        result = provider.check_build_script_output(output, receipt)
        self.check_count += 1
        if self.mutation and self.check_count == len(self.profile["native_test_filters"]):
            self.mutation(self)
        return result

    def command(self, argv, *, source, env, log):
        self.calls.append({"argv": list(argv), "env": dict(env), "log": log, "source": source})
        if argv[:4] == ["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"]:
            output = str(self.sdk) + "\n"
        elif argv[:4] == ["/usr/bin/xcrun", "--sdk", "macosx", "--find"]:
            output = str(self.compiler) + "\n"
        elif argv[:4] == ["/usr/bin/xcrun", "--sdk", "macosx", "clang"]:
            output = "controlled header syntax-only result\n"
        elif argv[:2] == ["controlled-cargo-never-executed", "tree"]:
            output = "controlled feature graph for " + argv[argv.index("-p") + 1] + "\n"
        elif argv[:2] == ["controlled-cargo-never-executed", "test"]:
            selected_filter = argv[argv.index("--message-format=json-render-diagnostics") + 1]
            selected = next(s for s in self.profile["native_test_filters"] if s["filter"] == selected_filter)
            out_dir = self.args.work_dir / "target" / runner.TARGET / "debug/build" / ("openssl-sys-" + log.stem) / "out"
            out_dir.mkdir(parents=True)
            selected_output = out_dir.parent / "output"
            receipt = json.loads((self.completed / "provider-input-receipt.json").read_bytes())
            selected_output.write_bytes(directives(Path(receipt["view_root"])))
            event = build_event(out_dir)
            if self.output_fault == "missing":
                selected_output.unlink()
            elif self.output_fault == "oversized":
                selected_output.write_bytes(b"x" * (1024 * 1024 + 1))
            elif self.output_fault == "symlink":
                moved = selected_output.with_name("redirected-output")
                selected_output.rename(moved)
                selected_output.symlink_to(moved)
            elif self.output_fault == "directives":
                with selected_output.open("ab") as stream:
                    stream.write(b"cargo:rustc-link-lib=dylib=ssl\n")
            elif self.output_fault == "wrong-package":
                event["package_id"] = "openssl-sys@0.9.112"
            output = json.dumps(event) + "\n"
            output += "suite-marker=" + selected["filter"] + "\n"
            output += (f"test result: ok. {selected['expected_passed'] + self.summary_offset} passed; 0 failed; "
                       "0 ignored; 0 measured; 0 filtered out; finished in 0.01s\n")
        else:
            raise AssertionError("unapproved command would have executed: " + repr(argv))
        code = "import sys,time; sys.stdout.write(" + repr(output) + "); sys.stdout.flush()"
        options = dict(timeout_seconds=2, max_log_bytes=8192, tail_bytes=8192,
                       term_grace_seconds=.2, kill_join_seconds=.2)
        if log.name == self.failure_log:
            if self.failure_kind == "timeout":
                code += "; time.sleep(5)"
                options["timeout_seconds"] = .15
            elif self.failure_kind == "output_limit":
                code += "; sys.stdout.write('x'*16384); sys.stdout.flush()"
            else:
                code += "; sys.stderr.write('controlled failure\\n'); sys.exit(7)"
        # The captured command's evidence is explicitly a Python fixture; the
        # runner's planned Cargo/clang argv is recorded separately in self.calls.
        return bounded_process.capture_helper_command([sys.executable, "-u", "-c", code],
            source=source, env=env, log=log, **options)

    def patches(self):
        stack = ExitStack()
        stack.enter_context(patch.object(provider, "load_contract", return_value=self.contract))
        api = SimpleNamespace(prepare_inputs=provider.prepare_inputs, build_environment=provider.build_environment,
                              audit_inputs=provider.audit_inputs, check_build_script_output=self.check_output)
        for name, value in {"load_profile": lambda _: (self.profile_path, copy.deepcopy(self.profile)),
                            "load_provider": lambda: api, "native_environment": self.environment,
                            "verify_toolchain": lambda *_: {"controlled_fixture": True}, "stage": self.stage,
                            "prepare_offline_vendor": self.vendor, "capture_helper_command": self.command}.items():
            stack.enter_context(patch.object(runner, name, side_effect=value))
        return stack


class ComponentProfileTests(unittest.TestCase):
    def test_registered_profiles_have_exact_reviewed_filters_and_opt_in(self):
        for name, expected in (("acquisition-only", ACQUISITION_SUITES), ("combined", ACQUISITION_SUITES + HOST_SUITES)):
            with self.subTest(profile=name):
                path, profile = runner.load_profile(name)
                self.assertEqual(path, "candidate-profiles/" + name + ".json")
                self.assertEqual([(s["package"], s["filter"], s["expected_passed"]) for s in profile["native_test_filters"]], expected)
                self.assertEqual(sum(s[2] for s in expected), 74 if name == "acquisition-only" else 94)
                self.assertEqual(profile["build_additional_features"], ["openssl"])
                self.assertTrue(profile["activation"]["test_only_execution_authorized"])
                self.assertFalse(profile["activation"]["enabled"])
                self.assertFalse(profile["activation"]["consumer_integration_allowed"])

    def test_scope_mutations_are_rejected(self):
        _, original = runner.load_profile("acquisition-only")
        for change in (lambda p: p["native_test_filters"].reverse(),
                       lambda p: p["native_test_filters"][0].update(expected_passed=19),
                       lambda p: p.update(build_additional_features=["openssl", "aws-lc"]),
                       lambda p: p.update(patch_complete=False),
                       lambda p: p["activation"].update(enabled=True),
                       lambda p: p["activation"].update(consumer_integration_allowed=True),
                       lambda p: p["activation"].update(test_only_execution_authorized=False)):
            profile = copy.deepcopy(original)
            change(profile)
            with patch.object(runner, "load_lock", return_value=profile), self.assertRaises(VerificationError):
                runner.load_profile("acquisition-only")

    def test_unknown_profile_is_rejected(self):
        for name in ("helper-only", "host-only", "default", "../combined"):
            with self.subTest(profile=name), self.assertRaises(VerificationError):
                runner.load_profile(name)

    def test_registered_provider_recipe_loads_the_approved_api(self):
        loaded = runner.load_provider()
        for name in ("prepare_inputs", "build_environment", "audit_inputs", "check_build_script_output"):
            self.assertTrue(callable(getattr(loaded, name)))


@unittest.skipUnless(os.name == "posix", "bounded Python fixture children require POSIX")
class ComponentRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="component fixture quoted \" 🌿 ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def assert_audits(self, fixture, *, published=False):
        directory = fixture.args.output if published else fixture.completed
        for name in AUDIT_FILES:
            self.assertTrue((directory / name).is_file(), name)
        return {name: json.loads((directory / name).read_bytes()) for name in AUDIT_FILES}

    def test_alias_parent_uses_receipt_paths_and_strict_checker_rejects_lexical_alias(self):
        actual = self.root / "actual-parent"
        actual.mkdir()
        alias = self.root / "alias-parent"
        alias.symlink_to(actual.resolve(), target_is_directory=True)
        for profile, count in (("acquisition-only", 74), ("combined", 94)):
            with self.subTest(profile=profile):
                fixture = RunnerFixture(alias / profile, profile)
                lexical_view = fixture.args.work_dir / "host-provider"
                with fixture.patches():
                    result = runner.execute(fixture.args)
                    receipt = result["provider_receipt"]
                    view = Path(receipt["view_root"])
                    self.assertNotEqual(str(view), str(lexical_view))
                    self.assertTrue(view.samefile(lexical_view))
                    with self.assertRaisesRegex(provider.InputError, "unexpected OpenSSL library search"):
                        provider.check_build_script_output(directives(lexical_view), receipt)
                self.assertEqual(result["passed"], count)
                self.assertEqual(len(result["tests"]), len(fixture.profile["native_test_filters"]))
                self.assert_audits(fixture, published=True)
                for suite in result["tests"]:
                    retained = suite["openssl_outputs"][0]
                    output = fixture.args.output / retained["retained_file"]
                    self.assertEqual(output.read_bytes(), directives(view))

    def test_successful_74_and_94_wiring_features_source_profile_and_exclusive_logs(self):
        for profile, expected in (("acquisition-only", 74), ("combined", 94)):
            with self.subTest(profile=profile):
                fixture = RunnerFixture(self.root / profile, profile)
                with fixture.patches():
                    result = runner.execute(fixture.args)
                self.assertEqual(result["passed"], expected)
                self.assertEqual(sum(s["passed"] for s in result["tests"]), expected)
                self.assertFalse(result["artifact_or_product_activation"])
                self.assertFalse(result["header_probe_linked_or_executed"])
                self.assertEqual(result["process_limits"], {"command_seconds": bounded_process.COMMAND_TIMEOUT_SECONDS,
                                                             "log_bytes": bounded_process.MAX_LOG_BYTES})
                self.assertFalse(fixture.completed.exists())
                self.assert_audits(fixture, published=True)
                saved = json.loads((fixture.args.output / "source-manifest.json").read_bytes())
                self.assertEqual(saved["source_profile"], fixture.profile_path)
                self.assertEqual(json.loads((fixture.args.output / "component-profile.json").read_bytes()), fixture.profile)
                graphs = result["feature_graphs"]
                self.assertEqual([g["package"] for g in graphs], ["idevice-ffi", "idevice"])
                self.assertEqual(len({g["log_file"] for g in graphs}), 2)
                for call in fixture.calls:
                    argv, env = call["argv"], call["env"]
                    self.assertEqual(env["CARGO_NET_OFFLINE"], "true")
                    self.assertEqual(env["AARCH64_APPLE_DARWIN_OPENSSL_LIBS"], "ssl:crypto")
                    self.assertNotIn("OPENSSL_DIR", env)
                    self.assertNotIn("RUSTFLAGS", env)
                    if argv[0] == "controlled-cargo-never-executed":
                        package = argv[argv.index("-p") + 1]
                        expected_features = ["openssl"] if package == "idevice-ffi" else [*fixture.defaults, "openssl"]
                        self.assertEqual(argv[argv.index("--features") + 1].split(","), expected_features)
                        self.assertIn("--frozen", argv)
                        self.assertNotIn("--no-default-features", argv)
                        self.assertEqual(argv[argv.index("--target") + 1], "aarch64-apple-darwin")
                        self.assertEqual(env["SDKROOT"], str(fixture.sdk))
                        self.assertEqual(env["CC_aarch64_apple_darwin"], str(fixture.compiler))
                        if argv[1] == "test":
                            self.assertIn("--lib", argv)
                            self.assertIn("--message-format=json-render-diagnostics", argv)
                            selected_filter = argv[argv.index("--message-format=json-render-diagnostics") + 1]
                            self.assertEqual(argv[-2:] == ["--", "--nocapture"], selected_filter == "staged_acquisition::")
                header = result["header_probe_command"]
                self.assertIn("-fsyntax-only", header)
                self.assertIn("-Werror=incompatible-function-pointer-types", header)
                self.assertEqual(header[-1], str(ROOT / "split-provider/header_probe.c"))
                self.assertEqual(header[header.index("-I") + 1], str(Path(result["provider_receipt"]["view_root"]) / "include"))
                self.assertNotIn("-o", header)
                self.assertNotIn("-lssl", header)
                self.assertNotIn("-framework", header)
                self.assertEqual(len([c for c in fixture.calls if "clang" in c["argv"] and "--find" not in c["argv"]]), 1)
                self.assertEqual(len({c["log"].name for c in fixture.calls}), len(fixture.calls))
                for suite in result["tests"]:
                    log = fixture.args.output / suite["log_file"]
                    text = log.read_text()
                    self.assertEqual([line for line in text.splitlines() if line.startswith("suite-marker=")],
                                     ["suite-marker=" + suite["filter"]])
                    status = json.loads((fixture.args.output / suite["status_file"]).read_bytes())
                    self.assertEqual(status["outcome"], "success")
                    self.assertTrue(status["cleanup"]["direct_child_reaped"])
                    self.assertEqual(len(suite["openssl_outputs"]), 1)
                    retained = suite["openssl_outputs"][0]
                    self.assertTrue(retained["retained_file"].startswith(log.stem + "-openssl-sys-"))
                    self.assertEqual(sha256((fixture.args.output / retained["retained_file"]).read_bytes()), retained["output_sha256"])
                self.assertTrue((fixture.args.output / "SHA256SUMS").is_file())

    def test_representative_phase_and_suite_failures_retain_all_audits_and_logs(self):
        for index, (profile, log_name) in enumerate([
            ("acquisition-only", "00-sdk-path.txt"), ("acquisition-only", "00-tool-clang++.txt"),
            ("acquisition-only", "00-header-compile.txt"), ("acquisition-only", "00-features-idevice-ffi.txt"),
            ("acquisition-only", "00-features-idevice.txt"), ("acquisition-only", "01-idevice-ffi.txt"),
            ("acquisition-only", "05-idevice.txt"), ("acquisition-only", "08-idevice.txt"),
            ("combined", "09-idevice-ffi.txt"), ("combined", "12-idevice.txt"),
        ]):
            with self.subTest(profile=profile, log=log_name):
                fixture = RunnerFixture(self.root / str(index), profile)
                fixture.failure_log = log_name
                with fixture.patches(), self.assertRaises(VerificationError):
                    runner.execute(fixture.args)
                self.assertFalse(fixture.args.output.exists())
                self.assertEqual(fixture.calls[-1]["log"].name, log_name)
                audits = self.assert_audits(fixture)
                self.assertTrue(audits["provider-input-audit.json"]["unchanged"])
                for name in AUDIT_FILES[:3]:
                    self.assertTrue(audits[name]["original_inputs_unchanged"])
                self.assertIn("controlled failure", (fixture.completed / log_name).read_text())
                status = json.loads((fixture.completed / (log_name + ".status.json")).read_bytes())
                self.assertEqual(status["outcome"], "nonzero_exit")
                self.assertEqual(status["returncode"], 7)
                self.assertTrue(status["cleanup"]["direct_child_reaped"])
                self.assertFalse((fixture.completed / "test-evidence.json").exists())

    def test_timeout_and_quota_failure_cannot_publish_valid_looking_summary(self):
        for failure in ("timeout", "output_limit"):
            with self.subTest(failure=failure):
                fixture = RunnerFixture(self.root / failure)
                fixture.failure_log = "01-idevice-ffi.txt"
                fixture.failure_kind = failure
                with fixture.patches(), self.assertRaises(VerificationError):
                    runner.execute(fixture.args)
                self.assert_audits(fixture)
                self.assertFalse(fixture.args.output.exists())
                log = fixture.completed / fixture.failure_log
                self.assertIn("18 passed", log.read_text())
                self.assertLessEqual(log.stat().st_size, 8192)
                status = json.loads(log.with_name(log.name + ".status.json").read_bytes())
                self.assertEqual(status["outcome"], failure)
                self.assertTrue(status["cleanup"]["direct_child_reaped"])

    def test_wrong_fixture_count_retains_successful_process_log_but_rejects_publication(self):
        fixture = RunnerFixture(self.root / "wrong-count")
        fixture.summary_offset = -1
        with fixture.patches(), self.assertRaises(VerificationError):
            runner.execute(fixture.args)
        self.assert_audits(fixture)
        self.assertFalse(fixture.args.output.exists())
        self.assertEqual(fixture.calls[-1]["log"].name, "01-idevice-ffi.txt")
        status = json.loads((fixture.completed / "01-idevice-ffi.txt.status.json").read_bytes())
        self.assertEqual(status["outcome"], "success")

    def test_output_failures_after_successful_summary_retain_logs_and_all_audits(self):
        for fault in ("missing", "oversized", "symlink", "directives", "wrong-package"):
            with self.subTest(fault=fault):
                fixture = RunnerFixture(self.root / fault)
                fixture.output_fault = fault
                with fixture.patches(), self.assertRaises((ValueError, OSError)):
                    runner.execute(fixture.args)
                self.assert_audits(fixture)
                self.assertFalse(fixture.args.output.exists())
                self.assertFalse((fixture.completed / "test-evidence.json").exists())
                self.assertEqual(fixture.calls[-1]["log"].name, "01-idevice-ffi.txt")
                self.assertIn("18 passed", (fixture.completed / "01-idevice-ffi.txt").read_text())
                status = json.loads((fixture.completed / "01-idevice-ffi.txt.status.json").read_bytes())
                self.assertEqual(status["outcome"], "success")
                retained = list(fixture.completed.glob("01-idevice-ffi-openssl-sys-*.txt"))
                if fault == "directives":
                    self.assertEqual(len(retained), 1)
                    self.assertIn(b"cargo:rustc-link-lib=dylib=ssl", retained[0].read_bytes())
                else:
                    self.assertEqual(retained, [])

    def test_openssl_in_defaults_is_rejected_before_any_cargo_command(self):
        fixture = RunnerFixture(self.root / "openssl-default")
        fixture.defaults.append("openssl")
        with fixture.patches(), self.assertRaisesRegex(VerificationError, "explicit"):
            runner.execute(fixture.args)
        self.assert_audits(fixture)
        self.assertFalse(fixture.args.output.exists())
        self.assertFalse(any(call["argv"][0] == "controlled-cargo-never-executed" for call in fixture.calls))

    def test_invalid_provider_input_fails_before_commands_but_retains_four_audits(self):
        fixture = RunnerFixture(self.root / "invalid-provider")
        (fixture.args.provider_inputs / "headers/ssl.h").write_bytes(b"changed input")
        with fixture.patches(), self.assertRaises(ValueError):
            runner.execute(fixture.args)
        self.assertEqual(fixture.calls, [])
        audits = self.assert_audits(fixture)
        self.assertFalse(audits["provider-input-audit.json"]["unchanged"])
        self.assertFalse(fixture.args.output.exists())

    def test_provider_mutation_after_every_suite_passed_still_blocks_publication(self):
        fixture = RunnerFixture(self.root / "late-provider-mutation", "combined")
        fixture.mutation = lambda f: (f.args.provider_inputs / "headers/ssl.h").write_bytes(b"changed after all checks\n")
        with fixture.patches(), self.assertRaisesRegex(VerificationError, "audit"):
            runner.execute(fixture.args)
        self.assertEqual(fixture.check_count, 12)
        self.assertEqual(len([c for c in fixture.calls if c["argv"][1] == "test"]), 12)
        self.assertFalse(fixture.args.output.exists())
        self.assertFalse(self.assert_audits(fixture)["provider-input-audit.json"]["unchanged"])
        self.assertFalse((fixture.completed / "test-evidence.json").exists())

    def test_mutated_pristine_derived_or_workspace_inputs_preserve_all_audits(self):
        for name, relative in (("vendor", "vendor/fixture-1/src/lib.rs"),
                               ("derived-vendor", "build-vendor/fixture-1/src/lib.rs"),
                               ("workspace", "source/Cargo.lock")):
            with self.subTest(input=name):
                fixture = RunnerFixture(self.root / name)
                fixture.mutation = lambda f, path=relative: (f.args.work_dir / path).write_bytes(b"changed after summaries\n")
                with fixture.patches(), self.assertRaisesRegex(VerificationError, "audit"):
                    runner.execute(fixture.args)
                self.assertEqual(fixture.check_count, 8)
                self.assertFalse(fixture.args.output.exists())
                self.assertFalse(self.assert_audits(fixture)[name + "-input-audit.json"]["original_inputs_unchanged"])

    def test_each_audit_exception_preserves_the_other_three_audit_receipts(self):
        original_vendor = runner.audit_vendor_inputs
        original_workspace = runner.audit_workspace_inputs
        for name in ("vendor", "derived-vendor", "workspace"):
            with self.subTest(audit=name):
                fixture = RunnerFixture(self.root / name)
                fixture.failure_log = "00-header-compile.txt"
                def audit_vendor(receipt):
                    selected = "derived-vendor" if receipt.get("input_kind") == "derived_build_vendor" else "vendor"
                    if selected == name:
                        raise OSError("controlled unreadable " + name + " audit")
                    return original_vendor(receipt)
                def audit_workspace(*args):
                    if name == "workspace":
                        raise OSError("controlled unreadable workspace audit")
                    return original_workspace(*args)
                with fixture.patches(), patch.object(runner, "audit_vendor_inputs", side_effect=audit_vendor), \
                        patch.object(runner, "audit_workspace_inputs", side_effect=audit_workspace):
                    with self.assertRaisesRegex(VerificationError, "nonzero_exit"):
                        runner.execute(fixture.args)
                self.assertFalse(fixture.args.output.exists())
                audits = self.assert_audits(fixture)
                self.assertFalse(audits[name + "-input-audit.json"]["original_inputs_unchanged"])
                self.assertEqual(audits[name + "-input-audit.json"]["error_type"], "OSError")
                self.assertTrue(audits["provider-input-audit.json"]["unchanged"])


class SelectedOpenSSLOutputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="selected OpenSSL fixture ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = self.root / "target" / runner.TARGET
        self.out_dir = self.target / "debug/build/openssl-sys-approved/out"
        self.out_dir.mkdir(parents=True)
        self.output = self.out_dir.parent / "output"
        self.output.write_bytes(b"controlled selected output\n")
        self.log = self.root / "01-suite.txt"
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        self.checker = SimpleNamespace(check_build_script_output=Mock(return_value={"checked": True}))

    def select(self, events=None):
        write_events(self.log, events if events is not None else [build_event(self.out_dir)])
        return runner.selected_openssl_outputs(self.log, self.target)

    def retain(self):
        return runner.retain_openssl_outputs(self.checker, {"controlled": True}, self.log, self.target, self.evidence)

    def test_package_reason_and_exact_target_path_select_only_approved_output(self):
        good = build_event(self.out_dir)
        unrelated = [dict(good, package_id=value, out_dir="/unrelated/output") for value in (
            "openssl-sys", "openssl-sys@0.9.112", runner.OPENSSL_PACKAGE_ID.replace("0.9.112", "0.9.111"),
            "path+file:///untrusted#openssl-sys@0.9.112", "registry+https://example.invalid#openssl-sys@0.9.112")]
        unrelated += [dict(good, reason="compiler-artifact", out_dir="/unrelated/output")]
        self.assertEqual(self.select([*unrelated, good, good]), [self.output])
        saved = self.retain()
        self.assertEqual(saved[0]["source_path"], str(self.output))
        self.assertEqual((self.evidence / saved[0]["retained_file"]).read_bytes(), self.output.read_bytes())
        self.checker.check_build_script_output.assert_called_once_with(self.output.read_bytes(), {"controlled": True})

    def test_wrong_package_events_do_not_substitute_for_missing_selected_package(self):
        for event in (dict(build_event(self.out_dir), package_id="openssl-sys@0.9.112"),
                      dict(build_event(self.out_dir), reason="compiler-artifact")):
            with self.subTest(event=event), self.assertRaises(VerificationError):
                self.select([event])

    def test_release_configuration_is_explicit_and_cannot_select_debug_output(self):
        release_out = self.target / "release/build/openssl-sys-approved/out"
        release_out.mkdir(parents=True)
        release_output = release_out.parent / "output"
        release_output.write_bytes(b"controlled release output\n")
        write_events(self.log, [build_event(release_out)])
        self.assertEqual(runner.selected_openssl_outputs(self.log, self.target, "release"), [release_output])
        saved = runner.retain_openssl_outputs(self.checker, {}, self.log, self.target, self.evidence, "release")
        self.assertEqual(saved[0]["source_path"], str(release_output))
        with self.assertRaises(VerificationError):
            runner.selected_openssl_outputs(self.log, self.target)
        write_events(self.log, [build_event(self.out_dir)])
        with self.assertRaises(VerificationError):
            runner.selected_openssl_outputs(self.log, self.target, "release")
        for configuration in ("", "Debug", "test", "../debug"):
            with self.subTest(configuration=configuration), self.assertRaises(VerificationError):
                runner.selected_openssl_outputs(self.log, self.target, configuration)

    def test_relative_escaped_wrong_target_or_malformed_selected_paths_fail(self):
        for path in ("", "debug/build/openssl-sys-approved/out", self.root / "foreign/debug/build/openssl-sys-approved/out",
                     self.target / "release/build/openssl-sys-approved/out", self.target / "debug/build/wrong-approved/out",
                     self.target / "debug/build/openssl-sys-approved/not-out", self.target / "debug/build/openssl-sys-approved/out/extra",
                     self.target / "debug/build/openssl-sys-approved/../out",
                     self.root / "target/debug/build/openssl-sys-approved/out"):
            with self.subTest(path=str(path)), self.assertRaises(VerificationError):
                self.select([build_event(path)])

    def test_missing_output_is_rejected_without_retained_copy(self):
        self.output.unlink()
        self.select()
        with self.assertRaises((OSError, VerificationError)):
            self.retain()
        self.checker.check_build_script_output.assert_not_called()
        self.assertEqual(list(self.evidence.iterdir()), [])

    def test_symlink_output_or_path_component_is_rejected_without_following_it(self):
        for part in (self.output, self.out_dir, self.out_dir.parent, self.target, self.target.parent):
            with self.subTest(path=part):
                moved = part.with_name(part.name + "-moved")
                part.rename(moved)
                part.symlink_to(moved, target_is_directory=moved.is_dir())
                try:
                    with self.assertRaises(VerificationError):
                        self.select()
                finally:
                    part.unlink()
                    moved.rename(part)
        self.checker.check_build_script_output.assert_not_called()

    def test_log_read_is_bounded_and_oversize_fails_before_selection(self):
        self.log.write_bytes(b"x" * 129)
        with patch.object(runner, "MAX_LOG_BYTES", 128), self.assertRaisesRegex(VerificationError, "bound"):
            runner.selected_openssl_outputs(self.log, self.target)

    def test_output_read_uses_exact_one_mib_plus_one_bound(self):
        self.select()
        reads = []
        class ObservedStream(io.BytesIO):
            def read(self, size=-1):
                reads.append(size)
                return super().read(size)
        original_open = Path.open
        stream = ObservedStream(b"x" * (1024 * 1024 + 2))
        def open_path(path, *args, **kwargs):
            return stream if path == self.output else original_open(path, *args, **kwargs)
        with patch.object(Path, "open", open_path), self.assertRaisesRegex(VerificationError, "1 MiB"):
            self.retain()
        self.assertEqual(reads, [1024 * 1024 + 1])
        self.checker.check_build_script_output.assert_not_called()
        self.assertEqual(list(self.evidence.iterdir()), [])

    def test_output_exact_size_limit_is_retained_and_one_extra_byte_is_rejected(self):
        self.select()
        self.output.write_bytes(b"x" * (1024 * 1024))
        saved = self.retain()
        retained = self.evidence / saved[0]["retained_file"]
        self.assertEqual(retained.stat().st_size, 1024 * 1024)
        retained.unlink()
        self.checker.check_build_script_output.reset_mock()
        self.output.write_bytes(b"x" * (1024 * 1024 + 1))
        with self.assertRaisesRegex(VerificationError, "1 MiB"):
            self.retain()
        self.checker.check_build_script_output.assert_not_called()
        self.assertEqual(list(self.evidence.iterdir()), [])

    def test_rejected_directives_leave_bounded_raw_evidence(self):
        self.select()
        self.checker.check_build_script_output.side_effect = ValueError("controlled invalid provider directives")
        with self.assertRaisesRegex(ValueError, "invalid provider"):
            self.retain()
        retained = list(self.evidence.iterdir())
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0].read_bytes(), self.output.read_bytes())
        self.assertLessEqual(retained[0].stat().st_size, 1024 * 1024)

    def test_repeated_retention_cannot_overwrite_existing_suite_evidence(self):
        self.select()
        saved = self.retain()
        retained = self.evidence / saved[0]["retained_file"]
        before = retained.read_bytes()
        self.output.write_bytes(b"different second suite output\n")
        with self.assertRaises((FileExistsError, VerificationError)):
            self.retain()
        self.assertEqual(retained.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
