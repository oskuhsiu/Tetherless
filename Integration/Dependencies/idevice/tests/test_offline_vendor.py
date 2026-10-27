"""Controlled archive/config/child-environment fixtures; no Cargo or network execution."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apply_patch import VerificationError
from offline_vendor import prepare_offline_vendor, audit_vendor_inputs, audit_workspace_inputs
import run_helper_tests


class OfflineVendorLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='vendor fixture "quoted" 🌿 ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.work = self.root / "work"
        self.source = self.work / "source"
        (self.source / "ffi").mkdir(parents=True)
        self.home = self.work / "cargo-home"
        self.home.mkdir()
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.env = {"CARGO_HOME": str(self.home), "CARGO_NET_OFFLINE": "true"}
        (self.source / "Cargo.toml").write_text('[workspace]\nmembers = ["ffi"]\n')
        (self.source / "ffi/Cargo.toml").write_text('[package]\nname = "ffi-fixture"\nversion = "0.1.0"\n')
        self.make_crate()

    def make_crate(self, additional=None):
        self.original_files = {"Cargo.toml": b'[package]\nname = "fixture"\nversion = "1.0.0"\n',
                               "src/lib.rs": b"// authenticated fixture source\n"}
        self.original_files.update(additional or {})
        archive = self.cache / "fixture-1.0.0.crate"
        with tarfile.open(archive, "w:gz") as tf:
            for name, data in self.original_files.items():
                entry = tarfile.TarInfo("fixture-1.0.0/" + name)
                entry.size = len(data)
                tf.addfile(entry, io.BytesIO(data))
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        (self.source / "Cargo.lock").write_text('version = 4\n[[package]]\nname = "fixture"\nversion = "1.0.0"\n'
            'source = "registry+https://github.com/rust-lang/crates.io-index"\nchecksum = "' + checksum + '"\n')
        self.workspace_before = {name: (self.source / name).read_bytes()
                                 for name in ("Cargo.toml", "ffi/Cargo.toml", "Cargo.lock")}

    def prepare(self):
        return prepare_offline_vendor(source=self.source, work=self.work, cache=self.cache, env=self.env)

    def test_vendor_is_sibling_and_manifests_remain_byte_identical(self):
        receipt = self.prepare()
        vendor = Path(receipt["vendor_directory"])
        self.assertEqual(vendor, self.work / "vendor")
        self.assertFalse(vendor.is_relative_to(self.source))
        self.assertFalse((self.source / "vendor").exists())
        self.assertFalse((self.source / ".cargo").exists())
        for name, data in self.workspace_before.items():
            self.assertEqual((self.source / name).read_bytes(), data)
        for name, data in self.original_files.items():
            self.assertEqual((vendor / "fixture-1.0.0" / name).read_bytes(), data)
        self.assertTrue(audit_vendor_inputs(receipt)["original_inputs_unchanged"])

    def test_absolute_config_path_handles_spaces_and_quotes(self):
        receipt = self.prepare()
        config = tomllib.loads((self.home / "config.toml").read_text())
        self.assertEqual(config["source"]["crates-io"]["replace-with"], "tetherless-vendor")
        self.assertEqual(Path(config["source"]["tetherless-vendor"]["directory"]), self.work / "vendor")
        self.assertTrue(config["net"]["offline"])
        self.assertTrue(receipt["top_level_frozen"])
        self.assertTrue(receipt["nested_metadata_offline"])
        self.assertFalse(receipt["nested_metadata_frozen"])

    def test_nested_child_inherits_same_global_config_and_offline_setting(self):
        receipt = self.prepare()
        cwd = Path(receipt["vendor_directory"]) / "fixture-1.0.0"
        code = '''import json,os,tomllib
from pathlib import Path
home=Path(os.environ["CARGO_HOME"])
config=tomllib.loads((home/"config.toml").read_text())
assert not any((p/"Cargo.toml").exists() for p in Path.cwd().parents)
print(json.dumps({"home":str(home),"offline":os.environ["CARGO_NET_OFFLINE"],"vendor":config["source"]["tetherless-vendor"]["directory"]}))
'''
        outer = "import subprocess,sys; subprocess.run([sys.executable,'-c'," + repr(code) + "],check=True,timeout=2)"
        # A real child and grandchild inherit cwd/env. This is deliberately a
        # config-discovery fixture, not a claim that Cargo metadata ran locally.
        result = subprocess.run([sys.executable, "-c", outer], cwd=cwd, env=dict(os.environ, **self.env),
                                check=True, timeout=4, text=True, capture_output=True)
        value = json.loads(result.stdout)
        self.assertEqual(value, {"home": str(self.home), "offline": "true", "vendor": str(self.work / "vendor")})
        self.assertTrue(audit_vendor_inputs(receipt)["original_inputs_unchanged"])

    def test_unrelated_ancestor_manifest_does_not_change_explicit_workspace_context(self):
        enclosing = self.root / "Cargo.toml"
        enclosing.write_text('[workspace]\nmembers=[]\n')
        self.prepare()
        self.assertEqual(enclosing.read_text(), '[workspace]\nmembers=[]\n')
        self.assertTrue((self.work / "vendor").is_dir())

    def test_ambient_source_config_and_symlink_are_rejected(self):
        config_dir = self.source / ".cargo"
        config_dir.mkdir()
        config = config_dir / "config"
        config.symlink_to(self.source / "Cargo.toml")
        with self.assertRaisesRegex(VerificationError, "ambient Cargo"):
            self.prepare()
        self.assertTrue(config.is_symlink())

    def test_inactive_crate_local_config_is_retained_without_override(self):
        self.make_crate({".cargo/config.toml": b'[net]\noffline = false\n'})
        receipt = self.prepare()
        self.assertTrue((self.home / "config.toml").exists())
        self.assertTrue(audit_vendor_inputs(receipt)["original_inputs_unchanged"])
        self.assertEqual((self.work / "vendor/fixture-1.0.0/.cargo/config.toml").read_bytes(), self.original_files[".cargo/config.toml"])

    def test_home_config_or_home_symlink_is_rejected(self):
        (self.home / "config").symlink_to(self.source / "Cargo.toml")
        with self.assertRaises(VerificationError):
            self.prepare()
        (self.home / "config").unlink()
        replacement = self.work / "alternate-home"
        replacement.mkdir()
        self.home.rmdir()
        self.home.symlink_to(replacement)
        with self.assertRaisesRegex(VerificationError, "isolated"):
            self.prepare()

    def test_missing_offline_environment_is_rejected(self):
        self.env.pop("CARGO_NET_OFFLINE")
        with self.assertRaisesRegex(VerificationError, "inherit offline"):
            self.prepare()

    def test_generated_nested_lock_is_reported_without_becoming_an_input_mutation(self):
        receipt = self.prepare()
        generated = Path(receipt["vendor_directory"]) / "fixture-1.0.0/Cargo.lock"
        generated.write_text('version = 4\n')
        audit = audit_vendor_inputs(receipt)
        self.assertTrue(audit["original_inputs_unchanged"])
        self.assertEqual(audit["generated_files"]["fixture-1.0.0/Cargo.lock"], hashlib.sha256(generated.read_bytes()).hexdigest())
        self.assertEqual(generated.read_text(), 'version = 4\n')

    def test_authenticated_manifest_or_lock_mutation_is_failure_not_rewritten(self):
        self.make_crate({"Cargo.lock": b'version = 4\n'})
        receipt = self.prepare()
        folder = Path(receipt["vendor_directory"]) / "fixture-1.0.0"
        for name in ("Cargo.toml", "Cargo.lock"):
            (folder / name).write_bytes(b"changed fixture bytes")
        audit = audit_vendor_inputs(receipt)
        self.assertFalse(audit["original_inputs_unchanged"])
        self.assertEqual(set(audit["changed_authenticated_inputs"]), {"fixture-1.0.0/Cargo.toml", "fixture-1.0.0/Cargo.lock"})
        self.assertEqual((folder / "Cargo.toml").read_bytes(), b"changed fixture bytes")

    def test_generated_config_and_changed_global_config_are_failures(self):
        receipt = self.prepare()
        local = Path(receipt["vendor_directory"]) / "fixture-1.0.0/.cargo/config.toml"
        local.parent.mkdir()
        local.write_text('[net]\noffline=false\n')
        (self.home / "config.toml").write_text('[net]\noffline=false\n')
        audit = audit_vendor_inputs(receipt)
        self.assertFalse(audit["original_inputs_unchanged"])
        self.assertFalse(audit["cargo_config_unchanged"])
        self.assertIn("fixture-1.0.0/.cargo/config.toml", audit["generated_files"])

    def test_generated_global_legacy_config_cannot_shadow_isolated_toml(self):
        receipt = self.prepare()
        (self.home / "config").symlink_to(self.source / "Cargo.toml")
        audit = audit_vendor_inputs(receipt)
        self.assertFalse(audit["original_inputs_unchanged"])
        self.assertIn("$CARGO_HOME/config", audit["unsafe_paths"])

    def test_helper_command_failure_still_retains_vendor_audit(self):
        # Controlled unit wiring only: no native toolchain or Cargo is invoked.
        # Real authenticated fixture archives and sibling-vendor preparation run.
        work = self.root / "failed-helper-work"
        toolchain = self.root / "toolchain-fixture.json"
        toolchain.write_text('{"schema":1,"source_date_epoch":1}')
        args = SimpleNamespace(source=self.source, crate_cache=self.cache, work_dir=work,
            output=self.root / "must-not-publish", toolchain_lock=toolchain,
            toolchain_lock_sha256=hashlib.sha256(toolchain.read_bytes()).hexdigest())
        def environment(_config, root):
            (root / "cargo-home").mkdir()
            return {"CARGO_HOME": str(root / "cargo-home"), "CARGO_NET_OFFLINE": "true"}, {"cargo": "never-executed"}
        def staged(_source, destination, *_args):
            shutil.copytree(self.source, destination)
            (destination / "ffi/Cargo.toml").write_text('[features]\ndefault = ["afc"]\n')
            return {"files": {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in destination.rglob("*") if p.is_file()}, "symlinks": {}}
        def failed_command(*_args, **_kwargs):
            generated = work / "vendor/fixture-1.0.0/Cargo.lock"
            generated.write_text('version = 4\n')
            raise VerificationError("controlled Cargo failure")
        with patch.object(run_helper_tests, "native_environment", side_effect=environment), \
             patch.object(run_helper_tests, "verify_toolchain", return_value={}), \
             patch.object(run_helper_tests, "stage", side_effect=staged), \
             patch.object(run_helper_tests, "prepare_offline_vendor", side_effect=lambda **kw: prepare_offline_vendor(**dict(kw, derive_metadata=False))), \
             patch.object(run_helper_tests, "capture_helper_command", side_effect=failed_command):
            with self.assertRaisesRegex(VerificationError, "controlled Cargo failure"):
                run_helper_tests.execute(args)
        audit = json.loads((work / "completed/vendor-input-audit.json").read_bytes())
        self.assertTrue(audit["original_inputs_unchanged"])
        self.assertIn("fixture-1.0.0/Cargo.lock", audit["generated_files"])
        self.assertTrue((work / "completed/vendor-layout.json").is_file())
        workspace_audit = json.loads((work / "completed/workspace-input-audit.json").read_bytes())
        self.assertTrue(workspace_audit["original_inputs_unchanged"])
        self.assertTrue((work / "completed/source-manifest.json").is_file())
        self.assertFalse(args.output.exists())

    def test_vendor_root_symlink_never_passes_with_identical_target_bytes(self):
        receipt = self.prepare()
        vendor = Path(receipt["vendor_directory"])
        moved = self.work / "moved-vendor"
        vendor.rename(moved)
        vendor.symlink_to(moved, target_is_directory=True)
        audit = audit_vendor_inputs(receipt)
        self.assertFalse(audit["original_inputs_unchanged"])
        self.assertFalse(audit["vendor_root_valid"])
        self.assertEqual(audit["unsafe_paths"], ["."])
        self.assertEqual(audit["generated_files"], {})

    def test_missing_vendor_root_is_unverified(self):
        receipt = self.prepare()
        Path(receipt["vendor_directory"]).rename(self.work / "removed-vendor")
        audit = audit_vendor_inputs(receipt)
        self.assertFalse(audit["original_inputs_unchanged"])
        self.assertFalse(audit["vendor_root_valid"])

    def test_workspace_manifest_and_lock_mutation_are_retained_in_audit(self):
        receipt = self.prepare()
        manifest = {"files": {name: hashlib.sha256(data).hexdigest() for name, data in self.workspace_before.items()}, "symlinks": {}}
        (self.source / "Cargo.lock").write_text("mutated workspace lock")
        (self.source / "ffi/Cargo.toml").write_text("mutated manifest")
        audit = audit_workspace_inputs(self.source, manifest, receipt["workspace_lock_sha256"])
        self.assertFalse(audit["original_inputs_unchanged"])
        self.assertFalse(audit["workspace_lock_unchanged"])
        self.assertEqual(set(audit["changed_inputs"]), {"Cargo.lock", "ffi/Cargo.toml"})
        self.assertEqual((self.source / "Cargo.lock").read_text(), "mutated workspace lock")

    def test_workspace_root_type_and_symlink_fail_before_input_reads(self):
        receipt = self.prepare()
        manifest = {"files": {name: hashlib.sha256(data).hexdigest() for name, data in self.workspace_before.items()}, "symlinks": {}}
        moved = self.work / "moved-source"
        self.source.rename(moved)
        self.source.symlink_to(moved, target_is_directory=True)
        for state in ("symlink", "file", "missing"):
            with self.subTest(state=state):
                audit = audit_workspace_inputs(self.source, manifest, receipt["workspace_lock_sha256"])
                self.assertFalse(audit["original_inputs_unchanged"])
                self.assertFalse(audit["source_root_valid"])
                self.assertEqual(audit["unsafe_paths"], ["."])
            self.source.unlink(missing_ok=True)
            if state == "symlink":
                self.source.write_text("not a source directory")

    def test_helper_profile_counts_and_source_identity_remain_unchanged(self):
        profile = json.loads((ROOT / "helper-test-profile.json").read_bytes())
        self.assertEqual([row["expected_passed"] for row in profile["native_test_filters"]], [18, 25])
        self.assertEqual(profile["upstream"]["commit"], "3e55c8486b2057e40c1f74aaaa1155c82341cf76")
        script = (ROOT / "run_helper_tests.py").read_text()
        self.assertIn('"test", "--frozen"', script)
        self.assertIn('finally:\n        audit = audit_vendor_inputs', script)
        self.assertIn('completed / "vendor-input-audit.json"', script)


if __name__ == "__main__":
    unittest.main()
