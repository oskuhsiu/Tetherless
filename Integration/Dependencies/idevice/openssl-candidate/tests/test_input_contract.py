import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InputContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((ROOT / "target-inputs.json").read_bytes())

    def test_disabled_and_no_binary_verification_claim(self):
        self.assertFalse(self.contract["enabled"])
        for target in self.contract["targets"].values():
            self.assertFalse(target["binary_bytes_verified"])
            self.assertFalse(target["native_compile_link_verified"])

    def test_complete_header_tree_hashes_reconstruct(self):
        for target in self.contract["targets"].values():
            headers = target["headers"]
            self.assertEqual(len(headers["entries"]), 143)
            self.assertEqual(headers["blob_count"], 143)
            prefix = headers["root"] + "/"
            raw = b""
            for entry in sorted(headers["entries"], key=lambda e: e["path"]):
                self.assertEqual(entry["type"], "blob")
                self.assertEqual(entry["mode"], "100644")
                self.assertTrue(entry["path"].startswith(prefix))
                name = entry["path"][len(prefix):]
                self.assertNotIn("/", name)
                raw += entry["mode"].encode() + b" " + name.encode() + b"\0" + bytes.fromhex(entry["sha"])
            self.assertEqual(hashlib.sha1(b"tree " + str(len(raw)).encode() + b"\0" + raw).hexdigest(), headers["git_tree"])

    def test_exact_static_archive_paths_and_counts(self):
        self.assertEqual(len(self.contract["targets"]), 3)
        for target in self.contract["targets"].values():
            prefix = target["repository_platform"] + "/lib/"
            self.assertEqual({x["path"] for x in target["libraries"]}, {prefix + "libssl.a", prefix + "libcrypto.a"})
            for entry in target["libraries"]:
                self.assertRegex(entry["sha"], r"^[a-f0-9]{40}$")
                self.assertGreater(entry["size"], 0)
                self.assertEqual(entry["mode"], "100644")

    def test_both_header_case_views_and_target_variables(self):
        for name, target in self.contract["targets"].items():
            prefix = name.upper().replace("-", "_") + "_"
            self.assertEqual(target["environment"][prefix + "OPENSSL_STATIC"], "1")
            self.assertEqual(target["environment"][prefix + "OPENSSL_NO_VENDOR"], "1")
            self.assertTrue(target["header_views"]["uppercase_destination"].endswith("/include/OpenSSL"))
            self.assertTrue(target["header_views"]["lowercase_destination"].endswith("/include/openssl"))
            self.assertTrue(all(key.startswith(prefix) for key in target["environment"]))

    def test_retained_source_evidence_hashes(self):
        for name, expected in self.contract["evidence_sha256"].items():
            data = (ROOT / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected)
            self.assertEqual(hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(),
                             self.contract["evidence_git_blobs"][name])

    def test_configurations_require_no_keylog_or_dynamic_engine(self):
        for target in self.contract["targets"].values():
            config = target["required_header_configuration"]
            data = (ROOT / "upstream" / config["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), config["sha256"])
            for macro in config["required_definitions"]:
                self.assertRegex(data.decode(), r"(?m)^#\s*define\s+" + re.escape(macro) + r"\b")
            self.assertTrue(config["native_preprocessor_assertions_required"])
            self.assertFalse(config["binary_configuration_correspondence_verified"])

    def test_existing_crate_versions_are_unchanged(self):
        self.assertEqual({p["name"]: p["version"] for p in self.contract["existing_locked_crates"]},
                         {"openssl": "0.10.76", "openssl-sys": "0.9.112", "tokio-openssl": "0.6.5"})
        self.assertFalse(self.contract["isolation"]["change_cargo_lock"])
        self.assertFalse(self.contract["isolation"]["change_main_default_features"])

    def test_no_implicit_framework_substitution_or_double_provider(self):
        self.assertFalse(self.contract["package_resolution"]["automatic_framework_to_static_mapping"])
        self.assertFalse(self.contract["linkage_ownership"]["duplicate_provider_permitted"])
        self.assertFalse(self.contract["linkage_ownership"]["existing_framework_may_be_removed_implicitly"])


if __name__ == "__main__":
    unittest.main()
