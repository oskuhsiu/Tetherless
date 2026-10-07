"""Compiler-text ownership and provenance tests; opaque archives never execute."""
from pathlib import Path
import copy
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import retained_c_provider as c
import symbol_visibility as v
from apply_patch import canonical_json
from test_rust_symbol_reader import ReaderFixture


def row(archive, member, name, kind="external", section="(__TEXT,__text)", address="0000000000000000"):
    return f"{archive}:{member}: {address} {section} {kind} {name}\n".encode()


def map_bytes(c_path="/fixture/c.a", rust_path="/fixture/rust.a", extra=True):
    return (f"# Object files:\n[ 1] {c_path}(c.o)\n[ 2] {rust_path}(rust.o)\n# Symbols:\n"
            "0x1 0x1 [ 1] _c\n0x2 0x1 [ 2] _rust\n"
            + ("0x3 0x1 [ 2] _c\n" if extra else "")).encode()


class EvidenceFixture:
    def __init__(self, root):
        self.reader = ReaderFixture(root).observe()
        self.target = "aarch64-apple-ios"
        self.context = {"source_manifest_sha256": "1" * 64, "recipe_lock_sha256": "2" * 64}
        self.archives = {role: {"source": "/fixture/" + role + ".a", **v.identity((role + " opaque").encode())}
                         for role in ("rust", "c")}
        self.files = {}
        inputs = {"schema": 2, "target": self.target, "diagnostic_only": False,
                  "ownership_acceptance_changed": True, "native_payloads_executed": False,
                  "archive_byte_limit_each": v.MAX_ARCHIVE_BYTES, "symbol_reader": self.reader,
                  "source_context": self.context, "observation_flags": v.FLAGS,
                  "archives": {role: {**value, "canonical_source": value["source"], "retained": role + "-staticlib.a"}
                               for role, value in self.archives.items()}}
        self.put("linkage-observation/inputs.json", inputs)
        self.snapshot = {role: {place: {key: value[key] for key in ("sha256", "bytes")}
                               for place in ("source", "retained")} for role, value in self.archives.items()}
        self.operations = []
        for role in ("rust", "c"):
            path = self.archives[role]["source"]
            raw = row(path, role + ".o", "_" + role)
            if role == "rust":
                raw += row(path, "rust.o", "_c", "non-external")
            self.add("linkage-observation/" + role + "-defined-members.txt", raw,
                     [self.reader["llvm_nm"]["path"], *v.FLAGS, path])
        for role in ("rust", "c"):
            self.add("04-" + role + "-export-symbols.txt", ("_" + role + "\n").encode(),
                     v.rust_symbol_reader.scan_command(self.reader, self.archives[role]["source"]))

    def put(self, name, value):
        self.files[name] = canonical_json(value)

    def add(self, name, raw, command, map_raw=None):
        basename = Path(name).name
        full = "/fixture/work/" + name
        self.files[name] = raw
        status = {"schema": 1, "command": command, "outcome": "success", "returncode": 0,
                  "output_complete": True, "output_truncated": False, "stop_reason": None,
                  "error_type": None, "output_bytes_over_limit_observed": 0, "log_bytes": len(raw),
                  "max_log_bytes": v.MAX_LOG_BYTES, "cleanup": {"direct_child_reaped": True, "group_empty": True}}
        self.put(name + ".status.json", status)
        outputs = {basename: {"path": full, **v.identity(raw)}, basename + ".status.json": {
            "path": full + ".status.json", **v.identity(self.files[name + ".status.json"])}}
        if map_raw is not None:
            map_name = name[:-4] + ".map"
            self.files[map_name] = map_raw
            outputs[Path(map_name).name] = {"path": full[:-4] + ".map", **v.identity(map_raw)}
        op = {"schema": 1, "diagnostic_only": False, "command": command, "log": full,
              "command_completed": True, "inputs_unchanged": True, "retention_errors": [],
              "before": self.snapshot, "after": self.snapshot, "outputs": outputs}
        self.operations.append("linkage-observation/" + f"{len(self.operations) + 1:02d}-" + basename[:-4] + ".json")
        self.put(self.operations[-1], op)

    def load(self, links=()):
        return v.load_evidence(lambda name, limit: self.files[name], target=self.target, reader=self.reader,
                               archives=self.archives, context=self.context, links=links)


class VisibilityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.fixture = EvidenceFixture(Path(temp.name))

    def proof(self, visibility=None, raw=None):
        return c.link_ownership(raw or map_bytes(), "/fixture/c.a", ["_c"], "/fixture/rust.a", ["_rust"],
                                visibility=visibility or self.fixture.load())

    def test_bound_exact_member_local_cannot_impersonate_external_owner(self):
        proof = self.proof()
        self.assertEqual(proof["owners"], {"_c": "1", "_rust": "2"})
        self.assertEqual(proof["proven_local_candidates"], {"_c": ["2"]})
        self.assertEqual(proof["map_sha256"], v.digest(map_bytes()))

    def test_legacy_call_keeps_duplicate_gate(self):
        with self.assertRaisesRegex(ValueError, "ambiguous required live map symbol"):
            c.link_ownership(map_bytes(), "/fixture/c.a", ["_c"], "/fixture/rust.a", ["_rust"])

    def test_wrong_archive_member_unknown_owner_missing_and_repeated_rows_fail(self):
        changes = [lambda raw: raw.replace(b"/fixture/rust.a(rust.o)", b"/other/rust.a(rust.o)"),
                   lambda raw: raw.replace(b"rust.o)", b"other.o)"),
                   lambda raw: raw.replace(b"[ 2] _c", b"[ 9] _c"),
                   lambda raw: raw.replace(b"0x1 0x1 [ 1] _c\n", b""),
                   lambda raw: raw + b"0x4 0x1 [ 2] _c\n",
                   lambda raw: raw.replace(b"0x2 0x1 [ 2] _rust\n", b"")]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.proof(raw=change(map_bytes()))

    def test_external_weak_missing_and_ambiguous_member_candidates_fail(self):
        for kinds in (["external"], ["weak"], [], ["local", "local"], ["local", "external"], ["unknown"]):
            value = self.fixture.load()
            value["archives"]["rust"]["members"]["rust.o"]["_c"] = kinds
            with self.subTest(kinds=kinds), self.assertRaises(ValueError):
                self.proof(value)

    def test_weak_winner_cannot_resolve_collision_but_singleton_is_preserved(self):
        value = self.fixture.load()
        value["archives"]["c"]["members"]["c.o"]["_c"] = ["weak"]
        with self.assertRaisesRegex(ValueError, "weak external"):
            self.proof(value)
        self.assertEqual(self.proof(value, map_bytes(extra=False))["owners"]["_c"], "1")

    def test_wrong_intended_visibility_and_archive_identity_fail(self):
        value = self.fixture.load()
        value["archives"]["c"]["members"]["c.o"]["_c"] = ["local"]
        with self.assertRaises(ValueError): self.proof(value)
        value = self.fixture.load()
        value["archives"]["c"]["source"] = "/other/c.a"
        with self.assertRaises(ValueError): self.proof(value)

    def test_rebase_requires_same_two_archive_hashes_and_sizes(self):
        value = self.fixture.load()
        rebased = copy.deepcopy(self.fixture.archives)
        for role in rebased: rebased[role]["source"] = "/derived/" + role + ".a"
        new = v.rebind(value, archives=rebased)
        self.assertEqual(value["archives"]["c"]["source"], "/fixture/c.a")
        self.assertEqual(c.link_ownership(map_bytes("/derived/c.a", "/derived/rust.a"),
            "/derived/c.a", ["_c"], "/derived/rust.a", ["_rust"], visibility=new)["owners"]["_c"], "1")
        for key, replacement in (("bytes", 99), ("sha256", "f" * 64)):
            changed = copy.deepcopy(rebased); changed["c"][key] = replacement
            with self.assertRaises(ValueError): v.rebind(value, archives=changed)

    def test_all_observed_record_forms_and_unrelated_duplicate_locals(self):
        raw = (row("/fixture/rust.a", "a.o", "_normal")
               + row("/fixture/rust.a", "b.o", "_cold", "non-external [cold func]")
               + row("/fixture/rust.a", "c.o", "_common", "(alignment 2^3) external", "(common)")
               + row("/fixture/rust.a", "d.o", "_weak", "weak private external", "(LTO,CODE)", "----------------")
               + row("/fixture/rust.a", "b.o", "_cold", "non-external"))
        parsed = v.parse_archive(raw, "/fixture/rust.a")
        self.assertEqual(parsed["members"]["b.o"]["_cold"], ["local", "local"])
        self.assertEqual(parsed["external_symbols"], ["_common", "_normal", "_weak"])

    def test_malformed_weak_sections_diagnostics_and_duplicate_globals_fail(self):
        good = row("/fixture/rust.a", "a.o", "_name")
        samples = [good[:-1], good + b"warning: no symbols\n", good.replace(b"external", b"non-external weak"),
                   good.replace(b"0000000000000000", b"----------------"), good.replace(b"(__TEXT,__text)", b"(unknown)"),
                   good.replace(b"_name", b"bad name"), good.replace(b":a.o:", b":../a.o:"),
                   good.replace(b"/fixture/rust.a:", b"/other/rust.a:"), good + good,
                   good + row("/fixture/rust.a", "b.o", "_name", "weak private external"),
                   good.replace(b"external", b"(alignment 2^3) external")]
        for raw in samples:
            with self.subTest(raw=raw[-100:]), self.assertRaises(ValueError): v.parse_archive(raw, "/fixture/rust.a")

    def test_clean_external_scan_accepts_exact_headers_but_no_contamination(self):
        self.assertEqual(v.exported(b"\na.o:\n_name\n\nb.rcgu.o:\n_other\n"), {"_name", "_other"})
        for raw in (b"_name\nwarning:\n", b"_name\nerror: no symbols\n", b"_name\n_name\n",
                    b"_name\r\n", b"_name", b"_name\n/root/a.o:\n", b"_name\n\xc0\n"):
            with self.subTest(raw=raw), self.assertRaises(ValueError): v.exported(raw)

    def test_source_context_archive_reader_and_legacy_capture_are_bound(self):
        name = "linkage-observation/inputs.json"
        original = self.fixture.files[name]
        for change in (lambda x: x.update(schema=1), lambda x: x.update(diagnostic_only=True),
                       lambda x: x["source_context"].update(source_manifest_sha256="f" * 64),
                       lambda x: x["source_context"].update(recipe_lock_sha256="f" * 64),
                       lambda x: x["archives"]["rust"].update(sha256="f" * 64),
                       lambda x: x["symbol_reader"]["llvm_nm"].update(sha256="f" * 64),
                       lambda x: x.update(observation_flags=[])):
            value = json.loads(original); change(value); self.fixture.put(name, value)
            with self.assertRaises(ValueError): self.fixture.load()
        self.fixture.files[name] = original

    def test_tampered_receipts_statuses_and_raw_scan_bytes_fail(self):
        original = dict(self.fixture.files)
        for name in ("linkage-observation/rust-defined-members.txt", self.fixture.operations[0],
                     "linkage-observation/rust-defined-members.txt.status.json"):
            self.fixture.files = dict(original)
            if name.endswith(".txt"):
                self.fixture.files[name] += b"extra text\n"
            else:
                value = json.loads(self.fixture.files[name])
                if "outputs" in value: value["before"]["rust"]["source"]["sha256"] = "f" * 64
                else: value["log_bytes"] += 1
                self.fixture.put(name, value)
            with self.subTest(name=name), self.assertRaises(ValueError): self.fixture.load()
        self.fixture.files = original
        for field, replacement in (("command", ["wrong-reader"]), ("output_complete", False),
                                   ("output_truncated", True), ("returncode", 1), ("outcome", "failure")):
            name = "04-rust-export-symbols.txt.status.json"
            value = json.loads(original[name]); value[field] = replacement; self.fixture.put(name, value)
            with self.subTest(field=field), self.assertRaises(ValueError): self.fixture.load()
        self.fixture.files = original

    def test_reached_link_map_log_status_and_inputs_bound_without_changing_scan_identity(self):
        initial = self.fixture.load()
        command = ["/usr/bin/clang", "-force_load", "/fixture/rust.a", "-force_load", "/fixture/c.a"]
        link = {"group": "mixed_provider", "language": "c", "command": command}
        self.fixture.add("05-link-mixed_provider-c.txt", b"", command, map_bytes())
        self.assertEqual(self.fixture.load([link]), initial)
        self.fixture.files["05-link-mixed_provider-c.map"] += b"\n"
        with self.assertRaises(ValueError): self.fixture.load([link])


