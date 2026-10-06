"""Portable synthetic tool identity tests. No Rust/LLVM/native binary executes."""
from pathlib import Path
import copy
import json
import subprocess
import textwrap
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import rust_symbol_reader as reader

RUST_VERSION = "rustc 1.98.1 (synthetic fixture)\nrelease: 1.98.1\nhost: aarch64-apple-darwin\nLLVM version: 22.1.8"
NM_VERSION = "llvm-nm, compatible with GNU nm\nLLVM (http://llvm.org/):\n  LLVM version 22.1.8-rust-1.98.1-stable\n  Optimized build."


class ReaderFixture:
    def __init__(self, root):
        self.root = Path(root).resolve() / "synthetic-rust-toolchain"
        self.rustc = self.root / "bin/rustc"
        self.nm = self.root / "lib/rustlib/aarch64-apple-darwin/bin/llvm-nm"
        self.manifest = self.root / "lib/rustlib/manifest-llvm-tools-preview-aarch64-apple-darwin"
        self.components = self.root / "lib/rustlib/components"
        for path, data in ((self.rustc, b"opaque synthetic compiler, never executed"),
                           (self.nm, b"opaque synthetic reader, never executed"),
                           (self.manifest, b"file:lib/rustlib/aarch64-apple-darwin/bin/llvm-nm\n"),
                           (self.components, b"llvm-tools-preview-aarch64-apple-darwin\n")):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.calls = []

    def capture(self, argv, name):
        self.calls.append((argv, name))
        expected = {(str(self.rustc), "--version", "--verbose"): RUST_VERSION,
                    (str(self.rustc), "--print", "sysroot"): str(self.root),
                    (str(self.nm), "--version"): NM_VERSION}
        return expected[tuple(argv)]

    def observe(self):
        return reader.observe(str(self.rustc), self.capture)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.f = ReaderFixture(Path(self.tmp.name))

    def test_resolves_only_pinned_compiler_host_component(self):
        value = self.f.observe()
        self.assertEqual(value["contract"], reader.CONTRACT)
        self.assertEqual(value["llvm_nm"]["path"], str(self.f.nm))
        self.assertEqual(len(self.f.calls), 3)
        self.assertEqual(reader.scan_command(value, "/opaque/full.a"),
            [str(self.f.nm), "--extern-only", "--defined-only", "--format=just-symbols", "/opaque/full.a"])

    def test_absent_component_never_falls_back_to_path_or_xcode(self):
        self.f.manifest.unlink()
        with self.assertRaises(ValueError): self.f.observe()
        self.assertEqual(len(self.f.calls), 2)

    def test_wrong_or_duplicate_component_membership_fails(self):
        for path in (self.f.manifest, self.f.components):
            original = path.read_bytes()
            for data in (b"wrong component\n", original * 2):
                path.write_bytes(data)
                with self.assertRaises(ValueError): self.f.observe()
            path.write_bytes(original)

    def test_missing_tool_or_symlink_fails(self):
        self.f.nm.unlink()
        with self.assertRaises(ValueError): self.f.observe()
        self.f.nm.symlink_to(self.f.rustc)
        with self.assertRaises(ValueError): self.f.observe()

    def test_reader_or_metadata_change_is_rejected(self):
        value = self.f.observe()
        for path in (self.f.nm, self.f.rustc, self.f.manifest, self.f.components):
            original = path.read_bytes()
            path.write_bytes(original + b"changed")
            with self.assertRaises(ValueError): reader.audit_local(value)
            path.write_bytes(original)

    def test_path_version_host_and_hash_mutations_are_rejected(self):
        value = self.f.observe()
        changes = [lambda x: x["contract"].update(rust_release="1.99.0"),
                   lambda x: x["llvm_nm"].update(path="/usr/bin/nm"),
                   lambda x: x["llvm_nm"].update(sha256=""),
                   lambda x: x["rustc"].update(version=RUST_VERSION.replace("aarch64-apple-darwin", "x86_64-apple-darwin")),
                   lambda x: x["rustc"].update(version=RUST_VERSION.replace("22.1.8", "17.0.0")),
                   lambda x: x["llvm_nm"].update(version=NM_VERSION.replace("22.1.8", "17.0.0")),
                   lambda x: x["llvm_nm"].update(version=NM_VERSION.replace("22.1.8", "22.1.80"))]
        for change in changes:
            modified = copy.deepcopy(value); change(modified)
            with self.assertRaises(ValueError): reader.validate_receipt(modified)

    def test_optional_official_stable_suffix_is_exact(self):
        value = self.f.observe()
        value["llvm_nm"]["version"] = NM_VERSION.replace("-rust-1.98.1-stable", "")
        reader.validate_receipt(value)
        for suffix in ("-rust-1.99.0-stable", "-rust-1.98.1-nightly", "-rust-dev", "-unknown"):
            value["llvm_nm"]["version"] = NM_VERSION.replace("-rust-1.98.1-stable", suffix)
            with self.assertRaises(ValueError): reader.validate_receipt(value)

    def test_malformed_receipt_fields_fail_as_value_errors(self):
        for change in (lambda x: x.update(sysroot=None), lambda x: x.update(llvm_nm=[]),
                       lambda x: x["llvm_nm"].update(sha256=None), lambda x: x["rustc"].update(version=None)):
            value = self.f.observe(); change(value)
            with self.assertRaises(ValueError): reader.validate_receipt(value)

    def test_reader_changed_during_version_command_fails(self):
        def capture(argv, name):
            result = self.f.capture(argv, name)
            if name == "toolchain-llvm-nm.txt": self.f.nm.write_bytes(b"changed during read")
            return result
        with self.assertRaises(ValueError): reader.observe(str(self.f.rustc), capture)

    def test_nonzero_or_incomplete_capture_cannot_produce_receipt(self):
        for failed in ("toolchain-symbol-rustc.txt", "toolchain-symbol-sysroot.txt", "toolchain-llvm-nm.txt"):
            def capture(argv, name):
                if name == failed: raise ValueError("bounded capture rejected partial output")
                return self.f.capture(argv, name)
            with self.assertRaises(ValueError): reader.observe(str(self.f.rustc), capture)

    def test_workflow_scalar_branches_preserve_each_lane_without_empty_arrays(self):
        repository = ROOT.parents[2]
        workflow = (repository / ".github/workflows/pairing-components.yml").read_text()
        start = workflow.index("          rustup --version > .proof/evidence/rustup-version.txt")
        end = workflow.index("\n      - name: Acquire only locked registry crates", start)
        block = textwrap.dedent(workflow[start:end])
        self.assertNotIn("READER_ARGS", block)
        self.assertNotIn("[@]", block)
        # Execute the exact workflow shell with harmless local functions only.
        # No rustup, Python recorder, component install or native tool is run.
        script = ("set -euo pipefail\n"
                  "rustup() { printf '%s\\n' \"rustup:$*\" >> \"$COMMANDS\"; }\n"
                  "python3() { printf '%s\\n' \"python3:$*\" >> \"$COMMANDS\"; }\n" + block)
        for proof in ("apple-producer", "acquisition-transcript", "host-transcript"):
            with self.subTest(proof=proof), tempfile.TemporaryDirectory() as temporary:
                work = Path(temporary)
                (work / ".proof/evidence").mkdir(parents=True)
                log = work / "commands.txt"
                env = {"PATH": "/usr/bin:/bin", "NATIVE_PROOF": proof, "COMMANDS": str(log)}
                completed = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-c", script],
                    cwd=work, env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                calls = log.read_text().splitlines()
                expected = ["rustup:--version",
                    "rustup:toolchain install 1.98.1 --profile minimal --no-self-update --target aarch64-apple-ios,aarch64-apple-ios-sim"]
                if proof == "apple-producer":
                    expected += ["rustup:component add --toolchain 1.98.1 llvm-tools",
                                 "rustup:component list --toolchain 1.98.1 --installed"]
                command = "python3:Integration/Dependencies/idevice/record_toolchain.py"
                if proof == "apple-producer": command += " --symbol-reader"
                expected += [command + " --output .proof/evidence/toolchain-lock.observed.json"]
                self.assertEqual(calls, expected)

    def test_recipe_workflow_and_consumer_contract_are_bound(self):
        index = json.loads((ROOT / "apple-recipe-files.json").read_bytes())
        for path in ("rust_symbol_reader.py", "record_toolchain.py", "build_pairing_apple.py", "tests/test_rust_symbol_reader.py"):
            self.assertEqual(index[path], reader.digest(ROOT / path))
        repository = ROOT.parents[2]
        contract = json.loads((repository / "Integration/pairing-ios-diagnostic/input-contract.json").read_bytes())
        self.assertEqual(contract["symbol_reader"], reader.CONTRACT)
        self.assertEqual(contract["apple_recipe_index_sha256"], reader.digest(ROOT / "apple-recipe-files.json"))
        workflow = repository / contract["retained_producer"]["workflow_path"]
        self.assertEqual(contract["retained_producer"]["workflow_sha256"], reader.digest(workflow))
        self.assertIn('rustup component add --toolchain 1.98.1 llvm-tools', workflow.read_text())
        self.assertIn('if [ "$NATIVE_PROOF" = apple-producer ]', workflow.read_text())


if __name__ == "__main__": unittest.main()
