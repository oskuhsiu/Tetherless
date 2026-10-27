"""Comparison diagnostics only; no admission normalization or native execution."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import derived_cbindgen as derived
from apply_patch import canonical_json, VerificationError
from test_derived_cbindgen import DerivedCbindgenTests


class InventoryDifferenceTests(unittest.TestCase):
    def test_missing_extra_and_changed_are_distinct(self):
        expected = {"a": "1" * 64, "missing": "2" * 64, "changed": "3" * 64}
        actual = {"a": "1" * 64, "extra": "4" * 64, "changed": "5" * 64}
        result = derived.inventory_difference(expected, actual)
        self.assertFalse(result["exact_match"])
        self.assertEqual(result["counts"], {"missing": 1, "extra": 1, "changed": 1})
        self.assertEqual(result["details"]["changed"][0]["expected_sha256"], "3" * 64)
        self.assertEqual(result["details"]["changed"][0]["actual_sha256"], "5" * 64)
        self.assertFalse(result["file_contents_retained"])

    def test_dotfiles_are_regular_comparison_entries(self):
        expected = {"crate/.cargo-checksum.json": "1" * 64, "crate/.hidden": "2" * 64}
        self.assertTrue(derived.inventory_difference(expected, dict(expected))["exact_match"])
        result = derived.inventory_difference(expected, {"crate/.hidden": "2" * 64})
        self.assertEqual(result["details"]["missing"][0]["path"], "crate/.cargo-checksum.json")

    def test_case_and_unicode_spelling_still_fail_exact_admission(self):
        for before, after in (("crate/Readme", "crate/README"), ("crate/é", "crate/e\u0301")):
            with self.subTest(before=before):
                result = derived.inventory_difference({before: "1" * 64}, {after: "1" * 64})
                self.assertFalse(result["exact_match"])
                self.assertEqual(result["details"]["missing"][0]["path"], before)
                self.assertEqual(result["details"]["extra"][0]["path"], after)
                self.assertEqual(result["counts"], {"missing": 1, "extra": 1, "changed": 0})

    def test_detail_count_and_path_bytes_are_bounded(self):
        expected = {f"crate/{n}/" + "x" * 513: "1" * 64 for n in range(200)}
        actual = {f"other/{n}": "2" * 64 for n in range(200)}
        result = derived.inventory_difference(expected, actual)
        self.assertTrue(result["details_truncated"])
        self.assertEqual(sum(map(len, result["details"].values())), 128)
        self.assertEqual(result["omitted_counts"], {"missing": 136, "extra": 136, "changed": 0})
        self.assertTrue(all(row["path"] is None and row["path_sha256"] for row in result["details"]["missing"]))
        self.assertEqual(result["counts"], {"missing": 200, "extra": 200, "changed": 0})
        self.assertLess(len(canonical_json(result)), 1024 * 1024)

    def test_each_overfull_category_retains_its_own_evidence(self):
        expected = {f"missing/{n}": "1" * 64 for n in range(100)}
        expected.update({f"changed/{n}": "2" * 64 for n in range(100)})
        actual = {f"extra/{n}": "3" * 64 for n in range(100)}
        actual.update({f"changed/{n}": "4" * 64 for n in range(100)})
        result = derived.inventory_difference(expected, actual)
        self.assertFalse(result["exact_match"])
        self.assertEqual(result["counts"], {"missing": 100, "extra": 100, "changed": 100})
        self.assertEqual(result["omitted_counts"], {"missing": 36, "extra": 36, "changed": 36})
        self.assertEqual({kind: len(rows) for kind, rows in result["details"].items()},
                         {"missing": 64, "extra": 64, "changed": 64})
        self.assertTrue(result["details_truncated"])
        self.assertLess(len(canonical_json(result)), 1024 * 1024)

    def test_equal_maps_have_complete_hash_receipt_without_differences(self):
        expected = {"file": "1" * 64}
        result = derived.inventory_difference(expected, expected)
        self.assertTrue(result["exact_match"])
        self.assertEqual(result["counts"], {"missing": 0, "extra": 0, "changed": 0})
        self.assertEqual(result["expected_inventory_sha256"], hashlib.sha256(canonical_json(expected)).hexdigest())
        self.assertEqual(result["observed_inventory_sha256"], result["expected_inventory_sha256"])


class PreparationDiagnosticTests(DerivedCbindgenTests):
    # Only these two additional wiring cases run from this class. The original
    # suite is imported for fixture setup rather than weakening its assertions.
    def test_inventory_mismatch_is_retained_before_original_error(self):
        original_rglob = Path.rglob
        def with_extra(path, pattern, *args, **kwargs):
            if path == self.work / "vendor":
                (path / "controlled-extra").write_text("unexpected file after authentication")
            return original_rglob(path, pattern, *args, **kwargs)
        with patch.object(Path, "rglob", with_extra):
            with self.assertRaisesRegex(VerificationError, "missing=0 extra=1 changed=0"):
                self.prepare()
        receipt = json.loads((self.work / "vendor-derivation-inventory.json").read_bytes())
        self.assertFalse(receipt["exact_match"])
        self.assertFalse(receipt["admitted"])
        self.assertEqual(receipt["details"]["extra"][0]["path"], "controlled-extra")
        self.assertFalse((self.work / "build-vendor").exists())

    def test_matching_inventory_receipt_is_bound_to_derived_layout(self):
        receipt = self.prepare()
        path = Path(receipt["derived_build"]["inventory_diagnostic"])
        self.assertTrue(json.loads(path.read_bytes())["exact_match"])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), receipt["derived_build"]["inventory_diagnostic_sha256"])


# Avoid rerunning inherited baseline tests through a second discovery class.
for _name in dir(DerivedCbindgenTests):
    if _name.startswith("test_"):
        setattr(PreparationDiagnosticTests, _name, None)
del DerivedCbindgenTests

if __name__ == "__main__":
    unittest.main()
