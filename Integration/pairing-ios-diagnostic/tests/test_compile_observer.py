"""New portable synthetic observer tests; no native tools or binaries execute."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("new_compile_observer", HERE / "observe_compile.py")
observer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observer)

# Short provenance receipt for the three command-shape regressions below.
# No historical response-file contents were recovered or reconstructed. The
# portable tests use separately labelled synthetic files and do not establish
# native acceptance, current composition membership, or historical build success.
COMMAND_SHAPE_PROVENANCE = {
    "schema": 1,
    "run_id": 37303840335,
    "source_commit": "1fc8968f1d37b59717cd655b9b8f7fc8ccc7f566",
    "artifact_id": 11342129657,
    "zip_sha256": "866221e61b4ba8f32f18f3b20b037fd88f21d079ff38bf66070acfb83577ffec",
    "log_name": "native-build.log",
    "log_bytes": 3108334,
    "log_sha256": "2cd18fbe3c04b23f34c7df5886636cb13e6b1fa3af7fac6182bff19803062d99",
    "line_sha256_excluding_line_ending": {
        "7182": "6815fce0c024c224a1b6f2735104db25c07a4c34bf674598fb4918ed713645aa",
        "7184": "412800f275346085340e04b8a12081165334d6d950485fc307c1c34b75bed2ce",
        "8694": "6f61ef5c642e378437d2b23ebdeeedc5827a94007b1c97441b636e9b15dd3ede",
        "8696": "f5d973532c7ebde0926c98a0bf12c5c3e23dc41c2281e7685ae387b536c38970",
        "11236": "6f23abf2a0f1dbc05ccb120e57adf03f0a54b5c41d84dee63222984b283be42f",
        "11238": "c1926b12c074f9283613c69cac88c7823f94e00208fa1e7b91d1d143b906f482",
    },
    "use": "ordinary SwiftDriver/Ld command shape only; never executed",
    "historical_response_contents_recovered": False,
    "current_composition_or_native_acceptance": False,
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


class CompileObserverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="diagnostic observer ")
        self.addCleanup(self.temp.cleanup)
        # Align fixture expectations and mutation hooks with the owned canonical
        # paths returned by the observer, including macOS /var parent aliases.
        self.base = Path(self.temp.name).resolve(strict=True)
        self.app = self.base / "owned app"
        self.derived = self.base / "DerivedData"
        self.app.mkdir()
        self.derived.mkdir()
        self.sdk = "/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS27.0.sdk"
        self.contract = {
            "prepared_composition_sources": {},
            "required_conditions": sorted(observer.REQUIRED_CONDITIONS),
            "sentinel": {"prepared_path": "SideStore/Views/Onboarding/OnboardingView.swift",
                         "sha256": sha((HERE / "PairingCompositionCompileSentinel.swift").read_bytes())},
            "gateway": {"prepared_path": "Dependencies/minimuxer/DeviceGateway/Package.swift",
                        "local_binary_path": "TetherlessDiagnosticArtifacts/IDevice.xcframework"},
        }
        self.binding = {"bound_files": {}, "local_device_files": {}, "sdk_path": self.sdk,
                        "native_artifact": {"targets": {"aarch64-apple-ios": {"provider_receipt": {}}}}}
        for name in sorted(observer.REQUIRED_SOURCES):
            data = ("// synthetic composition source " + name + "\n").encode()
            self.contract["prepared_composition_sources"][name] = {"sha256": sha(data), "source_path": name}
            if name == self.contract["sentinel"]["prepared_path"]:
                data += b"\n" + (HERE / "PairingCompositionCompileSentinel.swift").read_bytes()
            self.put(self.app / name, data)
            self.binding["bound_files"][name] = sha(data)
        self.gateway = self.app / observer.GATEWAY_SOURCE
        self.put(self.gateway, b"// synthetic exact gateway source\n")
        self.binding["bound_files"][observer.GATEWAY_SOURCE] = sha(self.gateway.read_bytes())
        self.xcframework = self.app / "Dependencies/minimuxer/DeviceGateway/TetherlessDiagnosticArtifacts/IDevice.xcframework"
        self.native = {
            "archive": self.xcframework / "ios-arm64/libidevice_ffi.a",
            "header": self.xcframework / "ios-arm64/Headers/idevice.h",
            "module_map": self.xcframework / "ios-arm64/Headers/module.modulemap",
        }
        data = {"archive": b"opaque synthetic archive, not a binary format\n",
                "header": b"typedef unsigned int TetherlessPairingHostResult;\n",
                "module_map": b'module IDevice { header "idevice.h" export * }\n'}
        self.processed = self.derived / "Build/Products/Debug-iphoneos/PackageFrameworks/IDevice"
        for key, path in self.native.items():
            self.put(path, data[key])
            name = path.relative_to(self.app).as_posix()
            self.binding["local_device_files"][key] = name
            self.binding["bound_files"][name] = sha(data[key])
            destination = self.processed / ("libidevice_ffi.a" if key == "archive" else "Headers/" + path.name)
            self.put(destination, data[key])
        self.framework = self.derived / "SourcePackages/artifacts/provider/ios-arm64/OpenSSL.framework/OpenSSL"
        self.put(self.framework, b"opaque synthetic external provider, never interpreted\n")
        self.binding["native_artifact"]["targets"]["aarch64-apple-ios"]["provider_receipt"]["framework_binary_sha256"] = sha(self.framework.read_bytes())
        self.app_list = self.derived / "app.SwiftFileList"
        self.gateway_list = self.derived / "gateway.SwiftFileList"
        self.write_sources()
        self.put(self.gateway_list, (shlex.quote(str(self.gateway)) + "\n").encode())
        self.headers = self.processed / "Headers"
        self.c_archive = self.processed / "libimobiledevice.a"
        self.put(self.c_archive, b"opaque synthetic C provider archive\n")
        self.put(self.headers / "plist/plist.h", b"/* opaque synthetic C plist declarations */\n")
        self.put(self.headers / "libimobiledevice/module.modulemap", b'module libimobiledevice [system] { header "../plist/plist.h" export * }\n')
        self.binding["native_artifact"]["targets"]["aarch64-apple-ios"]["mixed_provider"] = {
            "library_sha256": sha(self.c_archive.read_bytes()),
            "header_sha256": sha((self.headers / "plist/plist.h").read_bytes()),
            "module_map_sha256": sha((self.headers / "libimobiledevice/module.modulemap").read_bytes())}
        self.app_args = ["-module-name", "SideStore", "-target", "arm64-apple-ios17.0", "-sdk", self.sdk,
                         "-filelist", str(self.app_list), "-I", str(self.headers)]
        for flag in sorted(observer.REQUIRED_CONDITIONS):
            self.app_args += ["-D", flag]
        self.gateway_args = ["-module-name", "IdeviceGateway", "-target", "arm64-apple-ios14.0", "-sdk", self.sdk,
                             "-filelist", str(self.gateway_list), "-I", str(self.headers)]
        self.link_args = ["-target", "arm64-apple-ios17.0", "-isysroot", self.sdk,
                          str(self.processed / "libidevice_ffi.a"), str(self.c_archive), "-F", str(self.framework.parent.parent),
                          "-framework", "OpenSSL", "-o", str(self.derived / "Build/Products/Debug-iphoneos/SideStore.app/SideStore")]
        self.output = Path(self.link_args[-1])
        self.output_bytes = b"explicitly opaque synthetic final app output, never a native executable\n"
        self.put(self.output, self.output_bytes)
        self.log = self.base / "build.log"
        self.observations = 0

    def put(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def write_sources(self, omitted=None):
        names = sorted(observer.REQUIRED_SOURCES - ({omitted} if omitted else set()))
        self.put(self.app_list, ("\n".join(shlex.quote(str(self.app / name)) for name in names) + "\n").encode())

    def log_text(self):
        rows = []
        for module, args in (("SideStore", self.app_args), ("IdeviceGateway", self.gateway_args)):
            rows += [f"SwiftDriver {module} normal arm64 com.apple.xcode.tools.swift.compiler (in target '{module}' from project 'Fixture')",
                     "    cd " + shlex.quote(str(self.app)),
                     "    builtin-SwiftDriver -- /Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc " + shlex.join(args), ""]
        rows += ["Ld fixture/SideStore.app/SideStore normal arm64 (in target 'SideStore' from project 'Fixture')",
                 "    cd " + shlex.quote(str(self.app)),
                 "    /Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang " + shlex.join(self.link_args)]
        return "\n".join(rows) + "\n"

    def observe(self, text=None, configuration="Debug"):
        self.log.write_text(self.log_text() if text is None else text)
        self.observations += 1
        self.evidence = self.base / f"compiler-inputs-{self.observations}"
        return observer.observe_compile(self.log, self.app, self.derived, self.contract, self.binding, configuration,
                                        evidence_directory=self.evidence)

    def inventory(self):
        return [json.loads(line) for line in (self.evidence / "inventory.jsonl").read_text().splitlines()]

    def test_honest_swiftdriver_and_final_link_with_different_deployments(self):
        result = self.observe()
        self.assertEqual(len(result["compile"]["SideStore"]["required_inputs"]), 14)
        self.assertEqual(result["compile"]["IdeviceGateway"]["target"], "arm64-apple-ios14.0")
        self.assertEqual(result["link"]["processed_archive"], str(self.processed / "libidevice_ffi.a"))
        self.assertEqual(result["link"]["output_sha256"], sha(self.output_bytes))
        self.assertEqual(result["link"]["output_size"], len(self.output_bytes))
        self.assertFalse(result["binary_format_inspected"])
        self.assertFalse(result["ios_binaries_executed"])

    def test_historical_ld_heading_without_arch_uses_actual_command_target(self):
        # Exact shape from line11236; only the absolute fixture path differs.
        heading = f"Ld {self.output} normal (in target 'SideStore' from project 'AltStore')"
        old = "Ld fixture/SideStore.app/SideStore normal arm64 (in target 'SideStore' from project 'Fixture')"
        result = self.observe(self.log_text().replace(old, heading))
        self.assertEqual(result["link"]["target"], "arm64-apple-ios17.0")
        index = self.link_args.index("-target") + 1
        self.link_args[index] = "arm64-apple-ios17.0-simulator"
        with self.assertRaisesRegex(observer.ObservationError, "arm64 iOS device"):
            self.observe(self.log_text().replace(old, heading))

    def test_historical_swift_system_include_spelling(self):
        # Line7184 has the distinct Swift '-Isystem <SDK path>' option.
        original = self.gateway_args[:]
        index = self.gateway_args.index("-I")
        self.gateway_args[index:index + 2] = ["-Isystem", str(self.headers)]
        self.assertEqual(observer._include_directories(["-Isystem", str(self.headers)]), [str(self.headers)])
        self.observe()
        # A real second system-include map must participate in ambiguity checks.
        other = self.derived / "other-system-include"
        self.put(other / "module.modulemap", (self.headers / "module.modulemap").read_bytes())
        self.put(other / "idevice.h", (self.headers / "idevice.h").read_bytes())
        self.gateway_args = original + ["-Isystem", str(other)]
        with self.assertRaisesRegex(observer.ObservationError, "module selection.*ambiguous"):
            self.observe()

    def test_historical_forwarded_clang_system_include_spelling(self):
        # Line8696 forwards the option and its path through separate -Xcc atoms.
        original = self.app_args[:]
        index = self.app_args.index("-I")
        self.app_args[index:index + 2] = ["-Xcc", "-isystem", "-Xcc", str(self.headers)]
        self.observe()
        other = self.derived / "other-clang-system-include"
        self.put(other / "module.modulemap", (self.headers / "module.modulemap").read_bytes())
        self.put(other / "idevice.h", (self.headers / "idevice.h").read_bytes())
        self.app_args = original + ["-Xcc", "-isystem", "-Xcc", str(other)]
        with self.assertRaisesRegex(observer.ObservationError, "module selection.*ambiguous"):
            self.observe()

    def test_system_include_option_does_not_create_phantom_relative_directory(self):
        other = self.app / "system"
        self.put(other / "module.modulemap", (self.headers / "module.modulemap").read_bytes())
        self.put(other / "idevice.h", (self.headers / "idevice.h").read_bytes())
        self.gateway_args += ["-Isystem", "/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/usr/lib"]
        self.observe()

    def test_raw_compiler_inputs_and_inventory_are_retained(self):
        result = self.observe()
        rows = self.inventory()
        self.assertEqual(rows[-1]["event"], "complete")
        inputs = [row for row in rows if row["event"] == "input"]
        self.assertEqual(len(inputs), result["compiler_input_evidence"]["retained_files"])
        for row in inputs:
            data = (self.evidence / row["retained_path"]).read_bytes()
            self.assertEqual(sha(data), row["sha256"])
            self.assertEqual(len(data), row["size"])
            self.assertEqual(row["sha256"], result["text_input_hashes"][row["source_path"]])

    def test_owned_roots_with_parent_symlink_aliases(self):
        alias = self.base / "parent-alias"
        alias.symlink_to(self.base, target_is_directory=True)
        old_base = str(self.base)
        self.app = alias / "owned app"
        self.derived = alias / "DerivedData"
        self.write_sources()
        self.gateway_list.write_text(shlex.quote(str(alias / "owned app" / observer.GATEWAY_SOURCE)) + "\n")
        text = self.log_text().replace(old_base + "/DerivedData", str(self.derived))
        text = text.replace(old_base + "/owned app", str(self.app))
        result = self.observe(text)
        self.assertEqual(result["link"]["output_sha256"], sha(self.output_bytes))

    def test_owned_root_alias_does_not_allow_descendant_symlink_escape(self):
        escaped = self.base / "outside-inputs"
        escaped.mkdir()
        (escaped / "files.rsp").write_text("")
        link = self.derived / "linked-descendant"
        link.symlink_to(escaped, target_is_directory=True)
        self.app_args.append("@" + str(link / "files.rsp"))
        with self.assertRaisesRegex(observer.ObservationError, "symlinked evidence"):
            self.observe()

    def test_symlink_parent_traversal_cannot_forge_source_membership(self):
        outside = self.base / "outside/sub"
        outside.mkdir(parents=True)
        (self.app / "alias").symlink_to(outside, target_is_directory=True)
        data = self.app_list.read_text().replace(str(self.app) + "/", str(self.app) + "/alias/../")
        self.app_list.write_text(data)
        with self.assertRaisesRegex(observer.ObservationError, "parent traversal"):
            self.observe()

    def test_symlink_parent_traversal_cannot_forge_module_selection(self):
        outside = self.base / "outside/sub"
        outside.mkdir(parents=True)
        (self.derived / "alias").symlink_to(outside, target_is_directory=True)
        index = self.app_args.index("-I") + 1
        self.app_args[index] = self.app_args[index].replace(str(self.derived) + "/", str(self.derived) + "/alias/../")
        with self.assertRaisesRegex(observer.ObservationError, "parent traversal"):
            self.observe()

    def test_every_composition_file_is_mandatory(self):
        for name in sorted(observer.REQUIRED_SOURCES):
            with self.subTest(source=name):
                self.write_sources(omitted=name)
                with self.assertRaisesRegex(observer.ObservationError, "filelists lack"):
                    self.observe()

    def test_each_required_condition_is_mandatory(self):
        original = self.app_args[:]
        for flag in sorted(observer.REQUIRED_CONDITIONS):
            with self.subTest(flag=flag):
                self.app_args = original[:]
                position = self.app_args.index(flag)
                del self.app_args[position - 1:position + 1]
                with self.assertRaisesRegex(observer.ObservationError, "conditions"):
                    self.observe()

    def test_loose_paths_and_flags_in_banner_do_not_count(self):
        self.write_sources(omitted=sorted(observer.REQUIRED_SOURCES)[0])
        with self.assertRaises(observer.ObservationError):
            self.observe("Echo " + " ".join(observer.REQUIRED_SOURCES | observer.REQUIRED_CONDITIONS) + "\n" + self.log_text())

    def test_direct_source_arguments_do_not_replace_filelist_membership(self):
        self.app_args[self.app_args.index("-filelist"):self.app_args.index("-filelist") + 2] = list(map(str, (self.app / name for name in observer.REQUIRED_SOURCES)))
        with self.assertRaisesRegex(observer.ObservationError, "filelists lack"):
            self.observe()

    def test_response_file_paths_are_real_membership(self):
        response = self.derived / "app.rsp"
        self.put(response, shlex.join([str(self.app / name) for name in sorted(observer.REQUIRED_SOURCES)]).encode())
        index = self.app_args.index("-filelist")
        self.app_args[index:index + 2] = ["@" + str(response)]
        self.assertEqual(len(self.observe()["compile"]["SideStore"]["required_inputs"]), 14)

    def test_response_option_values_do_not_count_as_source_membership(self):
        response = self.derived / "options.rsp"
        args = []
        for name in sorted(observer.REQUIRED_SOURCES):
            args += ["-Xcc", "-include", "-Xcc", str(self.app / name)]
        self.put(response, shlex.join(args).encode())
        index = self.app_args.index("-filelist")
        self.app_args[index:index + 2] = ["@" + str(response)]
        with self.assertRaisesRegex(observer.ObservationError, "filelists lack"):
            self.observe()

    def test_nested_source_response_membership(self):
        sources = self.derived / "sources.rsp"
        outer = self.derived / "outer.rsp"
        self.put(sources, shlex.join([str(self.app / name) for name in sorted(observer.REQUIRED_SOURCES)]).encode())
        self.put(outer, shlex.join(["-O", "@" + str(sources)]).encode())
        index = self.app_args.index("-filelist")
        self.app_args[index:index + 2] = ["@" + str(outer)]
        self.observe()

    def test_missing_gateway_command(self):
        text = self.log_text().replace("SwiftDriver IdeviceGateway", "SwiftDriver OtherGateway")
        with self.assertRaisesRegex(observer.ObservationError, "SwiftDriver command"):
            self.observe(text)

    def test_gateway_source_is_required(self):
        self.gateway_list.write_text("")
        with self.assertRaisesRegex(observer.ObservationError, "IdeviceGateway compiler filelists"):
            self.observe()

    def test_swift_frontend_alone_is_not_driver_evidence(self):
        with self.assertRaisesRegex(observer.ObservationError, "SwiftDriver command"):
            self.observe(self.log_text().replace("/usr/bin/swiftc", "/usr/bin/swift-frontend"))

    def test_echoed_command_is_not_actual_command(self):
        with self.assertRaisesRegex(observer.ObservationError, "SwiftDriver command"):
            self.observe(self.log_text().replace("    builtin-SwiftDriver", "    echo builtin-SwiftDriver"))

    def test_each_command_rejects_wrong_sdk_or_platform(self):
        for name in ("app_args", "gateway_args", "link_args"):
            original = getattr(self, name)[:]
            for target in ("arm64-apple-ios17.0-simulator", "x86_64-apple-ios17.0", "arm64-apple-macos14.0"):
                with self.subTest(command=name, target=target):
                    args = original[:]
                    args[args.index("-target") + 1] = target
                    setattr(self, name, args)
                    with self.assertRaisesRegex(observer.ObservationError, "arm64 iOS device"):
                        self.observe()
            args = original[:]
            sdkflag = "-isysroot" if name == "link_args" else "-sdk"
            args[args.index(sdkflag) + 1] += ".other"
            setattr(self, name, args)
            with self.assertRaisesRegex(observer.ObservationError, "SDK differs"):
                self.observe()
            setattr(self, name, original)

    def test_response_cycle_is_rejected(self):
        response = self.derived / "cycle.rsp"
        self.put(response, ("@" + shlex.quote(str(response))).encode())
        self.app_args.append("@" + str(response))
        with self.assertRaisesRegex(observer.ObservationError, "cyclic"):
            self.observe()
        self.assertEqual(self.inventory()[-1]["event"], "failed")
        self.assertTrue(any(row.get("source_path") == str(response) for row in self.inventory()))

    def test_malformed_raw_inputs_remain_after_parse_failure(self):
        response = self.derived / "malformed.rsp"
        original = self.app_args[:]
        for data in (b"\xff\xfe", b"source\x00.swift", b'"unterminated'):
            with self.subTest(data=data):
                self.put(response, data)
                self.app_args = original + ["@" + str(response)]
                with self.assertRaises(observer.ObservationError):
                    self.observe()
                rows = self.inventory()
                self.assertEqual(rows[-1]["event"], "failed")
                entry = next(row for row in rows if row.get("source_path") == str(response))
                self.assertEqual((self.evidence / entry["retained_path"]).read_bytes(), data)

    def test_changed_repeated_text_read_retains_both_versions_and_fails(self):
        original_read = observer._Files.read
        module_map = self.headers / "module.modulemap"
        count = 0

        def mutate_between_reads(files, path, *args, **kwargs):
            nonlocal count
            if path == module_map and kwargs.get("compiler_text"):
                count += 1
                if count == 2:
                    module_map.write_bytes(module_map.read_bytes() + b"\n")
            return original_read(files, path, *args, **kwargs)

        with mock.patch.object(observer._Files, "read", mutate_between_reads):
            with self.assertRaisesRegex(observer.ObservationError, "text changed between reads"):
                self.observe()
        rows = [row for row in self.inventory() if row.get("source_path") == str(module_map)]
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["sha256"], rows[1]["sha256"])
        self.assertTrue(rows[1]["changed"])
        self.assertEqual(self.inventory()[-1]["event"], "failed")

    def test_repeated_reads_are_included_in_aggregate_bound(self):
        module_size = (self.headers / "module.modulemap").stat().st_size
        # App filelist plus the first module-map read fits. Its repeated read
        # exceeds the bound despite having no new unique path.
        budget = self.app_list.stat().st_size + module_size
        with mock.patch.object(observer, "MAX_TOTAL_TEXT", budget):
            with self.assertRaisesRegex(observer.ObservationError, "aggregate read-byte bound"):
                self.observe()
        self.assertEqual(self.inventory()[-1]["event"], "failed")

    def test_repeated_reads_are_included_in_read_count_bound(self):
        with mock.patch.object(observer, "MAX_TEXT_READS", 2):
            with self.assertRaisesRegex(observer.ObservationError, "read count bound"):
                self.observe()
        self.assertEqual(self.inventory()[-1]["event"], "failed")

    def test_evidence_directory_must_be_fresh_and_not_symlinked(self):
        self.log.write_text(self.log_text())
        for kind in ("existing", "symlink", "file"):
            with self.subTest(kind=kind):
                evidence = self.base / ("obstructed-" + kind)
                if kind == "existing":
                    evidence.mkdir()
                elif kind == "symlink":
                    evidence.symlink_to(self.base, target_is_directory=True)
                else:
                    evidence.write_bytes(b"obstruction")
                with self.assertRaises(observer.ObservationError):
                    observer.observe_compile(self.log, self.app, self.derived, self.contract, self.binding, "Debug",
                                             evidence_directory=evidence)

    def test_capture_destination_obstruction_fails_closed(self):
        original_retain = observer._Capture.retain

        def obstruct(capture, source, data, previous):
            (capture.root / "input-0001.raw").symlink_to(self.framework)
            return original_retain(capture, source, data, previous)

        with mock.patch.object(observer._Capture, "retain", obstruct):
            with self.assertRaises(observer.ObservationError):
                self.observe()
        self.assertEqual(self.inventory()[-1]["event"], "failed")

    def test_inventory_obstruction_fails_closed(self):
        original_retain = observer._Capture.retain

        def obstruct(capture, source, data, previous):
            capture.inventory.unlink()
            capture.inventory.symlink_to(self.framework)
            return original_retain(capture, source, data, previous)

        provider_before = self.framework.read_bytes()
        with mock.patch.object(observer._Capture, "retain", obstruct):
            with self.assertRaisesRegex(observer.ObservationError, "capture failed"):
                self.observe()
        self.assertEqual(self.framework.read_bytes(), provider_before)

    def test_inventory_same_size_mutation_fails_closed(self):
        original_finish = observer._Capture.finish

        def corrupt(capture, status, error=None):
            if status == "complete":
                data = capture.inventory.read_bytes()
                capture.inventory.write_bytes(data.replace(b"started", b"changed", 1))
            return original_finish(capture, status, error)

        with mock.patch.object(observer._Capture, "finish", corrupt):
            with self.assertRaisesRegex(observer.ObservationError, "inventory identity differs"):
                self.observe()

    def test_retained_raw_input_mutation_fails_closed(self):
        original_finish = observer._Capture.finish

        def corrupt(capture, status, error=None):
            if status == "complete":
                path = capture.root / "input-0001.raw"
                data = path.read_bytes()
                path.write_bytes(b"!" + data[1:])
            return original_finish(capture, status, error)

        with mock.patch.object(observer._Capture, "finish", corrupt):
            with self.assertRaisesRegex(observer.ObservationError, "retained compiler input identity differs"):
                self.observe()

    def test_response_path_escape_is_rejected_before_read(self):
        self.app_args.append("@" + str(self.base / "unowned.rsp"))
        with self.assertRaisesRegex(observer.ObservationError, "escapes"):
            self.observe()

    def test_filelist_symlink_is_rejected(self):
        self.app_list.unlink()
        self.app_list.symlink_to(self.gateway_list)
        with self.assertRaisesRegex(observer.ObservationError, "symlinked"):
            self.observe()

    def test_shell_expression_is_not_executed(self):
        marker = self.base / "must-not-exist"
        with self.assertRaisesRegex(observer.ObservationError, "shell expressions"):
            self.observe(self.log_text().replace(" -module-name SideStore", " $(touch " + str(marker) + ") -module-name SideStore"))
        self.assertFalse(marker.exists())

    def test_changed_each_local_artifact_fails(self):
        for key, path in self.native.items():
            with self.subTest(file=key):
                data = path.read_bytes()
                path.write_bytes(data + b"changed")
                with self.assertRaisesRegex(observer.ObservationError, "bound local native identity"):
                    self.observe()
                path.write_bytes(data)

    def test_changed_processed_archive_fails(self):
        (self.processed / "libidevice_ffi.a").write_bytes(b"wrong opaque archive")
        with self.assertRaisesRegex(observer.ObservationError, "processed native archive identity"):
            self.observe()

    def test_original_archive_does_not_count_as_processed_link(self):
        self.link_args[self.link_args.index(str(self.processed / "libidevice_ffi.a"))] = str(self.native["archive"])
        with self.assertRaisesRegex(observer.ObservationError, "processed DerivedData copy"):
            self.observe()

    def test_changed_selected_header_and_module_map_fail(self):
        for name in ("idevice.h", "module.modulemap"):
            with self.subTest(file=name):
                path = self.headers / name
                original = path.read_bytes()
                path.write_bytes(original + b"changed")
                with self.assertRaises(observer.ObservationError):
                    self.observe()
                path.write_bytes(original)

    def test_explicit_matching_module_map(self):
        for args in (self.app_args, self.gateway_args):
            index = args.index("-I")
            args[index:index + 2] = ["-Xcc", "-fmodule-map-file=" + str(self.headers / "module.modulemap")]
        # The C gateway remains a separate required module in the mixed build.
        self.app_args += ["-I", str(self.headers / "libimobiledevice")]
        self.observe()

    def test_missing_or_changed_selected_c_provider_is_rejected(self):
        self.c_archive.write_bytes(b"another provider")
        with self.assertRaisesRegex(observer.ObservationError, "C provider archive"):
            self.observe()

    def test_changed_selected_c_header_and_map_are_rejected(self):
        for name in ("plist/plist.h", "libimobiledevice/module.modulemap"):
            path = self.headers / name
            original = path.read_bytes()
            path.write_bytes(original + b"\n// changed")
            with self.subTest(name=name), self.assertRaisesRegex(observer.ObservationError, "C provider header/module"):
                self.observe()
            path.write_bytes(original)

    def test_missing_c_provider_link_is_rejected(self):
        self.link_args.remove(str(self.c_archive))
        with self.assertRaisesRegex(observer.ObservationError, "verified C provider"):
            self.observe()

    def test_explicit_alternate_c_module_map_is_rejected(self):
        alternate = self.derived / "other/libimobiledevice/module.modulemap"
        self.put(alternate, (self.headers / "libimobiledevice/module.modulemap").read_bytes())
        self.app_args += ["-Xcc", "-fmodule-map-file=" + str(alternate)]
        with self.assertRaisesRegex(observer.ObservationError, "C provider module selection.*ambiguous"):
            self.observe()

    def test_explicit_same_c_module_map_is_deduplicated(self):
        self.app_args += ["-Xcc", "-fmodule-map-file=" + str(self.headers / "libimobiledevice/module.modulemap")]
        self.observe()

    def test_c_provider_dynamic_and_weak_alternatives_are_rejected(self):
        original = list(self.link_args)
        for extra in ([str(self.processed / "libplist.dylib")], [str(self.processed / "libimobiledevice.tbd")],
                      ["-Wl,-weak-lplist"], ["-Wl,-reexport-limobiledevice"], ["-Wl,-upward-lplist-2.0"]):
            self.link_args = original + extra
            with self.subTest(extra=extra), self.assertRaisesRegex(observer.ObservationError, "alternate C"):
                self.observe()

    def test_ambiguous_module_maps_fail(self):
        extra = self.derived / "unselected-module"
        self.put(extra / "module.modulemap", (self.headers / "module.modulemap").read_bytes())
        self.put(extra / "idevice.h", (self.headers / "idevice.h").read_bytes())
        self.app_args += ["-I", str(extra)]
        with self.assertRaisesRegex(observer.ObservationError, "module selection.*ambiguous"):
            self.observe()

    def test_library_search_selects_exact_processed_archive(self):
        index = self.link_args.index(str(self.processed / "libidevice_ffi.a"))
        self.link_args[index:index + 1] = ["-L", str(self.processed), "-lidevice_ffi"]
        self.observe()

    def test_ordinary_xcode_system_search_paths_are_not_source_inputs(self):
        developer = "/Applications/Xcode.app/Contents/Developer"
        self.app_args += ["-I", developer + "/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift/iphoneos"]
        self.link_args += ["-F", developer + "/Platforms/iPhoneOS.platform/Developer/Library/Frameworks"]
        self.link_args += ["-L", "/usr/lib/swift"]
        self.test_library_search_selects_exact_processed_archive()

    def test_unowned_search_paths_are_rejected(self):
        self.app_args += ["-I", str(self.base / "unowned")]
        with self.assertRaisesRegex(observer.ObservationError, "unowned non-toolchain"):
            self.observe()

    def test_shadow_native_dynamic_library_is_rejected(self):
        self.test_library_search_selects_exact_processed_archive()
        self.put(self.processed / "libidevice_ffi.dylib", b"opaque alternative")
        with self.assertRaisesRegex(observer.ObservationError, "library search selection.*ambiguous"):
            self.observe()

    def test_xlinker_filelist_is_parsed(self):
        linklist = self.derived / "link.files"
        self.put(linklist, (shlex.quote(str(self.processed / "libidevice_ffi.a")) + "\n").encode())
        index = self.link_args.index(str(self.processed / "libidevice_ffi.a"))
        self.link_args[index:index + 1] = ["-Xlinker", "-filelist", "-Xlinker", str(linklist)]
        self.observe()

    def test_ordinary_dyld_rpaths_are_link_data(self):
        self.link_args += ["-Xlinker", "-rpath", "-Xlinker", "@executable_path/Frameworks"]
        self.link_args += ["-Wl,-rpath,@loader_path/Frameworks", "-rpath", "@rpath/Frameworks"]
        result = self.observe()
        self.assertEqual(result["link"]["output_sha256"], sha(self.output_bytes))
        self.assertFalse(any("@executable_path" in path for path in result["text_input_hashes"]))

    def test_dyld_rpath_inside_link_response_is_data(self):
        response = self.derived / "link.rsp"
        self.put(response, shlex.join(["-rpath", "@executable_path/Frameworks"]).encode())
        self.link_args += ["@" + str(response)]
        self.observe()

    def test_dyld_names_do_not_bypass_other_response_reads(self):
        original = self.link_args[:]
        for addition in (["@executable_path/Frameworks"], ["-rpath", "@unrecognized/Frameworks"],
                         ["-rpath", "@executable_path_suffix/Frameworks"]):
            with self.subTest(addition=addition):
                self.link_args = original + addition
                with self.assertRaises(observer.ObservationError):
                    self.observe()

    def test_dyld_name_is_not_a_swift_response(self):
        self.app_args += ["-rpath", "@executable_path/Frameworks"]
        with self.assertRaises(observer.ObservationError):
            self.observe()

    def test_real_link_response_still_requires_owned_file(self):
        self.link_args += ["@" + str(self.base / "unowned-link.rsp")]
        with self.assertRaisesRegex(observer.ObservationError, "escapes"):
            self.observe()

    def test_wrong_external_provider_hash_fails(self):
        self.framework.write_bytes(b"different opaque framework")
        with self.assertRaisesRegex(observer.ObservationError, "external OpenSSL framework identity"):
            self.observe()

    def test_ambiguous_external_provider_fails(self):
        other = self.derived / "other/OpenSSL.framework/OpenSSL"
        self.put(other, self.framework.read_bytes())
        self.link_args += ["-F", str(other.parent.parent)]
        with self.assertRaisesRegex(observer.ObservationError, "framework provider selection.*ambiguous"):
            self.observe()

    def test_extra_openssl_library_fails(self):
        self.link_args.append("-lcrypto")
        with self.assertRaisesRegex(observer.ObservationError, "extra OpenSSL"):
            self.observe()

    def test_other_external_openssl_library_forms_fail(self):
        original = self.link_args[:]
        for extra in ("-weak-lssl", "-reexport-lcrypto", str(self.derived / "libcrypto.dylib"),
                      str(self.derived / "libssl.tbd")):
            with self.subTest(argument=extra):
                self.link_args = original + [extra]
                with self.assertRaisesRegex(observer.ObservationError, "extra OpenSSL"):
                    self.observe()

    def test_alternate_idevice_library_fails(self):
        self.link_args.append("-lidevice")
        with self.assertRaisesRegex(observer.ObservationError, "alternate IDevice"):
            self.observe()

    def test_native_archive_cannot_be_absent(self):
        self.link_args.remove(str(self.processed / "libidevice_ffi.a"))
        with self.assertRaisesRegex(observer.ObservationError, "one bound native archive"):
            self.observe()

    def test_final_link_cannot_be_absent_or_duplicated(self):
        text = self.log_text()
        start = text.index("Ld ")
        for variant in (text[:start], text + text[start:]):
            with self.subTest(variant=len(variant)):
                with self.assertRaisesRegex(observer.ObservationError, "one actual final"):
                    self.observe(variant)

    def test_debug_dylib_is_not_final_executable(self):
        self.link_args[-1] += ".debug.dylib"
        with self.assertRaisesRegex(observer.ObservationError, "final SideStore"):
            self.observe()

    def test_final_app_output_must_exist(self):
        self.output.unlink()
        with self.assertRaisesRegex(observer.ObservationError, "opaque artifact unavailable"):
            self.observe()

    def test_final_app_output_must_be_nonempty(self):
        self.output.write_bytes(b"")
        with self.assertRaisesRegex(observer.ObservationError, "final SideStore output is empty"):
            self.observe()

    def test_final_app_output_must_not_be_symlinked(self):
        self.output.unlink()
        self.output.symlink_to(self.framework)
        with self.assertRaisesRegex(observer.ObservationError, "symlinked evidence"):
            self.observe()

    def test_final_app_output_must_not_be_directory(self):
        self.output.unlink()
        self.output.mkdir()
        with self.assertRaisesRegex(observer.ObservationError, "not a regular file"):
            self.observe()

    def test_final_app_output_mutation_during_hashing_fails(self):
        original_open = Path.open
        output = self.output

        class MutatingOutput:
            def __init__(self, stream):
                self.stream, self.mutated = stream, False

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def fileno(self):
                return self.stream.fileno()

            def read(self, size):
                data = self.stream.read(size)
                if not self.mutated:
                    self.mutated = True
                    with original_open(output, "ab") as writer:
                        writer.write(b"changed during observation")
                return data

        def intercepted_open(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            return MutatingOutput(stream) if path == output and args == ("rb",) else stream

        with mock.patch.object(Path, "open", intercepted_open):
            with self.assertRaisesRegex(observer.ObservationError, "changed while hashing"):
                self.observe()

    def test_changed_composition_source_fails(self):
        name = sorted(observer.REQUIRED_SOURCES)[0]
        (self.app / name).write_bytes(b"different source")
        with self.assertRaisesRegex(observer.ObservationError, "bound composition source identity"):
            self.observe()

    def test_onboarding_sentinel_is_independently_pinned(self):
        name = self.contract["sentinel"]["prepared_path"]
        path = self.app / name
        path.write_bytes(path.read_bytes() + b"// unreviewed appended bytes\n")
        self.binding["bound_files"][name] = sha(path.read_bytes())
        with self.assertRaisesRegex(observer.ObservationError, "onboarding source/sentinel"):
            self.observe()

    def test_contract_cannot_drop_a_mandatory_input(self):
        del self.contract["prepared_composition_sources"][sorted(observer.REQUIRED_SOURCES)[0]]
        with self.assertRaisesRegex(observer.ObservationError, "fourteen"):
            self.observe()

    def test_release_configuration_identity(self):
        self.link_args[-1] = self.link_args[-1].replace("Debug-iphoneos", "Release-iphoneos")
        self.put(Path(self.link_args[-1]), self.output_bytes)
        self.assertEqual(self.observe(configuration="Release")["configuration"], "Release")

    def test_log_and_reference_bounds(self):
        with mock.patch.object(observer, "MAX_LOG", 64):
            with self.assertRaisesRegex(observer.ObservationError, "log size bound"):
                self.observe()
        with mock.patch.object(observer, "MAX_REFERENCES", 1):
            with self.assertRaisesRegex(observer.ObservationError, "reference bound"):
                self.observe()

    def test_new_sentinel_is_compile_only_and_names_contract_apis(self):
        source = (HERE / "PairingCompositionCompileSentinel.swift").read_text()
        self.assertTrue(source.startswith(observer.SENTINEL_MARKER.decode()))
        for symbol in ("TetherlessPairingHostResult", "TetherlessPairingValidationResult", "PairingValidationBudget",
                       "PairingSetupView", "WirelessPairView", "OnboardingView", "tetherless_pairing_validate_staged"):
            self.assertIn(symbol, source)
        self.assertIn("#error", source)
        self.assertNotIn("@main", source)


class TemporaryObserverFixtureRootTests(unittest.TestCase):
    def test_owned_temporary_parent_alias_preserves_evidence_and_mutation_checks(self):
        methods = (
            "test_honest_swiftdriver_and_final_link_with_different_deployments",
            "test_changed_repeated_text_read_retains_both_versions_and_fails",
            "test_final_app_output_mutation_during_hashing_fails",
            "test_response_cycle_is_rejected",
            "test_malformed_raw_inputs_remain_after_parse_failure",
            "test_owned_root_alias_does_not_allow_descendant_symlink_escape",
            "test_symlink_parent_traversal_cannot_forge_source_membership",
        )
        with tempfile.TemporaryDirectory(prefix="observer alias regression ") as directory:
            root = Path(directory).resolve(strict=True)
            physical = root / "physical"
            physical.mkdir()
            alias = root / "alias"
            alias.symlink_to(physical, target_is_directory=True)
            self.assertTrue(alias.is_symlink())
            self.assertTrue(alias.samefile(physical))
            with mock.patch.object(tempfile, "tempdir", str(alias)):
                for method in methods:
                    with self.subTest(method=method):
                        result = unittest.TestResult()
                        CompileObserverTests(method).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.skipped, [])
                        self.assertEqual(result.errors, [])
                        self.assertEqual(result.failures, [])


if __name__ == "__main__":
    unittest.main()
