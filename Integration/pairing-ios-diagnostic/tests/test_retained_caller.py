from __future__ import annotations
import copy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fetch_retained_handoff as fetch
import call_retained_diagnostic as caller
import read_runtime_producer as runtime


ENV = {"GITHUB_REPOSITORY": "example/repository", "GITHUB_REPOSITORY_ID": "10",
       "GITHUB_RUN_ID": "200", "GITHUB_SHA": "c" * 40, "GITHUB_RUN_ATTEMPT": "1",
       "PRODUCER_RUN_ID": "100", "PRODUCER_SOURCE_COMMIT": "a" * 40, "PRODUCER_RUN_ATTEMPT": "3",
       "HANDOFF_SHA256": "b" * 64, "APPLE_RECEIPT_SHA256": "d" * 64,
       "BINDING_RECEIPT_SHA256": "e" * 64, "COMPONENT_FIXTURES_RESULT": "success",
       "NATIVE_PROOFS_RESULT": "success"}


def archive_bytes(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zipped:
        for name, contents in entries:
            zipped.writestr(name, contents)
    return stream.getvalue()


class FixtureAPI:
    def __init__(self):
        self.consumer, self.producer = fetch.identities(ENV)
        self.base = "https://api.github.com/repos/example/repository/actions/"
        self.requirements, self.rows, self.archives, self.jobs, self.calls = {}, [], {}, {}, []
        self.run = {"id": 100, "head_sha": "a" * 40, "run_attempt": 3, "path": fetch.WORKFLOW,
                    "repository": {"id": 10, "full_name": "example/repository"},
                    "head_repository": {"id": 10}, "status": "completed", "conclusion": "success"}
        for identity, lane in enumerate(sorted(fetch.LANES), 1):
            component = lane in ("host-only", "combined")
            group = "component-fixtures" if component else "native-proofs"
            output = "completed" if component else lane + "-output"
            self.requirements[lane] = {"artifact_prefix": "pairing-components-" if component else "pairing-native-proof-",
                                       "output_directory": output, "job_name": group + " (" + lane + ")"}
            data = archive_bytes([("evidence/run-context.json", "{}"),
                                  (output + "/apple-build-evidence.json", "{}"),
                                  ("unselected-review-sources/input.txt", "retained only in ZIP")])
            self.add(lane, 2 if lane == "host-only" else 3, identity, data)

    def add(self, lane, attempt, identity, data):
        requirement = self.requirements[lane]
        url = self.base + "artifacts/" + str(identity)
        row = {"id": identity, "name": requirement["artifact_prefix"] + lane + "-" + "a" * 40 + "-" + str(attempt),
               "url": url, "archive_download_url": url + "/zip", "expired": False,
               "size_in_bytes": len(data), "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
               "workflow_run": {"id": 100, "repository_id": 10, "head_repository_id": 10, "head_sha": "a" * 40}}
        self.rows.append(row)
        self.archives[identity] = data
        self.jobs.setdefault(attempt, []).append({"id": identity + 1000, "name": requirement["job_name"],
                                                "url": self.base + "jobs/" + str(identity + 1000),
                                                "run_id": 100, "head_sha": "a" * 40,
                                                "status": "completed", "conclusion": "success"})
        return row

    def get(self, suffix):
        self.calls.append(suffix)
        if suffix == "runs/100":
            return copy.deepcopy(self.run)
        if suffix.startswith("runs/100/artifacts?"):
            return {"total_count": len(self.rows), "artifacts": copy.deepcopy(self.rows)}
        if suffix.startswith("runs/100/attempts/"):
            attempt = int(suffix.split("/")[3])
            return {"total_count": len(self.jobs[attempt]), "jobs": copy.deepcopy(self.jobs[attempt])}
        if suffix.startswith("artifacts/"):
            return copy.deepcopy(next(row for row in self.rows if row["id"] == int(suffix.split("/")[1])))
        raise AssertionError("unexpected API path: " + suffix)

    def get_git_commit(self, identity):
        self.calls.append("git/commits/" + identity)
        return {"sha": identity, "tree": {"sha": ("f" if identity == self.producer["source_commit"] else "e") * 40}}

    def get_git_tree(self, identity):
        self.calls.append("git/trees/" + identity)
        return {"sha": identity, "truncated": False, "tree": []}

    def download(self, identity, destination, expected_size):
        destination.write_bytes(self.archives[identity])


class RetainedCallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.api = FixtureAPI()
        source_match = patch.object(fetch, "verify_source_match", return_value={"synthetic_source_match": True})
        self.source_match = source_match.start()
        self.addCleanup(source_match.stop)

    def tearDown(self):
        self.temp.cleanup()

    def acquire(self):
        return fetch.acquire(self.api, self.api.consumer, self.api.producer,
                             {"same_run_requirements": self.api.requirements,
                              "retained_producer": {"mode": "explicit-runtime-inputs",
                                                    "workflow_path": fetch.WORKFLOW}}, self.root / "handoff")

    def test_complete_retained_handoff_preserves_separate_contexts_and_original_metadata(self):
        result = self.acquire()
        path = self.root / "handoff/handoff.json"
        handoff = json.loads(path.read_text())
        self.assertEqual(result["handoff_sha256"], fetch.sha256(path))
        self.assertEqual(handoff["context"]["run_id"], 200)
        self.assertEqual(handoff["producer_context"]["run_id"], 100)
        self.assertEqual(handoff["context"]["source_commit"], "c" * 40)
        self.assertEqual(handoff["producer_context"]["source_commit"], "a" * 40)
        host = handoff["artifacts"]["host-only"]
        self.assertEqual(host["producer_attempt"], 2)
        self.assertTrue(host["producer_job_query"].endswith("/runs/100/attempts/2/jobs"))
        self.assertNotIn("run_attempt", host["producer_job"])
        self.assertEqual(host["api_metadata"], next(row for row in self.api.rows if row["id"] == host["api_metadata"]["id"]))
        self.assertFalse((self.root / "handoff/host-only/unselected-review-sources").exists())
        self.assertTrue((self.root / "handoff/host-only.zip").is_file())
        self.assertEqual(self.api.calls.count("runs/100"), 2)
        self.assertEqual(handoff["api_source_commit"]["sha"], self.api.producer["source_commit"])
        self.assertEqual(handoff["api_source_tree"]["sha"], "f" * 40)
        self.assertEqual(handoff["api_consumer_commit"]["sha"], self.api.consumer["source_commit"])
        self.assertEqual(handoff["api_consumer_tree"]["sha"], "e" * 40)
        self.assertEqual(self.api.calls[:5], ["runs/100", "git/commits/" + "a" * 40, "git/trees/" + "f" * 40,
                                           "git/commits/" + "c" * 40, "git/trees/" + "e" * 40])
        self.source_match.assert_called_once()
        self.assertEqual(self.source_match.call_args.kwargs, {
            "consumer": self.api.consumer, "consumer_commit": handoff["api_consumer_commit"],
            "consumer_tree": handoff["api_consumer_tree"]})
        self.assertEqual(json.loads((self.root / "handoff/api/consumer-source-commit.json").read_text()),
                         handoff["api_consumer_commit"])
        self.assertEqual(json.loads((self.root / "handoff/api/consumer-source-tree.json").read_text()),
                         handoff["api_consumer_tree"])

    def test_source_match_failure_precedes_any_artifact_download(self):
        self.source_match.side_effect = ValueError("producer source mismatch")
        with patch.object(self.api, "download") as download, self.assertRaisesRegex(ValueError, "source mismatch"):
            self.acquire()
        download.assert_not_called()
        self.assertFalse((self.root / "handoff/handoff.json").exists())

    def test_highest_available_lane_attempt_selected(self):
        self.api.add("host-only", 1, 90, self.api.archives[1])
        selected = fetch.select_artifacts(self.api.rows, self.api.requirements, self.api.producer)
        self.assertEqual(selected["host-only"][0], 2)

    def test_future_attempt_cannot_be_selected(self):
        self.api.add("host-only", 4, 90, self.api.archives[1])
        selected = fetch.select_artifacts(self.api.rows, self.api.requirements, self.api.producer)
        self.assertEqual(selected["host-only"][0], 2)

    def test_expired_new_attempt_can_leave_earlier_available_attempt(self):
        self.api.add("host-only", 3, 90, self.api.archives[1])["expired"] = True
        selected = fetch.select_artifacts(self.api.rows, self.api.requirements, self.api.producer)
        self.assertEqual(selected["host-only"][0], 2)

    def test_duplicate_exact_name_rejected_even_if_one_expired(self):
        row = copy.deepcopy(self.api.rows[0])
        row.update(id=90, expired=True)
        self.api.rows.append(row)
        with self.assertRaisesRegex(ValueError, "duplicate exact"):
            self.acquire()

    def test_newest_invalid_metadata_does_not_fall_back(self):
        self.api.add("host-only", 3, 90, self.api.archives[1])["digest"] = "sha256:bad"
        with self.assertRaisesRegex(ValueError, "artifact API"):
            self.acquire()

    def test_cross_identity_expired_missing_digest_and_size_rejected(self):
        for change in ({"expired": True}, {"digest": ""}, {"size_in_bytes": 0}, {"id": True},
                       {"workflow_run": {"id": 101}}, {"url": "https://example.org/artifact"}):
            with self.subTest(change=change):
                api = FixtureAPI()
                row = api.rows[0]
                row.update(change)
                lane = sorted(fetch.LANES)[0]
                with self.assertRaises(ValueError):
                    fetch.verify_metadata(row, lane, 3, api.requirements[lane], api.producer)

    def test_other_repository_head_rejected(self):
        self.api.rows[0]["workflow_run"]["head_repository_id"] = 20
        with self.assertRaisesRegex(ValueError, "artifact API"):
            self.acquire()

    def test_unsuccessful_wrong_workflow_or_changed_run_rejected(self):
        for change in ({"conclusion": "failure"}, {"status": "in_progress"}, {"run_attempt": 4},
                       {"head_sha": "b" * 40}, {"path": ".github/workflows/other.yml"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                fetch.verify_run(dict(self.api.run, **change), self.api.producer)

    def test_runtime_producer_identity_mismatch_stops_before_download(self):
        self.api.producer["run_id"] = 101
        with patch.object(self.api, "get", return_value=self.api.run) as read, \
                patch.object(self.api, "download") as download, self.assertRaises(ValueError):
            self.acquire()
        read.assert_called_once_with("runs/101")
        download.assert_not_called()

    def test_wrong_failed_duplicate_or_wrong_attempt_job_rejected(self):
        req = self.api.requirements["host-only"]
        job = self.api.jobs[2][0]
        for jobs in ([], [job, job], [dict(job, conclusion="failure")], [dict(job, head_sha="b" * 40)],
                     [dict(job, run_attempt=1)], [dict(job, name="unreviewed")]):
            with self.subTest(jobs=jobs), self.assertRaises(ValueError):
                fetch.select_job(jobs, req, 2, self.api.producer)

    def test_digest_mismatch_prevents_extraction_and_handoff(self):
        identity = self.api.rows[0]["id"]
        data = bytearray(self.api.archives[identity])
        data[10] ^= 1
        self.api.archives[identity] = data
        with self.assertRaisesRegex(ValueError, "ZIP size or digest"):
            self.acquire()
        self.assertFalse((self.root / "handoff/handoff.json").exists())
        self.assertFalse((self.root / "handoff" / sorted(fetch.LANES)[0]).exists())

    def test_racing_producer_rerun_rejected_after_download(self):
        original = self.api.download
        def download(*args):
            original(*args)
            self.api.run["run_attempt"] = 4
        self.api.download = download
        with self.assertRaisesRegex(ValueError, "producer run"):
            self.acquire()
        self.assertFalse((self.root / "handoff/handoff.json").exists())

    def test_unsafe_zip_members_rejected_without_output(self):
        symlink = zipfile.ZipInfo("evidence/link")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        for bad in ("../escape", "/escape", "evidence/../escape", "evidence//file", "evidence\\file",
                    "evidence/C:drive", symlink):
            with self.subTest(member=str(bad)):
                archive = self.root / "unsafe.zip"
                archive.write_bytes(archive_bytes([("evidence/context.json", "{}"), ("completed/test.json", "{}"), (bad, "bad")]))
                with self.assertRaises(ValueError):
                    fetch.extract_known(archive, self.root / "out", "completed")
                self.assertFalse((self.root / "out").exists())

    def test_duplicate_case_and_file_directory_collisions_rejected(self):
        for extras in ([('evidence/a', '1'), ('evidence/A', '2')],
                       [('evidence/a', '1'), ('evidence/a/b', '2')],
                       [('evidence/a/x', '1'), ('evidence/A/y', '2')]):
            archive = self.root / "collision.zip"
            archive.write_bytes(archive_bytes([("completed/test.json", "{}"), *extras]))
            with self.assertRaises(ValueError):
                fetch.extract_known(archive, self.root / "out", "completed")

    def test_wrong_proof_wrapper_rejected(self):
        archive = self.root / "wrapper.zip"
        archive.write_bytes(archive_bytes([(".proof/evidence/context.json", "{}"), (".proof/apple-producer-output/receipt.json", "{}")]))
        with self.assertRaisesRegex(ValueError, "required workflow roots"):
            fetch.extract_known(archive, self.root / "out", "apple-producer-output")

    def test_expansion_bound_checked_before_extracting(self):
        archive = self.root / "large.zip"
        archive.write_bytes(archive_bytes([("evidence/context.json", "{}"), ("completed/test.json", "{}")]))
        with patch.object(fetch, "MAX_EXPANDED", 1), self.assertRaisesRegex(ValueError, "expanded bytes"):
            fetch.extract_known(archive, self.root / "out", "completed")

    def test_existing_destination_rejected(self):
        (self.root / "handoff").mkdir()
        with self.assertRaisesRegex(ValueError, "fresh"):
            self.acquire()

    def test_incomplete_pagination_is_rejected(self):
        class Incomplete:
            def get(self, suffix):
                return {"total_count": 1, "artifacts": []}
        with self.assertRaisesRegex(ValueError, "incomplete"):
            fetch.listing(Incomplete(), "runs/100/artifacts", "artifacts", self.root, "page")

    def test_independent_context_and_hash_flags_for_all_phases(self):
        for phase in ("bind", "Debug", "Release"):
            command = caller.command(phase, ENV)
            values = dict(zip(command[2::2], command[3::2]))
            self.assertEqual(values["--run-id"], "200")
            self.assertEqual(values["--source-commit"], "c" * 40)
            self.assertEqual(values["--producer-run-id"], "100")
            self.assertEqual(values["--producer-source-commit"], "a" * 40)
            self.assertEqual(values["--consumer-attempt"], "1")
            self.assertEqual(values["--producer-run-attempt"], "3")
            self.assertEqual(values["--handoff-mode"], "retained-producer")
            self.assertEqual(values["--native-handoff-sha256"], "b" * 64)
            self.assertIn("--native-recipe", values)
            if phase != "bind":
                self.assertEqual(values["--configuration"], phase)
                self.assertTrue(values["--toolchain-lock"].endswith("/apple-producer/evidence/toolchain-lock.observed.json"))

    def test_missing_external_hash_or_producer_success_is_rejected(self):
        for key in ("HANDOFF_SHA256", "APPLE_RECEIPT_SHA256", "COMPONENT_FIXTURES_RESULT", "NATIVE_PROOFS_RESULT"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                caller.command("bind", dict(ENV, **{key: ""}))

    def test_api_token_is_scoped_to_api_requests(self):
        api = fetch.ActionsRead("example/repository", "test-token")
        class Recorder:
            def __init__(self):
                self.requests = []
            def open(self, request, timeout):
                self.requests.append(request)
                return object()
        api.opener = Recorder()
        api.open(api.base + "runs/100", authenticated=True)
        api.open("https://storage.blob.core.windows.net/artifact?signed=value", authenticated=False)
        self.assertEqual(api.opener.requests[0].get_header("Authorization"), "Bearer test-token")
        self.assertIsNone(api.opener.requests[1].get_header("Authorization"))
        with self.assertRaisesRegex(ValueError, "unreviewed authenticated"):
            api.open("https://example.org/", authenticated=True)
        api.open(api.repository_base + "git/commits/" + "a" * 40, authenticated=True)
        api.open(api.repository_base + "git/trees/" + "b" * 40 + "?recursive=1", authenticated=True)
        with self.assertRaisesRegex(ValueError, "unreviewed authenticated"):
            api.open(api.repository_base + "contents/private", authenticated=True)

    def test_automatic_redirect_is_disabled(self):
        self.assertIsNone(fetch.NoRedirect().redirect_request(None, None, 302, "Found", {},
            "https://storage.blob.core.windows.net/a?signed=synthetic-secret"))

    def test_network_error_never_logs_token_or_signed_redirect(self):
        stderr = io.StringIO()
        signed = "https://storage.blob.core.windows.net/a?signed=synthetic-storage-secret"
        with patch.object(sys, "argv", ["fetch_retained_handoff.py", "--output", str(self.root / "unused")]), \
                patch.dict(fetch.os.environ, dict(ENV, GH_TOKEN="synthetic-github-secret")), \
                patch.object(fetch, "ActionsRead"), \
                patch.object(fetch, "acquire", side_effect=urllib.error.URLError(signed)), \
                contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as stopped:
            fetch.main()
        self.assertEqual(stopped.exception.code, 1)
        self.assertIn("URLError", stderr.getvalue())
        self.assertNotIn("synthetic-storage-secret", stderr.getvalue())
        self.assertNotIn("synthetic-github-secret", stderr.getvalue())
        self.assertNotIn("blob.core.windows.net", stderr.getvalue())
        self.assertFalse((self.root / "unused").exists())

    def test_download_uses_exact_id_and_does_not_forward_auth(self):
        api = fetch.ActionsRead("example/repository", "test-token")
        calls = []
        class Response(io.BytesIO):
            status = 200
        def open_response(url, *, authenticated):
            calls.append((url, authenticated))
            if authenticated:
                raise urllib.error.HTTPError(url, 302, "Found", {
                    "Location": "https://storage.blob.core.windows.net/artifact?signed=value"}, None)
            return Response(b"ZIP")
        api.open = open_response
        api.download(42, self.root / "result.zip", 3)
        self.assertEqual(calls[0], (api.base + "artifacts/42/zip", True))
        self.assertFalse(calls[1][1])
        self.assertEqual((self.root / "result.zip").read_bytes(), b"ZIP")

    def test_unreviewed_storage_redirect_rejected_without_second_request(self):
        for location in ("http://storage.blob.core.windows.net/a", "https://example.org/a",
                         "https://user:pass@storage.blob.core.windows.net/a"):
            api = fetch.ActionsRead("example/repository", "test-token")
            calls = []
            def open_response(url, *, authenticated):
                calls.append(url)
                raise urllib.error.HTTPError(url, 302, "Found", {"Location": location}, None)
            api.open = open_response
            with self.subTest(location=location), self.assertRaisesRegex(ValueError, "reviewed HTTPS"):
                api.download(42, self.root / "result.zip", 3)
            self.assertEqual(len(calls), 1)

    def test_download_size_bound_and_truncation(self):
        for data in (b"ZI", b"ZIP!"):
            api = fetch.ActionsRead("example/repository", "test-token")
            class Response(io.BytesIO):
                status = 200
            def open_response(url, *, authenticated):
                if authenticated:
                    raise urllib.error.HTTPError(url, 302, "Found", {
                        "Location": "https://storage.blob.core.windows.net/a"}, None)
                return Response(data)
            api.open = open_response
            with self.subTest(data=data), self.assertRaisesRegex(ValueError, "API size"):
                api.download(42, self.root / (str(len(data)) + ".zip"), 3)


class RuntimeProducerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="runtime-producer-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.context = self.root / "selection.json"
        self.github_env = self.root / "github-env"
        self.valid = {"schema": 1, "producer_run_id": 1234,
                      "producer_source_commit": "a" * 40, "producer_run_attempt": 2}

    def write(self, value):
        self.context.write_text(json.dumps(value))

    def test_valid_selection_emits_only_three_fixed_names(self):
        self.write(self.valid)
        self.github_env.write_text("EXISTING=value\n")
        runtime.emit_context(self.context, self.github_env)
        self.assertEqual(self.github_env.read_text(), "EXISTING=value\nPRODUCER_RUN_ID=1234\n"
                         + "PRODUCER_SOURCE_COMMIT=" + "a" * 40 + "\nPRODUCER_RUN_ATTEMPT=2\n")

    def test_closed_template_rejected(self):
        here = Path(runtime.__file__).resolve().parent
        with self.assertRaisesRegex(ValueError, "positive integers"):
            runtime.read_context(here / "runtime-producer.template.json")

    def test_schema_missing_extra_and_wrong_field_types_rejected_without_env_writes(self):
        cases = [None, [], {}, dict(self.valid, schema=True), dict(self.valid, schema=2),
                 dict(self.valid, extra="INJECTED=yes"), {k: v for k, v in self.valid.items() if k != "producer_run_id"}]
        for key in ("producer_run_id", "producer_run_attempt"):
            cases.extend(dict(self.valid, **{key: value}) for value in (None, True, 0, -1, 1.5, "1234"))
        for value in (None, True, 123, "A" * 40, "a" * 39, "a" * 41, "a" * 40 + "\nINJECTED=yes"):
            cases.append(dict(self.valid, producer_source_commit=value))
        for value in cases:
            with self.subTest(value=value):
                self.write(value)
                with self.assertRaises(ValueError):
                    runtime.emit_context(self.context, self.github_env)
                self.assertFalse(self.github_env.exists())

    def test_duplicate_context_keys_rejected(self):
        self.context.write_text('{"schema":1,"schema":1}')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            runtime.emit_context(self.context, self.github_env)
        self.assertFalse(self.github_env.exists())

    def test_missing_symlink_or_oversized_context_rejected(self):
        with self.assertRaisesRegex(ValueError, "regular"):
            runtime.read_context(self.context)
        original = self.root / "original.json"
        original.write_text(json.dumps(self.valid))
        self.context.symlink_to(original)
        with self.assertRaisesRegex(ValueError, "regular"):
            runtime.read_context(self.context)
        self.context.unlink()
        self.context.write_bytes(b" " * (runtime.MAX_CONTEXT + 1))
        with self.assertRaisesRegex(ValueError, "4096 bytes"):
            runtime.read_context(self.context)

    def test_main_uses_fixed_context_path_and_runner_env_file(self):
        self.write(self.valid)
        with patch.object(runtime, "CONTEXT", self.context), patch.dict(runtime.os.environ, GITHUB_ENV=str(self.github_env)):
            self.assertEqual(runtime.main(), 0)
        self.assertIn("PRODUCER_RUN_ID=1234\n", self.github_env.read_text())


if __name__ == "__main__":
    unittest.main()
