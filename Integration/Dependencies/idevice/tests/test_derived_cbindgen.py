"""Controlled derived-vendor and helper wiring; no Rust/Cargo execution."""
from contextlib import contextmanager
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apply_patch import VerificationError
import derived_cbindgen as derived
import offline_vendor as vendor
import run_helper_tests as helper


class DerivedCbindgenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="derived-metadata-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / "work"
        self.source = self.work / "source"
        self.source.mkdir(parents=True)
        (self.work / "cargo-home").mkdir()
        (self.source / "Cargo.toml").write_text('[workspace]\nmembers=["ffi"]\n')
        (self.source / "ffi").mkdir()
        (self.source / "ffi/Cargo.toml").write_text('[features]\ndefault=["afc"]\n')
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.env = {"CARGO_HOME": str(self.work / "cargo-home"), "CARGO_NET_OFFLINE": "true"}
        self.original = (ROOT / "upstream/registry-build/cbindgen-0.29.2" / derived.SOURCE_PATH).read_bytes()
        self.cbindgen_digest = self.archive("cbindgen", "0.29.2", {
            "Cargo.toml": b'[package]\nname="cbindgen"\nversion="0.29.2"\n',
            derived.SOURCE_PATH: self.original, "Cargo.lock": b'version=4\n'})
        self.plist_files = {name: (ROOT / "upstream/registry-build/plist_ffi-0.1.6" / name).read_bytes()
                            for name in ("Cargo.toml", "Cargo.lock", "build.rs")}
        plist_digest = self.archive("plist_ffi", "0.1.6", self.plist_files)
        (self.source / "Cargo.lock").write_text('version=4\n' + ''.join(
            f'[[package]]\nname="{name}"\nversion="{version}"\n'
            'source="registry+https://github.com/rust-lang/crates.io-index"\n'
            f'checksum="{digest}"\n' for name, version, digest in
            [("cbindgen", "0.29.2", self.cbindgen_digest), ("plist_ffi", "0.1.6", plist_digest)]))
        self.workspace_lock = (self.source / "Cargo.lock").read_bytes()

    def archive(self, name, version, files):
        stem = name + "-" + version
        path = self.cache / (stem + ".crate")
        with tarfile.open(path, "w:gz") as tf:
            for relative, data in files.items():
                entry = tarfile.TarInfo(stem + "/" + relative)
                entry.size = len(data)
                tf.addfile(entry, io.BytesIO(data))
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def prepare(self):
        # Explicit fixture-only checksum substitution. Real source patch preimage
        # remains exact; this does not authenticate a real registry archive.
        with patch.object(derived, "ARCHIVE_SHA256", self.cbindgen_digest):
            return vendor.prepare_offline_vendor(source=self.source, work=self.work, cache=self.cache,
                                                  env=self.env, derive_metadata=True)

    def test_exact_patch_adds_cwd_frozen_and_workspace_manifest(self):
        output = derived.patch_metadata_source(self.original)
        self.assertEqual(hashlib.sha256(output).hexdigest(), derived.PATCHED_SHA256)
        text = output.decode()
        for token in ('cmd.current_dir(workspace_root);', 'cmd.arg("--frozen");',
                      'cmd.arg(&workspace_manifest);', 'missing owned workspace metadata context'):
            self.assertEqual(text.count(token), 1)
        self.assertIn('cmd.arg("--all-features");', text)
        self.assertIn('cmd.arg("--filter-platform").arg(target);', text)
        self.assertIn('manifest_path: &Path,', text)
        original_load = (ROOT / "upstream/registry-build/cbindgen-0.29.2/src/bindgen/cargo/cargo.rs").read_text()
        self.assertIn('manifest_path: toml_path,', original_load)
        self.assertIn('Path::new(&metadata.workspace_root).join("Cargo.lock")', original_load)

    def test_patch_fails_on_wrong_preimage(self):
        with self.assertRaisesRegex(VerificationError, "preimage"):
            derived.patch_metadata_source(self.original + b"\n")

    def test_real_archive_identity_cannot_be_substituted_by_synthetic_archive(self):
        with self.assertRaisesRegex(VerificationError, "archive identity"):
            vendor.prepare_offline_vendor(source=self.source, work=self.work, cache=self.cache,
                                          env=self.env, derive_metadata=True)
        self.assertFalse((self.work / "build-vendor").exists())

    def test_copy_changes_exactly_one_source_and_its_checksum_metadata(self):
        receipt = self.prepare()
        build = receipt["derived_build"]
        original_inputs = receipt["authenticated_inputs"]
        changed = {name for name, value in build["authenticated_inputs"].items() if original_inputs[name] != value}
        self.assertEqual(changed, {derived.CRATE + "/" + derived.SOURCE_PATH,
                                   derived.CRATE + "/.cargo-checksum.json"})
        self.assertEqual((self.work / "vendor" / derived.CRATE / derived.SOURCE_PATH).read_bytes(), self.original)
        for folder in ("vendor", "build-vendor"):
            for name, data in self.plist_files.items():
                self.assertEqual((self.work / folder / "plist_ffi-0.1.6" / name).read_bytes(), data)
        self.assertEqual((self.source / "Cargo.lock").read_bytes(), self.workspace_lock)
        config = tomllib.loads((self.work / "cargo-home/config.toml").read_text())
        self.assertEqual(config["source"]["tetherless-vendor"]["directory"], str(self.work / "build-vendor"))
        self.assertEqual(self.env[derived.CONTEXT_VARIABLE], str(self.source / "Cargo.toml"))
        self.assertTrue(receipt["nested_metadata_frozen"])
        self.assertEqual(build["metadata_context"]["cwd"], str(self.source))
        self.assertTrue(vendor.audit_vendor_inputs(receipt)["original_inputs_unchanged"])
        self.assertTrue(vendor.audit_vendor_inputs(derived.derived_audit_receipt(receipt))["original_inputs_unchanged"])

    def test_new_header_is_derived_output_without_original_lock_allowance(self):
        receipt = self.prepare()
        directory = self.work / "build-vendor/plist_ffi-0.1.6"
        (directory / "plist.h").write_text("// generated controlled header\n")
        audit = vendor.audit_vendor_inputs(derived.derived_audit_receipt(receipt))
        self.assertTrue(audit["original_inputs_unchanged"])
        self.assertIn("plist_ffi-0.1.6/plist.h", audit["generated_files"])
        (directory / "Cargo.lock").write_text("changed packaged lock")
        audit = vendor.audit_vendor_inputs(derived.derived_audit_receipt(receipt))
        self.assertFalse(audit["original_inputs_unchanged"])
        self.assertIn("plist_ffi-0.1.6/Cargo.lock", audit["changed_authenticated_inputs"])

    def test_pristine_and_derived_mutations_are_independently_rejected(self):
        receipt = self.prepare()
        (self.work / "vendor/plist_ffi-0.1.6/Cargo.toml").write_text("changed original")
        (self.work / "build-vendor" / derived.CRATE / derived.SOURCE_PATH).write_text("changed derived")
        self.assertFalse(vendor.audit_vendor_inputs(receipt)["original_inputs_unchanged"])
        self.assertFalse(vendor.audit_vendor_inputs(derived.derived_audit_receipt(receipt))["original_inputs_unchanged"])

    def test_extra_pristine_output_is_not_mistaken_for_derived_header(self):
        receipt = self.prepare()
        (self.work / "vendor/plist_ffi-0.1.6/plist.h").write_text("wrong output location")
        audit = vendor.audit_vendor_inputs(receipt)
        self.assertFalse(audit["original_inputs_unchanged"])
        self.assertTrue(audit["unexpected_pristine_outputs"])

    def test_derived_checksum_mutation_and_root_symlink_are_rejected(self):
        receipt = self.prepare()
        (self.work / "build-vendor" / derived.CRATE / ".cargo-checksum.json").write_text("{}")
        self.assertFalse(vendor.audit_vendor_inputs(derived.derived_audit_receipt(receipt))["original_inputs_unchanged"])
        moved = self.work / "moved"
        (self.work / "build-vendor").rename(moved)
        (self.work / "build-vendor").symlink_to(moved)
        self.assertFalse(vendor.audit_vendor_inputs(derived.derived_audit_receipt(receipt))["vendor_root_valid"])

    def test_effective_workspace_config_change_is_rejected_by_final_audit(self):
        receipt = self.prepare()
        manifest = {"files": {"Cargo.lock": hashlib.sha256(self.workspace_lock).hexdigest()}, "symlinks": {}}
        (self.source / ".cargo").mkdir()
        (self.source / ".cargo/config.toml").write_text('[net]\noffline=false\n')
        audit = vendor.audit_workspace_inputs(self.source, manifest, receipt["workspace_lock_sha256"])
        self.assertFalse(audit["original_inputs_unchanged"])
        self.assertIn("effective_workspace_or_ancestor_cargo_config", audit["unsafe_paths"])

    def test_workspace_generated_headers_are_recorded_without_input_exemption(self):
        receipt = self.prepare()
        manifest = {"files": {"Cargo.lock": hashlib.sha256(self.workspace_lock).hexdigest()}, "symlinks": {}}
        audit = vendor.audit_workspace_inputs(self.source, manifest, receipt["workspace_lock_sha256"])
        self.assertTrue(all(row["status"] == "not_generated" for row in audit["known_generated_headers"].values()))
        for name in ("ffi/idevice.h", "cpp/include/idevice.h"):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("// controlled generated header\n")
        audit = vendor.audit_workspace_inputs(self.source, manifest, receipt["workspace_lock_sha256"])
        self.assertTrue(audit["original_inputs_unchanged"])
        self.assertTrue(all(row["status"] == "generated" and row["sha256"] for row in audit["known_generated_headers"].values()))
        manifest["files"]["ffi/idevice.h"] = "0" * 64
        audit = vendor.audit_workspace_inputs(self.source, manifest, receipt["workspace_lock_sha256"])
        self.assertFalse(audit["original_inputs_unchanged"])
        self.assertIn("ffi/idevice.h", audit["changed_inputs"])
        (self.source / "cpp/include/idevice.h").unlink()
        (self.source / "cpp/include/idevice.h").symlink_to(self.source / "ffi/idevice.h")
        audit = vendor.audit_workspace_inputs(self.source, manifest, receipt["workspace_lock_sha256"])
        self.assertIn("cpp/include/idevice.h", audit["unsafe_paths"])

    def test_existing_derived_destination_is_not_reused(self):
        (self.work / "build-vendor").mkdir()
        with self.assertRaisesRegex(VerificationError, "fresh derived"):
            self.prepare()

    def test_helper_failure_retains_both_vendor_audits_and_workspace_audit(self):
        work = self.root / "helper-work"
        toolchain = self.root / "toolchain.json"
        toolchain.write_text('{"schema":1,"source_date_epoch":1}')
        args = SimpleNamespace(source=self.source, crate_cache=self.cache, work_dir=work,
            output=self.root / "not-published", toolchain_lock=toolchain,
            toolchain_lock_sha256=hashlib.sha256(toolchain.read_bytes()).hexdigest())
        def environment(_config, root):
            (root / "cargo-home").mkdir()
            return {"CARGO_HOME": str(root / "cargo-home"), "CARGO_NET_OFFLINE": "true"}, {"cargo": "never-executed"}
        def staged(_source, destination, *_args):
            shutil.copytree(self.source, destination)
            return {"files": {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in destination.rglob("*") if p.is_file()}, "symlinks": {}}
        def controlled_failure(command, *, source, env, log):
            self.assertEqual(source, work / "source")
            self.assertEqual(env[derived.CONTEXT_VARIABLE], str(source / "Cargo.toml"))
            self.assertIn("--frozen", command)
            (work / "build-vendor/plist_ffi-0.1.6/plist.h").write_text("// generated before failure\n")
            (source / "ffi/idevice.h").write_text("// generated before failure\n")
            raise VerificationError("controlled native failure")
        with patch.object(derived, "ARCHIVE_SHA256", self.cbindgen_digest), \
             patch.object(helper, "native_environment", side_effect=environment), \
             patch.object(helper, "verify_toolchain", return_value={}), \
             patch.object(helper, "stage", side_effect=staged), \
             patch.object(helper, "capture_helper_command", side_effect=controlled_failure):
            with self.assertRaisesRegex(VerificationError, "controlled native failure"):
                helper.execute(args)
        completed = work / "completed"
        for name in ("vendor-input-audit.json", "derived-vendor-input-audit.json", "workspace-input-audit.json"):
            self.assertTrue(json.loads((completed / name).read_bytes())["original_inputs_unchanged"])
        derived_audit = json.loads((completed / "derived-vendor-input-audit.json").read_bytes())
        self.assertIn("plist_ffi-0.1.6/plist.h", derived_audit["generated_files"])
        layout = json.loads((completed / "vendor-layout.json").read_bytes())
        self.assertEqual(layout["derived_build"]["metadata_context"]["cwd"], str(work / "source"))
        workspace_audit = json.loads((completed / "workspace-input-audit.json").read_bytes())
        self.assertEqual(workspace_audit["known_generated_headers"]["ffi/idevice.h"]["status"], "generated")
        self.assertFalse(args.output.exists())


if __name__ == "__main__":
    unittest.main()
