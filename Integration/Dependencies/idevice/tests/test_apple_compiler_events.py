"""Observed Cargo metadata and controlled path-only fixtures; no native tools."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_pairing_apple as apple
from apply_patch import VerificationError
from run_pairing_component_tests import selected_openssl_outputs


class AppleCompilerEventTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="apple-cargo-events-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.events = json.loads((ROOT / "tests/fixtures/apple-release-compiler-events.json").read_text())
        self.script, self.library = [e for e in self.events if e["reason"] == "compiler-artifact"]
        self.source = Path(self.library["manifest_path"]).parent.parent
        self.defaults = tomllib.loads((ROOT / "upstream/ffi/Cargo.toml").read_text())["features"]["default"]
        self.graph = self.root / "graph.txt"
        self.graph.write_text("controlled resolved graph without synthetic peer\n")
        self.log = self.root / "cargo.jsonl"

    def check(self, events=None):
        self.log.write_text("ordinary non-JSON compiler progress\n" + "\n".join(json.dumps(e) for e in
                            (self.events if events is None else events)) + "\n")
        return apple.check_production_features(self.log, self.graph, self.source, self.defaults, apple.TARGETS[0])

    def test_observed_build_script_then_unique_static_library_is_selected(self):
        self.assertEqual(self.script["target"]["kind"], ["custom-build"])
        self.assertEqual(self.script["target"]["crate_types"], ["bin"])
        result = self.check()
        self.assertEqual(result["ffi_artifact"]["filenames"], self.library["filenames"])
        self.assertEqual(result["ffi_artifact"]["features"], self.library["features"])
        self.assertIs(result["synthetic_peer_selected"], False)

    def test_build_script_only_cannot_stand_in_for_library(self):
        with self.assertRaisesRegex(VerificationError, "exactly one"):
            self.check([self.script])

    def test_duplicate_correct_static_libraries_still_fail(self):
        with self.assertRaisesRegex(VerificationError, "exactly one"):
            self.check([self.script, self.library, copy.deepcopy(self.library)])

    def test_only_the_exact_observed_custom_build_identity_is_ignored(self):
        for field, value in (("kind", ["bin"]), ("crate_types", ["rlib"]),
                             ("name", "other-build"), ("src_path", str(self.source / "ffi/other.rs"))):
            script = copy.deepcopy(self.script)
            script["target"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(VerificationError, "staticlib target"):
                self.check([script, self.library])

    def test_static_target_source_name_and_type_must_match(self):
        for field, value in (("kind", ["rlib"]), ("crate_types", ["bin"]),
                             ("name", "other_ffi"), ("src_path", str(self.source / "ffi/src/other.rs"))):
            library = copy.deepcopy(self.library)
            library["target"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(VerificationError, "staticlib target"):
                self.check([self.script, library])

    def test_target_release_archive_identity_is_required(self):
        library = copy.deepcopy(self.library)
        library["filenames"] = [str(self.source.parent / "target/release/libidevice_ffi.a")]
        with self.assertRaisesRegex(VerificationError, "target release archive"):
            self.check([self.script, library])

    def test_synthetic_feature_remains_rejected_on_script_library_and_other_crate(self):
        for subject in (self.script, self.library, dict(self.library, manifest_path="/other/Cargo.toml")):
            bad = copy.deepcopy(subject)
            bad["features"].append("tetherless-synthetic-peer")
            with self.subTest(target=bad["target"]["name"]), self.assertRaisesRegex(VerificationError, "synthetic-peer"):
                self.check([bad, self.library])

    def test_default_and_explicit_features_cannot_be_dropped(self):
        for feature in ("default", "openssl", "obfuscate", self.defaults[0]):
            library = copy.deepcopy(self.library)
            library["features"].remove(feature)
            with self.subTest(feature=feature), self.assertRaisesRegex(VerificationError, "preserve"):
                self.check([self.script, library])

    def test_observed_openssl_event_selects_exact_release_output_without_native_libs(self):
        event = next(e for e in self.events if e["reason"] == "build-script-executed")
        self.assertEqual(event["linked_libs"], [])
        original = Path(event["out_dir"])
        target_root = self.root / "target/aarch64-apple-ios"
        out_dir = target_root / "release/build" / original.parent.name / "out"
        out_dir.mkdir(parents=True)
        output = out_dir.parent / "output"
        output.write_text("controlled placeholder; actual directives were not retained\n")
        mapped = dict(event, out_dir=str(out_dir))
        self.log.write_text(json.dumps(mapped) + "\n")
        self.assertEqual(selected_openssl_outputs(self.log, target_root, "release"), [output])


if __name__ == "__main__":
    unittest.main()
