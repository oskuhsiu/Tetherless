"""New controlled runner tests; only short Python fixture children execute."""
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import run_compile as runner
import prepare_binding as prepare
from test_native_handoff import NativeHandoffFixture
from test_diagnostic_binding import put, put_json

SUPERVISOR = None


def supervised():
    global SUPERVISOR
    if SUPERVISOR is None:
        # The test caller supplies the already reviewed native tool directory.
        # No Cargo, Rust, Xcode, Swift or downloaded project command executes.
        path = Path(os.environ.get("TETHERLESS_DIAGNOSTIC_NATIVE_RECIPE", str(HERE.parent / "Dependencies/idevice")))
        SUPERVISOR = runner.load_supervisor(path, json.loads((HERE / "input-contract.json").read_bytes()))
    return SUPERVISOR


class RunnerFixture:
    def __init__(self, root, configuration="Debug"):
        self.f = NativeHandoffFixture(root / "handoff")
        self.sdk = root / "iPhoneOS26.2.sdk"
        self.sdk.mkdir()
        self.toolchain = root / "toolchain.json"
        retained_lock = self.f.fixture.artifact / "provenance/toolchain-lock.json"
        lock = json.loads(retained_lock.read_bytes())
        lock["developer_dir"] = "/Applications/Xcode_26.3.app/Contents/Developer"
        lock_hash = put_json(self.toolchain, lock)
        put_json(retained_lock, lock)
        self.f.fixture.receipt["toolchain_lock_sha256"] = lock_hash
        self.provider_bytes = b"controlled opaque framework fixture\n"
        for row in self.f.fixture.receipt["targets"]:
            row["sdk_root"] = str(self.sdk)
            row["provider_receipt"]["framework_binary_sha256"] = prepare.digest(self.provider_bytes)
        for row in self.f.fixture.receipt["targets"]:
            identity = prepare.retained_c_provider.provider_identity(row["provider_receipt"])
            row["mixed_provider"]["provider_identity"] = identity
            self.f.fixture.c_targets[row["target"]["rust"]]["provider_identity"] = identity
        self.f.fixture.refresh(inventory=True)
        self.f.pack("apple-producer")
        self.f.refresh()
        self.binding = self.f.bind()
        self.binding_path = self.f.fixture.output / "TETHERLESS_PAIRING_DIAGNOSTIC_BINDING.json"
        context, producer = self.f.context, self.f.context["producer_context"]
        self.args = SimpleNamespace(diagnostic_root=self.f.fixture.output, configuration=configuration,
            work_dir=root / ("compile-" + configuration), toolchain_lock=self.toolchain,
            binding_receipt_sha256=prepare.file_hash(self.binding_path), native_handoff=self.f.path,
            native_handoff_sha256=self.f.handoff_hash, native_recipe=self.f.recipe,
            repository=context["repository"], repository_id=context["repository_id"], run_id=context["run_id"],
            source_commit=context["source_commit"], consumer_attempt=context["consumer_attempt"],
            component_fixtures_result="success", native_proofs_result="success", handoff_mode="retained-producer",
            producer_run_id=producer["run_id"], producer_source_commit=producer["source_commit"],
            producer_run_attempt=producer["run_attempt"])
        self.calls, self.fail, self.mutate = [], None, None
        self.wrong_observation, self.omit_source = None, None

    def build_log(self):
        root, derived = Path(self.binding["diagnostic_root"]), self.args.work_dir.resolve() / "DerivedData"
        processed = derived / "Build/Products/PackageFrameworks/IDevice"
        for key, name in self.binding["local_device_files"].items():
            destination = processed / ("libidevice_ffi.a" if key == "archive" else "Headers/" + Path(name).name)
            put(destination, (root / name).read_bytes())
        framework = derived / "SourcePackages/artifacts/selected/OpenSSL.framework/OpenSSL"
        put(processed / "libimobiledevice.a", b"controlled opaque C provider fixture\n")
        put(processed / "Headers/plist/plist.h", b"/* controlled opaque C plist header */\n")
        put(processed / "Headers/libimobiledevice/module.modulemap", b'module libimobiledevice [system] { header "../plist/plist.h" export * }\n')
        c_provider = self.binding["native_artifact"]["targets"]["aarch64-apple-ios"]["mixed_provider"]
        local_module = root / self.binding["local_c_device_files"]["module_map"]
        for name in c_provider["header_inventory"]:
            put(processed / "Headers" / name, (local_module.parent.parent / name).read_bytes())
        from test_diagnostic_binding import synthetic_map
        map_path = derived / "LinkMaps/SideStore-arm64.map"
        put(map_path, synthetic_map(processed / "libimobiledevice.a", c_provider["symbols"],
            processed / "libidevice_ffi.a", self.binding["native_artifact"]["rust_symbols"]["aarch64-apple-ios"]).encode())
        put(framework, self.provider_bytes)
        app_list, gateway_list = derived / "app.SwiftFileList", derived / "gateway.SwiftFileList"
        put(app_list, ("\n".join(shlex.quote(str(root / name)) for name in self.f.contract["prepared_composition_sources"] if name != self.omit_source) + "\n").encode())
        put(gateway_list, (shlex.quote(str(root / "Dependencies/minimuxer/DeviceGateway/idevice/IdeviceGateway.swift")) + "\n").encode())
        rows = []
        for module, path, version in (("SideStore", app_list, "17.0"), ("IdeviceGateway", gateway_list, "14.0")):
            args = ["-module-name", module, "-target", "arm64-apple-ios" + version, "-sdk", str(self.sdk),
                    "-filelist", str(path), "-I", str(processed / "Headers")]
            if module == "SideStore":
                for condition in self.f.contract["required_conditions"]:
                    args += ["-D", condition]
            rows += [f"SwiftDriver {module} normal arm64 com.apple.xcode.tools.swift.compiler (in target '{module}' from project 'Controlled')",
                     "    cd " + shlex.quote(str(root)),
                     "    builtin-SwiftDriver -- /Applications/Xcode_26.3.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc " + shlex.join(args), ""]
        args = ["-target", "arm64-apple-ios17.0", "-isysroot", str(self.sdk), str(processed / "libidevice_ffi.a"), str(processed / "libimobiledevice.a"),
                "-F", str(framework.parent.parent), "-framework", "OpenSSL", "-o",
                str(derived / ("Build/Products/" + self.args.configuration + "-iphoneos/SideStore.app/SideStore"))]
        args[0:0] = ["-map", str(map_path)]
        for name in sorted(runner.C_SYSTEM_FRAMEWORKS):
            args[0:0] = ["-framework", name]
        for symbol in sorted(runner.APP_C_ROOTS | runner.APP_RUST_ROOTS):
            args[0:0] = ["-u", symbol]
        output_path = derived / ("Build/Products/" + self.args.configuration + "-iphoneos/SideStore.app/SideStore")
        put(output_path, b"controlled opaque app output; never executed\n")
        rows += ["Ld SideStore.app/SideStore normal arm64 (in target 'SideStore' from project 'Controlled')",
                 "    cd " + shlex.quote(str(root)), "    /Applications/Xcode_26.3.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang " + shlex.join(args)]
        return "\n".join(rows) + "\n"

    def capture(self, argv, *, source, env, log, **limits):
        self.calls.append({"argv": argv, "env": env, "log": log, **limits})
        observations = self.binding["native_artifact"]["targets"]["aarch64-apple-ios"]["toolchain_observations"]
        labels = [key for key, command in runner.TOOL_COMMANDS.items() if command == argv]
        if labels:
            output = observations[labels[0]]
            if self.wrong_observation == labels[0]:
                output += " unexpected output"
        elif argv == ["/usr/bin/xcrun", "--sdk", "iphoneos", "--show-sdk-path"]:
            output = str(self.sdk)
        elif argv[:2] == ["/usr/bin/xcodebuild", "build"]:
            output = self.build_log()
            if self.mutate:
                self.mutate(self)
        else:
            raise AssertionError("unexpected native command construction")
        code = "import sys,time; sys.stdout.write(" + repr(output + "\n") + "); sys.stdout.flush()"
        timeout = 2
        if log.name == "xcodebuild.txt" and self.fail == "exit":
            code += "; sys.stderr.write('controlled compiler failure\\n'); sys.exit(7)"
        if log.name == "xcodebuild.txt" and self.fail == "timeout":
            code += "; time.sleep(5)"
            timeout = .15
        return supervised().capture_helper_command([sys.executable, "-u", "-c", code], source=source,
            env=env, log=log, timeout_seconds=timeout, max_log_bytes=limits["max_log_bytes"],
            term_grace_seconds=.2, kill_join_seconds=.2)

    def patches(self):
        stack = ExitStack()
        real_is_dir = Path.is_dir
        stack.enter_context(patch.object(Path, "is_dir", lambda p: str(p) == "/Applications/Xcode_26.3.app/Contents/Developer" or real_is_dir(p)))
        stack.enter_context(patch.object(prepare, "HERE", self.f.fixture.here))
        stack.enter_context(self.f.fixture.mock_retained())
        stack.enter_context(patch.object(runner, "HERE", self.f.fixture.here))
        stack.enter_context(patch.object(runner, "load_supervisor", return_value=SimpleNamespace(capture_helper_command=self.capture)))
        return stack


class CompileRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        supervised()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="new compile runner ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def audits(self, f):
        evidence = f.args.work_dir / "evidence"
        return {name: json.loads((evidence / name).read_bytes()) for name in
                ("bound-input-audit.json", "recipe-input-audit.json", "native-handoff-audit.json")}

    def test_debug_and_release_real_supervision_and_observer_record_fourteen_inputs(self):
        for configuration in ("Debug", "Release"):
            f = RunnerFixture(self.root / configuration, configuration)
            with f.patches():
                result = runner.run(f.args)
            self.assertEqual(len(result["observations"]["compile"]["SideStore"]["required_inputs"]), 14)
            self.assertTrue(all(row["original_inputs_unchanged"] for row in self.audits(f).values()))
            self.assertFalse(result["app_binary_executed"])
            build = f.calls[-1]
            self.assertEqual(build["timeout_seconds"], 1800)
            self.assertEqual(build["max_log_bytes"], 32 * 1024 * 1024)
            self.assertIn("ENABLE_DEBUG_DYLIB=NO", build["argv"])
            self.assertIn("-onlyUsePackageVersionsFromResolvedFile", build["argv"])
            self.assertNotIn("GH_TOKEN", build["env"])
            self.assertTrue((f.args.work_dir / "evidence/diagnostic-compile-evidence.json").is_file())

    def test_native_failure_or_timeout_retains_logs_status_and_every_input_audit(self):
        for failure in ("exit", "timeout"):
            f = RunnerFixture(self.root / failure)
            f.fail = failure
            with f.patches(), self.assertRaises(ValueError):
                runner.run(f.args)
            self.assertTrue(all(row["original_inputs_unchanged"] for row in self.audits(f).values()))
            evidence = f.args.work_dir / "evidence"
            status = json.loads((evidence / "xcodebuild.txt.status.json").read_bytes())
            self.assertTrue(status["cleanup"]["direct_child_reaped"])
            self.assertTrue(status["cleanup"]["group_empty"])
            self.assertFalse((evidence / "diagnostic-compile-evidence.json").exists())

    def test_missing_budget_or_advanced_compiler_membership_prevents_success(self):
        for suffix in ("PairingValidationBudget.swift", "WirelessPairView.swift"):
            f = RunnerFixture(self.root / suffix)
            f.omit_source = next(name for name in f.f.contract["prepared_composition_sources"] if name.endswith(suffix))
            with f.patches(), self.assertRaises(ValueError):
                runner.run(f.args)
            self.assertTrue(all(row["original_inputs_unchanged"] for row in self.audits(f).values()))
            self.assertFalse((f.args.work_dir / "evidence/diagnostic-compile-evidence.json").exists())

    def test_changed_swift_stream_stops_before_compile_and_retains_audits(self):
        f = RunnerFixture(self.root)
        f.wrong_observation = "swiftc"
        with f.patches(), self.assertRaisesRegex(ValueError, "observation differs"):
            runner.run(f.args)
        self.assertFalse(any(c["argv"][:2] == ["/usr/bin/xcodebuild", "build"] for c in f.calls))
        self.assertTrue(all(row["original_inputs_unchanged"] for row in self.audits(f).values()))

    def test_bound_recipe_gate_and_artifact_mutations_block_publication_after_successful_compile(self):
        for kind in ("bound", "recipe", "gate", "artifact"):
            f = RunnerFixture(self.root / kind)
            paths = {"bound": f.f.fixture.output / next(iter(f.f.contract["prepared_support_sources"])),
                     "recipe": f.f.recipe / "marker.py",
                     "gate": f.f.fixture.here.parent / "pairing_safety.py",
                     "artifact": f.f.fixture.artifact / "IDevice.xcframework/ios-arm64/libidevice_ffi.a"}
            f.mutate = lambda _, p=paths[kind]: p.write_bytes(b"controlled post-command mutation")
            with f.patches(), self.assertRaises(ValueError):
                runner.run(f.args)
            self.assertTrue(any(not row["original_inputs_unchanged"] for row in self.audits(f).values()))
            self.assertFalse((f.args.work_dir / "evidence/diagnostic-compile-evidence.json").exists())

    def test_audit_write_obstruction_does_not_skip_other_audits_or_publish(self):
        f = RunnerFixture(self.root)
        f.mutate = lambda _: (f.args.work_dir / "evidence/bound-input-audit.json").mkdir()
        with f.patches(), self.assertRaisesRegex(ValueError, "input audit failed"):
            runner.run(f.args)
        for name in ("recipe-input-audit.json", "native-handoff-audit.json"):
            self.assertTrue((f.args.work_dir / "evidence" / name).is_file())
        self.assertFalse((f.args.work_dir / "evidence/diagnostic-compile-evidence.json").exists())

    def test_external_binding_or_handoff_hash_mismatch_runs_no_command(self):
        for key in ("binding_receipt_sha256", "native_handoff_sha256"):
            f = RunnerFixture(self.root / key)
            setattr(f.args, key, "0" * 64)
            with f.patches(), self.assertRaises(ValueError):
                runner.run(f.args)
            self.assertEqual(f.calls, [])

    def test_changed_producer_context_runs_no_command(self):
        f = RunnerFixture(self.root)
        f.args.producer_run_id += 1
        with f.patches(), self.assertRaises(ValueError):
            runner.run(f.args)
        self.assertEqual(f.calls, [])

    def test_bad_configuration_or_existing_work_root_runs_no_command(self):
        for kind in ("configuration", "existing"):
            f = RunnerFixture(self.root / kind)
            if kind == "configuration":
                f.args.configuration = "Unknown"
            else:
                f.args.work_dir.mkdir()
            with f.patches(), self.assertRaises(ValueError):
                runner.run(f.args)
            self.assertEqual(f.calls, [])

    def test_wrong_toolchain_lock_identity_runs_no_command(self):
        f = RunnerFixture(self.root)
        f.toolchain.write_bytes(b"{}")
        with f.patches(), self.assertRaises(ValueError):
            runner.run(f.args)
        self.assertEqual(f.calls, [])

    def test_symlinked_audit_or_success_receipt_cannot_overwrite_outside_bytes(self):
        for name in ("bound-input-audit.json", "diagnostic-compile-evidence.json"):
            f = RunnerFixture(self.root / name)
            outside = self.root / (name + ".outside")
            outside.write_bytes(b"controlled outside bytes")
            f.mutate = lambda _, n=name: (f.args.work_dir / "evidence" / n).symlink_to(outside)
            with f.patches(), self.assertRaises(ValueError):
                runner.run(f.args)
            self.assertEqual(outside.read_bytes(), b"controlled outside bytes")
            for retained in ("recipe-input-audit.json", "native-handoff-audit.json"):
                self.assertTrue((f.args.work_dir / "evidence" / retained).is_file())

    def test_invocation_receipt_is_created_exclusively(self):
        outside = self.root / "outside.json"
        outside.write_bytes(b"outside")
        for kind in ("symlink", "existing"):
            evidence = self.root / kind
            evidence.mkdir()
            target = evidence / "invocation.json"
            if kind == "symlink":
                target.symlink_to(outside)
            else:
                target.write_bytes(b"existing")
            with self.assertRaises(ValueError):
                runner.write_json(target, {"pretend": "success"})
        self.assertEqual(outside.read_bytes(), b"outside")


if __name__ == "__main__":
    unittest.main()
