"""Portable policy/tooling tests. These do not compile Rust or validate an iPhone."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import apply_patch as source_patch
import build_xcframework as native
import run_helper_tests as helper_tests


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.recipe = self.base / "recipe"
        self.recipe.mkdir()
        self.source = self.base / "source"
        self.source.mkdir()
        self.original = {"Cargo.lock": b"version = 4\n", "ffi/src/lib.rs": b"pub mod house_arrest;\n", "LICENSE.txt": b"Fixture license\n"}
        for name, data in self.original.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        entries = [{"path": name, "type": "blob", "mode": "100644", "sha": source_patch.git_blob(data)}
                   for name, data in self.original.items()]
        tree = source_patch.canonical_json(entries)
        (self.recipe / "source-tree.json").write_bytes(tree)
        overlay = self.recipe / "overlay/ffi/src/staged_pairing.rs"
        overlay.parent.mkdir(parents=True)
        overlay.write_bytes(b"// Synthetic fixture overlay\n")
        old, new = b"pub mod house_arrest;\n", b"pub mod house_arrest;\npub mod staged_pairing;\n"
        self.lock = {"schema": 1, "patch_complete": True, "upstream": {"commit": "fixture"}, "source_tree_sha256": source_patch.sha256(tree),
                     "evidence_sha256": {}, "edits": [{"path": "ffi/src/lib.rs", "old": old.decode(), "new": new.decode(),
                     "before_sha256": source_patch.sha256(old), "after_sha256": source_patch.sha256(new)}],
                     "overlays": [{"path": "ffi/src/staged_pairing.rs", "sha256": source_patch.sha256(overlay.read_bytes())}]}
        self.save_lock()
        self.destination = self.base / "destination"

    def save_lock(self):
        (self.recipe / "source-lock.json").write_bytes(source_patch.canonical_json(self.lock))

    def stage(self):
        return source_patch.stage(self.source, self.destination, self.recipe)

    def test_stages_complete_verified_source_and_retains_lock_and_license(self):
        manifest = self.stage()
        self.assertEqual((self.destination / "Cargo.lock").read_bytes(), self.original["Cargo.lock"])
        self.assertEqual((self.destination / "LICENSE.txt").read_bytes(), self.original["LICENSE.txt"])
        self.assertEqual(len(manifest["files"]), 4)
        self.assertIn(b"pub mod staged_pairing;", (self.destination / "ffi/src/lib.rs").read_bytes())

    def test_no_untracked_configuration_is_copied(self):
        (self.source / ".cargo").mkdir()
        (self.source / ".cargo/config.toml").write_text("untrusted config")
        self.stage()
        self.assertFalse((self.destination / ".cargo").exists())

    def test_source_mismatch_leaves_no_destination(self):
        (self.source / "Cargo.lock").write_bytes(b"changed")
        with self.assertRaisesRegex(source_patch.VerificationError, "source hash mismatch"):
            self.stage()
        self.assertFalse(self.destination.exists())

    def test_missing_source_fails(self):
        (self.source / "LICENSE.txt").unlink()
        with self.assertRaisesRegex(source_patch.VerificationError, "source missing"):
            self.stage()

    def test_reapply_or_existing_destination_fails(self):
        self.stage()
        with self.assertRaisesRegex(source_patch.VerificationError, "must not exist"):
            self.stage()

    def test_overlay_pending_fails_before_output(self):
        self.lock["overlays"][0]["sha256"] = None
        self.save_lock()
        with self.assertRaisesRegex(source_patch.VerificationError, "pending"):
            self.stage()
        self.assertFalse(self.destination.exists())

    def test_overlay_change_fails(self):
        (self.recipe / "overlay/ffi/src/staged_pairing.rs").write_bytes(b"unreviewed")
        with self.assertRaisesRegex(source_patch.VerificationError, "overlay hash"):
            self.stage()

    def test_tree_lock_change_fails(self):
        (self.recipe / "source-tree.json").write_bytes(b"[]")
        with self.assertRaisesRegex(source_patch.VerificationError, "source-tree"):
            self.stage()

    def test_patch_preimage_fails(self):
        self.lock["edits"][0]["before_sha256"] = "0" * 64
        self.save_lock()
        with self.assertRaisesRegex(source_patch.VerificationError, "preimage"):
            self.stage()

    def test_patch_postimage_fails(self):
        self.lock["edits"][0]["after_sha256"] = "0" * 64
        self.save_lock()
        with self.assertRaisesRegex(source_patch.VerificationError, "result mismatch"):
            self.stage()

    def test_upstream_overlay_replacement_forbidden(self):
        self.lock["overlays"][0]["path"] = "Cargo.lock"
        self.save_lock()
        with self.assertRaisesRegex(source_patch.VerificationError, "cannot replace"):
            self.stage()

    def test_replacement_overlay_requires_and_checks_preimage(self):
        name = "LICENSE.txt"
        overlay = self.recipe / "overlay" / name
        overlay.write_bytes(b"Synthetic replacement with preserved fixture attribution\n")
        self.lock["overlays"] = [{"path": name, "kind": "replace",
                                  "before_sha256": source_patch.sha256(self.original[name]),
                                  "sha256": source_patch.sha256(overlay.read_bytes())}]
        self.save_lock()
        self.stage()
        self.assertEqual((self.destination / name).read_bytes(), overlay.read_bytes())

    def test_replacement_overlay_wrong_preimage_fails(self):
        self.lock["overlays"] = [{"path": "LICENSE.txt", "kind": "replace",
                                  "before_sha256": "0" * 64, "sha256": "1" * 64}]
        self.save_lock()
        with self.assertRaisesRegex(source_patch.VerificationError, "preimage mismatch"):
            self.stage()

    def test_incomplete_composite_patch_fails(self):
        self.lock["patch_complete"] = False
        self.save_lock()
        with self.assertRaisesRegex(source_patch.VerificationError, "composite source patch"):
            self.stage()

    def test_source_symlink_fails(self):
        p = self.source / "LICENSE.txt"
        p.unlink()
        p.symlink_to(self.recipe / "source-lock.json")
        with self.assertRaisesRegex(source_patch.VerificationError, "symlink"):
            self.stage()

    def test_unsafe_paths_fail(self):
        for name in ("../escape", "/absolute", "a/../b", "a//b", "./file", "a\\b", ""):
            with self.subTest(name=name), self.assertRaises(source_patch.VerificationError):
                source_patch.safe_path(self.source, name)

    def add_locked_link(self, target: str):
        link = self.source / "docs/LICENSE.txt"
        link.parent.mkdir()
        link.symlink_to(target)
        entries = json.loads((self.recipe / "source-tree.json").read_bytes())
        entries.append({"path": "docs/LICENSE.txt", "mode": "120000", "type": "blob",
                        "sha": source_patch.git_blob(target.encode())})
        data = source_patch.canonical_json(entries)
        (self.recipe / "source-tree.json").write_bytes(data)
        self.lock["source_tree_sha256"] = source_patch.sha256(data)
        self.save_lock()

    def test_exact_committed_relative_link_is_preserved(self):
        self.add_locked_link("../LICENSE.txt")
        manifest = self.stage()
        link = self.destination / "docs/LICENSE.txt"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), "../LICENSE.txt")
        self.assertEqual(manifest["symlinks"], {"docs/LICENSE.txt": "../LICENSE.txt"})
        archive_path = self.base / "source.zip"
        native.deterministic_zip(self.destination, archive_path, source_symlinks=manifest["symlinks"])
        with zipfile.ZipFile(archive_path) as archive:
            self.assertEqual(archive.read("docs/LICENSE.txt"), b"../LICENSE.txt")
            self.assertEqual((archive.getinfo("docs/LICENSE.txt").external_attr >> 16) & 0o170000, 0o120000)

    def test_committed_link_cannot_escape_tree(self):
        self.add_locked_link("../../secret")
        with self.assertRaises(source_patch.VerificationError):
            self.stage()

    def test_committed_link_must_target_a_regular_source_blob(self):
        self.add_locked_link("../missing")
        with self.assertRaisesRegex(source_patch.VerificationError, "committed regular file"):
            self.stage()

    def test_materialized_source_contract_matches_the_pinned_tree(self):
        contract = json.loads((ROOT / "source-input.json").read_bytes())
        lock = source_patch.load_lock(ROOT)
        entries = json.loads((ROOT / "source-tree.json").read_bytes())
        self.assertEqual(contract["commit"], lock["upstream"]["commit"])
        self.assertEqual(contract["git_tree"], lock["upstream"]["tree"])
        self.assertEqual(contract["verified_blob_count"], sum(e["type"] == "blob" for e in entries))
        self.assertEqual(contract["source_symlinks"], {"idevice/README.md": "../README.md"})
        self.assertEqual(contract["archive"]["sha256"], "2ceadeee2cd42f89732da917a7fe953764f375a65f46f6a314abc57a6b4c7cf0")
        self.assertFalse(contract["archive"]["included_in_recipe"])

    def test_original_evidence_is_hash_locked(self):
        lock = source_patch.load_lock(ROOT)
        self.assertEqual(lock["upstream"]["commit"], "3e55c8486b2057e40c1f74aaaa1155c82341cf76")
        self.assertEqual(lock["consumer"]["commit"], "12be70dc2627307a16bfd2dc7a009080d5bec909")
        packages = native.locked_packages((ROOT / "upstream/Cargo.lock").read_bytes())
        plist = next(p for p in packages if p["name"] == "plist")
        self.assertEqual(plist["version"], "1.8.0")
        self.assertEqual(plist["checksum"], "740ebea15c5d1428f910cd1a5f52cebf8d25006245ed8ade92702f4943d91e07")


class HelperOnlyProfileTests(unittest.TestCase):
    def test_only_reviewed_helpers_are_selected(self):
        profile = helper_tests.load_helper_profile()
        originals = {str(p.relative_to(ROOT / "upstream")): p.read_bytes()
                     for p in (ROOT / "upstream").rglob("*") if p.is_file()}
        patched = source_patch.patched_files(ROOT, profile, originals)
        self.assertIn("ffi/src/staged_pairing.rs", patched)
        self.assertNotIn("ffi/src/staged_acquisition.rs", patched)
        self.assertNotIn(b"staged_acquisition", patched["ffi/src/lib.rs"])
        self.assertEqual(patched["Cargo.lock"], originals["Cargo.lock"])
        self.assertEqual(sum(suite["expected_passed"] for suite in profile["native_test_filters"]), 43)
        self.assertFalse(source_patch.load_lock(ROOT)["patch_complete"])

    def test_extra_composite_overlay_is_rejected(self):
        profile = helper_tests.load_helper_profile()
        profile["overlays"].append({"path": "ffi/src/staged_acquisition.rs", "sha256": "0" * 64})
        with patch.object(helper_tests, "load_lock", return_value=profile):
            with self.assertRaisesRegex(source_patch.VerificationError, "unexpected source overlay"):
                helper_tests.load_helper_profile()

    def test_full_stage_records_the_selected_profile(self):
        source = (ROOT / "apply_patch.py").read_text()
        self.assertIn('"source_profile": lock_filename', source)
        self.assertIn('sha256((root / lock_filename).read_bytes())', source)


class VendorAndArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.cache = self.base / "cache"
        self.cache.mkdir()

    def make_crate(self, name="demo-1.0.0/src/lib.rs", *, symlink=False, duplicate=False):
        archive = self.cache / "demo-1.0.0.crate"
        with tarfile.open(archive, "w:gz") as tf:
            data = b"// fixture\n"
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            if symlink:
                entry.type = tarfile.SYMTYPE
                entry.linkname = "/escape"
                entry.size = 0
            tf.addfile(entry, None if symlink else io.BytesIO(data))
            if duplicate:
                tf.addfile(entry, io.BytesIO(data))
        return (f'version = 4\n[[package]]\nname = "demo"\nversion = "1.0.0"\n'
                f'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
                f'checksum = "{native.file_hash(archive)}"\n').encode()

    def test_verified_crate_is_vendored_with_generated_checksums(self):
        lock = self.make_crate()
        destination = self.base / "vendor"
        native.vendor_crates(lock, self.cache, destination)
        folder = destination / "demo-1.0.0"
        self.assertEqual((folder / "src/lib.rs").read_bytes(), b"// fixture\n")
        meta = json.loads((folder / ".cargo-checksum.json").read_bytes())
        self.assertEqual(meta["files"]["src/lib.rs"], source_patch.sha256(b"// fixture\n"))

    def test_missing_crate_fails_before_vendor_output(self):
        lock = self.make_crate()
        (self.cache / "demo-1.0.0.crate").unlink()
        with self.assertRaisesRegex(source_patch.VerificationError, "missing"):
            native.vendor_crates(lock, self.cache, self.base / "vendor")
        self.assertFalse((self.base / "vendor").exists())

    def test_checksum_mismatch_fails_before_extracting(self):
        lock = self.make_crate()
        with (self.cache / "demo-1.0.0.crate").open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaisesRegex(source_patch.VerificationError, "checksum"):
            native.vendor_crates(lock, self.cache, self.base / "vendor")

    def test_archive_traversal_links_and_duplicate_members_fail(self):
        for name, link, duplicate in (("demo-1.0.0/../escape", False, False), ("foreign/file", False, False),
                                       ("demo-1.0.0/link", True, False), ("demo-1.0.0/a", False, True)):
            with self.subTest(name=name):
                lock = self.make_crate(name, symlink=link, duplicate=duplicate)
                with tempfile.TemporaryDirectory(dir=self.base) as tmp:
                    with self.assertRaises(source_patch.VerificationError):
                        native.vendor_crates(lock, self.cache, Path(tmp) / "vendor")

    def test_non_registry_source_fails(self):
        lock = self.make_crate().replace(b"registry+https://github.com/rust-lang/crates.io-index", b"git+https://example.com/repo#commit")
        with self.assertRaisesRegex(source_patch.VerificationError, "non-crates.io"):
            native.locked_packages(lock)

    def test_archive_vendor_metadata_is_rejected(self):
        lock = self.make_crate("demo-1.0.0/.cargo-checksum.json")
        with self.assertRaisesRegex(source_patch.VerificationError, "vendor metadata"):
            native.vendor_crates(lock, self.cache, self.base / "vendor")

    def test_frozen_build_preserves_default_features(self):
        command = native.build_command("cargo", "aarch64-apple-ios", ["obfuscate"])
        self.assertIn("--frozen", command)
        self.assertNotIn("--no-default-features", command)
        self.assertEqual(command[-2:], ["--features", "obfuscate"])
        simulator = native.build_command("cargo", "aarch64-apple-ios-sim", [])
        self.assertNotIn("--features", simulator)
        self.assertEqual(len(native.TARGETS), 2)

    def test_native_link_flags_are_compiler_reported_not_shell_commands(self):
        flags = native.native_static_flags("note: native-static-libs: -framework Security -lSystem -lc++\n")
        self.assertEqual(flags, ["-framework", "Security", "-lSystem", "-lc++"])
        for output in ("", "native-static-libs: -framework\n", "native-static-libs: -Wl,evil\n",
                       "native-static-libs: -lSystem\nnative-static-libs: -lSystem\n"):
            with self.subTest(output=output), self.assertRaises(source_patch.VerificationError):
                native.native_static_flags(output)

    def test_probe_sources_are_hash_locked(self):
        lock = source_patch.load_lock(ROOT)
        for entry in lock["link_probes"].values():
            self.assertEqual(native.file_hash(ROOT / entry["path"]), entry["sha256"])
        c_probe = (ROOT / lock["link_probes"]["c"]["path"]).read_text()
        swift_probe = (ROOT / lock["link_probes"]["swift"]["path"]).read_text()
        for symbol in lock["required_ffi_symbols"]:
            self.assertIn(symbol, c_probe)
            self.assertIn(symbol, swift_probe)

    def test_generated_header_requires_function_declarations(self):
        native.verify_generated_header(b"void fixture_api(void);", ["fixture_api"])
        with self.assertRaises(source_patch.VerificationError):
            native.verify_generated_header(b"#define fixture_api 1", ["fixture_api"])

    def test_artifact_hash_lock_rejects_tampering_and_extra_files(self):
        bundle = self.base / "bundle"
        bundle.mkdir()
        (bundle / "file").write_bytes(b"fixture")
        manifest = self.base / "manifest.json"
        manifest.write_bytes(source_patch.canonical_json({"files": native.inventory(bundle)}))
        expected = native.file_hash(manifest)
        native.verify_artifact(bundle, manifest, expected)
        (bundle / "extra").write_bytes(b"unexpected")
        with self.assertRaisesRegex(source_patch.VerificationError, "inventory"):
            native.verify_artifact(bundle, manifest, expected)

    def test_manifest_identity_itself_must_be_reviewed(self):
        manifest = self.base / "manifest.json"
        manifest.write_text('{"files":{}}')
        with self.assertRaisesRegex(source_patch.VerificationError, "manifest sha256"):
            native.verify_artifact(self.cache, manifest, "0" * 64)

    def test_deterministic_archive_normalizes_timestamps(self):
        (self.cache / "file").write_bytes(b"same bytes")
        one, two = self.base / "one.zip", self.base / "two.zip"
        native.deterministic_zip(self.cache, one)
        os.utime(self.cache / "file", (1000, 2000))
        native.deterministic_zip(self.cache, two)
        self.assertEqual(one.read_bytes(), two.read_bytes())
        with zipfile.ZipFile(one) as archive:
            self.assertEqual(archive.infolist()[0].date_time, (1980, 1, 1, 0, 0, 0))

    def test_artifact_symlink_fails(self):
        (self.cache / "link").symlink_to("/tmp")
        with self.assertRaisesRegex(source_patch.VerificationError, "symlinks"):
            native.inventory(self.cache)

    def test_ancestor_cargo_config_is_rejected(self):
        work = self.base / "work/source"
        work.mkdir(parents=True)
        ambient = self.base / ".cargo"
        ambient.mkdir()
        for name in ("config", "config.toml"):
            with self.subTest(name=name):
                path = ambient / name
                path.write_text("[build]\nrustc-wrapper = 'untrusted'\n")
                with self.assertRaisesRegex(source_patch.VerificationError, "ambient Cargo"):
                    native.reject_ambient_cargo_config(work)
                path.unlink()

    def test_non_macos_native_run_fails(self):
        with patch.object(native.platform, "system", return_value="Linux"):
            with self.assertRaisesRegex(source_patch.VerificationError, "arm64 macOS"):
                native.native_environment({}, self.base)

    def test_toolchain_template_intentionally_cannot_authorize_a_build(self):
        config = json.loads((ROOT / "toolchain-lock.template.json").read_bytes())
        self.assertEqual(config["rust_release"], "1.98.1")
        self.assertTrue(all(value is None for value in config["observations"].values()))
        with self.assertRaises(source_patch.VerificationError):
            native.require_equal("installed-version", None, "unobserved tool")


if __name__ == "__main__":
    unittest.main()
