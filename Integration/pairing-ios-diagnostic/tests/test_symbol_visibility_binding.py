"""Synthetic consumer lineage and App map boundaries; no native execution."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from test_diagnostic_binding import DiagnosticFixture, binding, put_json, sha
import test_compile_observer as observer_fixtures


class SymbolVisibilityBindingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="visibility-binding-")
        self.addCleanup(temporary.cleanup)
        self.fixture = DiagnosticFixture(Path(temporary.name))

    def mutate_json(self, name, change):
        path = self.fixture.evidence(name)
        value = json.loads(path.read_bytes())
        change(value)
        put_json(path, value)
        self.fixture.refresh(inventory=True)

    def add_proven_local_collision(self):
        f = self.fixture
        row = f.receipt["targets"][0]
        scan = f.evidence("linkage-observation/rust-defined-members.txt")
        scan.write_bytes(scan.read_bytes() + (row["library"] +
            ":bcm-local.o: 0000000000000010 (__TEXT,__text) non-external _plist_free\n").encode())
        for language in ("c", "swift"):
            path = f.evidence("05-link-mixed_provider-" + language + ".map")
            raw = path.read_bytes().replace(b"# Sections:",
                ("[ 5] " + row["library"] + "(bcm-local.o)\n# Sections:").encode())
            raw += b"0x3000 0x10 [ 5] _plist_free\n"
            path.write_bytes(raw)
            next(p for p in row["link_probes"] if p["group"] == "mixed_provider" and p["language"] == language)["link_map_sha256"] = sha(raw)
        f.refresh_visibility(emit_scans=False)
        f.refresh(inventory=True)

    def test_complete_bound_visibility_travels_to_app_binding(self):
        self.add_proven_local_collision()
        native = self.fixture.artifact_inputs()
        self.assertEqual(set(native["symbol_visibility"]), set(native["targets"]))
        visibility = native["symbol_visibility"]["aarch64-apple-ios"]
        self.assertEqual(visibility["archives"]["rust"]["members"]["bcm-local.o"]["_plist_free"], ["local"])
        for probe in native["targets"]["aarch64-apple-ios"]["link_probes"]:
            if probe["group"] == "mixed_provider":
                self.assertEqual(probe["ownership"]["proven_local_candidates"], {"_plist_free": ["5"]})

    def test_missing_visibility_never_falls_back_to_unique_names(self):
        self.fixture.evidence("linkage-observation/rust-defined-members.txt").unlink()
        with self.assertRaises((OSError, ValueError)):
            self.fixture.artifact_inputs()

    def test_old_diagnostic_only_capture_is_ineligible_even_after_rehash(self):
        self.mutate_json("linkage-observation/inputs.json", lambda value: value.update(schema=1, diagnostic_only=True))
        with self.assertRaisesRegex(ValueError, "capture/source/toolchain"):
            self.fixture.artifact_inputs()

    def test_source_context_mismatch_is_rejected_after_outer_rehash(self):
        self.fixture.receipt["targets"][0]["source_manifest"]["files"]["synthetic.rs"] = "0" * 64
        self.fixture.refresh()
        with self.assertRaisesRegex(ValueError, "capture/source/toolchain"):
            self.fixture.artifact_inputs()

    def test_archive_size_is_derived_from_packaged_bytes(self):
        self.mutate_json("linkage-observation/inputs.json",
                         lambda value: value["archives"]["rust"].update(bytes=1))
        with self.assertRaisesRegex(ValueError, "capture archive identity"):
            self.fixture.artifact_inputs()

    def test_scan_edit_and_outer_rehash_do_not_replace_operation_binding(self):
        path = self.fixture.evidence("linkage-observation/rust-defined-members.txt")
        path.write_bytes(path.read_bytes().replace(b" external ", b" private external ", 1))
        self.fixture.refresh(inventory=True)
        with self.assertRaisesRegex(ValueError, "matching complete successful|output bytes/paths"):
            self.fixture.artifact_inputs()

    def test_command_or_archive_snapshot_cannot_be_reauthenticated_as_success(self):
        path = self.fixture.evidence("linkage-observation/01-rust-defined-members.json")
        original = path.read_bytes()
        for change in (lambda value: value.update(command=["/synthetic/wrong-reader"]),
                       lambda value: value["after"]["rust"]["source"].update(sha256="0" * 64),
                       lambda value: value.update(inputs_unchanged=False)):
            with self.subTest(change=change):
                path.write_bytes(original)
                self.mutate_json("linkage-observation/01-rust-defined-members.json", change)
                with self.assertRaisesRegex(ValueError, "operation receipt/source"):
                    self.fixture.artifact_inputs()

    def test_link_map_must_match_its_operation_bytes(self):
        path = self.fixture.evidence("05-link-mixed_provider-c.map")
        path.write_bytes(path.read_bytes() + b"\n")
        row = self.fixture.receipt["targets"][0]
        next(p for p in row["link_probes"] if p["group"] == "mixed_provider" and p["language"] == "c")["link_map_sha256"] = sha(path.read_bytes())
        self.fixture.refresh(inventory=True)
        with self.assertRaisesRegex(ValueError, "operation output bytes/paths"):
            self.fixture.artifact_inputs()

    def test_wrong_member_cannot_borrow_locality_from_another_member(self):
        self.add_proven_local_collision()
        path = self.fixture.evidence("05-link-mixed_provider-c.map")
        path.write_bytes(path.read_bytes().replace(b"(bcm-local.o)", b"(other-local.o)"))
        row = self.fixture.receipt["targets"][0]
        next(p for p in row["link_probes"] if p["group"] == "mixed_provider" and p["language"] == "c")["link_map_sha256"] = sha(path.read_bytes())
        self.fixture.refresh_visibility(emit_scans=False, recompute_ownership=False)
        self.fixture.refresh(inventory=True)
        with self.assertRaisesRegex(ValueError, "exact member visibility"):
            self.fixture.artifact_inputs()


class AppSymbolVisibilityTests(unittest.TestCase):
    setUp = observer_fixtures.CompileObserverTests.setUp
    put = observer_fixtures.CompileObserverTests.put
    write_sources = observer_fixtures.CompileObserverTests.write_sources
    log_text = observer_fixtures.CompileObserverTests.log_text
    observe = observer_fixtures.CompileObserverTests.observe

    def visibility(self):
        return self.binding["native_artifact"]["symbol_visibility"]["aarch64-apple-ios"]

    def collision(self, kind="local", member="bcm-local.o"):
        archive = self.processed / "libidevice_ffi.a"
        raw = self.map_text.encode().replace(b"# Sections:",
            ("[ 5] " + str(archive) + "(" + member + ")\n# Sections:").encode())
        raw = raw.replace(b"# Dead Stripped Symbols:",
                          b"0x3000 0x10 [ 5] _synthetic_c_live\n# Dead Stripped Symbols:")
        self.put(self.map_path, raw)
        self.visibility()["archives"]["rust"]["members"]["bcm-local.o"] = {"_synthetic_c_live": [kind]}

    def test_processed_archives_rebase_only_exact_hash_and_size(self):
        self.collision()
        original = copy.deepcopy(self.visibility())
        result = self.observe()["link"]["live_map_ownership"]
        self.assertEqual(result["proven_local_candidates"], {"_synthetic_c_live": ["5"]})
        self.assertEqual(self.visibility(), original)
        self.assertIn(str(self.processed / "libidevice_ffi.a"), result["local_archive_members"]["5"])

    def test_bound_archive_size_or_hash_mismatch_rejects_rebase(self):
        for key, value in (("bytes", 1), ("sha256", "0" * 64)):
            with self.subTest(key=key):
                original = self.visibility()["archives"]["rust"][key]
                self.visibility()["archives"]["rust"][key] = value
                with self.assertRaisesRegex(observer_fixtures.observer.ObservationError, "visibility identity"):
                    self.observe()
                self.visibility()["archives"]["rust"][key] = original

    def test_wrong_member_and_weak_or_external_candidate_are_not_local(self):
        for kind, member in (("local", "other-local.o"), ("weak", "bcm-local.o"), ("external", "bcm-local.o")):
            with self.subTest(kind=kind, member=member):
                self.collision(kind, member)
                with self.assertRaisesRegex(observer_fixtures.observer.ObservationError, "exact member visibility|external map owner"):
                    self.observe()

    def test_unique_weak_global_remains_accepted_without_disambiguation(self):
        self.visibility()["archives"]["rust"]["members"]["rust-fixture.o"]["_synthetic_rust_live"] = ["weak"]
        self.assertIn("_synthetic_rust_live", self.observe()["link"]["live_map_ownership"]["rust_live_symbols"])

    def test_weak_intended_owner_cannot_resolve_a_local_collision(self):
        self.collision()
        self.visibility()["archives"]["c"]["members"]["c-fixture.o"]["_synthetic_c_live"] = ["weak"]
        with self.assertRaisesRegex(observer_fixtures.observer.ObservationError, "weak external cannot resolve"):
            self.observe()


if __name__ == "__main__":
    unittest.main()