class RealVisibilityReplay(unittest.TestCase):
    def test_complete_real_raw_map_and_definition_text_replay_without_producer_admission(self):
        fixture = ROOT / "tests/fixtures/symbol-visibility-run37547552049.zip"
        with zipfile.ZipFile(fixture) as z:
            files = {n: z.read(n) for n in z.namelist()}
        context = json.loads(files["context.json"])
        for name, expected in context["files"].items():
            self.assertEqual(v.identity(files[name]), expected)
        inputs = json.loads(files["inputs.json"])
        self.assertEqual(inputs["schema"], 1)  # failed diagnostic remains inadmissible
        scans = {}
        for role in ("rust", "c"):
            original = inputs["archives"][role]
            parsed = v.parse_archive(files[role + "-defined-members.txt"], original["source"])
            scans[role] = {**{key: original[key] for key in ("source", "sha256", "bytes")}, **parsed}
            self.assertEqual(len(parsed["external_symbols"]), 4819 if role == "rust" else 829)
        namespace = json.loads((ROOT / "namespace/contract.json").read_bytes())
        raw = files["mixed-c.map"]
        visibility = {"schema": 1, "archives": scans, "evidence_sha256": v.digest(files["context.json"])}
        proof = c.link_ownership(raw, scans["c"]["source"], scans["c"]["external_symbols"], scans["rust"]["source"],
            {"_" + name for name in namespace["expected_target_exports"]["aarch64-apple-ios"]["after"]}, visibility=visibility)
        self.assertEqual(proof["c_required_live_symbols"], 829)
        self.assertEqual(proof["rust_required_live_symbols"], 382)
        self.assertEqual(len(proof["proven_local_candidates"]), 29)
        self.assertEqual(proof["map_sha256"], "e6119d6bed477439b75e8d985f3019a2e6d5e370ebfc06bb7a56f575d6e9b321")
        with self.assertRaisesRegex(ValueError, "malformed external symbol"):
            v.exported(files["legacy-rust-export-symbols.txt"])
        # The original receipt/command/log bytes remain intact, including the
        # exact source/copy archive hashes, successful join and raw map hash.
        for name, scan_name in (("01-rust-defined-members.json", "rust-defined-members.txt"),
                                ("02-c-defined-members.json", "c-defined-members.txt")):
            operation = json.loads(files[name])
            self.assertEqual(operation["before"], operation["after"])
            self.assertEqual(operation["outputs"][scan_name]["sha256"], v.digest(files[scan_name]))
            for role in ("rust", "c"):
                self.assertEqual(operation["before"][role]["source"], operation["before"][role]["retained"])
                self.assertEqual(operation["before"][role]["source"], {k: inputs["archives"][role][k] for k in ("sha256", "bytes")})
            status = json.loads(files[scan_name + ".status.json"])
            v._success(status, operation["command"], len(files[scan_name]))
        link = json.loads(files["07-05-link-mixed_provider-c.json"])
        self.assertEqual(link["outputs"]["05-link-mixed_provider-c.map"]["sha256"], v.digest(raw))


if __name__ == "__main__":
    unittest.main()
