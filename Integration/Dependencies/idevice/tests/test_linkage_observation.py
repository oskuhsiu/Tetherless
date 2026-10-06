"""Opaque local archive fixtures and Python-only supervised command doubles."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import linkage_observation as observation
from apply_patch import VerificationError
from test_rust_symbol_reader import ReaderFixture
from test_pairing_apple import AppleFixture
import build_pairing_apple as apple


class LinkageObservationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.rust, self.c = self.root / "rust.a", self.root / "c.a"
        self.rust.write_bytes(b"opaque Rust archive fixture\n")
        self.c.write_bytes(b"opaque C archive fixture\n")
        self.reader = ReaderFixture(self.root).observe()
        self.folder = self.root / "linkage-observation"
        self.log = self.root / "scan.txt"

    def create(self):
        return observation.LinkageObservation(self.folder, target="aarch64-apple-ios", rust_archive=self.rust,
            c_archive=self.c, c_sha256=hashlib.sha256(self.c.read_bytes()).hexdigest(), reader=self.reader)

    def output(self, data=b"controlled output\n", log=None):
        log = log or self.log
        log.write_bytes(data)
        log.with_name(log.name + ".status.json").write_text('{"schema":1,"outcome":"success"}\n')

    def receipt(self, prefix="01-scan"):
        return json.loads((self.folder / (prefix + ".json")).read_bytes())

    def test_two_fixed_member_qualified_visibility_scans_and_exact_archive_copies(self):
        capture = self.create()
        calls = []
        def invoke(command, log):
            calls.append(command)
            self.output(log=log)
        capture.scans(invoke)
        self.assertEqual(calls, [[self.reader["llvm_nm"]["path"], "--defined-only", "--format=darwin",
            "--print-file-name", "--quiet", str(path)] for path in (self.rust, self.c)])
        self.assertNotIn("--extern-only", calls[0])  # locals remain visible in diagnostic output
        self.assertEqual((self.folder / "rust-staticlib.a").read_bytes(), self.rust.read_bytes())
        self.assertEqual((self.folder / "c-staticlib.a").read_bytes(), self.c.read_bytes())
        inputs = json.loads((self.folder / "inputs.json").read_bytes())
        self.assertTrue(inputs["diagnostic_only"])
        self.assertFalse(inputs["ownership_acceptance_changed"])
        for number, role in enumerate(("rust", "c"), 1):
            row = self.receipt(f"{number:02d}-{role}-defined-members")
            self.assertTrue(row["inputs_unchanged"])
            self.assertTrue(row["command_completed"])
            self.assertEqual(row["before"], row["after"])
            self.assertEqual(row["retention_errors"], [])

    def test_source_or_retained_archive_change_before_command_blocks_execution(self):
        for role in ("source", "retained"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmp:
                self.folder = Path(tmp).resolve() / "observation"
                capture = self.create()
                path = self.rust if role == "source" else capture.copies["c"]
                original = path.read_bytes()
                path.write_bytes(b"changed archive\n")
                with self.assertRaisesRegex(VerificationError, "before command"):
                    capture.run(["not-executed"], log=self.log, invoke=lambda: self.fail("must not run"))
                self.assertFalse(self.receipt()["command_completed"])
                self.assertFalse(self.receipt()["inputs_unchanged"])
                path.write_bytes(original)

    def test_source_or_retained_mutation_during_command_fails_after_retaining_hashes(self):
        for role in ("source", "retained"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmp:
                self.folder = Path(tmp).resolve() / "observation"
                capture = self.create()
                path = self.c if role == "source" else capture.copies["rust"]
                original = path.read_bytes()
                def mutate():
                    self.output()
                    path.write_bytes(b"changed archive\n")
                with self.assertRaisesRegex(VerificationError, "archive changed across command"):
                    capture.run(["controlled"], log=self.log, invoke=mutate)
                row = self.receipt()
                self.assertFalse(row["inputs_unchanged"])
                self.assertIn("scan.txt.status.json", row["outputs"])
                path.write_bytes(original)

    def test_primary_command_failure_is_not_replaced_by_retention_failure(self):
        capture = self.create()
        def fail():
            self.output()
            self.rust.unlink()
            raise VerificationError("original controlled command failure")
        with self.assertRaisesRegex(VerificationError, "original controlled command failure"):
            capture.run(["controlled"], log=self.log, invoke=fail)
        row = self.receipt()
        self.assertFalse(row["command_completed"])
        self.assertFalse(row["inputs_unchanged"])
        self.assertTrue(row["retention_errors"])
        self.assertIn("scan.txt.status.json", row["outputs"])

    def test_map_and_status_hashes_survive_later_ownership_rejection(self):
        capture = self.create()
        raw = b"literal string: invalid UTF8 \xc0\x01\x0b\x0d\n"
        map_path = self.root / "mixed.map"
        def link():
            self.output(b"")
            map_path.write_bytes(raw)
        capture.run(["controlled-link"], log=self.log, invoke=link, maps=(map_path,))
        with self.assertRaisesRegex(VerificationError, "unchanged duplicate gate"):
            raise VerificationError("unchanged duplicate gate")
        row = self.receipt()
        self.assertEqual(row["outputs"]["mixed.map"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(row["outputs"]["mixed.map"]["bytes"], len(raw))
        self.assertEqual(row["outputs"]["scan.txt"]["bytes"], 0)
        self.assertEqual(row["outputs"]["scan.txt.status.json"]["sha256"],
                         hashlib.sha256(self.log.with_name("scan.txt.status.json").read_bytes()).hexdigest())

    def test_missing_or_oversized_output_never_becomes_success(self):
        for fault in ("status", "map", "log-limit", "map-limit"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                self.folder = Path(tmp).resolve() / "observation"
                capture = self.create()
                map_path = self.root / "mixed.map"
                def emit():
                    self.output(b"x" * (65 if fault == "log-limit" else 1))
                    if fault == "status":
                        self.log.with_name("scan.txt.status.json").unlink()
                    if fault != "map":
                        map_path.write_bytes(b"x" * (65 if fault == "map-limit" else 1))
                if map_path.exists():
                    map_path.unlink()
                with patch.object(observation, "MAX_LOG_BYTES", 64), self.assertRaises(VerificationError):
                    capture.run(["controlled"], log=self.log, invoke=emit, maps=(map_path,))
                self.assertTrue(self.receipt()["retention_errors"])

    def test_empty_oversized_symlink_and_changed_c_identity_block_archive_capture(self):
        for fault in ("empty", "oversized", "symlink", "wrong-c-hash"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                self.folder = Path(tmp).resolve() / "observation"
                original = self.rust.read_bytes()
                if fault == "empty": self.rust.write_bytes(b"")
                if fault == "oversized": self.rust.write_bytes(b"x" * 65)
                if fault == "symlink":
                    self.rust.unlink()
                    self.rust.symlink_to(self.c)
                with patch.object(observation, "MAX_ARCHIVE_BYTES", 64), self.assertRaises(VerificationError):
                    if fault == "wrong-c-hash":
                        observation.LinkageObservation(self.folder, target="aarch64-apple-ios", rust_archive=self.rust,
                            c_archive=self.c, c_sha256="0" * 64, reader=self.reader)
                    else:
                        self.create()
                if self.rust.is_symlink(): self.rust.unlink()
                self.rust.write_bytes(original)

    def test_operation_count_and_reader_mutation_are_bounded(self):
        capture = self.create()
        capture.operations = observation.MAX_OPERATIONS
        with self.assertRaisesRegex(VerificationError, "unreviewed"):
            capture.run(["controlled"], log=self.log, invoke=lambda: self.fail("must not run"))
        capture.operations = 0
        Path(self.reader["llvm_nm"]["path"]).write_bytes(b"changed reader")
        with self.assertRaisesRegex(ValueError, "changed after observation"):
            capture.run(["controlled"], log=self.log, invoke=lambda: self.fail("must not run"))
        self.assertFalse(self.receipt()["command_completed"])

    def test_zero_byte_log_uses_same_stable_descriptor_hashing(self):
        self.log.write_bytes(b"")
        original = Path.open
        def open_after_mutation(path, *args, **kwargs):
            if path == self.log and args == ("rb",):
                with open(path, "wb") as stream:
                    stream.write(b"changed before descriptor read")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", open_after_mutation), self.assertRaisesRegex(VerificationError, "changed before reading"):
            observation.file_identity(self.log, 1024, allow_empty=True)


class AppleLinkageCaptureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.fixture = AppleFixture(Path(temp.name).resolve() / "fixture")

    def test_success_binds_all_scans_and_links_without_packaging_diagnostic_archives(self):
        fixture = self.fixture
        with fixture.patches():
            result = apple.build(fixture.args)
        for target in apple.TARGETS:
            root = fixture.args.work_dir / target["rust"] / "linkage-observation"
            receipts = [json.loads(path.read_bytes()) for path in sorted(root.glob("[0-9][0-9]-*.json"))]
            self.assertEqual(len(receipts), 12)
            self.assertTrue(all(row["inputs_unchanged"] and row["command_completed"] for row in receipts))
            self.assertEqual(sum("--format=darwin" in row["command"] for row in receipts), 2)
            self.assertEqual(sum("--format=just-symbols" in row["command"] for row in receipts), 2)
            self.assertEqual(sum("-force_load" in row["command"] for row in receipts), 8)
            for row in receipts:
                self.assertEqual(row["before"], row["after"])
                self.assertEqual(row["retention_errors"], [])
        self.assertFalse(any("linkage-observation" in name or "-staticlib.a" in name for name in result["files"]))

    def test_duplicate_owner_rejection_retains_archive_scan_map_and_status_evidence(self):
        fixture = self.fixture
        original = fixture.command
        def capture(argv, *, source, env, log):
            result = original(argv, source=source, env=env, log=log)
            if log.name == "05-link-mixed_provider-c.txt":
                map_path = Path(argv[argv.index("-map") + 2])
                with map_path.open("ab") as stream:
                    stream.write(b"0x00000001 0x00000001 [ 4] _sha512_init\n")
            return result
        with fixture.patches(), patch.object(apple, "capture_helper_command", side_effect=capture):
            with self.assertRaisesRegex(VerificationError, "ambiguous required live map symbol"):
                apple.build(fixture.args)
        target = fixture.args.work_dir / "aarch64-apple-ios"
        root = target / "linkage-observation"
        receipts = [json.loads(path.read_bytes()) for path in root.glob("[0-9][0-9]-*.json")]
        row = next(row for row in receipts if row["log"].endswith("05-link-mixed_provider-c.txt"))
        self.assertEqual(len(receipts), 7)  # four scans, then three links
        self.assertTrue(row["inputs_unchanged"])
        self.assertTrue(row["command_completed"])
        for name in ("05-link-mixed_provider-c.map", "05-link-mixed_provider-c.txt.status.json"):
            raw = (target / "completed" / name).read_bytes()
            self.assertEqual(row["outputs"][name]["sha256"], hashlib.sha256(raw).hexdigest())
        inputs = json.loads((root / "inputs.json").read_bytes())
        for role in ("rust", "c"):
            retained = root / inputs["archives"][role]["retained"]
            self.assertEqual(hashlib.sha256(retained.read_bytes()).hexdigest(), inputs["archives"][role]["sha256"])
            self.assertTrue((root / (role + "-defined-members.txt.status.json")).is_file())
        self.assertFalse(fixture.args.output.exists())
        self.assertFalse((fixture.args.work_dir / "aarch64-apple-ios-sim").exists())

    def test_failed_diagnostic_scan_preserves_primary_failure_and_blocks_acceptance_scans(self):
        fixture = self.fixture
        fixture.fail = ("aarch64-apple-ios", "rust-defined-members.txt")
        with fixture.patches(), self.assertRaisesRegex(VerificationError, "helper command failed"):
            apple.build(fixture.args)
        root = fixture.args.work_dir / "aarch64-apple-ios/linkage-observation"
        row = json.loads((root / "01-rust-defined-members.json").read_bytes())
        self.assertFalse(row["command_completed"])
        self.assertTrue(row["inputs_unchanged"])
        status = json.loads((root / "rust-defined-members.txt.status.json").read_bytes())
        self.assertEqual(status["outcome"], "nonzero_exit")
        self.assertFalse(any(call["log"].name.startswith(("04-rust-export", "04-c-export", "05-link")) for call in fixture.calls))
        self.assertFalse(fixture.args.output.exists())


if __name__ == "__main__":
    unittest.main()
