"""Synthetic bounded archive and orchestration checks, never native execution."""
from pathlib import Path
import json
import plistlib
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mixed_provider as mixed
from apply_patch import VerificationError, sha256


class MixedProviderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.archive, self.output = self.root / "input.zip", self.root / "output"
        self.target = {"rust": "aarch64-apple-ios", "sdk": "iphoneos"}
        self.rows = []
        self.files = {}
        for identifier, variant in (("ios-arm64", ""), ("ios-arm64_x86_64-simulator", "simulator")):
            row = {"LibraryIdentifier": identifier, "LibraryPath": "libimobiledevice.a", "HeadersPath": "Headers",
                   "SupportedPlatform": "ios", "SupportedArchitectures": ["arm64"]}
            if variant:
                row["SupportedPlatformVariant"] = variant
                row["SupportedArchitectures"].append("x86_64")
            self.rows.append(row)
            prefix = "libimobiledevice.xcframework/" + identifier + "/"
            self.files[prefix + "libimobiledevice.a"] = b"opaque synthetic archive " + identifier.encode()
            self.files[prefix + "Headers/plist/plist.h"] = b"/* opaque header fixture */"
            self.files[prefix + "Headers/libimobiledevice/module.modulemap"] = b"opaque map fixture"
        self.files["libimobiledevice.xcframework/Info.plist"] = plistlib.dumps({"AvailableLibraries": self.rows})
        self.write_zip()
        self.pin = patch.object(mixed, "ARCHIVE_SHA256", sha256(self.archive.read_bytes()))
        self.pin.start()
        self.addCleanup(self.pin.stop)

    def write_zip(self, extra=None):
        with zipfile.ZipFile(self.archive, "w") as archive:
            for name, data in self.files.items():
                archive.writestr(name, data)
            if extra:
                archive.writestr(*extra)

    def test_exact_opaque_archive_both_slices_are_verified_without_execution(self):
        receipt = mixed.prepare(self.archive, self.output)
        self.assertFalse(receipt["binaries_executed"])
        for sdk, target in (("iphoneos", "aarch64-apple-ios"), ("iphonesimulator", "aarch64-apple-ios-sim")):
            row = mixed.verify(self.output, {"sdk": sdk, "rust": target})
            self.assertEqual(row["target"], target)
            self.assertFalse(row["binary_format_inspected"])

    def test_wrong_original_archive_is_rejected_before_output(self):
        self.archive.write_bytes(b"different bytes")
        with self.assertRaises(VerificationError):
            mixed.prepare(self.archive, self.output)
        self.assertFalse(self.output.exists())

    def test_existing_output_and_symlink_are_not_overwritten(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.output.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(VerificationError):
            mixed.prepare(self.archive, self.output)
        self.assertEqual(list(outside.iterdir()), [])

    def test_unsafe_archive_entry_rejected_before_output_even_when_hash_matches(self):
        for name in ("../escape", "/absolute", "libimobiledevice.xcframework/../escape", "other/root"):
            with self.subTest(name=name):
                self.write_zip((name, b"bad path"))
                with patch.object(mixed, "ARCHIVE_SHA256", sha256(self.archive.read_bytes())):
                    with self.assertRaises(VerificationError):
                        mixed.prepare(self.archive, self.output)
                self.assertFalse(self.output.exists())

    def test_receipt_cannot_relabel_modified_provider_bytes(self):
        mixed.prepare(self.archive, self.output)
        name = next(n for n in self.files if n.endswith(".a"))
        (self.output / name).write_bytes(b"changed")
        receipt = self.output / "mixed-provider-inputs.json"
        value = json.loads(receipt.read_bytes())
        value["files"][name] = sha256(b"changed")
        receipt.write_text(json.dumps(value))
        with self.assertRaisesRegex(VerificationError, "authenticated archive"):
            mixed.verify(self.output, self.target)

    def test_missing_extra_symlink_or_changed_archive_is_rejected(self):
        mixed.prepare(self.archive, self.output)
        extra = self.output / "unregistered.h"
        extra.write_bytes(b"extra include")
        with self.assertRaises(VerificationError): mixed.verify(self.output, self.target)
        extra.unlink()
        extra.symlink_to(self.archive)
        with self.assertRaises(VerificationError): mixed.verify(self.output, self.target)
        extra.unlink()
        (self.output / "authenticated-provider.zip").write_bytes(b"changed")
        with self.assertRaises(VerificationError): mixed.verify(self.output, self.target)

    def test_budget_is_checked_before_extracting(self):
        with patch.object(mixed, "MAX_FILES", 1):
            with self.assertRaises(VerificationError): mixed.prepare(self.archive, self.output)
        self.assertFalse(self.output.exists())

    def test_malformed_receipt_is_a_retained_failed_audit(self):
        mixed.prepare(self.archive, self.output)
        for value in ([], None, 0, "not an object", {}):
            (self.output / "mixed-provider-inputs.json").write_text(json.dumps(value))
            with self.subTest(value=value):
                result = mixed.audit(self.output, self.target, {})
                self.assertFalse(result["original_inputs_unchanged"])
                self.assertEqual(result["error_kind"], "VerificationError")

    def test_audit_reports_failure_without_replacing_primary_exception(self):
        for failure in (VerificationError("changed"), OSError("missing")):
            def failed(root, target): raise failure
            self.assertEqual(mixed.audit(self.output, self.target, {}, verifier=failed),
                {"original_inputs_unchanged": False, "error_kind": type(failure).__name__})

    def test_c_provider_symbols_must_be_present_and_disjoint(self):
        c = "\n".join("_" + n for n in ("plist_new_dict", "plist_free", "plist_array_set_item",
            "afc_client_free", "lockdownd_client_free", "idevice_free"))
        result = mixed.check_mixed_symbols("_tetherless_native_plist_free\n", c)
        self.assertTrue(result["provider_export_sets_disjoint"])
        for rust, other in (("_plist_free\n", c), ("_tetherless_native_plist_free\n", c.replace("_idevice_free", ""))):
            with self.assertRaises(VerificationError): mixed.check_mixed_symbols(rust, other)


class MixedProviderAuditRunnerTests(unittest.TestCase):
    def test_failed_link_and_unreadable_provider_preserve_link_failure_and_failed_audit(self):
        from test_pairing_apple import AppleFixture
        import build_pairing_apple as apple
        with tempfile.TemporaryDirectory() as temporary:
            fixture = AppleFixture(Path(temporary) / "fixture")
            fixture.fail = ("aarch64-apple-ios", "05-link-host-c.txt")
            fixture.mutate = lambda f: (f.args.mixed_provider / "authenticated-provider.zip").unlink()
            with fixture.patches(), self.assertRaises(Exception) as raised:
                apple.build(fixture.args)
            self.assertNotIsInstance(raised.exception, FileNotFoundError)
            audit = json.loads((fixture.args.work_dir / "aarch64-apple-ios/completed/mixed-provider-input-audit.json").read_bytes())
            self.assertFalse(audit["original_inputs_unchanged"])
            self.assertEqual(audit["error_kind"], "FileNotFoundError")
            self.assertFalse(fixture.args.output.exists())


if __name__ == "__main__":
    unittest.main()
