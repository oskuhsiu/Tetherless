"""Exact reviewed README alias proof; native case-insensitive check is explicit."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import derived_cbindgen as derived
import offline_vendor as vendor
from apply_patch import safe_path as original_safe_path, canonical_json
from test_derived_cbindgen import DerivedCbindgenTests


class ReadmeCaseAliasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="readme-alias-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pristine = self.root / "vendor"
        self.upper = self.pristine / derived.README_OBSERVED
        self.lower = self.pristine / derived.README_LOGICAL
        self.upper.parent.mkdir(parents=True)
        self.data = (ROOT / "upstream/registry-build/nskeyedarchiver_converter-0.1.3/README.MD").read_bytes()
        self.upper.write_bytes(self.data)
        self.expected = {derived.README_LOGICAL: derived.README_SHA256,
                         derived.README_OBSERVED: derived.README_SHA256}
        self.actual = {derived.README_OBSERVED: derived.README_SHA256}
        self.crates = {derived.README_CRATE: derived.README_ARCHIVE_SHA256}

    def reconcile(self):
        return derived.reconcile_reviewed_readme(self.pristine, self.expected, self.actual, self.crates)

    def test_retained_readme_matches_exact_reviewed_pin(self):
        self.assertEqual(len(self.data), 2398)
        self.assertEqual(hashlib.sha256(self.data).hexdigest(), derived.README_SHA256)
        receipt = ROOT / "upstream/registry-build/nskeyedarchiver_converter-0.1.3/provenance.json"
        self.assertEqual(hashlib.sha256(receipt.read_bytes()).hexdigest(),
                         "54e8bc4f7034aa6b732e77d20c165d6b212151676e5f1c1056047d067383f31d")

    def test_real_volume_alias_and_copy_keep_both_logical_keys(self):
        if not self.lower.exists():
            self.skipTest("case-sensitive local volume; real alias proof requires the native macOS volume")
        self.assertTrue(os.path.samefile(self.lower, self.upper))
        self.assertEqual(self.upper.stat().st_nlink, 1)
        original_keys = set(self.expected)
        result = self.reconcile()
        self.assertTrue(result["applied"])
        self.assertTrue(result["samefile"])
        self.assertEqual(result["link_count"], 1)
        self.assertEqual(set(self.expected), original_keys)
        copy = self.root / "build-vendor"
        shutil.copytree(self.pristine, copy)
        for name, digest in self.expected.items():
            self.assertEqual(hashlib.sha256((copy / name).read_bytes()).hexdigest(), digest)
        self.assertTrue(os.path.samefile(copy / derived.README_LOGICAL, copy / derived.README_OBSERVED))

    def test_missing_counterpart_or_wrong_hash_never_reconciles(self):
        for kind in ("missing_counterpart", "wrong_expected_hash", "wrong_observed_hash"):
            with self.subTest(kind=kind):
                expected, actual = dict(self.expected), dict(self.actual)
                if kind == "missing_counterpart": expected.pop(derived.README_OBSERVED)
                elif kind == "wrong_expected_hash": expected[derived.README_LOGICAL] = "0" * 64
                else: actual[derived.README_OBSERVED] = "0" * 64
                self.assertFalse(derived.reconcile_reviewed_readme(self.pristine, expected, actual, self.crates)["applied"])

    def test_wrong_archive_or_unrelated_difference_is_rejected(self):
        variants = [(self.expected, self.actual, {}),
                    (dict(self.expected, unrelated="0" * 64), self.actual, self.crates),
                    (self.expected, dict(self.actual, extra="0" * 64), self.crates)]
        for expected, actual, crates in variants:
            self.assertFalse(derived.reconcile_reviewed_readme(self.pristine, expected, actual, crates)["applied"])

    def test_both_existing_but_different_file_identities_do_not_pass(self):
        other = self.root / "different-file"
        other.write_bytes(self.data)
        def lookup(root, name):
            return other if name == derived.README_LOGICAL else original_safe_path(root, name)
        with patch.object(derived, "safe_path", side_effect=lookup):
            self.assertFalse(self.reconcile()["applied"])

    def test_real_hardlink_is_not_a_filename_alias(self):
        hardlink = self.root / "hardlink"
        os.link(self.upper, hardlink)
        self.assertEqual(self.upper.stat().st_nlink, 2)
        def lookup(root, name):
            return hardlink if name == derived.README_LOGICAL else original_safe_path(root, name)
        with patch.object(derived, "safe_path", side_effect=lookup):
            self.assertFalse(self.reconcile()["applied"])

    def test_real_symlink_is_not_a_filename_alias(self):
        link = self.root / "symlink"
        link.symlink_to(self.upper)
        def lookup(root, name):
            return link if name == derived.README_LOGICAL else original_safe_path(root, name)
        with patch.object(derived, "safe_path", side_effect=lookup):
            self.assertFalse(self.reconcile()["applied"])

    def test_real_content_mutation_is_rejected_even_with_claimed_hash(self):
        self.upper.write_bytes(self.data + b"changed")
        def lookup(root, name):
            return self.upper if name == derived.README_LOGICAL else original_safe_path(root, name)
        with patch.object(derived, "safe_path", side_effect=lookup):
            self.assertFalse(self.reconcile()["applied"])


class ReadmeAuditAndDerivationTests(DerivedCbindgenTests):
    def test_matched_inventory_with_hardlink_is_rejected_before_copy(self):
        from apply_patch import VerificationError
        original_rglob = Path.rglob
        def linked(path, pattern, *args, **kwargs):
            if path == self.work / "vendor":
                target = path / "plist_ffi-0.1.6/Cargo.lock"
                os.link(target, self.root / "outside-hardlink")
            return original_rglob(path, pattern, *args, **kwargs)
        with patch.object(Path, "rglob", linked):
            with self.assertRaisesRegex(VerificationError, "hardlink"):
                self.prepare()
        self.assertFalse((self.work / "build-vendor").exists())

    def test_post_copy_hardlinks_fail_both_input_audits(self):
        receipt = self.prepare()
        for folder in ("vendor", "build-vendor"):
            os.link(self.work / folder / "plist_ffi-0.1.6/Cargo.lock", self.root / (folder + "-outside-link"))
        self.assertFalse(vendor.audit_vendor_inputs(receipt)["original_inputs_unchanged"])
        self.assertFalse(vendor.audit_vendor_inputs(derived.derived_audit_receipt(receipt))["original_inputs_unchanged"])


for _name in dir(DerivedCbindgenTests):
    if _name.startswith("test_"):
        setattr(ReadmeAuditAndDerivationTests, _name, None)
del DerivedCbindgenTests

if __name__ == "__main__":
    unittest.main()
