"""Portable namespace boundaries, not Apple build/link/device acceptance.

Rust, C shim, archive and nm fixtures below are deliberately synthetic. The
header checks also use the repository's frozen upstream/ffi/plist.h unchanged.
Optional C checks invoke only the host compiler's syntax-only mode: they never
build a native dependency, link a provider, or execute generated code.
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ffi_namespace as namespace
import mixed_provider
from apply_patch import VerificationError, canonical_json, sha256


RUST_SOURCE = b'''// Synthetic fixture: preserve names, cfgs, layouts and bodies.
#[repr(C)]
pub struct Pair { pub left: u32, pub right: *mut u8 }

#[cfg(feature = "alpha")]
#[unsafe(no_mangle)]
pub unsafe extern "C" fn plist_alpha(value: *mut Pair) -> i32 {
    // plist_alpha must remain an internal Rust identifier.
    let label = "plist_alpha and tetherless_native_plist_alpha";
    let _ = label;
    unsafe { (*value).left as i32 }
}

#[unsafe(no_mangle)]
#[cfg(feature = "beta")]
pub extern "C" fn plist_beta(value: u32) -> u32 {
    value.wrapping_add(7)
}

#[unsafe(no_mangle)]
pub extern "C" fn tetherless_pairing_fixture(value: u32) -> u32 {
    plist_beta(value)
}
'''
RUST_NAMES = {name: "tetherless_native_" + name for name in ("plist_alpha", "plist_beta")}
# Independent literal oracle; do not compute expected output using the helper
# being tested. The attribute and its position are the only intended changes.
RUST_POSTIMAGE = RUST_SOURCE.replace(
    b'#[unsafe(no_mangle)]\npub unsafe extern "C" fn plist_alpha',
    b'#[unsafe(export_name = "tetherless_native_plist_alpha")]\npub unsafe extern "C" fn plist_alpha',
).replace(
    b'#[unsafe(no_mangle)]\n#[cfg(feature = "beta")]',
    b'#[unsafe(export_name = "tetherless_native_plist_beta")]\n#[cfg(feature = "beta")]',
)

C_SHIM = b'''/* Synthetic shim: plist_access_path and plist_access_path_shim. */
#include <stdarg.h>
typedef void *plist_t;
extern plist_t plist_access_path_shim(plist_t, unsigned, const void **);
static const char *label = "plist_access_pathv \\"plist_access_path\\"";
plist_t plist_access_path(plist_t node, unsigned length, ...) {
    const void *path[2] = {node, 0};
    return plist_access_path_shim(node, length, path);
}
plist_t plist_access_pathv(plist_t node, unsigned length, va_list args) {
    const void *path[2] = {va_arg(args, const void *), 0};
    return plist_access_path_shim(node, length, path);
}
'''
C_NAMES = {name: "tetherless_native_" + name for name in (
    "plist_access_path", "plist_access_pathv", "plist_access_path_shim")}
C_POSTIMAGE = C_SHIM.replace(
    b'extern plist_t plist_access_path_shim(', b'extern plist_t tetherless_native_plist_access_path_shim('
).replace(
    b'plist_t plist_access_path(', b'plist_t tetherless_native_plist_access_path('
).replace(
    b'plist_t plist_access_pathv(', b'plist_t tetherless_native_plist_access_pathv('
).replace(
    b'return plist_access_path_shim(', b'return tetherless_native_plist_access_path_shim('
)


def source_row(before=RUST_SOURCE, after=RUST_POSTIMAGE, names=None, kind="exports"):
    return {"before_sha256": sha256(before), "after_sha256": sha256(after),
            kind: dict(RUST_NAMES if names is None else names)}


def small_contract(workspace=None):
    return {"schema": 1, "prefix": "tetherless_native_", "preserved_prefix": "tetherless_",
            "workspace": {} if workspace is None else workspace}


class TemporaryFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="FFI namespace fixture ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write_contract(self, contract):
        path = self.root / namespace.CONTRACT_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        data = canonical_json(contract)
        path.write_bytes(data)
        return sha256(data)


class NamespaceContractTests(TemporaryFixture):
    def test_frozen_contract_has_655_rust_exports_and_two_c_exports_plus_reference(self):
        contract = namespace.load_contract()
        rust_names = [name for role in ("workspace", "vendor")
                      for row in contract[role].values() for name in row.get("exports", {})]
        self.assertEqual(len(rust_names), 655)
        self.assertEqual(len(set(rust_names)), 655)
        for role in ("workspace", "vendor"):
            for row in contract[role].values():
                for old, new in row.get("exports", row.get("c_identifiers", {})).items():
                    self.assertFalse(old.startswith("tetherless_"))
                    self.assertEqual(new, "tetherless_native_" + old)
        c_rows = [row for row in contract["vendor"].values() if "c_identifiers" in row]
        self.assertEqual(len(c_rows), 1)
        self.assertEqual(c_rows[0]["c_identifiers"], C_NAMES)
        self.assertNotIn("PLIST_OPT_COERCE", contract["header_identifiers"])
        self.assertNotIn("TETHERLESS_NATIVE_PLIST_OPT_COERCE", contract["header_identifiers"].values())

    def test_each_target_pins_exactly_382_bijective_export_names(self):
        targets = namespace.load_contract()["expected_target_exports"]
        self.assertEqual(set(targets), {"aarch64-apple-ios", "aarch64-apple-ios-sim"})
        for target, row in targets.items():
            with self.subTest(target=target):
                self.assertEqual(len(row["before"]), 382)
                self.assertEqual(len(row["after"]), 382)
                self.assertEqual(len(set(row["before"])), 382)
                self.assertEqual(len(set(row["after"])), 382)
                self.assertEqual(row["after"], ["tetherless_native_" + name for name in row["before"]])

    def test_contract_identity_is_checked_before_use(self):
        contract = small_contract()
        digest = self.write_contract(contract)
        self.assertEqual(namespace.load_contract(self.root, digest), contract)
        with self.assertRaisesRegex(VerificationError, "contract identity"):
            namespace.load_contract(self.root, "0" * 64)
        (self.root / namespace.CONTRACT_PATH).write_bytes(canonical_json(contract) + b"\n")
        with self.assertRaisesRegex(VerificationError, "contract identity"):
            namespace.load_contract(self.root, digest)

    def test_unsupported_contract_schema_and_prefixes_fail_closed(self):
        for field, value in (("schema", 2), ("prefix", "other_"), ("preserved_prefix", "pairing_")):
            contract = small_contract()
            contract[field] = value
            digest = self.write_contract(contract)
            with self.subTest(field=field), self.assertRaisesRegex(VerificationError, "unsupported"):
                namespace.load_contract(self.root, digest)


class RustExportPostimageTests(unittest.TestCase):
    def test_only_export_attributes_change_and_inverse_is_byte_exact(self):
        before = bytes(RUST_SOURCE)
        row = source_row()
        result = namespace.source_postimage(before, row)
        self.assertEqual(result, RUST_POSTIMAGE)
        inverse = result
        for new in RUST_NAMES.values():
            inverse = inverse.replace(f'#[unsafe(export_name = "{new}")]'.encode(), b"#[unsafe(no_mangle)]")
        self.assertEqual(inverse, before)
        self.assertEqual(before, RUST_SOURCE)
        self.assertEqual(row, source_row())
        self.assertIn(b'fn plist_alpha(value: *mut Pair) -> i32', result)
        self.assertIn(b'#[unsafe(no_mangle)]\npub extern "C" fn tetherless_pairing_fixture', result)
        self.assertNotIn(b'fn tetherless_native_', result)

    def test_wrong_source_preimage_fails_before_any_rewrite(self):
        for data in (RUST_SOURCE + b"\n", RUST_SOURCE.replace(b"wrapping_add(7)", b"wrapping_add(8)")):
            with self.subTest(data=sha256(data)), self.assertRaisesRegex(VerificationError, "preimage"):
                namespace.source_postimage(data, source_row())

    def test_wrong_expected_postimage_is_rejected(self):
        row = source_row()
        row["after_sha256"] = "0" * 64
        with self.assertRaisesRegex(VerificationError, "postimage"):
            namespace.source_postimage(RUST_SOURCE, row)

    def test_second_application_is_not_silently_accepted(self):
        with self.assertRaisesRegex(VerificationError, "preimage"):
            namespace.source_postimage(RUST_POSTIMAGE, source_row())

    def test_missing_and_unregistered_exports_are_rejected(self):
        for names in ({"plist_alpha": RUST_NAMES["plist_alpha"]},
                      {**RUST_NAMES, "plist_extra": "tetherless_native_plist_extra"}):
            with self.subTest(names=names), self.assertRaisesRegex(VerificationError, "inventory"):
                namespace.source_postimage(RUST_SOURCE, source_row(names=names))

    def test_duplicate_rust_export_is_rejected_even_with_matching_preimage(self):
        source = RUST_SOURCE + b'#[unsafe(no_mangle)]\npub extern "C" fn plist_beta() {}\n'
        with self.assertRaisesRegex(VerificationError, "inventory"):
            namespace.source_postimage(source, source_row(before=source))

    def test_unrecognized_no_mangle_shape_fails_closed_in_registered_file(self):
        source = RUST_SOURCE + b'#[unsafe(no_mangle)]\nextern "C" fn private_export() {}\n'
        with self.assertRaisesRegex(VerificationError, "inventory"):
            namespace.source_postimage(source, source_row(before=source))

    def test_noncanonical_destination_and_preserved_export_mapping_are_rejected(self):
        cases = [{**RUST_NAMES, "plist_beta": "wrong_plist_beta"},
                 {**RUST_NAMES, "tetherless_pairing_fixture": "tetherless_native_tetherless_pairing_fixture"}]
        for names in cases:
            with self.subTest(names=names), self.assertRaisesRegex(VerificationError, "inventory"):
                namespace.source_postimage(RUST_SOURCE, source_row(names=names))

    def test_preserved_pairing_only_file_is_identical(self):
        source = b'#[unsafe(no_mangle)]\npub extern "C" fn tetherless_pairing_only() {}\n'
        self.assertEqual(namespace.source_postimage(source, source_row(source, source, {})), source)


class CShimPostimageTests(unittest.TestCase):
    def test_two_exports_and_rust_shim_reference_are_renamed_without_behavior_changes(self):
        row = source_row(C_SHIM, C_POSTIMAGE, C_NAMES, "c_identifiers")
        result = namespace.source_postimage(C_SHIM, row)
        self.assertEqual(result, C_POSTIMAGE)
        self.assertEqual(namespace.rename_c_identifiers(result, {new: old for old, new in C_NAMES.items()}), C_SHIM)
        self.assertEqual(result.count(b"return tetherless_native_plist_access_path_shim("), 2)
        self.assertIn(b'/* Synthetic shim: plist_access_path and plist_access_path_shim. */', result)
        self.assertIn(b'va_arg(args, const void *)', result)

    def test_missing_or_extra_c_shim_identifiers_are_rejected(self):
        for names in ({name: value for name, value in C_NAMES.items() if name != "plist_access_path_shim"},
                      {**C_NAMES, "plist_free": "tetherless_native_plist_free"}):
            with self.subTest(names=names), self.assertRaisesRegex(VerificationError, "shim inventory"):
                namespace.source_postimage(C_SHIM, source_row(C_SHIM, C_POSTIMAGE, names, "c_identifiers"))

    def test_c_preimage_and_postimage_hashes_are_independently_checked(self):
        row = source_row(C_SHIM, C_POSTIMAGE, C_NAMES, "c_identifiers")
        with self.assertRaisesRegex(VerificationError, "preimage"):
            namespace.source_postimage(C_SHIM + b"\n", row)
        row["after_sha256"] = sha256(C_POSTIMAGE + b"\n")
        with self.assertRaisesRegex(VerificationError, "postimage"):
            namespace.source_postimage(C_SHIM, row)

    def test_inverse_guard_rejects_preexisting_colliding_c_symbol(self):
        source = C_SHIM + b'void tetherless_native_plist_access_path(void);\n'
        row = source_row(source, C_POSTIMAGE, C_NAMES, "c_identifiers")
        with self.assertRaisesRegex(VerificationError, "shim behavior"):
            namespace.source_postimage(source, row)


class WorkspaceNamespaceTests(TemporaryFixture):
    def test_owned_workspace_copy_preserves_unrelated_inputs_and_pairing(self):
        files = {"ffi/src/example.rs": RUST_SOURCE, "Cargo.lock": b"locked dependencies\n",
                 "ffi/src/unchanged.rs": b"pub struct Layout { pub width: u32 }\n"}
        original = dict(files)
        contract = small_contract({"ffi/src/example.rs": source_row()})
        contract["preserved_workspace_exports"] = {"ffi/src/example.rs": {
            "sha256": sha256(RUST_SOURCE), "exports": ["tetherless_pairing_fixture"]}}
        digest = self.write_contract(contract)
        result = namespace.namespace_workspace(files, self.root, digest)
        self.assertEqual(files, original)
        self.assertIsNot(result, files)
        self.assertEqual(result, {**original, "ffi/src/example.rs": RUST_POSTIMAGE})

    def test_missing_registered_source_is_rejected(self):
        digest = self.write_contract(small_contract({"ffi/src/example.rs": source_row()}))
        with self.assertRaises((VerificationError, KeyError)):
            namespace.namespace_workspace({}, self.root, digest)

    def test_unregistered_public_export_in_new_file_is_rejected(self):
        digest = self.write_contract(small_contract())
        with self.assertRaisesRegex(VerificationError, "unregistered|inventory"):
            namespace.namespace_workspace({"ffi/src/new.rs": RUST_SOURCE}, self.root, digest)

    def test_unregistered_private_no_mangle_export_in_new_file_is_rejected(self):
        digest = self.write_contract(small_contract())
        source = b'#[unsafe(no_mangle)]\nextern "C" fn rogue() {}\n'
        with self.assertRaises(VerificationError):
            namespace.namespace_workspace({"ffi/src/new.rs": source}, self.root, digest)

    def test_unregistered_explicit_export_name_in_new_file_is_rejected(self):
        digest = self.write_contract(small_contract())
        source = b'#[unsafe(export_name = "rogue")]\npub extern "C" fn internal() {}\n'
        with self.assertRaises(VerificationError):
            namespace.namespace_workspace({"ffi/src/new.rs": source}, self.root, digest)

    def test_registered_pairing_export_remains_owned_and_unmodified(self):
        source = b'#[unsafe(no_mangle)]\npub extern "C" fn tetherless_pairing_new() {}\n'
        contract = small_contract()
        contract["preserved_workspace_exports"] = {"ffi/src/new.rs": {
            "sha256": sha256(source), "exports": ["tetherless_pairing_new"]}}
        digest = self.write_contract(contract)
        files = {"ffi/src/new.rs": source}
        self.assertEqual(namespace.namespace_workspace(files, self.root, digest), files)

    def test_unregistered_pairing_export_is_rejected(self):
        digest = self.write_contract(small_contract())
        source = b'#[unsafe(no_mangle)]\npub extern "C" fn tetherless_pairing_new() {}\n'
        with self.assertRaises(VerificationError):
            namespace.namespace_workspace({"ffi/src/new.rs": source}, self.root, digest)

    def test_registered_pairing_source_hash_is_required(self):
        source = b'#[unsafe(no_mangle)]\npub extern "C" fn tetherless_pairing_new() {}\n'
        contract = small_contract()
        contract["preserved_workspace_exports"] = {"ffi/src/new.rs": {
            "sha256": sha256(source), "exports": ["tetherless_pairing_new"]}}
        digest = self.write_contract(contract)
        with self.assertRaisesRegex(VerificationError, "preserved pairing"):
            namespace.namespace_workspace({"ffi/src/new.rs": source + b"\n"}, self.root, digest)


class VendorNamespaceTests(TemporaryFixture):
    CRATE = "plist_ffi-0.1.6"

    def setUp(self):
        super().setUp()
        self.pristine = self.root / "pristine"
        self.derived = self.root / "derived"
        self.archive = self.root / (self.CRATE + ".crate")
        self.archive.write_bytes(b"synthetic opaque archive fixture; never a real crate\n")
        self.archive_bytes = self.archive.read_bytes()
        self.archive_digest = sha256(self.archive_bytes)
        relative_files = {"src/lib.rs": RUST_SOURCE, "src/shims.c": C_SHIM,
                          "Cargo.lock": b"synthetic unchanged packaged lock\n",
                          "build.rs": b"fn main() {}\n"}
        checksum = {"package": self.archive_digest,
                    "files": {name: sha256(data) for name, data in relative_files.items()}}
        relative_files[".cargo-checksum.json"] = canonical_json(checksum)
        self.original_bytes = {self.CRATE + "/" + name: data for name, data in relative_files.items()}
        for name, data in self.original_bytes.items():
            path = self.pristine / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        shutil.copytree(self.pristine, self.derived)
        self.originals = {name: sha256(data) for name, data in self.original_bytes.items()}
        self.crates = {self.CRATE: self.archive_digest}
        self.contract = {"plist_crate_sha256": self.archive_digest, "vendor": {
            self.CRATE + "/src/lib.rs": source_row(),
            self.CRATE + "/src/shims.c": source_row(C_SHIM, C_POSTIMAGE, C_NAMES, "c_identifiers")}}

    def snapshot(self):
        return {path.relative_to(self.derived).as_posix(): path.read_bytes()
                for path in self.derived.rglob("*") if path.is_file()}

    def run_namespace(self):
        return namespace.namespace_vendor(self.derived, self.originals, self.crates, self.contract)

    def assert_rejected_without_writes(self, message):
        before = self.snapshot()
        with self.assertRaisesRegex(VerificationError, message):
            self.run_namespace()
        self.assertEqual(self.snapshot(), before)

    def test_derived_files_and_checksum_receipt_are_separate_from_pristine_inputs(self):
        receipt = self.run_namespace()
        checksum_name = self.CRATE + "/.cargo-checksum.json"
        self.assertEqual(set(receipt), set(self.contract["vendor"]) | {checksum_name})
        for name, row in receipt.items():
            self.assertEqual(row["before_sha256"], self.originals[name])
            self.assertEqual(row["after_sha256"], sha256((self.derived / name).read_bytes()))
            self.assertNotEqual(row["before_sha256"], row["after_sha256"])
        for name, data in self.original_bytes.items():
            self.assertEqual((self.pristine / name).read_bytes(), data)
            if name not in receipt:
                self.assertEqual((self.derived / name).read_bytes(), data)
        self.assertEqual(self.archive.read_bytes(), self.archive_bytes)
        checksum = json.loads((self.derived / checksum_name).read_bytes())
        self.assertEqual(checksum["package"], self.archive_digest)
        for relative, digest in checksum["files"].items():
            self.assertEqual(digest, sha256((self.derived / self.CRATE / relative).read_bytes()))
        self.assertEqual((self.derived / self.CRATE / "src/lib.rs").read_bytes(), RUST_POSTIMAGE)
        self.assertEqual((self.derived / self.CRATE / "src/shims.c").read_bytes(), C_POSTIMAGE)

    def test_missing_or_wrong_archive_identity_is_rejected_before_writes(self):
        for crates in ({}, {self.CRATE: "0" * 64}):
            self.crates = crates
            self.assert_rejected_without_writes("exact plist_ffi crate archive")

    def test_wrong_authenticated_source_inventory_is_rejected_before_writes(self):
        self.originals[self.CRATE + "/src/shims.c"] = "0" * 64
        self.assert_rejected_without_writes("inventory preimage")

    def test_source_bytes_mismatch_is_rejected_before_writes(self):
        (self.derived / self.CRATE / "src/shims.c").write_bytes(C_SHIM + b"\n")
        self.assert_rejected_without_writes("source preimage")

    def test_late_postimage_failure_never_partially_mutates_earlier_file(self):
        self.contract["vendor"][self.CRATE + "/src/shims.c"]["after_sha256"] = "0" * 64
        self.assert_rejected_without_writes("source postimage")

    def test_checksum_bytes_mismatch_is_rejected_before_writes(self):
        path = self.derived / self.CRATE / ".cargo-checksum.json"
        path.write_bytes(path.read_bytes() + b"\n")
        self.assert_rejected_without_writes("checksum preimage")

    def test_wrong_package_or_file_checksum_is_rejected_before_writes(self):
        name = self.CRATE + "/.cargo-checksum.json"
        original = json.loads(self.original_bytes[name])
        for kind in ("package", "file"):
            checksum = deepcopy(original)
            if kind == "package":
                checksum["package"] = "0" * 64
            else:
                checksum["files"]["src/shims.c"] = "0" * 64
            data = canonical_json(checksum)
            (self.derived / name).write_bytes(data)
            self.originals[name] = sha256(data)
            with self.subTest(kind=kind):
                self.assert_rejected_without_writes("archive identity|file checksum")

    def test_source_symlink_is_rejected_without_touching_target(self):
        path = self.derived / self.CRATE / "src/shims.c"
        outside = self.root / "outside.c"
        outside.write_bytes(C_SHIM)
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaisesRegex(VerificationError, "symlink"):
            self.run_namespace()
        self.assertEqual(outside.read_bytes(), C_SHIM)
        self.assertEqual((self.derived / self.CRATE / "src/lib.rs").read_bytes(), RUST_SOURCE)


class PublicHeaderNamespaceTests(TemporaryFixture):
    def setUp(self):
        super().setUp()
        self.contract = namespace.load_contract()

    def test_comments_literals_escapes_and_identifier_boundaries_are_preserved(self):
        source = (b'// plist_t plist_free PLIST_INT\n'
                  b'/* plist_t\n PLIST_INT */\n'
                  b'const char *s = "plist_t \\"plist_free\\"";\n'
                  b"const int quote = '\\'';\n"
                  b'plist_t item; void plist_free(plist_t);\n'
                  b'int plist_free_extra; int XPLIST_INT;\n')
        expected = source.replace(b'plist_t item; void plist_free(plist_t);',
                                  b'tetherless_native_plist_t item; void tetherless_native_plist_free(tetherless_native_plist_t);')
        self.assertEqual(namespace.public_header(source, self.contract), expected)

    def test_token_paste_macro_prefix_is_namespaced(self):
        source = (b'#define _PLIST_IS_TYPE(p, type) (plist_get_node_type(p) == PLIST_##type)\n'
                  b'#define PLIST_IS_INT(p) _PLIST_IS_TYPE(p, INT)\n')
        expected = (b'#define TETHERLESS_NATIVE__PLIST_IS_TYPE(p, type) (tetherless_native_plist_get_node_type(p) == TETHERLESS_NATIVE_PLIST_##type)\n'
                    b'#define TETHERLESS_NATIVE_PLIST_IS_INT(p) TETHERLESS_NATIVE__PLIST_IS_TYPE(p, INT)\n')
        self.assertEqual(namespace.public_header(source, self.contract), expected)

    def test_existing_generated_namespaced_declaration_and_appended_old_declaration_coexist(self):
        source = b'void tetherless_native_plist_free(void *node);\nvoid plist_free(void *node);\n'
        expected = b'void tetherless_native_plist_free(void *node);\n' * 2
        self.assertEqual(namespace.public_header(source, self.contract), expected)

    def test_coerce_in_comments_and_literals_is_not_a_declared_capability(self):
        source = (b'// PLIST_OPT_COERCE is intentionally unsupported\n'
                  b'const char *note = "PLIST_OPT_COERCE";\nplist_t item;\n')
        expected = source.replace(b'plist_t item;', b'tetherless_native_plist_t item;')
        self.assertEqual(namespace.public_header(source, self.contract), expected)

    def test_real_coerce_declaration_is_rejected_in_either_namespace(self):
        for name in ("PLIST_OPT_COERCE", "TETHERLESS_NATIVE_PLIST_OPT_COERCE"):
            source = f'enum {{ {name} = 1 << 4 }};\n'.encode()
            with self.subTest(name=name), self.assertRaisesRegex(VerificationError, "COERCE"):
                namespace.public_header(source, self.contract)

    def test_frozen_old_header_is_token_only_reversible_and_has_no_coerce(self):
        source = (ROOT / "upstream/ffi/plist.h").read_bytes()
        result = namespace.public_header(source, self.contract)
        inverse = {new: old for old, new in self.contract["header_identifiers"].items()}
        self.assertEqual(namespace.rename_c_identifiers(result, inverse), source)
        self.assertNotIn(b"PLIST_OPT_COERCE", result)
        self.assertIn(b"#ifndef TETHERLESS_NATIVE_LIBPLIST_H", result)
        self.assertIn(b"TETHERLESS_NATIVE_PLIST_##__plist_type", result)

    def syntax_check(self, source):
        compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if compiler is None:
            self.skipTest("host C compiler unavailable; Python namespace checks still run")
        path = self.root / "probe.c"
        path.write_text(source)
        result = subprocess.run([compiler, "-std=c11", "-Werror", "-fsyntax-only", str(path)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_old_and_namespaced_headers_coexist_in_both_orders_and_retain_all_enum_values(self):
        original = (ROOT / "upstream/ffi/plist.h").read_bytes()
        (self.root / "old.h").write_bytes(original)
        (self.root / "native.h").write_bytes(namespace.public_header(original, self.contract))
        values = {"NONE": -1, "BOOLEAN": 0, "INT": 1, "REAL": 2, "STRING": 3,
                  "ARRAY": 4, "DICT": 5, "DATE": 6, "DATA": 7, "KEY": 8, "UID": 9, "NULL": 10,
                  "UINT": 1, "ERR_SUCCESS": 0, "ERR_INVALID_ARG": -1, "ERR_FORMAT": -2,
                  "ERR_PARSE": -3, "ERR_NO_MEM": -4, "ERR_IO": -5, "ERR_CIRCULAR_REF": -6,
                  "ERR_MAX_NESTING": -7, "ERR_UNKNOWN": -255,
                  "FORMAT_NONE": 0, "FORMAT_XML": 1, "FORMAT_BINARY": 2, "FORMAT_JSON": 3,
                  "FORMAT_OSTEP": 4, "FORMAT_PRINT": 10, "FORMAT_LIMD": 11, "FORMAT_PLUTIL": 12,
                  "OPT_NONE": 0, "OPT_COMPACT": 1, "OPT_PARTIAL_DATA": 2,
                  "OPT_NO_NEWLINE": 4, "OPT_INDENT": 8}
        assertions = "\n".join(
            f'_Static_assert({prefix}PLIST_{name} == {value}, "{prefix}{name}");'
            for prefix in ("", "TETHERLESS_NATIVE_") for name, value in values.items())
        assertions += '''
_Static_assert(PLIST_OPT_INDENT_BY(2) == (2 << 24), "old indentation bits");
_Static_assert(TETHERLESS_NATIVE_PLIST_OPT_INDENT_BY(2) == (2 << 24), "native indentation bits");
_Static_assert(sizeof(plist_t) == sizeof(tetherless_native_plist_t), "node pointer width");
_Static_assert(sizeof(plist_write_options_t) == sizeof(tetherless_native_plist_write_options_t), "option width");
int old_type_macro(plist_t node) { return PLIST_IS_INT(node); }
int native_type_macro(tetherless_native_plist_t node) { return TETHERLESS_NATIVE_PLIST_IS_INT(node); }
'''
        for first, second in (("old.h", "native.h"), ("native.h", "old.h")):
            with self.subTest(first=first):
                self.syntax_check(f'#include "{first}"\n#include "{second}"\n' + assertions)


class NativeSymbolInventoryTests(unittest.TestCase):
    def setUp(self):
        self.contract = namespace.load_contract()

    def nm_text(self, target, extra=()):
        names = ["_" + name for name in self.contract["expected_target_exports"][target]["after"]]
        return "\nmember.o:\n" + "\n".join(names + list(extra)) + "\n"

    def test_exact_nm_export_inventory_accepts_each_target_and_records_input_hash(self):
        for target in self.contract["expected_target_exports"]:
            text = self.nm_text(target, ("_tetherless_pairing_fixture", "_unrelated_dependency_symbol"))
            with self.subTest(target=target):
                receipt = mixed_provider.check_symbols(text, self.contract, target)
                self.assertEqual(receipt["target"], target)
                self.assertEqual(receipt["namespaced_export_count"], 382)
                self.assertTrue(receipt["old_exports_absent"])
                self.assertTrue(receipt["expected_exports_present"])
                self.assertEqual(receipt["nm_stdout_sha256"], sha256(text.encode()))

    def test_every_missing_expected_export_is_rejected_for_each_target(self):
        for target, row in self.contract["expected_target_exports"].items():
            baseline = self.nm_text(target)
            for name in row["after"]:
                with self.subTest(target=target, missing=name), self.assertRaises(VerificationError):
                    mixed_provider.check_symbols(baseline.replace("_" + name + "\n", ""), self.contract, target)

    def test_every_registered_old_rust_or_c_alias_is_rejected(self):
        old_names = {name for role in ("workspace", "vendor") for row in self.contract[role].values()
                     for name in row.get("exports", row.get("c_identifiers", {}))}
        for target in self.contract["expected_target_exports"]:
            for name in sorted(old_names):
                with self.subTest(target=target, alias=name), self.assertRaises(VerificationError):
                    mixed_provider.check_symbols(self.nm_text(target, ("_" + name,)), self.contract, target)

    def test_unexpected_namespaced_export_is_rejected_for_each_target(self):
        for target in self.contract["expected_target_exports"]:
            text = self.nm_text(target, ("_tetherless_native_unregistered",))
            with self.subTest(target=target), self.assertRaises(VerificationError):
                mixed_provider.check_symbols(text, self.contract, target)

    def test_empty_output_or_unknown_target_never_yields_success(self):
        for target in self.contract["expected_target_exports"]:
            with self.subTest(target=target), self.assertRaises(VerificationError):
                mixed_provider.check_symbols("", self.contract, target)
        with self.assertRaises((VerificationError, KeyError)):
            mixed_provider.check_symbols("", self.contract, "unknown-target")


if __name__ == "__main__":
    unittest.main()
