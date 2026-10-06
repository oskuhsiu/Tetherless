"""Real handoff/source validators with controlled API transport and five ZIPs."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import unittest

from test_native_handoff import NativeHandoffFixture
import fetch_retained_handoff as fetch
import native_handoff


class HandoffAPI:
    def __init__(self, fixture, consumer):
        self.fixture = fixture
        self.producer = copy.deepcopy(fixture.data["producer_context"])
        self.base = "https://api.github.com/repos/" + self.producer["repository"] + "/actions/"
        self.calls, self.downloads = [], []
        self.artifacts = copy.deepcopy(fixture.data["artifacts"])
        for row in self.artifacts.values():
            metadata = row["api_metadata"]
            metadata["archive_download_url"] = metadata["url"] + "/zip"
        self.commit = copy.deepcopy(fixture.data["api_source_commit"])
        self.tree = copy.deepcopy(fixture.data["api_source_tree"])
        self.consumer = copy.deepcopy(consumer)
        git_base = "https://api.github.com/repos/" + consumer["repository"] + "/git/"
        self.consumer_commit = copy.deepcopy(fixture.data["api_consumer_commit"])
        self.consumer_tree = copy.deepcopy(fixture.data["api_consumer_tree"])
        self.consumer_commit.update(sha=consumer["source_commit"],
                                    url=git_base + "commits/" + consumer["source_commit"], tree={"sha": "e" * 40})
        self.consumer_tree.update(sha="e" * 40, url=git_base + "trees/" + "e" * 40)

    def get(self, suffix):
        self.calls.append(suffix)
        run = self.producer["run_id"]
        if suffix == f"runs/{run}":
            return {"id": run, "head_sha": self.producer["source_commit"],
                    "run_attempt": self.producer["run_attempt"], "path": fetch.WORKFLOW,
                    "repository": {"id": self.producer["repository_id"], "full_name": self.producer["repository"]},
                    "head_repository": {"id": self.producer["repository_id"]},
                    "status": "completed", "conclusion": "success"}
        if suffix.startswith(f"runs/{run}/artifacts?"):
            rows = [row["api_metadata"] for row in self.artifacts.values()]
            return {"total_count": len(rows), "artifacts": copy.deepcopy(rows)}
        if suffix.startswith(f"runs/{run}/attempts/1/jobs?"):
            jobs = [row["producer_job"] for row in self.artifacts.values()]
            return {"total_count": len(jobs), "jobs": copy.deepcopy(jobs)}
        if suffix.startswith("artifacts/"):
            identity = int(suffix.split("/")[1])
            return copy.deepcopy(next(row["api_metadata"] for row in self.artifacts.values()
                                      if row["api_metadata"]["id"] == identity))
        raise AssertionError("unexpected controlled API request: " + suffix)

    def get_git_commit(self, identity):
        self.calls.append("git/commits/" + identity)
        if identity == self.producer["source_commit"]:
            return copy.deepcopy(self.commit)
        if identity == self.consumer["source_commit"]:
            return copy.deepcopy(self.consumer_commit)
        raise AssertionError("unexpected controlled source commit")

    def get_git_tree(self, identity):
        self.calls.append("git/trees/" + identity + "?recursive=1")
        if identity == self.tree["sha"]:
            return copy.deepcopy(self.tree)
        if identity == self.consumer_tree["sha"]:
            return copy.deepcopy(self.consumer_tree)
        raise AssertionError("unexpected controlled source tree")

    def download(self, identity, destination, expected_size):
        self.downloads.append(identity)
        row = next(row for row in self.artifacts.values() if row["api_metadata"]["id"] == identity)
        destination.write_bytes((self.fixture.root / row["archive_file"]).read_bytes())


class HandoffIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="retained-transport-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture = NativeHandoffFixture(self.root / "producer")
        retained = self.fixture.fixture.mock_retained()
        retained.start()
        self.addCleanup(retained.stop)
        producer = self.fixture.data["producer_context"]
        self.consumer = {"repository": producer["repository"],
                         "repository_id": producer["repository_id"],
                         "run_id": 789, "source_commit": "b" * 40, "consumer_attempt": 1}
        self.api = HandoffAPI(self.fixture, self.consumer)
        self.output = self.root / "downloaded"

    def acquire(self):
        return fetch.acquire(self.api, self.consumer, self.api.producer, self.fixture.contract,
                             self.output, native_recipe=self.fixture.recipe)

    def verify(self, result):
        context = dict(self.consumer, needs=dict(native_handoff.NEEDS), producer_context=self.api.producer)
        return native_handoff.verify_handoff(self.fixture.contract, self.output / "handoff.json",
            result["handoff_sha256"], context, self.output / "apple-producer/apple-producer-output",
            result["apple_receipt_sha256"], self.fixture.recipe)

    def test_five_downloaded_artifacts_and_real_git_blobs_pass_the_handoff_validator(self):
        result = self.acquire()
        verified = self.verify(result)
        self.assertEqual(set(verified["producers"]), fetch.LANES)
        self.assertEqual(len(set(self.api.downloads)), 5)
        self.assertEqual(verified["context"]["run_id"], 789)
        self.assertEqual(verified["producer_context"]["run_id"], 456)
        self.assertEqual(verified["context"]["source_commit"], "b" * 40)
        self.assertEqual(verified["producer_context"]["source_commit"], "a" * 40)
        self.assertTrue(all(row["producer_attempt"] == 1 for row in verified["producers"].values()))
        matched = json.loads((self.output / "api/producer-source-match.json").read_text())
        self.assertEqual(len(matched["producer"]["files"]), 3)  # recipe marker/index and producer workflow
        self.assertEqual(len(matched["consumer"]["files"]), 16)  # 14 mandatory compiler sources, manager support and gate
        self.assertEqual(matched["producer"]["commit"], "a" * 40)
        self.assertEqual(matched["consumer"]["commit"], "b" * 40)
        self.assertTrue((self.output / "api/producer-source-commit.json").is_file())
        self.assertTrue((self.output / "api/producer-source-tree.json").is_file())
        self.assertEqual(json.loads((self.output / "api/consumer-source-commit.json").read_text()), self.api.consumer_commit)
        self.assertEqual(json.loads((self.output / "api/consumer-source-tree.json").read_text()), self.api.consumer_tree)
        handoff = json.loads((self.output / "handoff.json").read_text())
        self.assertEqual(handoff["api_consumer_commit"], self.api.consumer_commit)
        self.assertEqual(handoff["api_consumer_tree"], self.api.consumer_tree)
        self.assertEqual(result["apple_receipt_sha256"], self.fixture.fixture.receipt_hash)

    def app_source(self):
        return next(iter(self.fixture.contract["prepared_composition_sources"].values()))["source_path"]

    def change_producer_app_blob(self):
        next(row for row in self.api.tree["tree"] if row["path"] == self.app_source())["sha"] = "0" * 40

    def test_producer_app_only_difference_accepts_matching_approved_consumer_app(self):
        self.change_producer_app_blob()
        verified = self.verify(self.acquire())
        self.assertEqual(len(verified["source_match"]["consumer"]["files"]), 16)
        self.assertNotIn(self.app_source(), verified["source_match"]["producer"]["files"])

    def test_producer_app_difference_does_not_allow_wrong_consumer_app_blob(self):
        self.change_producer_app_blob()
        next(row for row in self.api.consumer_tree["tree"] if row["path"] == self.app_source())["sha"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "consumer source blob differs"):
            self.acquire()
        self.assertEqual(self.api.downloads, [])

    def test_producer_app_difference_does_not_allow_unapproved_current_app_bytes(self):
        self.change_producer_app_blob()
        (self.fixture.repository / self.app_source()).write_bytes(b"// unapproved app input\n")
        with self.assertRaisesRegex(ValueError, "current recipe/composition source identity differs"):
            self.acquire()
        self.assertEqual(self.api.downloads, [])

    def test_wrong_consumer_commit_context_is_rejected_before_download(self):
        self.api.consumer_commit["sha"] = "c" * 40
        with self.assertRaisesRegex(ValueError, "consumer commit/tree"):
            self.acquire()
        self.assertEqual(self.api.downloads, [])

    def test_changed_producer_blob_is_rejected_before_artifact_listing_or_download(self):
        row = next(row for row in self.api.tree["tree"]
                   if row["path"] == "Integration/Dependencies/idevice/marker.py")
        row["sha"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "producer source blob differs"):
            self.acquire()
        self.assertEqual(self.api.downloads, [])
        self.assertFalse(any("/artifacts" in route for route in self.api.calls))
        self.assertFalse((self.output / "handoff.json").exists())

    def test_changed_current_source_is_rejected_before_download(self):
        (self.fixture.recipe / "marker.py").write_bytes(b"# changed current source\n")
        with self.assertRaisesRegex(ValueError, "current recipe/composition source identity differs"):
            self.acquire()
        self.assertEqual(self.api.downloads, [])

    def test_extracted_receipt_mutation_is_rejected_by_zip_authenticated_validator(self):
        result = self.acquire()
        receipt = self.output / "host-only/completed/test-evidence.json"
        value = json.loads(receipt.read_text())
        value["observed_fixture_count"] = 0
        receipt.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            self.verify(result)


if __name__ == "__main__":
    unittest.main()
