"""Synthetic retained-C orchestration tests; no producer/native binaries run.

Only the retained Actions artifact authentication boundary is stubbed by the
shared fixture. Actual SDK/provider, C-global, disjointness, and map ownership
validators execute against controlled text and opaque Python-created files.
"""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_pairing_apple as apple
from apply_patch import VerificationError
from test_pairing_apple import AppleFixture, SYSTEM_FLAGS


class RetainedCAppleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def fixture(self, name="fixture"):
        return AppleFixture(self.root / name)

    def assert_not_built(self, fixture):
        self.assertFalse(fixture.args.output.exists())
        self.assertFalse(any(call["log"].name == "03-release-build.txt" for call in fixture.calls))

    def test_unselected_handoff_fails_closed_before_any_native_command(self):
        fixture = self.fixture()
        actual_verify = apple.retained_c_provider.verify
        selection = self.root / "selection.json"
        selection.write_text('{"schema":1,"selection":null}\n')
        def verify(root, target, *, expected_handoff_sha256):
            return actual_verify(root, target, expected_handoff_sha256=expected_handoff_sha256, selection_path=selection)
        with fixture.patches(), patch.object(apple.retained_c_provider, "verify", side_effect=verify):
            with self.assertRaisesRegex(VerificationError, "no successful C producer is selected"):
                apple.build(fixture.args)
        self.assertEqual(fixture.calls, [])
        self.assertFalse(fixture.args.work_dir.exists())
        self.assert_not_built(fixture)

    def test_missing_or_wrong_handoff_hash_fails_before_native_commands(self):
        for name, value in (("missing", ""), ("wrong", "0" * 64)):
            fixture = self.fixture(name)
            fixture.args.retained_c_handoff_sha256 = value
            with fixture.patches(), self.assertRaises(VerificationError):
                apple.build(fixture.args)
            self.assertEqual(fixture.calls, [])
            self.assert_not_built(fixture)

    def test_handoff_work_or_output_overlap_is_rejected_before_commands(self):
        for name in ("work_dir", "output"):
            fixture = self.fixture(name)
            setattr(fixture.args, name, fixture.args.retained_c_provider / "nested-output")
            with fixture.patches(), self.assertRaisesRegex(VerificationError, "must not overlap"):
                apple.build(fixture.args)
            self.assertEqual(fixture.calls, [])
            self.assert_not_built(fixture)

    def test_sdk_or_provider_mismatch_blocks_cargo_and_linking(self):
        for name in ("sdk_version", "sdk_build", "xcode", "framework_binary_sha256", "contract_sha256"):
            fixture = self.fixture(name)
            original = fixture.mixed_provider
            def verify(root, target, *, expected_handoff_sha256):
                result = original(root, target, expected_handoff_sha256=expected_handoff_sha256)
                if name in ("framework_binary_sha256", "contract_sha256"):
                    result["provider_identity"][name] = "0" * 64
                else:
                    result[name] = "wrong controlled identity"
                return result
            with fixture.patches(), patch.object(apple.retained_c_provider, "verify", side_effect=verify):
                with self.assertRaises(VerificationError):
                    apple.build(fixture.args)
            self.assert_not_built(fixture)
            self.assertFalse(any(call["log"].name.startswith("05-link-") for call in fixture.calls))

    def test_complete_c_nm_rejects_missing_extra_and_duplicate_globals(self):
        for name, transform in (
            ("missing", lambda text: text.replace("_sha512_init\n", "")),
            ("extra", lambda text: text + "_unreviewed_extra_c_global\n"),
            ("duplicate", lambda text: text + "_sha512_init\n"),
        ):
            fixture = self.fixture(name)
            def capture(argv, *, source, env, log):
                tail = fixture.command(argv, source=source, env=env, log=log)
                if log.name == "04-c-export-symbols.txt":
                    # Replace controlled scanner bytes at the capture boundary.
                    # The retained full log, not the returned summary, must win.
                    log.write_text(transform(log.read_text()))
                return tail
            with fixture.patches(), patch.object(apple, "capture_helper_command", side_effect=capture):
                with self.assertRaises(VerificationError):
                    apple.build(fixture.args)
            self.assertFalse(fixture.args.output.exists())
            self.assertFalse(any(call["log"].name.startswith("05-link-") for call in fixture.calls))

    def test_each_language_requires_full_live_correct_archive_ownership(self):
        for language in ("c", "swift"):
            for fault in ("missing-c", "missing-rust", "wrong-owner", "dead-stripped"):
                fixture = self.fixture(language + "-" + fault)
                original = fixture.command
                def capture(argv, *, source, env, log):
                    if log.name == "05-link-mixed_provider-" + language + ".txt":
                        map_path = Path(argv[argv.index("-map") + 2])
                        result = original(argv, source=source, env=env, log=log)
                        text = map_path.read_text()
                        if fault == "missing-c":
                            text = "\n".join(line for line in text.splitlines() if not line.endswith(" _sha512_init")) + "\n"
                        elif fault == "missing-rust":
                            text = "\n".join(line for line in text.splitlines() if not line.endswith(" _tetherless_native_adapter_close")) + "\n"
                        elif fault == "wrong-owner":
                            text = text.replace("[ 4] _tetherless_native_adapter_close", "[ 1] _tetherless_native_adapter_close")
                        else:
                            text = text.replace("# Symbols:\n", "# Dead Stripped Symbols:\n")
                        map_path.write_text(text)
                        return result
                    return original(argv, source=source, env=env, log=log)
                with fixture.patches(), patch.object(apple, "capture_helper_command", side_effect=capture):
                    with self.assertRaises(VerificationError):
                        apple.build(fixture.args)
                self.assertFalse(fixture.args.output.exists())
                self.assertFalse(any(call["log"].name == "create-xcframework.txt" for call in fixture.calls))

    def test_success_retains_whole_handoff_and_sixteen_diagnostic_probes(self):
        fixture = self.fixture()
        with fixture.patches():
            result = apple.build(fixture.args)
        self.assertEqual(result["retained_c_handoff_sha256"], fixture.args.retained_c_handoff_sha256)
        self.assertEqual(result["retained_c_provider_files"], apple.inventory(fixture.args.retained_c_provider))
        self.assertEqual(sum(len(row["link_probes"]) for row in result["targets"]), 16)
        self.assertTrue(result["mixed_c_provider_link_probes_only"])
        self.assertFalse(result["mixed_c_provider_embedded_in_IDevice"])
        for name, digest in result["retained_c_provider_files"].items():
            relative = "provenance/retained-c-provider/" + name
            self.assertEqual(result["files"][relative], digest)
            self.assertEqual(apple.file_hash(fixture.args.output / relative), digest)
        for required in ("actions-artifact.zip", "handoff.json", "product/NOTICE.md", "product/matching-source.tar", "product/producer-receipt.json"):
            self.assertIn(required, result["retained_c_provider_files"])
        for row in result["targets"]:
            self.assertEqual(row["export_namespace"]["namespaced_export_count"], 382)
            self.assertTrue(row["export_namespace"]["provider_export_sets_disjoint"])
            self.assertTrue(row["c_export_contract"]["internal_global_definitions_unique"])
            self.assertEqual(row["system_link_flags"], SYSTEM_FLAGS)
            for probe in row["link_probes"]:
                command = probe["command"]
                self.assertFalse(probe["executed"])
                self.assertNotIn("-dead_strip", command)
                self.assertEqual(command[command.index("-target") + 1], row["target"]["clang"])
                if probe["group"] == "mixed_provider":
                    self.assertEqual(command.count("-force_load"), 2)
                    self.assertEqual(probe["ownership"]["c_required_live_symbols"], len(fixture.c_export_names()))
                    self.assertEqual(probe["ownership"]["rust_required_live_symbols"], 382)
                    for framework in ("CoreFoundation", "SystemConfiguration"):
                        self.assertEqual(command.count(framework), 1)
                else:
                    self.assertEqual(command.count("-force_load"), 1)
                    self.assertNotIn("CoreFoundation", command)
                    self.assertNotIn("SystemConfiguration", command)
        self.assertEqual(result["xcframework_command"].count("-library"), 2)
        self.assertNotIn("libimobiledevice.a", " ".join(result["xcframework_command"]))
        self.assertFalse(any("libimobiledevice" in name or "OpenSSL" in name
            for name in apple.inventory(fixture.args.output / "IDevice.xcframework")))

    def test_unknown_c_framework_options_are_rejected(self):
        mixed = {"headers": "/fixture/headers", "library": "/fixture/c.a",
                 "system_frameworks": ["CoreFoundation", "SystemConfiguration"]}
        for frameworks in ([], ["CoreFoundation"], ["CoreFoundation", "SystemConfiguration", "OpenSSL"],
                           ["-framework", "CoreFoundation", "-framework", "SystemConfiguration"]):
            with self.subTest(frameworks=frameworks), self.assertRaises(VerificationError):
                apple.mixed_link_arguments(dict(mixed, system_frameworks=frameworks), Path("/fixture/link.map"))

    def test_c_provenance_copy_mutation_blocks_publication(self):
        fixture = self.fixture()
        original = apple.retain_c_handoff
        def retain(args, destination):
            expected = original(args, destination)
            (destination / "product/NOTICE.md").write_text("changed after initial copy check\n")
            return expected
        with fixture.patches(), patch.object(apple, "retain_c_handoff", side_effect=retain):
            with self.assertRaisesRegex(VerificationError, "packaged retained C handoff"):
                apple.build(fixture.args)
        self.assertFalse(fixture.args.output.exists())

    def test_workflow_acquisition_precedes_build_and_limits_actions_read(self):
        workflow = (ROOT.parents[2] / ".github/workflows/pairing-components.yml").read_text()
        before, native = workflow.split("  native-proofs:\n", 1)
        self.assertNotIn("actions: read", before)
        self.assertEqual(native.count("actions: read"), 1)
        self.assertIn("permissions:\n      contents: read\n      actions: read", native)
        acquisition = native.index("acquire_retained_c_provider.py")
        self.assertLess(acquisition, native.index("rustup toolchain install"))
        self.assertLess(acquisition, native.index("fetch --locked"))
        self.assertIn("GH_TOKEN: ${{ github.token }}", native[:acquisition])
        self.assertIn("if: matrix.proof == 'apple-producer'", native[:acquisition])
        self.assertIn("--output .proof/retained-c-provider", native)
        self.assertIn("${{ steps.retained-c-provider.outputs.handoff_sha256 }}", native)
        self.assertIn("'--retained-c-handoff-sha256', os.environ['RETAINED_C_HANDOFF_SHA256']", native)
        self.assertNotIn("--mixed-provider", native)
        self.assertNotIn("releases/download/1.4.0-ss-0f88f7b", native)
        self.assertIn(".proof/retained-c-provider/", native)


if __name__ == "__main__":
    unittest.main()
