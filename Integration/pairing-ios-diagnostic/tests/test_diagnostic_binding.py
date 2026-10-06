"""NEW portable boundary fixtures authored after loss of the former tests.

Every artifact and retained command receipt here is synthetic. No native tool,
downloaded source, binary parser, signing path, or device operation is executed.
These tests establish Python rejection/copy boundaries, not Apple acceptance.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import prepare_binding as binding
import read_runtime_producer as runtime


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha(data)


def put_json(path, value):
    return put(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def success():
    return {"outcome": "success", "returncode": 0, "output_complete": True,
            "output_truncated": False,
            "cleanup": {"direct_child_reaped": True, "group_empty": True}}


class DiagnosticFixture:
    """Synthetic owned files, retaining the real contract's source/path roles."""

    def __init__(self, root, artifact=None):
        self.root = Path(root)
        self.repository = self.root / "repository"
        self.here = self.repository / "Integration/pairing-ios-diagnostic"
        self.prepared = self.root / "prepared"
        self.output = self.root / "bound"
        self.artifact = Path(artifact) if artifact else self.root / "apple-artifact"
        self.contract = copy.deepcopy(json.loads((HERE / "input-contract.json").read_text()))
        self.recipe = self.repository / "Integration/Dependencies/idevice"
        for selected in (self.contract["prepared_composition_sources"],
                         self.contract["prepared_support_sources"]):
            for name, item in selected.items():
                # Source bodies are opaque fixture bytes; runtime uses only identities.
                data = ("// synthetic opaque source: " + name + "\n").encode()
                item["sha256"] = put(self.prepared / name, data)
                put(self.repository / item["source_path"], data)
        gate = (HERE.parent / self.contract["preparation_gate"]["path"]).read_bytes()
        if sha(gate) != self.contract["preparation_gate"]["sha256"]:
            raise AssertionError("reviewed gate identity changed before fixture construction")
        put(self.here.parent / self.contract["preparation_gate"]["path"], gate)
        sentinel = (HERE / "PairingCompositionCompileSentinel.swift").read_bytes()
        self.contract["sentinel"]["sha256"] = put(self.here / "PairingCompositionCompileSentinel.swift", sentinel)
        gateway = (HERE / "upstream/DeviceGateway-Package.swift").read_bytes()
        if (sha(gateway) != self.contract["gateway"]["sha256"]
                or git_blob(gateway) != self.contract["gateway"]["git_blob"]):
            raise AssertionError("reviewed gateway preimage changed")
        put(self.prepared / self.contract["gateway"]["prepared_path"], gateway)
        put(self.prepared / "Dependencies/minimuxer/DeviceGateway/idevice/IdeviceGateway.swift",
            b"// synthetic opaque gateway source\n")
        index = {"marker.py": put(self.recipe / "marker.py", b"# synthetic native recipe identity\n")}
        self.contract["apple_recipe_index_sha256"] = put_json(self.recipe / "apple-recipe-files.json", index)
        workflow = self.contract["retained_producer"]["workflow_path"]
        self.contract["retained_producer"]["workflow_sha256"] = put(
            self.repository / workflow, b"# synthetic retained producer workflow identity\n")
        self.receipt = {"profile_sha256": self.contract["apple_profile_sha256"],
                        "recipe_lock_sha256": self.contract["apple_recipe_index_sha256"],
                        "toolchain_lock_sha256": sha(b"synthetic toolchain lock"),
                        "framework_provider_bundled": False, "ios_binaries_executed": False,
                        "consumer_or_product_activation": False, "targets": [], "files": {}}
        libraries = []
        for target, identifier, variant in (("aarch64-apple-ios", "ios-arm64", ""),
                                             ("aarch64-apple-ios-sim", "ios-arm64-simulator", "simulator")):
            prefix = "IDevice.xcframework/" + identifier + "/"
            # Deliberately not native archive bytes; validation must remain opaque.
            archive = b"synthetic opaque archive for " + target.encode() + b"\n"
            baseline = b"/* synthetic retained baseline, not generated C */\n"
            scoped = b"/* synthetic retained scoped header, not generated C */\n"
            final = scoped + b"/* synthetic retained plist append */\n"
            row = {"target": {"rust": target},
                   "library_sha256": put(self.artifact / (prefix + "libidevice_ffi.a"), archive),
                   "header_sha256": put(self.artifact / (prefix + "Headers/idevice.h"), final),
                   "provider_receipt": {"kind": "apple-framework", "native_libraries": [],
                       "environment": {target.upper().replace("-", "_") + "_OPENSSL_LIBS": ""}},
                   "production_features": {"synthetic_peer_selected": False},
                   "header_probe_linked_or_executed": False,
                   "toolchain_observations": {key: "synthetic retained " + key for key in
                       ("xcode", "clang", "swiftc", "sdk_iphoneos_version", "sdk_iphoneos_build")},
                   "link_probes": [{"group": group, "language": language,
                       "command": ["synthetic-" + language, "-Wl,-u,_synthetic_" + group],
                       "output_sha256": sha((target + group + language).encode()), "executed": False}
                       for group in ("pairing", "host", "result_constants") for language in ("c", "swift")]}
            put(self.artifact / (prefix + "Headers/module.modulemap"), b"module IDevice { header \"idevice.h\" export * }\n")
            library = {"LibraryIdentifier": identifier, "LibraryPath": "libidevice_ffi.a",
                       "HeadersPath": "Headers", "SupportedPlatform": "ios", "SupportedArchitectures": ["arm64"]}
            if variant:
                library["SupportedPlatformVariant"] = variant
            libraries.append(library)
            evidence = self.artifact / "provenance" / target
            checked = {"schema": 1, "baseline_sha256": sha(baseline), "scoped_sha256": sha(scoped),
                       "declarations_sha256": self.contract["result_header_contract"]["declarations_sha256"],
                       "unrelated_nonempty_lines_identical": True, "blank_item_separators_ignored": True,
                       "native_import_or_link_established_by_this_check": False,
                       "final_header_sha256": sha(final), "cpp_header_identical": True}
            row["result_header_contract"] = checked
            put_json(evidence / "pairing-result-header-check.json", checked)
            retained = {"schema": 1, "per_file_byte_limit": self.contract["result_header_contract"]["per_file_byte_limit"], "files": {}}
            for name, data in (("ffi/idevice.cbindgen-baseline.h", baseline),
                               ("ffi/idevice.cbindgen-scoped.h", scoped), ("ffi/idevice.h", final),
                               ("cpp/include/idevice.h", final)):
                retained["files"][name] = {"status": "retained", "bytes": len(data),
                    "sha256": put(evidence / "generated-headers" / name, data)}
            put_json(evidence / "generated-header-retention.json", retained)
            for probe in row["link_probes"]:
                put_json(evidence / ("05-link-" + probe["group"] + "-" + probe["language"] + ".txt.status.json"), success())
            self.receipt["targets"].append(row)
        put(self.artifact / "IDevice.xcframework/Info.plist", plistlib.dumps({"AvailableLibraries": libraries}))
        self.refresh(inventory=True)
        self.write_contract()

    def write_contract(self):
        put_json(self.here / "input-contract.json", self.contract)

    def refresh(self, inventory=False):
        if inventory:
            self.receipt["files"] = {p.relative_to(self.artifact).as_posix(): binding.file_hash(p)
                for p in sorted(self.artifact.rglob("*")) if p.is_file() and p.name != "apple-build-evidence.json"}
        self.receipt_hash = put_json(self.artifact / "apple-build-evidence.json", self.receipt)
        return self.receipt_hash

    def evidence(self, name, target=0):
        return self.artifact / "provenance" / self.receipt["targets"][target]["target"]["rust"] / name

    def artifact_inputs(self):
        return binding.artifact_inputs(self.artifact, self.receipt_hash, self.contract)


class DiagnosticBindingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="new-diagnostic-fixtures-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture = DiagnosticFixture(self.root)

    def reject_artifact(self):
        with self.assertRaises((ValueError, KeyError, OSError)):
            self.fixture.artifact_inputs()

    def test_synthetic_two_slice_six_probe_metadata_is_accepted_without_execution(self):
        result = self.fixture.artifact_inputs()
        self.assertEqual(len(result["targets"]), 2)
        self.assertTrue(all(len(row["link_probes"]) == 6 for row in result["targets"].values()))
        self.assertFalse(result["binary_format_inspected"])
        self.assertEqual(set(result["device_slice"]), {"archive", "header", "module_map"})

    def test_frozen_contract_has_fourteen_compiler_and_one_opaque_support_sources(self):
        contract = json.loads((HERE / "input-contract.json").read_text())
        self.assertEqual(len(contract["prepared_composition_sources"]), 14)
        self.assertEqual(list(contract["prepared_support_sources"]), ["SideStore/Core/Pairing/PairingFileManager.swift"])
        self.assertEqual(contract["preparation_gate"]["sha256"], "9ddf28114d14bd99353ef4219e3043e85a2f22ea9429c85d1f887674bceebd68")
        self.assertFalse(contract["native_prerequisite_cleared"])
        self.assertFalse(contract["consumer_or_product_activation"])

    def test_external_apple_receipt_hash_is_mandatory(self):
        with self.assertRaises(ValueError):
            binding.artifact_inputs(self.fixture.artifact, "0" * 64, self.fixture.contract)

    def test_missing_slice_is_rejected(self):
        self.fixture.receipt["targets"].pop()
        self.fixture.refresh()
        self.reject_artifact()

    def test_duplicate_slice_is_rejected(self):
        self.fixture.receipt["targets"][1] = copy.deepcopy(self.fixture.receipt["targets"][0])
        self.fixture.refresh()
        self.reject_artifact()

    def test_missing_result_constants_probe_is_rejected(self):
        self.fixture.receipt["targets"][0]["link_probes"].pop()
        self.fixture.refresh()
        self.reject_artifact()

    def test_duplicate_probe_cannot_replace_required_probe(self):
        probes = self.fixture.receipt["targets"][0]["link_probes"]
        probes[-1] = copy.deepcopy(probes[0])
        self.fixture.refresh()
        self.reject_artifact()

    def test_executed_link_probe_is_rejected(self):
        self.fixture.receipt["targets"][1]["link_probes"][0]["executed"] = True
        self.fixture.refresh()
        self.reject_artifact()

    def test_provider_archive_is_rejected(self):
        self.fixture.receipt["targets"][0]["provider_receipt"]["native_libraries"] = ["unapproved.a"]
        self.fixture.refresh()
        self.reject_artifact()

    def test_provider_empty_openssl_setting_must_be_present(self):
        self.fixture.receipt["targets"][0]["provider_receipt"]["environment"].clear()
        self.fixture.refresh()
        self.reject_artifact()

    def test_missing_toolchain_observation_is_rejected(self):
        self.fixture.receipt["targets"][0]["toolchain_observations"].pop("sdk_iphoneos_build")
        self.fixture.refresh()
        self.reject_artifact()

    def test_synthetic_peer_feature_is_rejected(self):
        self.fixture.receipt["targets"][0]["production_features"]["synthetic_peer_selected"] = True
        self.fixture.refresh()
        self.reject_artifact()

    def test_activation_claim_is_rejected(self):
        self.fixture.receipt["consumer_or_product_activation"] = True
        self.fixture.refresh()
        self.reject_artifact()

    def test_header_check_receipt_mutation_is_rejected(self):
        put_json(self.fixture.evidence("pairing-result-header-check.json"), {"schema": 1})
        self.reject_artifact()

    def test_header_comparison_flags_cannot_be_reauthenticated_as_success(self):
        checked = self.fixture.receipt["targets"][0]["result_header_contract"]
        checked["unrelated_nonempty_lines_identical"] = False
        put_json(self.fixture.evidence("pairing-result-header-check.json"), checked)
        self.fixture.refresh(inventory=True)
        self.reject_artifact()

    def test_changed_result_declaration_pin_is_rejected(self):
        checked = self.fixture.receipt["targets"][0]["result_header_contract"]
        checked["declarations_sha256"] = "0" * 64
        put_json(self.fixture.evidence("pairing-result-header-check.json"), checked)
        self.fixture.refresh(inventory=True)
        self.reject_artifact()

    def test_missing_retained_baseline_is_rejected(self):
        self.fixture.evidence("generated-headers/ffi/idevice.cbindgen-baseline.h").unlink()
        self.reject_artifact()

    def test_changed_retained_scoped_bytes_are_rejected(self):
        put(self.fixture.evidence("generated-headers/ffi/idevice.cbindgen-scoped.h"), b"changed opaque bytes")
        self.reject_artifact()

    def test_copied_header_must_match_final_header(self):
        put(self.fixture.evidence("generated-headers/cpp/include/idevice.h"), b"changed copied opaque bytes")
        self.fixture.refresh(inventory=True)
        self.reject_artifact()

    def test_unexpected_retention_entry_is_rejected(self):
        path = self.fixture.evidence("generated-header-retention.json")
        retained = json.loads(path.read_text())
        retained["files"]["ffi/unexpected.h"] = {"status": "missing"}
        put_json(path, retained)
        self.fixture.refresh(inventory=True)
        self.reject_artifact()

    def test_retained_header_byte_count_must_be_exact_integer(self):
        path = self.fixture.evidence("generated-header-retention.json")
        retained = json.loads(path.read_text())
        retained["files"]["ffi/idevice.h"]["bytes"] = True
        put_json(path, retained)
        self.fixture.refresh(inventory=True)
        self.reject_artifact()

    def test_header_receipt_cannot_omit_raw_file_inventory(self):
        key = next(name for name in self.fixture.receipt["files"] if "cbindgen-baseline" in name)
        del self.fixture.receipt["files"][key]
        self.fixture.refresh()
        self.reject_artifact()

    def test_missing_force_link_success_receipt_is_rejected(self):
        self.fixture.evidence("05-link-result_constants-swift.txt.status.json").unlink()
        self.reject_artifact()

    def test_incomplete_force_link_cleanup_is_rejected(self):
        status = success()
        status["cleanup"]["group_empty"] = False
        put_json(self.fixture.evidence("05-link-result_constants-c.txt.status.json"), status)
        self.fixture.refresh(inventory=True)
        self.reject_artifact()

    def test_changed_opaque_archive_is_rejected(self):
        put(self.fixture.artifact / "IDevice.xcframework/ios-arm64/libidevice_ffi.a", b"changed")
        self.reject_artifact()

    def test_uninventoried_framework_file_is_rejected(self):
        put(self.fixture.artifact / "IDevice.xcframework/unexpected", b"extra")
        self.reject_artifact()

    def test_framework_symlink_is_rejected(self):
        (self.fixture.artifact / "IDevice.xcframework/alias").symlink_to("Info.plist")
        self.reject_artifact()

    def test_wrong_architecture_metadata_is_rejected(self):
        path = self.fixture.artifact / "IDevice.xcframework/Info.plist"
        info = plistlib.loads(path.read_bytes())
        info["AvailableLibraries"][0]["SupportedArchitectures"] = ["x86_64"]
        put(path, plistlib.dumps(info))
        self.fixture.refresh(inventory=True)
        self.reject_artifact()

    def test_prepared_support_source_is_checked_as_opaque_identity(self):
        name = next(iter(self.fixture.contract["prepared_support_sources"]))
        put(self.fixture.prepared / name, b"changed opaque manager support")
        with self.assertRaisesRegex(ValueError, "composition/support"):
            binding.composition_inputs(self.fixture.prepared, self.fixture.contract)

    def test_gateway_patch_requires_exact_reviewed_preimage(self):
        with self.assertRaisesRegex(ValueError, "preimage"):
            binding.patched_gateway(b"// changed", self.fixture.contract)

    def test_current_recipe_file_change_is_rejected(self):
        put(self.fixture.recipe / "marker.py", b"# changed")
        with self.assertRaisesRegex(ValueError, "recipe source"):
            binding.verify_recipe_inputs(self.fixture.recipe, self.fixture.contract)


