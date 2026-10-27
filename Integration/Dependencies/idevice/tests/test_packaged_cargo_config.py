"""Cargo discovery-scope inventory fixtures; no Cargo or network execution."""
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import offline_vendor as vendor


class PackagedCargoConfigInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="config-inventory-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.vendor = self.root / "vendor"
        self.vendor.mkdir()
        self.source = self.root / "source"
        self.source.mkdir()
        self.records = []
        self.output = self.root / "inventory.json"

    def add(self, name, data, relative=".cargo/config.toml", version="0.12.0", archive="0" * 64):
        package = {"name": name, "version": version, "source": "registry+https://github.com/rust-lang/crates.io-index",
                   "checksum": archive}
        path = self.vendor / (name + "-" + version) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.records.append((package, {"package": archive, "files": {relative: hashlib.sha256(data).hexdigest()}}))
        return path

    def inventory(self):
        return vendor.inventory_packaged_configs(self.vendor, self.records, self.output, [self.source])

    def test_all_four_observed_configs_are_byte_preserved_and_inactive(self):
        expected = {
            "dialoguer-0.12.0": "362771141e605c79a39783cb704a5736c746688c4ec9c20c9c448c75e2e8d2fa",
            "netconfig-rs-0.1.6": "c870ffcd2eb0fe71a29cbaf92366c31cb3105d06366ebc0fd6bc992c9112fb0a",
            "route_manager-0.2.11": "c870ffcd2eb0fe71a29cbaf92366c31cb3105d06366ebc0fd6bc992c9112fb0a",
            "tun-rs-2.8.1": "ea04d31b5ebd3b5362f092d479a1537e78454ae789336a96db85bbad2cf64d07"}
        paths = []
        for stem, digest in expected.items():
            data = (ROOT / "upstream/packaged-config" / stem / "config.toml").read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
            name, version = stem.rsplit("-", 1)
            paths.append((self.add(name, data, version=version), data))
        result = self.inventory()
        self.assertFalse(result["blocked"])
        self.assertTrue(result["all_packages_examined"])
        self.assertEqual(len(result["configs"]), 4)
        self.assertTrue(all(row["discovery_class"] == "inactive_sibling" for row in result["configs"]))
        for path, data in paths:
            self.assertEqual(path.read_bytes(), data)

    def test_arbitrary_inactive_settings_are_not_an_admission_rule(self):
        self.add("first", b'[env]\nPRIVATE_MARKER="must-not-appear-in-evidence"\n')
        self.add("last", b'[net]\noffline=false\n')
        result = self.inventory()
        self.assertEqual(len(result["configs"]), 2)
        self.assertFalse(result["blocked"])
        self.assertEqual(result["configs"][0]["setting_names"], [["env"], ["env", "PRIVATE_MARKER"]])
        self.assertNotIn("must-not-appear-in-evidence", self.output.read_text())

    def test_actual_cwd_discovery_is_distinct_from_manifest_selection(self):
        path = self.add("direct", b'[net]\noffline=false\n')
        result = vendor.inventory_packaged_configs(self.vendor, self.records, self.output, [path.parent.parent])
        self.assertTrue(result["blocked"])
        self.assertTrue(result["configs"][0]["effective_for_owned_cargo"])

    def test_invalid_toml_retains_fixed_uncertainty_and_continues(self):
        self.add("first", b'password="secret-value-with-broken-quote\n')
        self.add("second", b'[net]\noffline=true\n')
        result = self.inventory()
        self.assertEqual(len(result["configs"]), 2)
        self.assertFalse(result["blocked"])
        self.assertEqual(result["configs"][0]["setting_names"], [])
        self.assertNotIn("secret-value", self.output.read_text())

    def test_file_and_total_byte_limits_are_diagnostic_for_inactive_files(self):
        self.add("large", b"#" * 65)
        self.add("first", b"#" * 40)
        self.add("later", b"#" * 40)
        with patch.object(vendor, "MAX_CONFIG_FILE_BYTES", 64), patch.object(vendor, "MAX_CONFIG_TOTAL_BYTES", 64):
            result = self.inventory()
        self.assertEqual([row["status"] for row in result["configs"]],
                         ["file_byte_budget_exceeded", "parsed", "total_byte_budget_exceeded"])
        self.assertFalse(result["blocked"])
        self.assertTrue(result["all_packages_examined"])

    def test_key_length_depth_and_count_limits_retain_no_values(self):
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
                self.assertFalse(result["blocked"])
                self.assertEqual(result["configs"][0]["status"], "invalid_or_over_budget_setting_names")
                self.assertEqual(result["configs"][0]["setting_names"], [])

    def test_count_limit_retains_explicit_incompleteness(self):
        for name in ("one", "two", "three"):
            self.add(name, b'[net]\noffline=true\n')
        with patch.object(vendor, "MAX_CONFIG_FILES", 2):
            result = self.inventory()
        self.assertFalse(result["blocked"])
        self.assertFalse(result["all_packages_examined"])
        self.assertTrue(result["config_count_budget_exceeded"])
        self.assertEqual(len(result["configs"]), 2)

    def test_symlink_and_legacy_config_metadata_do_not_follow_links(self):
        path = self.add("symlink", b'never="retained"\n')
        path.unlink()
        path.symlink_to(self.root / "absent")
        self.add("legacy", b'[net]\noffline=true\n', ".cargo/config")
        result = self.inventory()
        self.assertEqual(result["configs"][0]["status"], "unsafe_nonregular_path")
        self.assertEqual(result["configs"][1]["path"], ".cargo/config")
        # Archive extraction/input audits reject symlinks independently of Cargo discovery.
        self.assertFalse(result["blocked"])

    def test_inventory_destination_never_overwritten(self):
        self.output.write_text("existing evidence")
        with self.assertRaises(FileExistsError):
            self.inventory()
        self.assertEqual(self.output.read_text(), "existing evidence")

    def test_inventory_byte_limit_retains_bounded_uncertainty(self):
        self.add("one", b'[net]\noffline=true\n')
        with patch.object(vendor, "MAX_CONFIG_INVENTORY_BYTES", 256):
            result = self.inventory()
        self.assertFalse(result["blocked"])
        self.assertEqual(result["error"], "inventory_byte_budget_exceeded")
        self.assertLessEqual(self.output.stat().st_size, 256)


if __name__ == "__main__":
    unittest.main()
