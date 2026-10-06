"""Synthetic App C-consumer boundaries, not successful C or Apple build evidence.

The older surrounding artifact fixtures explicitly mock only the nested C
verifier. Its complete Actions/source/product reader has its own fixture suite.
Actual map parsing, export checks, manifests, copies and observations run here.
"""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_diagnostic_binding import DiagnosticFixture, binding, put, put_json, sha
import test_compile_observer as observer_fixtures
observer = observer_fixtures.observer


def genuine_literal_rows():
    """Unchanged owner-2 literal rows from the separately proven raw-map excerpt."""
    path = (Path(__file__).resolve().parents[2] / "Dependencies/idevice/tests/fixtures/"
            "mixed-provider-raw-byte-excerpt.map")
    return b"\n".join(row for row in path.read_bytes().split(b"\n")
                      if b"[  2] literal string: " in row) + b"\n"


class RetainedCBindingBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="retained-app-C-")
        self.addCleanup(temporary.cleanup)
        self.fixture = DiagnosticFixture(Path(temporary.name))

    def test_nested_verifier_gets_both_targets_and_exact_caller_hash_with_default_selection(self):
        f = self.fixture
        with f.mock_retained() as verified:
            result = binding.artifact_inputs(f.artifact, f.receipt_hash, f.contract)
        self.assertEqual(verified.call_count, 2)
        for call in verified.call_args_list:
            self.assertEqual(call.args[0], f.artifact / binding.C_ROOT)
            self.assertEqual(call.kwargs, {"expected_handoff_sha256": f.receipt["retained_c_handoff_sha256"]})
            self.assertIn(call.args[1]["rust"], result["c_targets"])
        self.assertTrue(result["c_files"])
        self.assertEqual(set(result["rust_symbols"]), set(result["c_targets"]))
        self.assertTrue(all(path.startswith("libimobiledevice.xcframework/") for path in result["c_files"]))

    def test_nested_verifier_rejection_cannot_fall_back_to_old_release(self):
        f = self.fixture
        with patch.object(binding.retained_c_provider, "verify", side_effect=ValueError("unselected C handoff")):
            with self.assertRaisesRegex(ValueError, "unselected C handoff"):
                binding.artifact_inputs(f.artifact, f.receipt_hash, f.contract)

    def test_synthetic_artifact_does_not_pass_real_nested_verifier(self):
        f = self.fixture
        with self.assertRaises(ValueError):
            binding.artifact_inputs(f.artifact, f.receipt_hash, f.contract)

    def test_caller_hash_missing_or_changed_is_rejected(self):
        f = self.fixture
        for value in (None, "0" * 64, "g" * 64):
            with self.subTest(value=value):
                f.receipt["retained_c_handoff_sha256"] = value
                f.refresh()
                with self.assertRaises(ValueError):
                    f.artifact_inputs()

    def test_mutated_nested_c_file_is_rejected_by_outer_inventory(self):
        f = self.fixture
        for name in ("handoff.json", "product/libimobiledevice.xcframework/ios-arm64/Headers/libimobiledevice/afc.h"):
            path = f.artifact / binding.C_ROOT / name
            original = path.read_bytes()
            path.write_bytes(original + b"changed")
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "handoff bytes"):
                f.artifact_inputs()
            path.write_bytes(original)

    def test_c_header_inventory_or_provider_or_sdk_mismatch_fails(self):
        f = self.fixture
        row = f.receipt["targets"][0]
        original = copy.deepcopy(row)
        changes = (
            lambda: row["mixed_provider"]["header_inventory"].pop("libimobiledevice/afc.h"),
            lambda: row["provider_receipt"].update(framework_binary_sha256="0" * 64),
            lambda: row["toolchain_observations"].update(sdk_iphoneos_version="mismatch"),
        )
        for change in changes:
            row.clear(); row.update(copy.deepcopy(original)); change(); f.refresh()
            with self.subTest(change=change), self.assertRaises(ValueError):
                f.artifact_inputs()

    def test_complete_c_nm_scan_rejects_duplicate_global_even_after_rehash(self):
        f = self.fixture
        path = f.evidence("04-c-export-symbols.txt")
        path.write_text(path.read_text() + "_plist_free\n")
        f.refresh(inventory=True)
        with self.assertRaisesRegex(ValueError, "duplicate C globals"):
            f.artifact_inputs()

    def test_producer_map_requires_exact_owner_path_not_archive_basename(self):
        f = self.fixture
        row = f.receipt["targets"][0]
        path = f.evidence("05-link-mixed_provider-c.map")
        path.write_text(path.read_text().replace(row["mixed_provider"]["library"], "/other/libimobiledevice.a"))
        next(p for p in row["link_probes"] if p["group"] == "mixed_provider" and p["language"] == "c")["link_map_sha256"] = binding.file_hash(path)
        f.refresh(inventory=True)
        with self.assertRaisesRegex(ValueError, "wrong archive"):
            f.artifact_inputs()

    def test_both_producer_maps_read_and_hash_genuine_literal_bytes(self):
        f = self.fixture
        namespace = binding.ffi_namespace.load_contract(expected_sha256=f.contract["ffi_namespace_sha256"])
        for index, row in enumerate(f.receipt["targets"]):
            target = row["target"]["rust"]
            for language in ("c", "swift"):
                path = f.evidence("05-link-mixed_provider-" + language + ".map", index)
                raw = path.read_bytes() + genuine_literal_rows()
                path.write_bytes(raw)
                probe = next(p for p in row["link_probes"] if p["group"] == "mixed_provider" and p["language"] == language)
                probe["link_map_sha256"] = sha(raw)
                probe["ownership"] = binding.retained_c_provider.link_ownership(raw,
                    row["mixed_provider"]["library"], f.c_targets[target]["symbols"], row["library"],
                    {"_" + name for name in namespace["expected_target_exports"][target]["after"]})
                put_json(f.evidence("05-link-mixed_provider-" + language + "-ownership.json", index), probe["ownership"])
        f.refresh(inventory=True)
        result = f.artifact_inputs()
        self.assertEqual(len(result["targets"]), 2)
        path = f.evidence("05-link-mixed_provider-c.map")
        path.write_bytes(path.read_bytes().replace(b"\xc0", b"\xc1", 1))
        # Even opaque payload changes still invalidate the authenticated bytes.
        with self.assertRaisesRegex(ValueError, "inventory"):
            f.artifact_inputs()

    def test_producer_map_literal_bytes_do_not_hide_duplicate_required_rows(self):
        f = self.fixture
        row = f.receipt["targets"][0]
        path = f.evidence("05-link-mixed_provider-c.map")
        raw = path.read_bytes() + genuine_literal_rows() + b"0x1000 0x10 [ 4] _plist_free\n"
        path.write_bytes(raw)
        next(p for p in row["link_probes"] if p["group"] == "mixed_provider" and p["language"] == "c")["link_map_sha256"] = sha(raw)
        f.refresh(inventory=True)
        with self.assertRaisesRegex(ValueError, "ambiguous required live map symbol"):
            f.artifact_inputs()

    def test_owned_copy_binds_every_c_byte_and_preserves_unmodified_c_gateway(self):
        from test_native_handoff import NativeHandoffFixture
        fixture = NativeHandoffFixture(self.fixture.root / "copy-boundary")
        f = fixture.fixture
        source = "Dependencies/minimuxer/DeviceGateway/libimobiledevice/LibimobiledeviceGateway.swift"
        original = b"// synthetic C gateway Swift; copy unchanged, never compiled\n"
        put(f.prepared / source, original)
        result = fixture.bind()
        self.assertEqual((f.output / source).read_bytes(), original)
        for name, expected in result["native_artifact"]["c_files"].items():
            bound_name = "Dependencies/minimuxer/DeviceGateway/TetherlessDiagnosticArtifacts/" + name
            self.assertEqual(result["bound_files"][bound_name], expected)
            self.assertEqual(binding.file_hash(f.output / bound_name), expected)
        self.assertEqual(set(result["local_c_device_files"]), {"archive", "header", "module_map"})

    def test_reserved_local_c_artifact_cannot_be_overwritten(self):
        from test_native_handoff import NativeHandoffFixture
        fixture = NativeHandoffFixture(self.fixture.root / "reserved-boundary")
        f = fixture.fixture
        reserved = f.prepared / "Dependencies/minimuxer/DeviceGateway/TetherlessDiagnosticArtifacts/libimobiledevice.xcframework"
        put(reserved, b"preexisting owned data")
        with self.assertRaisesRegex(ValueError, "already exists"):
            fixture.bind()
        self.assertEqual(reserved.read_bytes(), b"preexisting owned data")
        self.assertFalse(f.output.exists())

    def test_whole_package_preimage_and_only_two_exact_target_replacements(self):
        f = self.fixture
        original = (f.prepared / f.contract["gateway"]["prepared_path"]).read_bytes()
        result = binding.patched_gateway(original, f.contract)
        expected = original.replace(binding.OLD_TARGET.encode(),
            b'         .binaryTarget(\n             name: "IDevice",\n             path: "TetherlessDiagnosticArtifacts/IDevice.xcframework"\n         ),', 1)
        expected = expected.replace(binding.OLD_C_TARGET.encode(),
            b'        .binaryTarget(\n            name: "libimobiledevice",\n            path: "TetherlessDiagnosticArtifacts/libimobiledevice.xcframework"\n        ),', 1)
        self.assertEqual(result, expected)
        with self.assertRaisesRegex(ValueError, "preimage"):
            binding.patched_gateway(original + b"\n// unrelated edit", f.contract)


