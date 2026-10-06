"""NEW synthetic five-lane handoff tests, authored after original fixture loss.

The API records, Git objects, command statuses and opaque archives are controlled
Python data. Passing these tests never establishes a native build or device result.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_handoff
import prepare_binding as binding
from test_diagnostic_binding import DiagnosticFixture, git_blob, put, put_json, success


class NativeHandoffFixture:
    """An authenticated-looking fixture transport, with independent Git identities.

    pack(lane) refreshes that ZIP/API identity only. refresh() writes the outer
    handoff and records its external expected hash. Neither silently rewrites
    mutated receipts, source snapshots, or extracted bytes.
    """

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.fixture = DiagnosticFixture(self.root / "binding", self.root / "apple-producer/apple-producer-output")
        self.contract = self.fixture.contract
        self.repository, self.recipe = self.fixture.repository, self.fixture.recipe
        producer = {"repository": "example/repository", "repository_id": 123, "run_id": 456,
                    "source_commit": "a" * 40, "run_attempt": 3}
        self.context = {"repository": producer["repository"], "repository_id": producer["repository_id"],
                        "run_id": 789, "source_commit": "b" * 40, "consumer_attempt": 1,
                        "needs": dict(native_handoff.NEEDS), "producer_context": copy.deepcopy(producer)}
        self.data = {"schema": 1, "mode": "retained-producer", "producer_context": copy.deepcopy(producer),
                     "context": copy.deepcopy(self.context), "artifacts": {}}
        self.path = self.root / "handoff.json"
        self.source_identities()
        api = "https://api.github.com/repos/" + producer["repository"] + "/actions/"
        for identity, (lane, requirement) in enumerate(self.contract["same_run_requirements"].items(), 1):
            root = self.root / lane
            output = root / requirement["output_directory"]
            field = "profile" if requirement["job_id"] == "component-fixtures" else "proof"
            put_json(root / "evidence/run-context.json", {field: lane, "source_commit": producer["source_commit"],
                     "run_id": str(producer["run_id"]), "run_attempt": "1"})
            kind = requirement["receipt_kind"]
            if kind != "apple":
                receipt = {"profile_sha256": requirement["profile_sha256"],
                           "source_commit": self.contract["native_upstream_commit"],
                           "artifact_or_product_activation": False, "header_probe_linked_or_executed": False}
                suites = []
                for number, suite in enumerate(requirement["suites"], 1):
                    status_file, log_file = f"{number:02d}-suite.status.json", f"{number:02d}-suite.txt"
                    put_json(output / status_file, success())
                    put(output / log_file, b"synthetic test log; no commands executed\n")
                    suites.append({**suite, "passed": suite["expected_passed"],
                                   "status_file": status_file, "log_file": log_file})
                if kind == "host":
                    receipt.update(profile_kind="host-only-native-tests", expected_fixture_count=requirement["expected_count"],
                                   observed_fixture_count=requirement["expected_count"], tests=suites)
                elif kind == "component":
                    receipt.update(profile=lane, passed=requirement["expected_count"], tests=suites)
                else:
                    receipt.update(suite=requirement["suites"][0], passed=requirement["expected_count"],
                                   features=requirement["features"], apple_or_device_compatibility=False,
                                   status_file=suites[0]["status_file"], log_file=suites[0]["log_file"])
                put_json(output / "test-evidence.json", receipt)
                for name in ("vendor-input-audit.json", "derived-vendor-input-audit.json", "workspace-input-audit.json"):
                    put_json(output / name, {"original_inputs_unchanged": True})
                put_json(output / "provider-input-audit.json", {"unchanged": True})
            metadata = {"id": identity, "name": requirement["artifact_prefix"] + lane + "-" + producer["source_commit"] + "-1",
                        "expired": False, "url": api + "artifacts/" + str(identity),
                        "workflow_run": {"id": producer["run_id"], "head_sha": producer["source_commit"],
                                         "repository_id": producer["repository_id"], "head_repository_id": producer["repository_id"]}}
            job = {"id": 1000 + identity, "url": api + "jobs/" + str(1000 + identity),
                   "name": requirement["job_name"], "run_id": producer["run_id"], "run_attempt": 1,
                   "head_sha": producer["source_commit"], "status": "completed", "conclusion": "success"}
            self.data["artifacts"][lane] = {"producer_attempt": 1, "api_metadata": metadata, "producer_job": job,
                "producer_job_query": api + "runs/456/attempts/1/jobs", "archive_file": lane + ".zip", "extracted_root": lane}
            self.pack(lane)
        self.refresh()

    def source_identities(self):
        entries = [{"path": path.relative_to(self.repository).as_posix(), "mode": "100644", "type": "blob",
                    "sha": git_blob(path.read_bytes())} for path in sorted(self.repository.rglob("*")) if path.is_file()]
        for prefix, context, tree_id in (("source", self.data["producer_context"], "f" * 40),
                                         ("consumer", self.context, "e" * 40)):
            base = "https://api.github.com/repos/" + context["repository"] + "/git/"
            self.data["api_" + prefix + "_commit"] = {"sha": context["source_commit"],
                "url": base + "commits/" + context["source_commit"], "tree": {"sha": tree_id}}
            self.data["api_" + prefix + "_tree"] = {"sha": tree_id, "url": base + "trees/" + tree_id,
                "truncated": False, "tree": copy.deepcopy(entries)}

    def pack(self, lane):
        row = self.data["artifacts"][lane]
        extracted = self.root / row["extracted_root"]
        archive = self.root / row["archive_file"]
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
            for path in sorted(extracted.rglob("*")):
                if path.is_file():
                    zipped.write(path, path.relative_to(extracted).as_posix())
        row["api_metadata"]["digest"] = "sha256:" + binding.file_hash(archive)
        row["api_metadata"]["size_in_bytes"] = archive.stat().st_size

    def refresh(self):
        self.data["context"] = copy.deepcopy(self.context)
        self.handoff_hash = put_json(self.path, self.data)
        return self.handoff_hash

    def verify(self):
        with self.fixture.mock_retained():
            return native_handoff.verify_handoff(self.contract, self.path, self.handoff_hash, self.context,
                self.fixture.artifact, self.fixture.receipt_hash, self.recipe)

    def bind(self):
        self.fixture.write_contract()
        with patch.object(binding, "HERE", self.fixture.here), self.fixture.mock_retained():
            return binding.bind(self.fixture.prepared, self.fixture.artifact, self.fixture.receipt_hash, self.fixture.output,
                handoff_path=self.path, handoff_sha256=self.handoff_hash, context=self.context, native_recipe=self.recipe)

    def lane_output(self, lane):
        return self.root / lane / self.contract["same_run_requirements"][lane]["output_directory"]

    def mutate_json(self, lane, name, change):
        path = self.lane_output(lane) / name
        value = json.loads(path.read_text())
        change(value)
        put_json(path, value)
        self.pack(lane)
        self.refresh()

    def set_attempt(self, lane, attempt):
        row = self.data["artifacts"][lane]
        requirement = self.contract["same_run_requirements"][lane]
        row["producer_attempt"] = attempt
        row["api_metadata"]["name"] = requirement["artifact_prefix"] + lane + "-" + self.data["producer_context"]["source_commit"] + "-" + str(attempt)
        row["producer_job"]["run_attempt"] = attempt
        row["producer_job_query"] = row["producer_job_query"].replace("/attempts/1/", "/attempts/" + str(attempt) + "/")
        path = self.root / lane / "evidence/run-context.json"
        value = json.loads(path.read_text())
        value["run_attempt"] = str(attempt)
        put_json(path, value)
        self.pack(lane)
        self.refresh()


class NativeHandoffTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="new-native-handoff-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture = NativeHandoffFixture(self.root)

    def reject(self):
        self.fixture.refresh()
        with self.assertRaises((ValueError, KeyError, OSError)):
            self.fixture.verify()

    def test_five_authenticated_synthetic_lanes_use_independent_source_identities(self):
        result = self.fixture.verify()
        self.assertEqual(set(result["producers"]), {"host-only", "combined", "acquisition-transcript", "host-transcript", "apple-producer"})
        self.assertEqual(result["producer_context"]["source_commit"], "a" * 40)
        self.assertEqual(result["context"]["source_commit"], "b" * 40)
        self.assertEqual(len(result["source_match"]["producer"]["files"]), 3)
        self.assertEqual(len(result["source_match"]["consumer"]["files"]), 16)
        self.assertEqual([self.fixture.contract["same_run_requirements"][lane]["expected_count"]
                          for lane in ("host-only", "combined", "acquisition-transcript", "host-transcript")], [26, 100, 3, 10])

    def test_earlier_lane_attempts_in_one_later_successful_run_are_allowed(self):
        self.fixture.set_attempt("host-only", 2)
        self.fixture.set_attempt("apple-producer", 3)
        result = self.fixture.verify()
        self.assertEqual(result["producers"]["host-only"]["producer_attempt"], 2)
        self.assertEqual(result["producers"]["apple-producer"]["producer_attempt"], 3)
        self.assertEqual(result["producers"]["combined"]["producer_attempt"], 1)

    def test_missing_handoff_is_rejected(self):
        with self.assertRaises(ValueError):
            native_handoff.verify_handoff(self.fixture.contract, None, None, None,
                self.fixture.fixture.artifact, self.fixture.fixture.receipt_hash, self.fixture.recipe)

    def test_changed_handoff_cannot_use_previously_trusted_outer_hash(self):
        put(self.fixture.path, self.fixture.path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "identity differs"):
            self.fixture.verify()

    def test_wrong_external_apple_receipt_hash_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Apple artifact or receipt"):
            native_handoff.verify_handoff(self.fixture.contract, self.fixture.path, self.fixture.handoff_hash,
                self.fixture.context, self.fixture.fixture.artifact, "0" * 64, self.fixture.recipe)

    def test_static_prerequisite_preclearance_is_rejected(self):
        self.fixture.contract["native_prerequisite_cleared"] = True
        self.reject()

    def test_non_success_consumer_need_is_rejected(self):
        self.fixture.context["needs"]["native-proofs"] = "skipped"
        self.reject()

    def test_boolean_consumer_identity_is_rejected(self):
        self.fixture.context["run_id"] = True
        self.reject()

    def test_unexpected_consumer_context_field_is_rejected(self):
        self.fixture.context["unreviewed"] = "value"
        self.reject()

    def test_wrong_handoff_mode_is_rejected(self):
        self.fixture.data["mode"] = "same-run"
        self.reject()

    def test_inconsistent_independent_producer_selection_is_rejected(self):
        self.fixture.data["producer_context"]["run_id"] += 1
        self.reject()

    def test_missing_lane_is_rejected(self):
        del self.fixture.data["artifacts"]["host-transcript"]
        self.reject()

    def test_extra_lane_is_rejected(self):
        self.fixture.data["artifacts"]["unreviewed"] = copy.deepcopy(self.fixture.data["artifacts"]["host-only"])
        self.reject()

    def test_future_lane_attempt_is_rejected(self):
        self.fixture.set_attempt("host-only", 4)
        self.reject()

    def test_boolean_lane_attempt_is_rejected(self):
        self.fixture.data["artifacts"]["host-only"]["producer_attempt"] = True
        self.reject()

    def test_reused_artifact_identity_is_rejected(self):
        rows = list(self.fixture.data["artifacts"].values())
        rows[1]["api_metadata"]["id"] = rows[0]["api_metadata"]["id"]
        rows[1]["api_metadata"]["url"] = rows[0]["api_metadata"]["url"]
        self.reject()

    def test_expired_artifact_is_rejected(self):
        self.fixture.data["artifacts"]["host-only"]["api_metadata"]["expired"] = True
        self.reject()

    def test_other_repository_artifact_url_is_rejected(self):
        self.fixture.data["artifacts"]["host-only"]["api_metadata"]["url"] = "https://api.github.com/repos/other/repository/actions/artifacts/1"
        self.reject()

    def test_wrong_producer_run_in_artifact_metadata_is_rejected(self):
        self.fixture.data["artifacts"]["combined"]["api_metadata"]["workflow_run"]["id"] = 789
        self.reject()

    def test_unsuccessful_exact_producer_job_is_rejected(self):
        self.fixture.data["artifacts"]["combined"]["producer_job"]["conclusion"] = "failure"
        self.reject()

    def test_lookalike_job_name_is_rejected(self):
        self.fixture.data["artifacts"]["combined"]["producer_job"]["name"] += " extra"
        self.reject()

    def test_wrong_attempt_job_query_is_rejected(self):
        row = self.fixture.data["artifacts"]["combined"]
        row["producer_job_query"] = row["producer_job_query"].replace("attempts/1", "attempts/2")
        self.reject()

    def test_wrong_zip_api_size_is_rejected(self):
        self.fixture.data["artifacts"]["host-only"]["api_metadata"]["size_in_bytes"] += 1
        self.reject()

    def test_wrong_zip_api_digest_is_rejected(self):
        self.fixture.data["artifacts"]["host-only"]["api_metadata"]["digest"] = "sha256:" + "0" * 64
        self.reject()

    def test_extracted_receipt_change_is_rejected_without_repacking(self):
        put(self.fixture.lane_output("host-only") / "test-evidence.json", b"{}\n")
        self.reject()

    def test_duplicate_zip_member_is_rejected_even_with_fresh_api_digest(self):
        lane = "host-only"
        row = self.fixture.data["artifacts"][lane]
        archive = self.root / row["archive_file"]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(archive, "a") as zipped:
                zipped.writestr("evidence/run-context.json", b"{}")
        row["api_metadata"].update(digest="sha256:" + binding.file_hash(archive), size_in_bytes=archive.stat().st_size)
        self.reject()

    def test_zip_symlink_receipt_is_rejected(self):
        lane = "host-only"
        row = self.fixture.data["artifacts"][lane]
        archive = self.root / row["archive_file"]
        with zipfile.ZipFile(archive) as zipped:
            entries = [(info.filename, zipped.read(info)) for info in zipped.infolist()]
        with zipfile.ZipFile(archive, "w") as zipped:
            for name, data in entries:
                if name == "evidence/run-context.json":
                    info = zipfile.ZipInfo(name)
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    zipped.writestr(info, data)
                else:
                    zipped.writestr(name, data)
        row["api_metadata"].update(digest="sha256:" + binding.file_hash(archive), size_in_bytes=archive.stat().st_size)
        self.reject()

    def test_symlinked_extraction_root_is_rejected(self):
        source = self.root / "host-only"
        source.rename(self.root / "host-only-real")
        source.symlink_to(self.root / "host-only-real", target_is_directory=True)
        self.reject()

    def test_shared_extraction_root_is_rejected(self):
        self.fixture.data["artifacts"]["host-only"]["extracted_root"] = "combined"
        self.reject()

    def test_wrong_authenticated_lane_context_is_rejected(self):
        path = self.root / "host-only/evidence/run-context.json"
        data = json.loads(path.read_text())
        data["source_commit"] = "b" * 40
        put_json(path, data)
        self.fixture.pack("host-only")
        self.reject()

    def test_host_aggregate_count_must_match_reviewed_twenty_six(self):
        self.fixture.mutate_json("host-only", "test-evidence.json", lambda value: value.update(observed_fixture_count=25))
        self.reject()

    def test_combined_aggregate_count_must_match_reviewed_one_hundred(self):
        self.fixture.mutate_json("combined", "test-evidence.json", lambda value: value.update(passed=99))
        self.reject()

    def test_suite_count_substitution_cannot_hide_behind_correct_aggregate(self):
        def mutate(value):
            value["tests"][0]["passed"] -= 1
            value["tests"][1]["passed"] += 1
        self.fixture.mutate_json("combined", "test-evidence.json", mutate)
        self.reject()

    def test_duplicate_suite_cannot_replace_required_suite(self):
        def mutate(value):
            value["tests"][-1] = copy.deepcopy(value["tests"][0])
        self.fixture.mutate_json("host-only", "test-evidence.json", mutate)
        self.reject()

    def test_transcript_features_are_exact(self):
        self.fixture.mutate_json("host-transcript", "test-evidence.json", lambda value: value["features"].append("unreviewed"))
        self.reject()

    def test_transcript_cannot_claim_device_compatibility(self):
        self.fixture.mutate_json("acquisition-transcript", "test-evidence.json", lambda value: value.update(apple_or_device_compatibility=True))
        self.reject()

    def test_wrong_native_upstream_commit_is_rejected(self):
        self.fixture.mutate_json("host-only", "test-evidence.json", lambda value: value.update(source_commit="0" * 40))
        self.reject()

    def test_wrong_source_profile_is_rejected(self):
        self.fixture.mutate_json("combined", "test-evidence.json", lambda value: value.update(profile_sha256="0" * 64))
        self.reject()

    def test_truncated_command_success_is_rejected(self):
        self.fixture.mutate_json("host-only", "01-suite.status.json", lambda value: value.update(output_truncated=True))
        self.reject()

    def test_nonzero_exit_cannot_claim_success(self):
        self.fixture.mutate_json("combined", "01-suite.status.json", lambda value: value.update(returncode=1))
        self.reject()

    def test_unreaped_child_is_rejected(self):
        self.fixture.mutate_json("host-transcript", "01-suite.status.json", lambda value: value["cleanup"].update(direct_child_reaped=False))
        self.reject()

    def test_missing_status_receipt_is_rejected(self):
        (self.fixture.lane_output("host-only") / "01-suite.status.json").unlink()
        self.fixture.pack("host-only")
        self.reject()

    def test_vendor_input_mutation_is_rejected(self):
        self.fixture.mutate_json("host-only", "vendor-input-audit.json", lambda value: value.update(original_inputs_unchanged=False))
        self.reject()

    def test_derived_vendor_input_mutation_is_rejected(self):
        self.fixture.mutate_json("combined", "derived-vendor-input-audit.json", lambda value: value.update(original_inputs_unchanged=False))
        self.reject()

    def test_original_workspace_input_mutation_is_rejected(self):
        self.fixture.mutate_json("acquisition-transcript", "workspace-input-audit.json", lambda value: value.update(original_inputs_unchanged=False))
        self.reject()

    def test_provider_input_mutation_is_rejected(self):
        self.fixture.mutate_json("host-transcript", "provider-input-audit.json", lambda value: value.update(unchanged=False))
        self.reject()

    def test_missing_provider_audit_is_rejected(self):
        (self.fixture.lane_output("combined") / "provider-input-audit.json").unlink()
        self.fixture.pack("combined")
        self.reject()

    def test_changed_current_native_recipe_cannot_use_old_git_tree(self):
        put(self.fixture.recipe / "marker.py", b"# changed")
        self.reject()

    def test_wrong_producer_blob_is_rejected(self):
        entry = next(row for row in self.fixture.data["api_source_tree"]["tree"]
                     if row["path"] == "Integration/Dependencies/idevice/marker.py")
        entry["sha"] = "0" * 40
        self.reject()

    def test_wrong_consumer_support_blob_is_rejected(self):
        support = next(iter(self.fixture.contract["prepared_support_sources"].values()))["source_path"]
        entry = next(row for row in self.fixture.data["api_consumer_tree"]["tree"] if row["path"] == support)
        entry["sha"] = "0" * 40
        self.reject()

    def test_missing_consumer_gate_blob_is_rejected(self):
        rows = self.fixture.data["api_consumer_tree"]["tree"]
        rows[:] = [row for row in rows if row["path"] != "Integration/pairing_safety.py"]
        self.reject()

    def test_duplicate_git_path_is_ambiguous_and_rejected(self):
        rows = self.fixture.data["api_consumer_tree"]["tree"]
        rows.append(copy.deepcopy(rows[0]))
        self.reject()

    def test_truncated_producer_git_tree_is_rejected(self):
        self.fixture.data["api_source_tree"]["truncated"] = True
        self.reject()

    def test_wrong_git_commit_tree_relationship_is_rejected(self):
        self.fixture.data["api_consumer_commit"]["tree"]["sha"] = "c" * 40
        self.reject()

    def test_symlink_mode_source_blob_is_rejected(self):
        entry = next(row for row in self.fixture.data["api_source_tree"]["tree"]
                     if row["path"] == "Integration/Dependencies/idevice/marker.py")
        entry["mode"] = "120000"
        self.reject()


if __name__ == "__main__":
    unittest.main()
