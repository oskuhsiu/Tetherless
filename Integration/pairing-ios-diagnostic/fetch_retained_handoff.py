#!/usr/bin/env python3
"""Retain authenticated GitHub producer ZIPs for the diagnostic-only consumer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from native_handoff import verify_source_match

LANES = {"host-only", "combined", "acquisition-transcript", "host-transcript", "apple-producer"}
MAX_JSON = 16 * 1024 * 1024
MAX_ZIP = 1024 * 1024 * 1024
MAX_EXPANDED = 4 * MAX_ZIP
MAX_ENTRIES = 100000
WORKFLOW = ".github/workflows/pairing-components.yml"
NEEDS = {"component-fixtures": "success", "native-proofs": "success"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def identities(env):
    repository = env["GITHUB_REPOSITORY"]
    require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository), "invalid repository")
    consumer = {"repository": repository, "repository_id": int(env["GITHUB_REPOSITORY_ID"]),
                "run_id": int(env["GITHUB_RUN_ID"]), "source_commit": env["GITHUB_SHA"],
                "consumer_attempt": int(env["GITHUB_RUN_ATTEMPT"])}
    producer = {"repository": repository, "repository_id": consumer["repository_id"],
                "run_id": int(env["PRODUCER_RUN_ID"]), "source_commit": env["PRODUCER_SOURCE_COMMIT"],
                "run_attempt": int(env["PRODUCER_RUN_ATTEMPT"])}
    for context in (consumer, producer):
        require(re.fullmatch(r"[0-9a-f]{40}", context["source_commit"]), "invalid full commit")
        require(all(type(value) is not int or value > 0 for value in context.values()), "invalid identity number")
    return consumer, producer


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


class ActionsRead:
    def __init__(self, repository, token):
        require(bool(token), "the job's read-only GitHub token is required")
        self.repository_base = "https://api.github.com/repos/" + repository + "/"
        self.base = self.repository_base + "actions/"
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect())
        self.deadline = time.monotonic() + 600

    def open(self, url, *, authenticated):
        require(time.monotonic() < self.deadline, "artifact acquisition exceeded 600 seconds")
        headers = {"User-Agent": "tetherless-diagnostic-handoff", "Accept": "application/vnd.github+json"}
        if authenticated:
            git_route = re.fullmatch(re.escape(self.repository_base) + r"git/(?:commits/[0-9a-f]{40}|trees/[0-9a-f]{40}\?recursive=1)", url)
            require(url.startswith(self.base) or git_route is not None, "unreviewed authenticated API destination")
            headers.update({"Authorization": "Bearer " + self.token, "X-GitHub-Api-Version": "2022-11-28"})
        return self.opener.open(urllib.request.Request(url, headers=headers), timeout=30)

    def get(self, suffix):
        return self.read_json(self.base + suffix)

    def get_git_commit(self, identity):
        require(re.fullmatch(r"[0-9a-f]{40}", identity), "invalid Git commit identity")
        return self.read_json(self.repository_base + "git/commits/" + identity)

    def get_git_tree(self, identity):
        require(isinstance(identity, str) and re.fullmatch(r"[0-9a-f]{40}", identity), "invalid Git tree identity")
        return self.read_json(self.repository_base + "git/trees/" + identity + "?recursive=1")

    def read_json(self, url):
        with self.open(url, authenticated=True) as response:
            require(response.status == 200, "Actions metadata request failed")
            data = response.read(MAX_JSON + 1)
        require(len(data) <= MAX_JSON, "Actions metadata exceeds size bound")
        return json.loads(data)

    def download(self, artifact_id, destination, expected_size):
        url = self.base + "artifacts/" + str(artifact_id) + "/zip"
        try:
            response = self.open(url, authenticated=True)
        except urllib.error.HTTPError as error:
            try:
                require(error.code == 302, "Actions artifact download did not return its expected redirect")
                location = error.headers.get("Location", "")
            finally:
                error.close()
        else:
            response.close()
            raise ValueError("Actions artifact download did not return its expected redirect")
        target = urllib.parse.urlsplit(location)
        require(target.scheme == "https" and target.hostname and not target.username and not target.password
                and target.port in (None, 443) and not target.fragment
                and any(target.hostname.endswith(suffix) for suffix in
                        (".blob.core.windows.net", ".actions.githubusercontent.com")),
                "artifact redirect is outside reviewed HTTPS storage")
        # Never forward GITHUB_TOKEN to the signed storage URL; never retain that URL.
        with self.open(location, authenticated=False) as response, destination.open("xb") as output:
            require(response.status == 200, "artifact storage request failed")
            count = 0
            while True:
                require(time.monotonic() < self.deadline, "artifact acquisition exceeded 600 seconds")
                chunk = response.read(min(1024 * 1024, expected_size - count + 1))
                if not chunk:
                    break
                count += len(chunk)
                require(count <= expected_size, "artifact download exceeds API size")
                output.write(chunk)
        require(count == expected_size, "artifact download is shorter than API size")


def listing(api, suffix, key, retained, stem):
    result, total = [], None
    for page in range(1, 21):
        data = api.get(suffix + ("&" if "?" in suffix else "?") + f"per_page=100&page={page}")
        write_json(retained / f"{stem}-{page:02d}.json", data)
        count = data.get("total_count")
        require(type(count) is int and 0 <= count <= 2000 and (total is None or total == count),
                "unstable or oversized Actions listing")
        total = count
        rows = data.get(key)
        require(isinstance(rows, list) and len(rows) <= 100, "invalid Actions listing page")
        result.extend(rows)
        require(len(result) <= total, "Actions listing exceeds declared count")
        if len(result) == total:
            return result
        require(bool(rows), "incomplete Actions listing")
    raise ValueError("Actions listing exceeds page bound")


def verify_run(run, producer):
    require(run.get("id") == producer["run_id"] and run.get("head_sha") == producer["source_commit"]
            and run.get("run_attempt") == producer["run_attempt"]
            and run.get("repository", {}).get("id") == producer["repository_id"]
            and run.get("repository", {}).get("full_name") == producer["repository"]
            and run.get("head_repository", {}).get("id") == producer["repository_id"]
            and run.get("path") == WORKFLOW and run.get("status") == "completed"
            and run.get("conclusion") == "success", "producer run identity, workflow or success differs")


def verify_metadata(row, lane, attempt, requirement, producer):
    identity = row.get("id")
    url = "https://api.github.com/repos/" + producer["repository"] + "/actions/artifacts/" + str(identity)
    run = row.get("workflow_run", {})
    require(type(identity) is int and identity > 0 and row.get("expired") is False
            and row.get("name") == requirement["artifact_prefix"] + lane + "-" + producer["source_commit"] + "-" + str(attempt)
            and row.get("url") == url and row.get("archive_download_url") == url + "/zip"
            and run.get("id") == producer["run_id"] and run.get("head_sha") == producer["source_commit"]
            and run.get("repository_id") == producer["repository_id"]
            and run.get("head_repository_id") == producer["repository_id"]
            and re.fullmatch(r"sha256:[0-9a-f]{64}", row.get("digest", ""))
            and type(row.get("size_in_bytes")) is int and 0 < row["size_in_bytes"] <= MAX_ZIP,
            "artifact API identity, digest or size differs: " + lane)


def select_artifacts(rows, requirements, producer):
    selected, ids = {}, set()
    for lane, requirement in requirements.items():
        prefix = requirement["artifact_prefix"] + lane + "-" + producer["source_commit"] + "-"
        candidates = {}
        for row in rows:
            name = row.get("name", "")
            if not name.startswith(prefix):
                continue
            tail = name[len(prefix):]
            if not re.fullmatch(r"[1-9][0-9]*", tail) or int(tail) > producer["run_attempt"]:
                continue
            attempt = int(tail)
            require(attempt not in candidates, "duplicate exact artifact name: " + lane)
            candidates[attempt] = row
        candidates = {attempt: row for attempt, row in candidates.items() if row.get("expired") is False}
        require(bool(candidates), "missing unexpired exact producer artifact: " + lane)
        attempt = max(candidates)
        row = candidates[attempt]
        verify_metadata(row, lane, attempt, requirement, producer)
        require(row["id"] not in ids, "artifact ID reused across lanes")
        ids.add(row["id"])
        selected[lane] = (attempt, row)
    return selected


def select_job(jobs, requirement, attempt, producer):
    name = requirement["job_name"]
    matches = [job for job in jobs if job.get("name") == name]
    require(len(matches) == 1, "missing or duplicate exact producer job: " + name)
    job = matches[0]
    expected_url = "https://api.github.com/repos/" + producer["repository"] + "/actions/jobs/" + str(job.get("id"))
    require(type(job.get("id")) is int and job["id"] > 0 and job.get("run_id") == producer["run_id"]
            and job.get("url") == expected_url
            and job.get("head_sha") == producer["source_commit"]
            and job.get("run_attempt", attempt) == attempt
            and job.get("status") == "completed" and job.get("conclusion") == "success",
            "producer job identity or success differs: " + name)
    return job


def extract_known(archive, destination, output_directory):
    require(not destination.exists() and not destination.is_symlink(), "extraction root must be fresh")
    allowed = {"evidence", output_directory}
    with zipfile.ZipFile(archive) as zipped:
        members = zipped.infolist()
        require(len(members) <= MAX_ENTRIES, "ZIP member count exceeds bound")
        names, files, spellings, selected, expanded = set(), set(), {}, [], 0
        for member in members:
            name = member.filename.rstrip("/") if member.is_dir() else member.filename
            path = PurePosixPath(name)
            require(name and not path.is_absolute() and path.as_posix() == name
                    and all(part not in (".", "..") for part in path.parts)
                    and not any(ord(c) < 32 or c in "\\:" for c in name), "unsafe ZIP path")
            key = unicodedata.normalize("NFC", name).casefold()
            require(key not in names, "duplicate or case-colliding ZIP path")
            names.add(key)
            for depth in range(1, len(path.parts) + 1):
                spelling = "/".join(path.parts[:depth])
                normalized = unicodedata.normalize("NFC", spelling).casefold()
                require(spellings.setdefault(normalized, spelling) == spelling, "case-colliding ZIP directory")
            mode = stat.S_IFMT(member.external_attr >> 16)
            require(mode in (0, stat.S_IFDIR if member.is_dir() else stat.S_IFREG)
                    and not member.flag_bits & 1, "nonregular or encrypted ZIP member")
            if not member.is_dir():
                files.add(key)
            expanded += member.file_size
            require(expanded <= MAX_EXPANDED, "ZIP expanded bytes exceed bound")
            if path.parts[0] in allowed:
                selected.append((member, path))
        for key in names:
            require(not any(parent.as_posix() in files for parent in PurePosixPath(key).parents
                            if parent.as_posix() != "."), "ZIP file/directory collision")
        require({path.parts[0] for _, path in selected} == allowed, "ZIP lacks required workflow roots")
        destination.mkdir(parents=True)
        for member, relative in selected:
            target = destination.joinpath(*relative.parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zipped.open(member) as source, target.open("xb") as output:
                remaining = member.file_size
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    require(bool(chunk), "truncated ZIP member")
                    output.write(chunk)
                    remaining -= len(chunk)
                require(source.read(1) == b"", "ZIP member exceeds declared size")


def acquire(api, consumer, producer, contract, destination, *, native_recipe=None):
    require(not destination.exists() and not destination.is_symlink(), "handoff directory must be fresh")
    requirements = contract["same_run_requirements"]
    require(set(requirements) == LANES, "reviewed five-lane contract is required")
    pinned = contract["retained_producer"]
    require(pinned.get("mode") == "explicit-runtime-inputs" and pinned["workflow_path"] == WORKFLOW,
            "explicit runtime producer contract is required")
    destination.mkdir(parents=True)
    retained = destination / "api"
    retained.mkdir()
    run_path = "runs/" + str(producer["run_id"])
    run = api.get(run_path)
    write_json(retained / "producer-run.json", run)
    verify_run(run, producer)
    source_commit = api.get_git_commit(producer["source_commit"])
    write_json(retained / "producer-source-commit.json", source_commit)
    source_tree = api.get_git_tree(source_commit["tree"]["sha"])
    write_json(retained / "producer-source-tree.json", source_tree)
    consumer_commit = api.get_git_commit(consumer["source_commit"])
    write_json(retained / "consumer-source-commit.json", consumer_commit)
    consumer_tree = api.get_git_tree(consumer_commit["tree"]["sha"])
    write_json(retained / "consumer-source-tree.json", consumer_tree)
    recipe = native_recipe or Path(__file__).resolve().parents[1] / "Dependencies/idevice"
    source_match = verify_source_match(contract, recipe, source_commit, source_tree, producer,
                                      consumer=consumer, consumer_commit=consumer_commit, consumer_tree=consumer_tree)
    write_json(retained / "producer-source-match.json", source_match)
    rows = listing(api, run_path + "/artifacts", "artifacts", retained, "artifacts")
    selected = select_artifacts(rows, requirements, producer)
    jobs = {attempt: listing(api, run_path + f"/attempts/{attempt}/jobs", "jobs", retained, f"jobs-attempt-{attempt}")
            for attempt in sorted({attempt for attempt, _ in selected.values()})}
    artifacts = {}
    for lane, (attempt, listed) in selected.items():
        requirement = requirements[lane]
        job = select_job(jobs[attempt], requirement, attempt, producer)
        metadata = api.get("artifacts/" + str(listed["id"]))
        write_json(retained / (lane + "-artifact.json"), metadata)
        require(metadata == listed, "artifact metadata changed after selection: " + lane)
        verify_metadata(metadata, lane, attempt, requirement, producer)
        archive = destination / (lane + ".zip")
        api.download(metadata["id"], archive, metadata["size_in_bytes"])
        require(archive.stat().st_size == metadata["size_in_bytes"]
                and sha256(archive) == metadata["digest"][7:], "artifact ZIP size or digest differs: " + lane)
        extracted = destination / lane
        extract_known(archive, extracted, requirement["output_directory"])
        query = api.base + run_path + f"/attempts/{attempt}/jobs"
        artifacts[lane] = {"producer_attempt": attempt, "api_metadata": metadata, "producer_job": job,
                           "producer_job_query": query,
                           "archive_file": archive.name, "extracted_root": lane}
    # Recheck latest attempt/success after downloads so a racing producer rerun fails closed.
    final_run = api.get(run_path)
    write_json(retained / "producer-run-after.json", final_run)
    verify_run(final_run, producer)
    context = dict(consumer, needs=dict(NEEDS), producer_context=producer)
    handoff = {"schema": 1, "mode": "retained-producer", "context": context,
               "producer_context": producer, "api_source_commit": source_commit,
               "api_source_tree": source_tree, "api_consumer_commit": consumer_commit,
               "api_consumer_tree": consumer_tree, "artifacts": artifacts}
    path = destination / "handoff.json"
    write_json(path, handoff)
    apple = destination / "apple-producer/apple-producer-output/apple-build-evidence.json"
    return {"handoff_sha256": sha256(path), "apple_receipt_sha256": sha256(apple),
            "component_fixtures_result": "success", "native_proofs_result": "success"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        consumer, producer = identities(os.environ)
        contract = json.loads((Path(__file__).parent / "input-contract.json").read_text())
        result = acquire(ActionsRead(consumer["repository"], os.environ["GH_TOKEN"]), consumer, producer, contract, args.output)
        # These hashes/results originate in this trusted caller, outside every downloaded artifact.
        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
            for key, value in result.items():
                stream.write(key + "=" + value + "\n")
    except (ValueError, KeyError, OSError, zipfile.BadZipFile) as error:
        # HTTP exceptions can contain signed storage URLs; do not print them.
        message = type(error).__name__ if isinstance(error, urllib.error.URLError) else str(error)
        parser.exit(1, "Producer handoff failed: " + message + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
