"""Controlled header fixtures; native generated-header import is a separate gate."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pairing_result_header as headers
from apply_patch import VerificationError, sha256


def generated_fixture(other=b"void unrelated(uint32_t value);\n"):
    old = b"#include <stdint.h>\n\n"
    for name, values in headers.RESULTS.items():
        if name == "TetherlessPairingValidationResult":
            old += ("/**\n * " + headers.VALIDATION_DOC + "\n */\n").encode()
        old += ("enum " + name + " {\n" + "\n".join(
            f"  {name.removesuffix('Result')}{label} = {value}," for label, value in values)
            + "\n};\ntypedef uint32_t " + name + ";\n\n").encode()
    return old + other, b"#include <stdint.h>\n\n" + headers.declarations() + b"\n" + other


def write_generated_fixture(source, other=b"void unrelated(uint32_t value);\n"):
    baseline, scoped = generated_fixture(other)
    plist = source / "ffi/plist.h"
    if not plist.exists():
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_bytes(b"// controlled original plist header\n")
    final = scoped + b"\n\n\n" + plist.read_bytes()
    for name, data in zip(headers.GENERATED, [baseline, scoped, final, final]):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


class ResultHeaderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="Pairing header fixture ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fragment = ROOT / "overlay/ffi/pairing_result_abi.h"

    def test_exact_scalar_fragment_and_both_generated_replacements(self):
        self.assertEqual(self.fragment.read_bytes(), headers.declarations())
        baseline, scoped = generated_fixture()
        receipt = headers.compare_generated(baseline, scoped, self.fragment.read_bytes())
        self.assertTrue(receipt["unrelated_nonempty_lines_identical"])
        self.assertFalse(receipt["native_import_or_link_established_by_this_check"])

    def test_old_collision_is_rejected_for_either_type(self):
        baseline, scoped = generated_fixture()
        for name in headers.RESULTS:
            with self.subTest(name=name), self.assertRaises(VerificationError):
                headers.compare_generated(baseline, scoped + ("\nenum " + name + " {};\n").encode(), headers.declarations())

    def test_every_baseline_discriminant_is_checked(self):
        baseline, scoped = generated_fixture()
        for name, values in headers.RESULTS.items():
            for label, value in values:
                old = f"{name.removesuffix('Result')}{label} = {value},".encode()
                with self.subTest(name=name, label=label), self.assertRaises(VerificationError):
                    headers.compare_generated(baseline.replace(old, old.replace(str(value).encode(), b"99")), scoped, headers.declarations())

    def test_width_signedness_missing_duplicate_and_unknown_declarations_rejected(self):
        baseline, scoped = generated_fixture()
        cases = [baseline.replace(b"typedef uint32_t", b"typedef int32_t", 1),
                 baseline.replace(b"typedef uint32_t", b"typedef uint64_t", 1),
                 baseline.replace(b"enum TetherlessPairingHostResult", b"enum UnknownResult"),
                 baseline + baseline, baseline.replace(b" = 8,", b" = 9,", 1)]
        for changed in cases:
            with self.subTest(changed=sha256(changed)), self.assertRaises(VerificationError):
                headers.compare_generated(changed, scoped, headers.declarations())

    def test_unrelated_declaration_include_comment_and_indentation_changes_rejected(self):
        baseline, scoped = generated_fixture(b"// unrelated docs\n  void unrelated(uint32_t value);\n")
        for old, new in [(b"uint32_t value", b"uint64_t value"), (b"// unrelated docs", b"// edited docs"),
                         (b"  void unrelated", b" void unrelated"), (b"#include <stdint.h>", b"#include <other.h>")]:
            with self.subTest(old=old), self.assertRaises(VerificationError):
                headers.compare_generated(baseline, scoped.replace(old, new, 1), headers.declarations())

    def test_injected_block_changes_and_duplicates_rejected(self):
        baseline, scoped = generated_fixture()
        fragment = headers.declarations()
        for changed in [fragment.replace(b"uint32_t", b"int32_t"), fragment.replace(b")8)", b")9)"), fragment + fragment]:
            with self.subTest(changed=sha256(changed)), self.assertRaises(VerificationError):
                headers.compare_generated(baseline, scoped, changed)
        with self.assertRaises(VerificationError):
            headers.compare_generated(baseline, scoped + fragment, fragment)

    def test_final_plist_append_and_cpp_copy_are_exact(self):
        write_generated_fixture(self.root)
        receipt = headers.verify_headers(self.root, self.fragment)
        self.assertTrue(receipt["cpp_header_identical"])
        for name in ["ffi/idevice.h", "cpp/include/idevice.h"]:
            before = (self.root / name).read_bytes()
            (self.root / name).write_bytes(before + b"// mutation\n")
            with self.subTest(name=name), self.assertRaises(VerificationError):
                headers.verify_headers(self.root, self.fragment)
            (self.root / name).write_bytes(before)

    def test_validation_doc_change_is_rejected(self):
        baseline, scoped = generated_fixture()
        with self.assertRaises(VerificationError):
            headers.compare_generated(baseline.replace(headers.VALIDATION_DOC.encode(), b"Changed docs"), scoped, headers.declarations())

    def test_header_bytes_retained_even_when_comparison_fails(self):
        write_generated_fixture(self.root / "source")
        source = self.root / "source"
        (source / "ffi/idevice.h").write_bytes(b"broken final header")
        evidence = self.root / "completed"
        evidence.mkdir()
        receipt = headers.retain_headers(source, evidence)
        with self.assertRaises(VerificationError):
            headers.verify_headers(source, self.fragment)
        self.assertEqual(len(receipt["files"]), 4)
        for name, row in receipt["files"].items():
            self.assertEqual(row["status"], "retained")
            self.assertEqual((evidence / "generated-headers" / name).read_bytes(), (source / name).read_bytes())

    def test_missing_symlink_and_oversized_headers_are_retained_as_explicit_failures(self):
        source, evidence = self.root / "source", self.root / "completed"
        (source / "ffi").mkdir(parents=True)
        evidence.mkdir()
        outside = self.root / "outside.h"
        outside.write_bytes(b"opaque")
        (source / headers.GENERATED[0]).symlink_to(outside)
        (source / headers.GENERATED[1]).write_bytes(b"x" * 101)
        with patch.object(headers, "MAX_HEADER_BYTES", 100):
            receipt = headers.retain_headers(source, evidence)
            with self.assertRaises(VerificationError):
                headers.verify_headers(source, self.fragment)
        self.assertEqual(receipt["files"][headers.GENERATED[0]]["status"], "unreadable_or_outside_bound")
        self.assertEqual(receipt["files"][headers.GENERATED[1]]["status"], "unreadable_or_outside_bound")
        self.assertEqual(receipt["files"][headers.GENERATED[2]]["status"], "missing")

    def test_overlay_uses_supported_scoped_generator_and_preserves_original_append(self):
        original = (ROOT / "upstream/ffi/build.rs").read_text()
        overlay = (ROOT / "overlay/ffi/build.rs").read_text()
        marker = "    // Check if plist.h exists locally first, otherwise download"
        self.assertEqual(overlay[overlay.index(marker):], original[original.index(marker):])
        self.assertIn('builder.clone().generate()', overlay)
        self.assertIn('.with_after_include(include_str!("pairing_result_abi.h"))', overlay)
        for name in headers.RESULTS:
            self.assertEqual(overlay.count('.exclude_item("' + name + '")'), 1)
        self.assertNotIn('Style::', overlay)


class ResultHeaderRunnerTests(unittest.TestCase):
    def test_retention_root_symlink_cannot_write_outside_evidence_and_audits_survive(self):
        from test_pairing_apple import AppleFixture, AUDITS, apple
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = AppleFixture(root / "fixture")
            outside = root / "outside"
            outside.mkdir()
            marker = outside / "unchanged.txt"
            marker.write_bytes(b"controlled outside bytes")
            fixture.mutate_on = ("aarch64-apple-ios", "04-native-static-libs.txt")
            fixture.mutate = lambda f: (f.args.work_dir / "aarch64-apple-ios/completed/generated-headers").symlink_to(outside, target_is_directory=True)
            with fixture.patches(), self.assertRaisesRegex(VerificationError, "destination is a symlink"):
                apple.build(fixture.args)
            self.assertEqual(list(outside.iterdir()), [marker])
            self.assertEqual(marker.read_bytes(), b"controlled outside bytes")
            for name in AUDITS:
                self.assertTrue((fixture.args.work_dir / "aarch64-apple-ios/completed" / name).is_file())
            self.assertFalse(fixture.args.output.exists())

    def test_retention_receipt_symlink_cannot_overwrite_outside_file_and_audits_survive(self):
        from test_pairing_apple import AppleFixture, AUDITS, apple
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = AppleFixture(root / "fixture")
            outside = root / "outside.json"
            outside.write_bytes(b"controlled original receipt bytes")
            fixture.mutate_on = ("aarch64-apple-ios", "04-native-static-libs.txt")
            fixture.mutate = lambda f: (f.args.work_dir / "aarch64-apple-ios/completed/generated-header-retention.json").symlink_to(outside)
            with fixture.patches(), self.assertRaisesRegex(VerificationError, "destination is a symlink"):
                apple.build(fixture.args)
            self.assertEqual(outside.read_bytes(), b"controlled original receipt bytes")
            for name in AUDITS:
                self.assertTrue((fixture.args.work_dir / "aarch64-apple-ios/completed" / name).is_file())
            self.assertFalse(fixture.args.output.exists())

    def test_retention_directory_or_receipt_write_error_still_runs_all_input_audits(self):
        from test_pairing_apple import AppleFixture, AUDITS, apple
        for obstruction in ("directory", "receipt"):
            with self.subTest(obstruction=obstruction), tempfile.TemporaryDirectory() as tmp:
                fixture = AppleFixture(Path(tmp) / "fixture")
                fixture.mutate_on = ("aarch64-apple-ios", "04-native-static-libs.txt")
                def mutate(f):
                    evidence = f.args.work_dir / "aarch64-apple-ios/completed"
                    if obstruction == "directory":
                        (evidence / "generated-headers").write_bytes(b"controlled path obstruction")
                    else:
                        (evidence / "generated-header-retention.json").mkdir()
                fixture.mutate = mutate
                with fixture.patches(), self.assertRaises(OSError):
                    apple.build(fixture.args)
                for name in AUDITS:
                    self.assertTrue((fixture.args.work_dir / "aarch64-apple-ios/completed" / name).is_file())
                self.assertFalse(fixture.args.output.exists())

    def test_failed_individual_header_copy_prevents_publication_and_keeps_audits(self):
        from test_pairing_apple import AppleFixture, AUDITS, apple
        with tempfile.TemporaryDirectory() as tmp:
            fixture = AppleFixture(Path(tmp) / "fixture")
            fixture.mutate_on = ("aarch64-apple-ios", "04-native-static-libs.txt")
            fixture.mutate = lambda f: (f.args.work_dir / "aarch64-apple-ios/completed/generated-headers/ffi/idevice.cbindgen-baseline.h").mkdir(parents=True)
            with fixture.patches(), self.assertRaisesRegex(VerificationError, "evidence was not retained"):
                apple.build(fixture.args)
            evidence = fixture.args.work_dir / "aarch64-apple-ios/completed"
            receipt = json.loads((evidence / "generated-header-retention.json").read_bytes())
            self.assertEqual(receipt["files"][headers.GENERATED[0]]["status"], "unreadable_or_outside_bound")
            for name in AUDITS:
                self.assertTrue((evidence / name).is_file())
            self.assertFalse(fixture.args.output.exists())

    def test_secondary_retention_error_preserves_native_failure_and_all_audits(self):
        from test_pairing_apple import AppleFixture, AUDITS, apple
        with tempfile.TemporaryDirectory() as tmp:
            fixture = AppleFixture(Path(tmp) / "fixture")
            fixture.fail = ("aarch64-apple-ios", "04-native-static-libs.txt")
            fixture.mutate = lambda f: (f.args.work_dir / "aarch64-apple-ios/completed/generated-headers").write_bytes(b"controlled obstruction")
            with fixture.patches(), self.assertRaises(VerificationError):
                apple.build(fixture.args)
            evidence = fixture.args.work_dir / "aarch64-apple-ios/completed"
            status = json.loads((evidence / "04-native-static-libs.txt.status.json").read_bytes())
            self.assertEqual(status["outcome"], "nonzero_exit")
            for name in AUDITS:
                self.assertTrue((evidence / name).is_file())
            self.assertFalse(fixture.args.output.exists())

    def test_real_supervisor_failure_retains_all_headers_and_four_audits(self):
        from test_pairing_apple import AppleFixture, AUDITS, apple
        with tempfile.TemporaryDirectory(prefix="Result import failure fixture ") as tmp:
            fixture = AppleFixture(Path(tmp) / "fixture")
            fixture.fail = ("aarch64-apple-ios", "05-link-host-swift.txt")
            with fixture.patches(), self.assertRaises(VerificationError):
                apple.build(fixture.args)
            evidence = fixture.args.work_dir / "aarch64-apple-ios/completed"
            receipt = json.loads((evidence / "generated-header-retention.json").read_bytes())
            self.assertTrue(all(row["status"] == "retained" for row in receipt["files"].values()))
            self.assertTrue((evidence / "pairing-result-header-check.json").is_file())
            for name in AUDITS:
                self.assertTrue((evidence / name).is_file())
            self.assertFalse(fixture.args.output.exists())

    def test_header_contract_failure_blocks_all_links_with_evidence_and_audits(self):
        from test_pairing_apple import AppleFixture, AUDITS, apple
        with tempfile.TemporaryDirectory(prefix="Result contract failure fixture ") as tmp:
            fixture = AppleFixture(Path(tmp) / "fixture")
            fixture.mutate_on = ("aarch64-apple-ios", "04-native-static-libs.txt")
            def mutate(f):
                p = f.args.work_dir / "aarch64-apple-ios/source/ffi/idevice.cbindgen-baseline.h"
                p.write_bytes(p.read_bytes().replace(b"TetherlessPairingHostOk = 0", b"TetherlessPairingHostOk = 99"))
            fixture.mutate = mutate
            with fixture.patches(), self.assertRaisesRegex(VerificationError, "discriminants"):
                apple.build(fixture.args)
            evidence = fixture.args.work_dir / "aarch64-apple-ios/completed"
            self.assertIn(b"HostOk = 99", (evidence / "generated-headers/ffi/idevice.cbindgen-baseline.h").read_bytes())
            for name in AUDITS:
                self.assertTrue((evidence / name).is_file())
            self.assertFalse(any(call["log"].name.startswith("05-link") for call in fixture.calls))
            self.assertFalse(fixture.args.output.exists())

    def test_success_packages_exact_headers_and_new_scalar_probes(self):
        from test_pairing_apple import AppleFixture, apple
        import zipfile
        with tempfile.TemporaryDirectory(prefix="Result header success fixture ") as tmp:
            fixture = AppleFixture(Path(tmp) / "fixture")
            with fixture.patches():
                result = apple.build(fixture.args)
            for row in result["targets"]:
                evidence = fixture.args.output / "provenance" / row["target"]["rust"]
                for name in headers.GENERATED:
                    self.assertEqual((evidence / "generated-headers" / name).read_bytes(), (Path(row["source"]) / name).read_bytes())
                self.assertEqual({p["language"] for p in row["link_probes"] if p["group"] == "result_constants"}, {"c", "swift"})
                self.assertTrue(row["result_header_contract"]["unrelated_nonempty_lines_identical"])
            with zipfile.ZipFile(fixture.args.output / "corresponding-source.zip") as archive:
                self.assertEqual(archive.read("recipe/overlay/ffi/pairing_result_abi.h"), headers.declarations())
                self.assertIn("workspace/ffi/idevice.h", archive.namelist())


if __name__ == "__main__":
    unittest.main()
