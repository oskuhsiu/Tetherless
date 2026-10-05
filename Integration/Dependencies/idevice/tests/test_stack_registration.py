"""Check the repaired source/test registration without compiling native code."""
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apply_patch import sha256
import run_pairing_component_tests as runner
import verify_registration


class StackRegistrationTests(unittest.TestCase):
    def test_source_receipt_and_exact_eleven_authored_tests_agree(self):
        receipt = json.loads((ROOT / "registration/receipts/acquisition-stack-repair.json").read_bytes())
        source = (ROOT / "overlay/ffi/src/staged_acquisition.rs").read_bytes()
        self.assertEqual(sha256(source), receipt["changed_source"]["sha256"])
        names = re.findall(rb"#\[(?:tokio::)?test\]\s+(?:async\s+)?fn\s+(\w+)\s*\(", source)
        self.assertEqual(len(names), 11)
        self.assertEqual(len(set(names)), 11)
        for full_name in receipt["native_test_delta"]["new_tests"]:
            self.assertIn(full_name.rsplit("::", 1)[1].encode(), names)
        self.assertNotIn(b"#[ignore", source)
        self.assertFalse(receipt["rust_runtime_executed"])
        historical = json.loads((ROOT / "registration/receipts/contributory-acquisition.json").read_bytes())
        old = next(row for row in historical["files"] if row["path"] == "ffi/src/staged_acquisition.rs")
        self.assertEqual(old["overlay_sha256"], receipt["changed_source"]["preimage_sha256"])

    def test_profiles_registry_runner_and_receipts_select_exact_74_and_94(self):
        registry = json.loads((ROOT / "registration/registration.json").read_bytes())
        for name, total in (("acquisition-only", 74), ("combined", 94)):
            with self.subTest(profile=name):
                path, profile = runner.load_profile(name)
                self.assertEqual(registry["profiles"][name]["sha256"], sha256((ROOT / path).read_bytes()))
                self.assertEqual(registry["profiles"][name]["authored_fixtures"], total)
                self.assertEqual(profile["fixture_inventory"]["authored_count"], total)
                suites = profile["native_test_filters"]
                self.assertEqual(sum(item["expected_passed"] for item in suites), total)
                staged = [item for item in suites if item["filter"] == "staged_acquisition::"]
                self.assertEqual(len(staged), 1)
                self.assertEqual(staged[0]["expected_passed"], 11)
                receipt_path = "registration/receipts/acquisition-stack-repair.json"
                receipt_hash = sha256((ROOT / receipt_path).read_bytes())
                self.assertEqual(profile["registration_receipts"][receipt_path], receipt_hash)
                self.assertEqual(registry["registered_source_receipts"][receipt_path], receipt_hash)
                self.assertFalse(profile["activation"]["consumer_integration_allowed"])
        checked = verify_registration.verify(ROOT)
        self.assertEqual(checked["acquisition-only"]["authored_fixture_count"], 74)
        self.assertEqual(checked["combined"]["authored_fixture_count"], 94)


if __name__ == "__main__":
    unittest.main()
