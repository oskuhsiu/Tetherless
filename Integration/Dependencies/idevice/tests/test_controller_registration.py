"""Exact production M5 source/count propagation; no native protocol execution."""
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apply_patch import sha256
import run_host_tests
import run_pairing_component_tests

FILTER = "remote_pairing::responder::bounded_controller_signature_tests::"


class ControllerRegistrationTests(unittest.TestCase):
    def test_only_reviewed_production_responder_and_exact_six_tests_are_registered(self):
        source = json.loads((ROOT / "registration/receipts/host-controller-signature.json").read_bytes())
        review = json.loads((ROOT / "registration/receipts/host-controller-signature-review.json").read_bytes())
        relative = "idevice/src/remote_pairing/responder.rs"
        data = (ROOT / "overlay" / relative).read_bytes()
        expected = next(item["sha256"] for item in source["files"] if item["path"] == "Integration/Dependencies/idevice/overlay/" + relative)
        self.assertEqual(sha256(data), expected)
        self.assertEqual(review["final_reviewed_files"][relative], expected)
        module = data.split(b"mod bounded_controller_signature_tests {", 1)[1]
        names = re.findall(rb"#\[test\]\s+fn\s+(\w+)\s*\(", module)
        self.assertEqual(sorted(name.decode() for name in names), sorted(source["authored_native_test_names"][FILTER]))
        self.assertEqual(len(names), 6)
        self.assertEqual(source["native_test_filters"][FILTER], 6)
        self.assertFalse(review["native_compilation_executed"])
        self.assertFalse((ROOT / "overlay/idevice/src/remote_pairing/host_test_phone.rs").exists())
        self.assertFalse((ROOT / "overlay/ffi/src/bounded_pairing_host/host_transcript.rs").exists())

    def test_host26_combined100_keep_acquisition74_profile_identity(self):
        registry = json.loads((ROOT / "registration/registration.json").read_bytes())
        for name, total in (("host-only", 26), ("combined", 100)):
            profile = run_host_tests.load_host_profile() if name == "host-only" else run_pairing_component_tests.load_profile(name)[1]
            self.assertEqual(sum(item["expected_passed"] for item in profile["native_test_filters"]), total)
            self.assertEqual(profile["fixture_inventory"]["authored_count"], total)
            self.assertEqual(registry["profiles"][name]["authored_fixtures"], total)
            self.assertEqual(registry["profiles"][name]["sha256"], sha256((ROOT / "candidate-profiles" / (name + ".json")).read_bytes()))
            selected = [item for item in profile["native_test_filters"] if item["filter"] == FILTER]
            self.assertEqual(selected, [{"package": "idevice", "filter": FILTER, "expected_passed": 6}])
            self.assertFalse(profile["activation"]["enabled"])
            self.assertFalse(profile["activation"]["consumer_integration_allowed"])
        acquisition = ROOT / "candidate-profiles/acquisition-only.json"
        self.assertEqual(sha256(acquisition.read_bytes()), "954a3700d53010885c060569f5192ecfb0a3a69a119daaf183c00ece51de08aa")


if __name__ == "__main__":
    unittest.main()
