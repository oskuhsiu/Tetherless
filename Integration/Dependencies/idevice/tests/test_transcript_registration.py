"""Controlled orchestration/source tests, never a native transcript result."""
from contextlib import ExitStack
import copy
import json
from pathlib import Path
import sys
import tempfile
import tomllib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import apply_patch
import run_pairing_transcript_tests as runner
from test_pairing_component_runner import RunnerFixture, provider, AUDIT_FILES


def source_preimages(profile):
    names = {e["path"] for e in profile["edits"]}
    names.update(e["path"] for e in profile["overlays"] if e["kind"] == "replace")
    names.add("Cargo.lock")
    return {name: (ROOT / "upstream" / name).read_bytes() for name in names}


class TranscriptSourceTests(unittest.TestCase):
    def test_exact_profile_and_review_receipts(self):
        profile = runner.load_transcript_profile()
        self.assertEqual(profile["native_test_filters"], [runner.SUITE])
        self.assertEqual(profile["build_additional_features"], runner.FEATURES)
        self.assertEqual(len(profile["overlays"]), 13)
        self.assertEqual(len(profile["edits"]), 3)

    def test_manifest_composition_preserves_plist_stream_feature_and_defaults(self):
        profile = runner.load_transcript_profile()
        original = source_preimages(profile)
        files = apply_patch.patched_files(ROOT, profile, original)
        for package in ("ffi", "idevice"):
            before = tomllib.loads(original[package + "/Cargo.toml"].decode())
            after = tomllib.loads(files[package + "/Cargo.toml"].decode())
            self.assertEqual(before["features"]["default"], after["features"]["default"])
            expected_dependencies = copy.deepcopy(before["dependencies"])
            if package == "ffi":
                expected_dependencies["plist"] = {"version": "1.7.1", "features": [
                    "enable_unstable_features_that_may_break_with_minor_version_bumps"]}
                self.assertEqual(after["features"]["tetherless-synthetic-peer"], ["idevice/tetherless-synthetic-peer"])
            else:
                self.assertEqual(after["features"]["tetherless-synthetic-peer"], ["openssl", "remote_pairing", "rsd", "tunnel_tcp_stack"])
            self.assertEqual(after["dependencies"], expected_dependencies)
            features = dict(after["features"])
            del features["tetherless-synthetic-peer"]
            self.assertEqual(features, before["features"])
        self.assertEqual(files["Cargo.lock"], original["Cargo.lock"])

    def test_production_overlays_and_profiles_remain_unchanged(self):
        profile = runner.load_transcript_profile()
        fixtures = [e for e in profile["overlays"] if "source_path" in e]
        self.assertEqual(len(fixtures), 4)
        for name in ("acquisition-only", "combined"):
            production = apply_patch.load_lock(ROOT, "candidate-profiles/" + name + ".json")
            for entry in production["overlays"]:
                self.assertNotIn("source_path", entry)
                self.assertEqual(apply_patch.sha256((ROOT / "overlay" / entry["path"]).read_bytes()), entry["sha256"])
        originals = profile["registration_receipts"]
        self.assertIn("registration/receipts/composite-transcript-review.md", originals)

    def test_transcript_keeps_the_repaired_production_prefix_byte_exact(self):
        production = (ROOT / "overlay/ffi/src/staged_acquisition.rs").read_bytes()
        fixture = (ROOT / "transcript-overlay/ffi/src/staged_acquisition.rs").read_bytes()
        declaration = b'\n#[cfg(all(test, feature = "tetherless-synthetic-peer"))]\nmod composite_transcript;\n'
        self.assertEqual(apply_patch.sha256(production), "3057cc162efc267d3e8e3dee323141822adf789f226fed17292b4098ac1c5d89")
        self.assertEqual(fixture, production + declaration)
        profile = runner.load_transcript_profile()
        for name in ("acquisition-stack-repair.json", "acquisition-stack-independent-review.json"):
            self.assertIn("registration/receipts/" + name, profile["registration_receipts"])

    def test_fixture_overlay_source_is_closed_to_its_declared_path_and_profile(self):
        original = runner.load_transcript_profile()
        for kind in ("wrong-profile", "wrong-path"):
            profile = copy.deepcopy(original)
            if kind == "wrong-profile":
                profile["profile_kind"] = "registered-acquisition-only-candidate"
            else:
                next(e for e in profile["overlays"] if "source_path" in e)["source_path"] = "../unreviewed.rs"
            with self.subTest(kind=kind), self.assertRaises(apply_patch.VerificationError):
                apply_patch.patched_files(ROOT, profile, source_preimages(profile))

    def test_profile_scope_mutations_are_rejected(self):
        original = runner.load_transcript_profile()
        for change in (lambda p: p["native_test_filters"][0].update(expected_passed=4),
                       lambda p: p.update(build_additional_features=["openssl"]),
                       lambda p: p["activation"].update(enabled=True),
                       lambda p: p["activation"].update(consumer_integration_allowed=True),
                       lambda p: p["activation"].update(test_only_execution_authorized=False),
                       lambda p: p["fixture_inventory"].update(executed=True)):
            changed = copy.deepcopy(original)
            change(changed)
            with patch.object(runner, "load_lock", return_value=changed), self.assertRaises(apply_patch.VerificationError):
                runner.load_transcript_profile()


