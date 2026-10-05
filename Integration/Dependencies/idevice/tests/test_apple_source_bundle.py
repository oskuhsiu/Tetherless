"""Matching-source ZIP fixtures; opaque bytes only, no native tools or network."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import apple_source_bundle as bundle
from apply_patch import VerificationError, canonical_json, sha256


def make_archive(cache):
    cache.mkdir(parents=True, exist_ok=True)
    data = b"controlled authenticated crate archive bytes; never unpacked or executed\n"
    path = cache / "fixture-1.0.0.crate"
    path.write_bytes(data)
    return ('version = 4\n[[package]]\nname = "fixture"\nversion = "1.0.0"\n'
            'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
            f'checksum = "{sha256(data)}"\n').encode()


def write_workspace(source, lock, defaults, *, links=False):
    files = {"Cargo.toml": b'[workspace]\nmembers = ["ffi"]\n', "Cargo.lock": lock,
             "ffi/Cargo.toml": ("[features]\ndefault = " + json.dumps(defaults) + "\n").encode(),
             "ffi/src/lib.rs": b"// controlled source fixture\n", "LICENSE.txt": b"controlled upstream license\n",
             "swift/include/module.modulemap": b'module idevice { header "idevice.h" export * }\n'}
    for name, data in files.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    manifest = {"files": {name: sha256(data) for name, data in files.items()}, "symlinks": {}}
    if links:
        (source / "docs").mkdir()
        (source / "docs/LICENSE.txt").symlink_to("../LICENSE.txt")
        manifest["files"]["docs/LICENSE.txt"] = sha256(b"../LICENSE.txt")
        manifest["symlinks"]["docs/LICENSE.txt"] = "../LICENSE.txt"
    return manifest


def write_vendor(work, source):
    authenticated = {}
    for label, data in (("vendor", b"// controlled pristine source\n"), ("build-vendor", b"// controlled derived source\n")):
        files = {"fixture-1.0.0/src/lib.rs": data, "fixture-1.0.0/LICENSE": b"controlled crate license\n"}
        for name, content in files.items():
            path = work / label / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        authenticated[label] = {name: sha256(content) for name, content in files.items()}
    home = work / "cargo-home"
    home.mkdir(exist_ok=True)
    config = home / "config.toml"
    config.write_text("[net]\noffline=true\n")
    return {"vendor_directory": str(work / "vendor"), "authenticated_inputs": authenticated["vendor"],
            "cargo_home": str(home), "cargo_config": str(config), "cargo_config_sha256": sha256(config.read_bytes()),
            "workspace_lock_sha256": sha256((source / "Cargo.lock").read_bytes()), "nested_metadata_frozen": True,
            "derived_build": {"directory": str(work / "build-vendor"), "authenticated_inputs": authenticated["build-vendor"]}}


class SourceBundleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='Apple source fixture " 🌿 ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "work/source"
        self.cache = self.root / "cache"
        self.manifest = write_workspace(self.source, make_archive(self.cache), ["afc", "house_arrest"], links=True)
        self.vendor = write_vendor(self.source.parent, self.source)
        self.recipe = self.root / "recipe"
        self.recipe.mkdir()
        (self.recipe / "recipe.py").write_text("# controlled explicit recipe\n")
        self.recipe_files = {"recipe.py": sha256((self.recipe / "recipe.py").read_bytes())}
        self.output = self.root / "corresponding-source.zip"
        self.staging = self.root / "staging"

    def create(self):
        return bundle.create_source_bundle(source=self.source, source_manifest=self.manifest, vendor_receipt=self.vendor,
            crate_cache=self.cache, recipe_root=self.recipe, recipe_files=self.recipe_files,
            output=self.output, staging=self.staging)

    def test_bundle_contains_exact_source_vendor_archives_recipe_licenses_and_symlinks(self):
        (self.recipe / "unlisted-provider-payload").write_bytes(b"must not ship")
        receipt = self.create()
        with zipfile.ZipFile(self.output) as archive:
            names = set(archive.namelist())
            expected = {"workspace/" + name for name in self.manifest["files"]}
            expected |= {"vendor/pristine/" + name for name in self.vendor["authenticated_inputs"]}
            expected |= {"vendor/derived/" + name for name in self.vendor["derived_build"]["authenticated_inputs"]}
            expected |= {"crate-archives/fixture-1.0.0.crate", "recipe/recipe.py", "source-provenance.json"}
            self.assertEqual(names, expected)
            for name in ("LICENSE.txt", "Cargo.lock", "ffi/src/lib.rs"):
                self.assertEqual(archive.read("workspace/" + name), (self.source / name).read_bytes())
            self.assertEqual(archive.read("crate-archives/fixture-1.0.0.crate"), (self.cache / "fixture-1.0.0.crate").read_bytes())
            self.assertEqual(archive.read("workspace/docs/LICENSE.txt"), b"../LICENSE.txt")
            self.assertEqual((archive.getinfo("workspace/docs/LICENSE.txt").external_attr >> 16) & 0o170000, 0o120000)
            metadata = json.loads(archive.read("source-provenance.json"))
            self.assertFalse(metadata["target_or_probe_binaries_included"])
            self.assertEqual(metadata["recipe_files"], self.recipe_files)
            self.assertEqual(metadata["vendor_layout"]["authenticated_inputs"], self.vendor["authenticated_inputs"])
            for info in archive.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
        self.assertEqual(receipt["sha256"], sha256(self.output.read_bytes()))
        self.assertEqual(receipt["crate_archive_count"], 1)
        self.assertEqual(receipt["recipe_file_count"], 1)
        self.assertFalse(receipt["opaque_provider_payloads_included"])
        self.assertTrue(receipt["logical_vendor_keys_preserved"])

    def test_generated_target_probe_provider_and_derived_outputs_are_never_shipped(self):
        extras = [self.source / "target/release/opaque-artifact", self.source / "provider/opaque-payload",
                  self.source / "unregistered-probe", self.source.parent / "build-vendor/fixture-1.0.0/target/opaque-artifact"]
        for path in extras:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"opaque generated artifact must not ship\n")
        try:
            self.create()
        except VerificationError:
            self.assertFalse(self.output.exists())
        else:
            with zipfile.ZipFile(self.output) as archive:
                self.assertFalse(any(b"opaque generated artifact" in archive.read(name) for name in archive.namelist()))

    def test_known_generated_headers_are_hashed_and_copied_without_other_outputs(self):
        generated = {
            self.source / "ffi/idevice.h": ("workspace/ffi/idevice.h", b"// controlled generated FFI header\n"),
            self.source / "cpp/include/idevice.h": ("workspace/cpp/include/idevice.h", b"// controlled generated C++ header\n"),
            self.source.parent / "build-vendor/plist_ffi-0.1.6/plist.h": ("vendor/derived/plist_ffi-0.1.6/plist.h", b"// controlled generated plist header\n"),
        }
        for path, (_name, data) in generated.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        unrelated = self.source.parent / "build-vendor/plist_ffi-0.1.6/generated-probe"
        unrelated.write_bytes(b"opaque unrelated output\n")
        self.create()
        with zipfile.ZipFile(self.output) as archive:
            metadata = json.loads(archive.read("source-provenance.json"))
            for _path, (name, data) in generated.items():
                self.assertEqual(archive.read(name), data)
                if name.startswith("workspace/"):
                    self.assertEqual(metadata["bundled_workspace_files"][name.removeprefix("workspace/")], sha256(data))
                else:
                    self.assertEqual(metadata["bundled_derived_vendor_files"][name.removeprefix("vendor/derived/")], sha256(data))
            self.assertNotIn("vendor/derived/plist_ffi-0.1.6/generated-probe", archive.namelist())
            self.assertFalse(metadata["unregistered_build_outputs_copied"])

    def test_same_inputs_produce_identical_zip_bytes(self):
        self.create()
        before = self.output.read_bytes()
        self.output = self.root / "repeat.zip"
        self.staging = self.root / "repeat-staging"
        self.create()
        self.assertEqual(self.output.read_bytes(), before)

    def test_changed_workspace_pristine_derived_archive_or_recipe_prevents_output(self):
        for name, path in (("workspace", self.source / "Cargo.lock"),
                           ("pristine", self.source.parent / "vendor/fixture-1.0.0/src/lib.rs"),
                           ("derived", self.source.parent / "build-vendor/fixture-1.0.0/src/lib.rs"),
                           ("archive", self.cache / "fixture-1.0.0.crate"), ("recipe", self.recipe / "recipe.py")):
            with self.subTest(input=name):
                before = path.read_bytes()
                path.write_bytes(b"controlled changed bytes\n")
                try:
                    with self.assertRaises(VerificationError):
                        self.create()
                    self.assertFalse(self.output.exists())
                    self.assertFalse(self.staging.exists())
                finally:
                    path.write_bytes(before)

    def test_missing_or_symlink_crate_archive_is_rejected(self):
        path = self.cache / "fixture-1.0.0.crate"
        moved = self.cache / "archive-backup"
        path.rename(moved)
        with self.assertRaises(VerificationError):
            self.create()
        path.symlink_to(moved)
        with self.assertRaises(VerificationError):
            self.create()
        self.assertFalse(self.output.exists())

    def test_empty_unsafe_or_unlisted_recipe_map_does_not_expand_bundle(self):
        self.recipe_files = {}
        with self.assertRaises(VerificationError):
            self.create()
        self.recipe_files = {"../cache/fixture-1.0.0.crate": sha256((self.cache / "fixture-1.0.0.crate").read_bytes())}
        with self.assertRaises(VerificationError):
            self.create()
        self.assertFalse(self.output.exists())

    def test_existing_or_symlink_destinations_are_never_overwritten(self):
        self.output.write_bytes(b"previous archive")
        with self.assertRaises(VerificationError):
            self.create()
        self.assertEqual(self.output.read_bytes(), b"previous archive")
        self.output.unlink()
        self.staging.symlink_to(self.recipe, target_is_directory=True)
        with self.assertRaises(VerificationError):
            self.create()
        self.assertFalse(self.output.exists())

    def test_copied_input_identity_is_rechecked_before_zip(self):
        original = bundle.shutil.copyfile
        def corrupt_copy(source, destination, *args, **kwargs):
            result = original(source, destination, *args, **kwargs)
            if Path(destination) == self.staging / "crate-archives/fixture-1.0.0.crate":
                Path(destination).write_bytes(b"controlled copy mutation\n")
            return result
        with patch.object(bundle.shutil, "copyfile", side_effect=corrupt_copy), self.assertRaises(VerificationError):
            self.create()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
