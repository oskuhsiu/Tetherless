"""Exact packaged-config rule fixtures. No Cargo, registry fetch or native work."""
from copy import deepcopy
from contextlib import nullcontext
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import offline_vendor as vendor
from apply_patch import VerificationError


class ExactPackagedCargoConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="packaged-config-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / "dialoguer-0.12.0"
        self.config = self.directory / ".cargo/config.toml"
        self.config.parent.mkdir(parents=True)
        self.bytes = (ROOT / "upstream/packaged-config/dialoguer-0.12.0/config.toml").read_bytes()
        self.config.write_bytes(self.bytes)
        self.rule = deepcopy(vendor.PACKAGED_CONFIG_RULE)
        self.package = {key: self.rule[key] for key in ("name", "version", "source")}
        self.package["checksum"] = self.rule["archive_sha256"]
        self.checksums = {"package": self.package["checksum"], "files": {".cargo/config.toml": self.rule["file_sha256"]}}

    def check(self):
        return vendor.check_packaged_cargo_config(self.directory, self.package, self.checksums)

    def test_exact_candidate_and_production_rule_identities(self):
        self.assertEqual(len(self.bytes), 198)
        self.assertEqual(hashlib.sha256(self.bytes).hexdigest(), self.rule["file_sha256"])
        self.assertEqual(self.rule["archive_sha256"], "25f104b501bf2364e78d0d3974cbc774f738f5865306ed128e1e0d7499c0ad96")
        self.assertEqual(tomllib.loads(self.bytes.decode()), {"alias": {
            "format": "fmt", "format-check": "fmt --check",
            "lint": "clippy --all-targets --all-features -- -D warnings",
            "test-cover": "llvm-cov --all-features --lcov --output-path lcov.info"}})
        result = self.check()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["archive_sha256"], self.rule["archive_sha256"])
        self.assertEqual(result[0]["file_sha256"], self.rule["file_sha256"])
        self.assertEqual(self.config.read_bytes(), self.bytes)

    def test_other_package_version_source_or_checksum_is_rejected(self):
        for key, value in (("name", "other"), ("version", "0.12.1"), ("source", "registry+https://other.invalid"), ("checksum", "0" * 64)):
            with self.subTest(key=key), patch.dict(self.package, {key: value}):
                with self.assertRaises(VerificationError):
                    self.check()

    def test_other_directory_is_rejected_even_with_matching_metadata(self):
        renamed = self.directory.with_name("other-0.12.0")
        self.directory.rename(renamed)
        self.directory = renamed
        with self.assertRaises(VerificationError):
            self.check()

    def test_legacy_config_path_is_rejected_even_for_identical_bytes(self):
        self.config.rename(self.config.with_name("config"))
        with self.assertRaises(VerificationError):
            self.check()

    def test_legacy_config_alongside_approved_config_is_rejected(self):
        self.config.with_name("config").write_bytes(self.bytes)
        with self.assertRaises(VerificationError):
            self.check()

    def test_changed_alias_or_added_configuration_is_rejected(self):
        for data in (self.bytes.replace(b'"fmt"', b'"metadata"'), self.bytes + b"\n[net]\noffline=false\n", self.bytes + b"\n"):
            with self.subTest(data=data):
                self.config.write_bytes(data)
                with self.assertRaises(VerificationError):
                    self.check()

    def test_checksum_metadata_mismatch_is_rejected(self):
        for checksums in ({"package": "0" * 64, "files": self.checksums["files"]},
                          {"package": self.package["checksum"], "files": {}},
                          {"package": self.package["checksum"], "files": {".cargo/config.toml": "0" * 64}}):
            self.checksums = checksums
            with self.assertRaises(VerificationError):
                self.check()

    def test_config_symlink_is_rejected_even_with_identical_target_bytes(self):
        target = self.root / "same-config"
        target.write_bytes(self.bytes)
        self.config.unlink()
        self.config.symlink_to(target)
        with self.assertRaises(VerificationError):
            self.check()

    def test_cargo_directory_symlink_is_rejected(self):
        target = self.directory / "moved-cargo"
        self.config.parent.rename(target)
        self.config.parent.symlink_to(target)
        with self.assertRaises(VerificationError):
            self.check()

    def test_nonregular_config_is_rejected(self):
        self.config.unlink()
        self.config.mkdir()
        with self.assertRaises(VerificationError):
            self.check()

    def test_ancestor_config_is_rejected(self):
        ambient = self.root / ".cargo/config.toml"
        ambient.parent.mkdir()
        ambient.write_bytes(self.bytes)
        with self.assertRaises(VerificationError):
            self.check()

    def make_archive(self):
        work = self.root / "work"
        source = work / "source"
        source.mkdir(parents=True)
        (work / "cargo-home").mkdir()
        cache = self.root / "cache"
        cache.mkdir()
        archive = cache / "dialoguer-0.12.0.crate"
        files = {"Cargo.toml": b'[package]\nname="dialoguer"\nversion="0.12.0"\nbuild=false\n',
                 "src/lib.rs": b"// controlled fixture, not registry source\n", ".cargo/config.toml": self.bytes}
        with tarfile.open(archive, "w:gz") as tf:
            for name, data in files.items():
                entry = tarfile.TarInfo("dialoguer-0.12.0/" + name)
                entry.size = len(data)
                tf.addfile(entry, io.BytesIO(data))
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        (source / "Cargo.lock").write_text('version=4\n[[package]]\nname="dialoguer"\nversion="0.12.0"\n'
            'source="registry+https://github.com/rust-lang/crates.io-index"\nchecksum="' + digest + '"\n')
        return {"source": source, "work": work, "cache": cache,
                "env": {"CARGO_HOME": str(work / "cargo-home"), "CARGO_NET_OFFLINE": "true"}}, digest, files

    def test_production_rule_rejects_synthetic_archive_with_identical_config(self):
        kwargs, digest, _files = self.make_archive()
        self.assertNotEqual(digest, self.rule["archive_sha256"])
        with self.assertRaises(VerificationError):
            vendor.prepare_offline_vendor(**kwargs)
        self.assertFalse((kwargs["work"] / "cargo-home/config.toml").exists())
        inventory = json.loads((kwargs["work"] / "vendor-config-inventory.json").read_bytes())
        self.assertTrue(inventory["blocked"])
        self.assertTrue(inventory["all_packages_examined"])
        self.assertEqual(inventory["configs"][0]["status"], "unreviewed")

    def test_controlled_archive_wiring_retains_config_and_audits_mutation(self):
        kwargs, digest, files = self.make_archive()
        # Only this fixture swaps the expected archive digest. It does not claim
        # the real registry archive has been observed or authenticated locally.
        fixture_rule = dict(self.rule, archive_sha256=digest)
        with patch.object(vendor, "PACKAGED_CONFIG_RULE", fixture_rule):
            receipt = vendor.prepare_offline_vendor(**kwargs)
        folder = kwargs["work"] / "vendor/dialoguer-0.12.0"
        for name, data in files.items():
            self.assertEqual((folder / name).read_bytes(), data)
        self.assertEqual(receipt["reviewed_packaged_configs"][0]["archive_sha256"], digest)
        self.assertTrue(vendor.audit_vendor_inputs(receipt)["original_inputs_unchanged"])
        config = folder / ".cargo/config.toml"
        config.write_bytes(self.bytes + b"\n[net]\noffline=false\n")
        audit = vendor.audit_vendor_inputs(receipt)
        self.assertFalse(audit["original_inputs_unchanged"])
        self.assertIn("dialoguer-0.12.0/.cargo/config.toml", audit["changed_authenticated_inputs"])

    def test_no_config_remains_accepted_for_other_packages(self):
        self.config.unlink()
        self.package["name"] = "other"
        self.assertEqual(self.check(), [])


class PackagedCargoConfigInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="config-inventory-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.records = []
        self.output = self.root / "inventory.json"

    def add(self, name, data, relative=".cargo/config.toml"):
        package = {"name": name, "version": "0.12.0", "source": "registry+https://github.com/rust-lang/crates.io-index",
                   "checksum": vendor.PACKAGED_CONFIG_RULE["archive_sha256"]}
        path = self.root / (name + "-0.12.0") / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.records.append((package, {"package": package["checksum"], "files": {relative: hashlib.sha256(data).hexdigest()}}))
        return path

    def inventory(self):
        return vendor.inventory_packaged_configs(self.root, self.records, self.output)

    def test_all_configs_reported_after_unknown_without_retaining_values(self):
        self.add("first", b'[env]\nPRIVATE_MARKER="must-not-appear-in-evidence"\n')
        self.add("dialoguer", (ROOT / "upstream/packaged-config/dialoguer-0.12.0/config.toml").read_bytes())
        self.add("last", b'[net]\noffline=false\n')
        result = self.inventory()
        self.assertEqual(len(result["configs"]), 3)
        self.assertTrue(result["all_packages_examined"])
        self.assertTrue(result["blocked"])
        self.assertEqual(result["configs"][1]["status"], "reviewed_exact_match")
        self.assertEqual(result["configs"][0]["setting_names"], [["env"], ["env", "PRIVATE_MARKER"]])
        text = self.output.read_text()
        self.assertNotIn("must-not-appear-in-evidence", text)
        self.assertNotIn("clippy --all-targets", text)
        self.assertNotIn("llvm-cov", text)

    def test_invalid_toml_retains_fixed_error_and_continues(self):
        self.add("first", b'password="secret-value-with-broken-quote\n')
        self.add("second", b'[net]\noffline=true\n')
        result = self.inventory()
        self.assertEqual(len(result["configs"]), 2)
        self.assertTrue(result["blocked"])
        self.assertEqual(result["configs"][0]["setting_names"], [])
        self.assertNotIn("secret-value", self.output.read_text())

    def test_file_and_total_byte_budgets_fail_closed_with_later_metadata(self):
        self.add("large", b"#" * 65)
        self.add("first", b"#" * 40)
        self.add("later", b"#" * 40)
        with patch.object(vendor, "MAX_CONFIG_FILE_BYTES", 64), patch.object(vendor, "MAX_CONFIG_TOTAL_BYTES", 64):
            result = self.inventory()
        self.assertEqual([row["status"] for row in result["configs"]],
                         ["file_byte_budget_exceeded", "unreviewed", "total_byte_budget_exceeded"])
        self.assertTrue(result["blocked"])
        self.assertTrue(result["all_packages_examined"])
        self.assertTrue(all(row["file_sha256"] for row in result["configs"]))

    def test_key_length_depth_and_count_budgets_fail_closed(self):
        for label, data, limits in (
            ("length", b"a" * 129 + b'=1\n', {}),
            ("depth", ('[' + '.'.join('a' for _ in range(17)) + ']\nx=1\n').encode(), {}),
            ("count", b'a=1\nb=2\n', {"MAX_CONFIG_KEYS": 1}),
            ("total-key-bytes", b'longname=1\n', {"MAX_CONFIG_KEY_TOTAL_BYTES": 2}),
        ):
            with self.subTest(label=label):
                self.records = []
                self.output.unlink(missing_ok=True)
                self.add(label, data)
                with patch.multiple(vendor, **limits) if limits else nullcontext():
                    result = self.inventory()
                self.assertTrue(result["blocked"])
                self.assertEqual(result["configs"][0]["status"], "invalid_or_over_budget_setting_names")
                self.assertEqual(result["configs"][0]["setting_names"], [])

    def test_count_budget_is_bounded_and_incompleteness_explicit(self):
        for name in ("one", "two", "three"):
            self.add(name, b'[net]\noffline=true\n')
        with patch.object(vendor, "MAX_CONFIG_FILES", 2):
            result = self.inventory()
        self.assertTrue(result["blocked"])
        self.assertFalse(result["all_packages_examined"])
        self.assertTrue(result["config_count_budget_exceeded"])
        self.assertEqual(len(result["configs"]), 2)

    def test_symlink_and_legacy_config_are_reported_without_following(self):
        path = self.add("symlink", b'never="retained"\n')
        path.unlink()
        path.symlink_to(self.root / "absent")
        self.add("legacy", b'[net]\noffline=true\n', ".cargo/config")
        result = self.inventory()
        self.assertEqual(result["configs"][0]["status"], "unsafe_nonregular_path")
        self.assertEqual(result["configs"][1]["path"], ".cargo/config")
        self.assertTrue(result["blocked"])

    def test_inventory_destination_never_overwritten(self):
        self.output.write_text("existing evidence")
        with self.assertRaises(FileExistsError):
            self.inventory()
        self.assertEqual(self.output.read_text(), "existing evidence")

    def test_inventory_byte_budget_retains_bounded_failure_receipt(self):
        self.add("one", b'[net]\noffline=true\n')
        with patch.object(vendor, "MAX_CONFIG_INVENTORY_BYTES", 256):
            result = self.inventory()
        self.assertTrue(result["blocked"])
        self.assertEqual(result["error"], "inventory_byte_budget_exceeded")
        self.assertLessEqual(self.output.stat().st_size, 256)


if __name__ == "__main__":
    unittest.main()