class TranscriptFixture(RunnerFixture):
    def __init__(self, root):
        super().__init__(root)
        self.profile_path = runner.PROFILE
        self.profile = runner.load_transcript_profile()

    def patches(self):
        stack = ExitStack()
        stack.enter_context(patch.object(provider, "load_contract", return_value=self.contract))
        api = SimpleNamespace(prepare_inputs=provider.prepare_inputs, build_environment=provider.build_environment,
                              audit_inputs=provider.audit_inputs, check_build_script_output=self.check_output)
        for name, value in {"load_transcript_profile": lambda: copy.deepcopy(self.profile),
                            "load_provider": lambda: api, "native_environment": self.environment,
                            "verify_toolchain": lambda *_: {"controlled_fixture": True},
                            "stage": self.stage, "prepare_offline_vendor": self.vendor,
                            "capture_helper_command": self.command}.items():
            stack.enter_context(patch.object(runner, name, value))
        return stack


class TranscriptRunnerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="transcript fixture ")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def audits(self, fixture, published=False):
        root = fixture.args.output if published else fixture.completed
        for name in AUDIT_FILES:
            self.assertTrue((root / name).is_file(), name)
        return {name: json.loads((root / name).read_bytes()) for name in AUDIT_FILES}

    def test_exact_three_test_command_and_success_evidence(self):
        fixture = TranscriptFixture(self.root / "success")
        with fixture.patches():
            result = runner.execute(fixture.args)
        self.assertEqual(result["passed"], 3)
        self.assertFalse(result["artifact_or_product_activation"])
        self.assertFalse(result["apple_or_device_compatibility"])
        self.assertFalse(result["header_probe_linked_or_executed"])
        self.audits(fixture, published=True)
        cargo = [c["argv"] for c in fixture.calls if c["argv"][0] == "controlled-cargo-never-executed"]
        self.assertEqual([c[1] for c in cargo], ["tree", "test"])
        for argv in cargo:
            self.assertEqual(argv[argv.index("--features") + 1], "openssl,tetherless-synthetic-peer")
            self.assertIn("--frozen", argv)
            self.assertNotIn("--no-default-features", argv)
        self.assertEqual(cargo[-1][-1], runner.SUITE["filter"])
        self.assertEqual(len(result["openssl_outputs"]), 1)
        self.assertEqual(len({c["log"].name for c in fixture.calls}), len(fixture.calls))
        self.assertTrue((fixture.args.output / "01-transcript.txt.status.json").is_file())

    def test_each_phase_failure_retains_all_audits_and_failure_status(self):
        for index, name in enumerate(("00-sdk-path.txt", "00-header-compile.txt", "00-features-idevice-ffi.txt", "01-transcript.txt")):
            fixture = TranscriptFixture(self.root / str(index))
            fixture.failure_log = name
            with fixture.patches(), self.assertRaises(apply_patch.VerificationError):
                runner.execute(fixture.args)
            self.assertFalse(fixture.args.output.exists())
            self.audits(fixture)
            status = json.loads((fixture.completed / (name + ".status.json")).read_bytes())
            self.assertEqual(status["outcome"], "nonzero_exit")
            self.assertTrue(status["cleanup"]["direct_child_reaped"])

    def test_wrong_count_does_not_publish(self):
        fixture = TranscriptFixture(self.root / "count")
        fixture.summary_offset = -1
        with fixture.patches(), self.assertRaises(apply_patch.VerificationError):
            runner.execute(fixture.args)
        self.audits(fixture)
        self.assertFalse(fixture.args.output.exists())

    def test_timeout_and_quota_cannot_publish_a_success_shaped_summary(self):
        for kind in ("timeout", "output_limit"):
            fixture = TranscriptFixture(self.root / kind)
            fixture.failure_kind, fixture.failure_log = kind, "01-transcript.txt"
            with fixture.patches(), self.assertRaises(apply_patch.VerificationError):
                runner.execute(fixture.args)
            self.audits(fixture)
            self.assertFalse(fixture.args.output.exists())
            status = json.loads((fixture.completed / "01-transcript.txt.status.json").read_bytes())
            self.assertEqual(status["outcome"], kind)

    def test_changed_provider_and_missing_output_are_rejected_after_summary(self):
        for fault in ("directives", "missing"):
            fixture = TranscriptFixture(self.root / fault)
            fixture.output_fault = fault
            with fixture.patches(), self.assertRaises((OSError, ValueError)):
                runner.execute(fixture.args)
            self.audits(fixture)
            self.assertFalse(fixture.args.output.exists())

    def test_post_success_source_mutation_prevents_publication(self):
        fixture = TranscriptFixture(self.root / "mutate")
        fixture.mutation = lambda f: (f.args.work_dir / "source/Cargo.lock").write_text("changed\n")
        with fixture.patches(), self.assertRaises(apply_patch.VerificationError):
            runner.execute(fixture.args)
        audits = self.audits(fixture)
        self.assertFalse(audits["workspace-input-audit.json"]["original_inputs_unchanged"])
        self.assertFalse(fixture.args.output.exists())


if __name__ == "__main__":
    unittest.main()