class RetainedCObserverBoundaryTests(unittest.TestCase):
    setUp = observer_fixtures.CompileObserverTests.setUp
    put = observer_fixtures.CompileObserverTests.put
    write_sources = observer_fixtures.CompileObserverTests.write_sources
    log_text = observer_fixtures.CompileObserverTests.log_text
    observe = observer_fixtures.CompileObserverTests.observe
    inventory = observer_fixtures.CompileObserverTests.inventory

    def test_live_map_checks_complete_observed_exports_and_ignores_dead_only_nonroots(self):
        result = self.observe()["link"]["live_map_ownership"]
        self.assertIn("_synthetic_c_live", result["c_live_symbols"])
        self.assertIn("_synthetic_rust_live", result["rust_live_symbols"])
        self.assertNotIn("_synthetic_c_dead", result["c_live_symbols"])
        self.assertNotIn("_synthetic_rust_dead", result["rust_live_symbols"])
        self.assertFalse(result["dead_stripped_symbols_used"])

    def test_live_app_map_preserves_genuine_literal_bytes_in_hash_and_capture(self):
        raw = self.map_text.encode().replace(b"# Dead Stripped Symbols:",
            genuine_literal_rows() + b"# Dead Stripped Symbols:")
        self.map_path.write_bytes(raw)
        proof = self.observe()["link"]["live_map_ownership"]
        self.assertEqual(proof["map_sha256"], sha(raw))
        entry = next(row for row in self.inventory() if row.get("source_path") == str(self.map_path))
        self.assertEqual(entry["sha256"], sha(raw))
        self.assertEqual((self.evidence / entry["retained_path"]).read_bytes(), raw)
        self.assertEqual(self.inventory()[-1]["event"], "complete")

    def test_bad_owner_after_raw_literals_is_rejected_and_original_bytes_retained(self):
        for bad in (b"0x1000 0x10 [ 9999] literal string: \xff\v\n",
                    b"0x1000 0x10 [ 4] _plist_free\n",
                    b"0x1000 0x10 [ 4] _unrelated\xff\n"):
            raw = self.map_text.encode().replace(b"# Dead Stripped Symbols:",
                genuine_literal_rows() + bad + b"# Dead Stripped Symbols:")
            self.map_path.write_bytes(raw)
            with self.subTest(bad=bad), self.assertRaises(observer.ObservationError):
                self.observe()
            entry = next(row for row in self.inventory() if row.get("source_path") == str(self.map_path))
            self.assertEqual((self.evidence / entry["retained_path"]).read_bytes(), raw)
            self.assertEqual(self.inventory()[-1]["event"], "failed")

    def test_opaque_literal_required_name_does_not_satisfy_app_root(self):
        raw = self.map_text.encode().replace(b"0x1000 0x10 [ 3] _plist_free\n",
            b"0x1000 0x10 [ 3] literal string: _plist_free\n")
        self.map_path.write_bytes(raw)
        with self.assertRaisesRegex(observer.ObservationError, "roots are absent"):
            self.observe()

    def test_unrelated_c_public_header_mutation_and_extra_c_header_fail(self):
        path = self.headers / "libimobiledevice/afc.h"
        original = path.read_bytes()
        path.write_bytes(original + b"changed")
        with self.assertRaisesRegex(observer.ObservationError, "full header/module"):
            self.observe()
        path.write_bytes(original)
        self.put(self.headers / "libimobiledevice/extra.h", b"unexpected")
        with self.assertRaisesRegex(observer.ObservationError, "full header/module"):
            self.observe()

    def test_shadow_header_tree_without_module_map_fails(self):
        shadow = self.derived / "shadow"
        self.put(shadow / "plist/plist.h", b"alternate declarations")
        self.app_args += ["-I", str(shadow)]
        with self.assertRaisesRegex(observer.ObservationError, "alternate C public header"):
            self.observe()

    def test_bound_local_c_archive_mutation_fails(self):
        path = self.app / self.binding["local_c_device_files"]["archive"]
        path.write_bytes(b"wrong bound provider")
        with self.assertRaisesRegex(observer.ObservationError, "bound local C"):
            self.observe()

    def test_final_live_map_wrong_archive_and_path_lookalike_fail(self):
        for owner in ("/other/libimobiledevice.a", str(self.c_archive) + ".wrong"):
            self.map_path.write_text(self.map_text.replace(str(self.c_archive), owner))
            with self.subTest(owner=owner), self.assertRaisesRegex(observer.ObservationError, "wrong archive"):
                self.observe()

    def test_alternate_C_framework_forms_and_direct_framework_binary_fail(self):
        additions = (["-framework", "libimobiledevice"], ["-weak_framework", "plist"],
                     ["-reexport_framework", "usbmuxd"], ["-upward_framework", "libimobiledevice-glue"],
                     ["-weak_library", "/tmp/libimobiledevice.framework/libimobiledevice"],
                     ["/tmp/Frameworks/libplist.framework/libplist"])
        for flags in additions:
            with self.subTest(flags=flags):
                original=list(self.link_args)
                try:
                    self.link_args += flags
                    with self.assertRaisesRegex(observer.ObservationError, "alternate C framework"):
                        self.observe()
                finally:
                    self.link_args=original
    def test_dead_stripped_root_cannot_satisfy_app_live_requirement(self):
        row = "0x1000 0x10 [ 3] _plist_free\n"
        self.assertIn(row, self.map_text)
        self.map_path.write_text(self.map_text.replace(row, "") + "<<dead>> 0x10 [ 3] _plist_free\n")
        with self.assertRaisesRegex(observer.ObservationError, "roots are absent"):
            self.observe()

    def test_duplicate_live_symbol_is_not_hidden_by_set(self):
        text = self.map_text.replace("# Dead Stripped Symbols:", "0x1000 0x10 [ 4] _plist_free\n# Dead Stripped Symbols:")
        self.map_path.write_text(text)
        with self.assertRaisesRegex(observer.ObservationError, "ambiguous required live map symbol"):
            self.observe()

    def test_nonroot_live_exports_must_also_have_exact_owners(self):
        for symbol, old_owner, new_owner in (("_synthetic_c_live", 3, 4), ("_synthetic_rust_live", 4, 3)):
            text = self.map_text.replace(f"[ {old_owner}] {symbol}", f"[ {new_owner}] {symbol}")
            self.map_path.write_text(text)
            with self.subTest(symbol=symbol), self.assertRaisesRegex(observer.ObservationError, "wrong archive"):
                self.observe()

    def test_diagnostic_roots_and_both_strong_system_frameworks_are_required(self):
        original = self.link_args[:]
        for value in ("_plist_free", "CoreFoundation", "SystemConfiguration"):
            self.link_args = original[:]
            index = self.link_args.index(value)
            del self.link_args[index - 1:index + 1]
            with self.subTest(value=value), self.assertRaisesRegex(observer.ObservationError, "final Ld lacks"):
                self.observe()

    def test_additional_unmerged_c_constituent_is_rejected(self):
        for extra in ("-lusbmuxd-2.0", str(self.processed / "libusbmuxd-2.0.a")):
            self.link_args.append(extra)
            with self.subTest(extra=extra), self.assertRaisesRegex(observer.ObservationError, "alternate C"):
                self.observe()
            self.link_args.pop()


if __name__ == "__main__":
    unittest.main()