class OwnedBindingCopyTests(unittest.TestCase):
    def setUp(self):
        from test_native_handoff import NativeHandoffFixture
        temporary = tempfile.TemporaryDirectory(prefix="new-binding-copy-")
        self.addCleanup(temporary.cleanup)
        self.fixture = NativeHandoffFixture(Path(temporary.name))

    def test_handoff_success_allows_only_owned_diagnostic_postimages(self):
        f = self.fixture.fixture
        before = {p.relative_to(f.prepared): p.read_bytes() for p in f.prepared.rglob("*") if p.is_file()}
        result = self.fixture.bind()
        self.assertEqual(before, {p.relative_to(f.prepared): p.read_bytes() for p in f.prepared.rglob("*") if p.is_file()})
        self.assertFalse(result["consumer_or_product_activation"])
        self.assertFalse(result["native_or_app_build_executed"])
        self.assertFalse(result["runtime_capability_gates_changed"])
        self.assertEqual(len(result["source_inputs"]), 17)
        self.assertTrue((f.output / "TETHERLESS_PAIRING_DIAGNOSTIC_BINDING.json").is_file())
        gateway = (f.output / f.contract["gateway"]["prepared_path"]).read_text()
        self.assertIn('path: "TetherlessDiagnosticArtifacts/IDevice.xcframework"', gateway)
        self.assertNotIn(binding.OLD_TARGET, gateway)
        self.assertEqual(gateway.encode(), binding.patched_gateway(
            before[Path(f.contract["gateway"]["prepared_path"])], f.contract))
        support = next(iter(f.contract["prepared_support_sources"]))
        self.assertEqual((f.output / support).read_bytes(), before[Path(support)])

    def test_missing_handoff_never_starts_copy(self):
        f = self.fixture.fixture
        with patch.object(binding, "HERE", f.here), patch.object(binding.shutil, "copytree") as copytree:
            with self.assertRaises(ValueError):
                binding.bind(f.prepared, f.artifact, f.receipt_hash, f.output, native_recipe=self.fixture.recipe)
            copytree.assert_not_called()
        self.assertFalse(f.output.exists())

    def test_failed_prerequisite_never_starts_copy(self):
        self.fixture.context["needs"]["native-proofs"] = "failure"
        self.fixture.refresh()
        with patch.object(binding.shutil, "copytree") as copytree:
            with self.assertRaises(ValueError):
                self.fixture.bind()
            copytree.assert_not_called()
        self.assertFalse(self.fixture.fixture.output.exists())

    def test_preexisting_output_is_rejected(self):
        self.fixture.fixture.output.mkdir()
        with self.assertRaisesRegex(ValueError, "fresh and separate"):
            self.fixture.bind()

    def test_output_nested_in_prepared_source_is_rejected(self):
        self.fixture.fixture.output = self.fixture.fixture.prepared / "nested"
        with self.assertRaisesRegex(ValueError, "fresh and separate"):
            self.fixture.bind()

    def test_changed_sentinel_is_rejected_before_copy(self):
        put(self.fixture.fixture.here / "PairingCompositionCompileSentinel.swift", b"// changed")
        with patch.object(binding.shutil, "copytree") as copytree:
            with self.assertRaisesRegex(ValueError, "sentinel changed"):
                self.fixture.bind()
            copytree.assert_not_called()

    def assert_copy_mutation_rejected(self, mutation, message=None):
        original = shutil.copytree
        f = self.fixture.fixture
        def copy_then_change(source, destination, *args, **kwargs):
            result = original(source, destination, *args, **kwargs)
            if Path(source) == f.prepared:
                mutation()
            return result
        with patch.object(binding.shutil, "copytree", side_effect=copy_then_change):
            with self.assertRaises((ValueError, OSError, KeyError)):
                self.fixture.bind()
        self.assertFalse((f.output / "TETHERLESS_PAIRING_DIAGNOSTIC_BINDING.json").exists())

    def test_prepared_support_change_during_copy_is_rejected(self):
        f = self.fixture.fixture
        name = next(iter(f.contract["prepared_support_sources"]))
        self.assert_copy_mutation_rejected(lambda: put(f.prepared / name, b"changed opaque support"))

    def test_native_provider_change_during_copy_is_rejected(self):
        f = self.fixture.fixture
        def mutate():
            f.receipt["targets"][0]["provider_receipt"]["native_libraries"] = ["changed"]
            f.refresh()
        self.assert_copy_mutation_rejected(mutate)

    def test_gate_change_during_copy_is_rejected(self):
        f = self.fixture.fixture
        self.assert_copy_mutation_rejected(lambda: put(f.here.parent / "pairing_safety.py", b"changed opaque gate"))

    def test_current_recipe_change_during_copy_is_rejected(self):
        self.assert_copy_mutation_rejected(lambda: put(self.fixture.recipe / "marker.py", b"# changed"))

    def test_handoff_change_during_copy_is_rejected(self):
        self.assert_copy_mutation_rejected(lambda: put(self.fixture.path, b"{}\n"))


