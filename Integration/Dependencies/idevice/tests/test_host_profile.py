"""Host-only source/profile checks; no native compilation or account/device work."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import apply_patch
import run_host_tests


class HostOnlyProfileTests(unittest.TestCase):
    def test_profile_stages_only_three_host_sources_and_one_declaration(self):
        profile = run_host_tests.load_host_profile()
        originals = {str(p.relative_to(ROOT / "upstream")): p.read_bytes()
                     for p in (ROOT / "upstream").rglob("*") if p.is_file()}
        staged = apply_patch.patched_files(ROOT, profile, originals)
        changes = {p for p in set(originals) | set(staged) if originals.get(p) != staged.get(p)}
        self.assertEqual(changes, {"ffi/src/lib.rs", "ffi/src/bounded_pairing_host.rs",
                                  "idevice/src/remote_pairing/opack.rs", "idevice/src/remote_pairing/responder.rs"})
        self.assertNotIn("ffi/src/staged_pairing.rs", staged)
        self.assertNotIn("ffi/src/staged_acquisition.rs", staged)
        self.assertNotIn(b"pub mod staged_acquisition", staged["ffi/src/lib.rs"])
        self.assertNotIn(b"pub mod staged_pairing", staged["ffi/src/lib.rs"])
        self.assertEqual(staged["Cargo.lock"], originals["Cargo.lock"])
        self.assertEqual(staged["ffi/Cargo.toml"], originals["ffi/Cargo.toml"])
        self.assertEqual(sum(e["expected_passed"] for e in profile["native_test_filters"]), 26)
        self.assertFalse(profile["activation"]["enabled"])
        self.assertFalse(profile["activation"]["consumer_integration_allowed"])
        self.assertTrue(profile["activation"]["test_only_execution_authorized"])

    def test_acquisition_or_decoder_overlay_is_rejected(self):
        for path in ("ffi/src/staged_acquisition.rs", "idevice/src/xpc/mod.rs"):
            profile = run_host_tests.load_host_profile()
            profile["overlays"].append({"path": path, "sha256": "0" * 64})
            with self.subTest(path=path), patch.object(run_host_tests, "load_lock", return_value=profile):
                with self.assertRaises(apply_patch.VerificationError):
                    run_host_tests.load_host_profile()

    def test_unguarded_host_module_is_rejected(self):
        profile = run_host_tests.load_host_profile()
        profile["edits"][0]["new"] = profile["edits"][0]["old"] + "pub mod bounded_pairing_host;\n"
        with patch.object(run_host_tests, "load_lock", return_value=profile):
            with self.assertRaises(apply_patch.VerificationError):
                run_host_tests.load_host_profile()

    def test_openssl_or_artifact_activation_is_rejected(self):
        for change in ("feature", "artifact"):
            profile = run_host_tests.load_host_profile()
            if change == "feature":
                profile["build_additional_features"] = ["openssl"]
            else:
                profile["activation"]["enabled"] = True
            with self.subTest(change=change), patch.object(run_host_tests, "load_lock", return_value=profile):
                with self.assertRaises(apply_patch.VerificationError):
                    run_host_tests.load_host_profile()

    def test_test_counts_and_source_receipt_remain_exact(self):
        profile = run_host_tests.load_host_profile()
        self.assertEqual([e["expected_passed"] for e in profile["native_test_filters"]], [8, 5, 3, 4, 6])
        profile["native_test_filters"][3]["expected_passed"] = 10  # Must not count six older OPACK tests.
        with patch.object(run_host_tests, "load_lock", return_value=profile):
            with self.assertRaises(apply_patch.VerificationError):
                run_host_tests.load_host_profile()

    def test_source_receipt_mutation_is_rejected(self):
        profile = run_host_tests.load_host_profile()
        profile["registration_receipts"]["registration/receipts/host-generation.json"] = "0" * 64
        with patch.object(run_host_tests, "load_lock", return_value=profile):
            with self.assertRaises(apply_patch.VerificationError):
                run_host_tests.load_host_profile()


if __name__ == "__main__":
    unittest.main()
