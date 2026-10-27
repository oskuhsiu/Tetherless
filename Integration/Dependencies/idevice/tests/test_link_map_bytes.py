"""Raw ld-map dialect regressions, never native execution or provider admission."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import retained_c_provider as c

FIXTURES = Path(__file__).parent / "fixtures"


class RawLinkMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = json.loads((FIXTURES / "mixed-provider-raw-byte-excerpt.json").read_bytes())
        cls.raw = (FIXTURES / cls.context["excerpt"]["file"]).read_bytes()

    def minimal(self, extra=b""):
        return (b"# Object files:\n[ 1] /fixture/c.a(c.o)\n[ 2] /fixture/rust.a(rust.o)\n"
                b"# Sections:\n# Address Size Segment Section\n0x1000 0x20 __TEXT __text\n"
                b"# Symbols:\n# Address Size File Name\n0x1000 0x10 [ 1] _required\n" + extra +
                b"# Dead Stripped Symbols:\n# Size File Name\n")

    def proof(self, raw):
        return c.link_ownership(raw, "/fixture/c.a", ["_required"])

    def test_genuine_excerpt_retains_invalid_utf8_and_all_control_payload_rows(self):
        meta = self.context["excerpt"]
        self.assertLess(len(self.raw), 128 * 1024)
        self.assertEqual(len(self.raw), meta["bytes"])
        self.assertEqual(c.digest(self.raw), meta["sha256"])
        self.assertEqual(len(self.raw.split(b"\n")) - 1, meta["lf_rows"])
        with self.assertRaises(UnicodeDecodeError):
            self.raw.decode("utf-8")
        rows = [row for row in self.raw.split(b"\n") if b"literal string: " in row]
        self.assertEqual(len(rows), 606)
        for control in (b"\x0b", b"\x0c", b"\x1c", b"\x1d", b"\x1e"):
            self.assertTrue(any(control in row for row in rows))
        # The excerpt deliberately preserves all 29 real duplicated C names.
        objects, live = c.parse_link_map(self.raw)
        counts = Counter(name for _owner, name in live)
        self.assertEqual(set(counts), set(self.context["c_symbols"]))
        self.assertEqual(sorted(name for name, count in counts.items() if count > 1),
                         self.context["duplicate_required_names"])
        self.assertEqual(len(self.context["duplicate_required_names"]), 29)
        for name in self.context["duplicate_required_names"]:
            owners = [objects[owner] for owner, symbol in live if symbol == name]
            self.assertEqual(len(owners), 2)
            self.assertTrue(any("libidevice_ffi.a(" in owner and owner.endswith("bcm.o)") for owner in owners))
            self.assertTrue(any(owner.startswith(self.context["c_library"] + "(") for owner in owners))
        with self.assertRaisesRegex(ValueError, "ambiguous required live map symbol"):
            c.link_ownership(self.raw, self.context["c_library"], self.context["c_symbols"])

    def test_genuine_literal_row_bytes_parse_under_a_synthetic_unique_contract(self):
        # Keep genuine payload rows unchanged; only the surrounding fixture is synthetic.
        literal_rows = b"\n".join(row for row in self.raw.split(b"\n") if b"literal string: " in row) + b"\n"
        owners = {row.split(b"]", 1)[0].rsplit(b"[", 1)[1].strip() for row in literal_rows.split(b"\n") if row}
        self.assertEqual(owners, {b"2", b"175"})
        raw = self.minimal(literal_rows).replace(b"# Sections:", b"[175] /fixture/rust.a(literals.o)\n# Sections:")
        self.assertEqual(self.proof(raw)["map_sha256"], c.digest(raw))
        self.assertEqual(self.proof(raw)["owners"], {"_required": "1"})

    def test_only_lf_delimits_rows_and_hash_is_over_unmodified_bytes(self):
        payload = b"\xff\xc0\x00\x0b\x0c\r\x1c\x1d\x1e\xc2\x85\xe2\x80\xa8"
        raw = self.minimal(b"0x2000 0x20 [ 2] literal string: " + payload + b"\n")
        proof = self.proof(raw)
        self.assertEqual(proof["map_sha256"], c.digest(raw))
        changed = raw.replace(b"\xff", b"\xfe")
        self.assertNotEqual(self.proof(changed)["map_sha256"], proof["map_sha256"])
        self.assertEqual(self.proof(changed)["owners"], proof["owners"])

    def test_bytes_api_and_32_mib_bound_are_mandatory(self):
        self.assertEqual(c.MAX_TEXT, 32 * 1024 * 1024)
        for value in (self.minimal().decode(), bytearray(self.minimal()), None):
            with self.subTest(value=type(value).__name__), self.assertRaisesRegex(ValueError, "requires raw bytes"):
                self.proof(value)
        with patch.object(c, "MAX_TEXT", len(self.minimal()) - 1):
            with self.assertRaisesRegex(ValueError, "exceeds bound"):
                self.proof(self.minimal())

    def test_unicode_local_paths_are_strict_utf8_without_hash_normalization(self):
        archive = '/fixture " 🌿 café/c.a'
        raw = (b"# Path: " + (archive + "/probe").encode() + b"\n# Arch: arm64\n" +
               self.minimal().replace(b"/fixture/c.a", archive.encode()))
        proof = c.link_ownership(raw, archive, ["_required"])
        self.assertEqual(proof["archive_members"]["1"], archive + "(c.o)")
        self.assertEqual(proof["map_sha256"], c.digest(raw))
        # UTF-8 path support does not make the optional ld archive index Unicode.
        with self.assertRaisesRegex(ValueError, "wrong archive"):
            c.link_ownership(raw.replace(b"c.a(c.o)", "c.a[١](c.o)".encode()), archive, ["_required"])
        for bad in (b"\xff", b"\xc0", b"\xc2\x85", b"\xe2\x80\xa8"):
            for target in (b"# Path: ", b"[ 1] "):
                with self.subTest(bad=bad, target=target), self.assertRaises(ValueError):
                    c.link_ownership(raw.replace(target, target + bad), archive, ["_required"])

    def test_arbitrary_bytes_are_forbidden_in_every_structural_field(self):
        original = self.minimal()
        for bad in (b"\xff", b"\x00", b"\x0b", b"\x0c", b"\r", b"\x1c", b"\xc2\xa0", b"\x7f"):
            for old, new in ((b"# Symbols:", b"# Symbols:" + bad),
                             (b"[ 1] /fixture", b"[ " + bad + b"1] /fixture"),
                             (b"c.a(c.o)", b"c.a(c" + bad + b".o)"),
                             (b"0x1000 0x20", b"0x1000" + bad + b"0x20"),
                             (b"__TEXT", b"__TEXT" + bad),
                             (b"[ 1] _required", b"[ 1" + bad + b"] _required"),
                             (b"_required", b"_required" + bad)):
                with self.subTest(byte=bad, field=old), self.assertRaises(ValueError):
                    self.proof(original.replace(old, new))

    def test_opaque_payload_does_not_relax_owner_or_row_validation(self):
        for row in (b"0x2000 0x20 [ 999] literal string: \xff\x0b\n",
                    b"0x2000 0x20 [ 02] literal string: \xff\n",
                    b"0x2000\v0x20 [ 2] literal string: \xff\n",
                    b"0xINVALID 0x20 [ 2] literal string: \xff\n",
                    b"0x2000 0x20 [ 2] other: \xff\n",
                    b"0x2000 0x20 [ 2] literal string:\xff\n",
                    b"0x2000 0x20 [ 2] literal string: valid\n\xff\n"):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.proof(self.minimal(row))
        with self.assertRaisesRegex(ValueError, "dead-stripped"):
            self.proof(self.minimal() + b"<<dead>> 0x10 [ 999] literal string: \xff\n")

    def test_literals_dead_rows_and_duplicates_never_satisfy_required_names(self):
        for row in (b"0x1000 0x10 [ 1] literal string: _required",
                    b"0x1000 0x10 [ 2] literal string: \xff\v_required"):
            raw = self.minimal().replace(b"0x1000 0x10 [ 1] _required", row)
            with self.assertRaisesRegex(ValueError, "required symbol missing"):
                self.proof(raw)
        raw = self.minimal().replace(b"0x1000 0x10 [ 1] _required\n", b"")
        with self.assertRaisesRegex(ValueError, "required symbol missing"):
            self.proof(raw + b"<<dead>> 0x10 [ 1] _required\n")
        for owner in (b"1", b"2"):
            with self.assertRaisesRegex(ValueError, "ambiguous required live map symbol"):
                self.proof(self.minimal(b"0x2000 0x10 [ " + owner + b"] _required\n"))
        with self.assertRaisesRegex(ValueError, "wrong archive"):
            self.proof(self.minimal().replace(b"[ 1] _required", b"[ 2] _required"))


if __name__ == "__main__":
    unittest.main()