class ReservedBindingOutputsTests(unittest.TestCase):
    def test_copied_artifact_parent_symlink_cannot_receive_outside_writes(self):
        from test_native_handoff import NativeHandoffFixture
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = NativeHandoffFixture(root / "fixture")
            outside = root / "outside"
            outside.mkdir()
            marker = outside / "untouched.txt"
            marker.write_bytes(b"controlled outside bytes")
            parent = fixture.fixture.prepared / "Dependencies/minimuxer/DeviceGateway/TetherlessDiagnosticArtifacts"
            parent.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "output parent"):
                fixture.bind()
            self.assertEqual(list(outside.iterdir()), [marker])
            self.assertEqual(marker.read_bytes(), b"controlled outside bytes")
            self.assertFalse(fixture.fixture.output.exists())

    def test_reserved_binding_receipt_symlink_or_regular_file_is_never_overwritten(self):
        from test_native_handoff import NativeHandoffFixture
        for kind in ("symlink", "regular"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixture = NativeHandoffFixture(root / "fixture")
                outside = root / "outside.json"
                outside.write_bytes(b"controlled outside bytes")
                receipt = fixture.fixture.prepared / "TETHERLESS_PAIRING_DIAGNOSTIC_BINDING.json"
                if kind == "symlink":
                    receipt.symlink_to(outside)
                else:
                    receipt.write_bytes(b"existing receipt")
                with self.assertRaisesRegex(ValueError, "output already exists"):
                    fixture.bind()
                self.assertEqual(outside.read_bytes(), b"controlled outside bytes")
                self.assertFalse(fixture.fixture.output.exists())


class ClosedRuntimeTemplateTests(unittest.TestCase):
    def test_checked_in_runtime_template_is_closed(self):
        with self.assertRaises(ValueError):
            runtime.read_context(HERE / "runtime-producer.template.json")
        self.assertFalse((HERE / "runtime-producer.json").exists())

    def test_invalid_runtime_context_emits_no_partial_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context, output = root / "context.json", root / "environment"
            put_json(context, {"schema": 1, "producer_run_id": 456,
                     "producer_source_commit": "a" * 40, "producer_run_attempt": True})
            put(output, b"UNCHANGED=1\n")
            with self.assertRaises(ValueError):
                runtime.emit_context(context, output)
            self.assertEqual(output.read_bytes(), b"UNCHANGED=1\n")


if __name__ == "__main__":
    unittest.main()
