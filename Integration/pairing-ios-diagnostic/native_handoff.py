"""Verify a caller-authenticated, same-run native artifact handoff locally.

The caller obtains metadata from GitHub's authenticated Actions API. This module
does not authenticate a JSON file's origin: its expected hash and consumer
context must come from that trusted caller, outside the downloaded artifacts.
"""
from __future__ import annotations
import json
import hashlib
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

NEEDS = {"component-fixtures": "success", "native-proofs": "success"}


def add_handoff_arguments(parser):
    parser.add_argument("--native-handoff", required=True, type=Path)
    parser.add_argument("--native-handoff-sha256", required=True)
    for key in ("repository", "source-commit"):
        parser.add_argument("--" + key, required=True)
    for key in ("repository-id", "run-id", "consumer-attempt"):
        parser.add_argument("--" + key, required=True, type=int)
    for key in NEEDS:
        parser.add_argument("--" + key + "-result", required=True,
                            choices=("success", "failure", "cancelled", "skipped"))
    parser.add_argument("--handoff-mode", choices=("same-run", "retained-producer"), default="same-run")
    parser.add_argument("--producer-run-id", type=int)
    parser.add_argument("--producer-source-commit")
    parser.add_argument("--producer-run-attempt", type=int)


def context_from_args(args):
    result = {"repository": args.repository, "repository_id": args.repository_id,
            "run_id": args.run_id, "source_commit": args.source_commit,
            "consumer_attempt": args.consumer_attempt,
            "needs": {name: getattr(args, name.replace("-", "_") + "_result") for name in NEEDS}}
    if getattr(args, "handoff_mode", "same-run") == "retained-producer":
        result["producer_context"] = {"repository": args.repository, "repository_id": args.repository_id,
            "run_id": args.producer_run_id, "source_commit": args.producer_source_commit,
            "run_attempt": args.producer_run_attempt}
    return result


def _directory(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if (not isinstance(name, str) or relative.is_absolute() or not relative.parts
            or any(part in (".", "..") for part in relative.parts)
            or relative.as_posix() != name):
        raise ValueError("unsafe handoff extraction path")
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink() or not current.is_dir():
            raise ValueError("handoff extraction root is absent or a symlink")
    return current


def _success(status):
    cleanup = status.get("cleanup", {})
    if (status.get("outcome") != "success" or status.get("returncode") != 0
            or status.get("output_complete") is not True
            or status.get("output_truncated") is not False
            or cleanup.get("direct_child_reaped") is not True
            or cleanup.get("group_empty") is not True):
        raise ValueError("native producer command did not retain complete successful cleanup")


def _git_entries(commit: dict, tree: dict, context: dict, role: str):
    api_base = "https://api.github.com/repos/" + context["repository"] + "/git/"
    tree_sha = commit.get("tree", {}).get("sha")
    if (commit.get("sha") != context["source_commit"]
            or commit.get("url") != api_base + "commits/" + context["source_commit"]
            or not isinstance(tree_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", tree_sha)
            or tree.get("sha") != tree_sha or tree.get("url") != api_base + "trees/" + tree_sha
            or tree.get("truncated") is not False or not isinstance(tree.get("tree"), list)):
        raise ValueError("authenticated " + role + " commit/tree identity is incomplete")
    rows = tree["tree"]
    if any(not isinstance(row, dict) or not isinstance(row.get("path"), str) for row in rows):
        raise ValueError("invalid " + role + " Git tree entry")
    entries = {row["path"]: row for row in rows}
    if len(entries) != len(rows):
        raise ValueError("duplicate " + role + " Git tree path")
    return tree_sha, entries


def verify_source_match(contract: dict, native_recipe: Path, commit: dict, tree: dict,
                        producer: dict, *, consumer: dict, consumer_commit: dict,
                        consumer_tree: dict) -> dict:
    """Bind native inputs to producer, and app inputs to consumer, separately."""
    from prepare_binding import MAX_RECEIPT, digest, read_json, safe_file
    recipe = Path(native_recipe).resolve(strict=True)
    repository = recipe.parents[2]
    prefix = "Integration/Dependencies/idevice/"
    if recipe.relative_to(repository).as_posix() != prefix.rstrip("/"):
        raise ValueError("native recipe must be the current checkout's exact dependency subtree")
    producer_tree_sha, native_entries = _git_entries(commit, tree, producer, "producer")
    consumer_tree_sha, app_entries = _git_entries(consumer_commit, consumer_tree, consumer, "consumer")
    index_name = "apple-recipe-files.json"
    index = read_json(safe_file(recipe, index_name), contract["apple_recipe_index_sha256"])
    native_expected = {prefix + name: value for name, value in index.items()}
    native_expected[prefix + index_name] = contract["apple_recipe_index_sha256"]
    native_expected[contract["retained_producer"]["workflow_path"]] = contract["retained_producer"]["workflow_sha256"]
    app_expected = {}
    for selected in (contract["prepared_composition_sources"], contract["prepared_support_sources"]):
        for item in selected.values():
            name = item["source_path"]
            if name in app_expected and app_expected[name] != item["sha256"]:
                raise ValueError("conflicting current source input identity")
            app_expected[name] = item["sha256"]
    app_expected["Integration/" + contract["preparation_gate"]["path"]] = contract["preparation_gate"]["sha256"]

    def checked(expected, entries, role):
        verified = {}
        for name, expected_sha in sorted(expected.items()):
            with safe_file(repository, name).open("rb") as stream:
                data = stream.read(MAX_RECEIPT + 1)
            if len(data) > MAX_RECEIPT or digest(data) != expected_sha:
                raise ValueError("current recipe/composition source identity differs: " + name)
            blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            entry = entries.get(name, {})
            if entry.get("type") != "blob" or entry.get("mode") not in ("100644", "100755") or entry.get("sha") != blob:
                raise ValueError(role + " source blob differs from the verified current input: " + name)
            verified[name] = {"sha256": expected_sha, "git_blob": blob}
        return verified

    return {"recipe_index_sha256": contract["apple_recipe_index_sha256"],
            "producer": {"commit": producer["source_commit"], "tree_sha": producer_tree_sha,
                         "files": checked(native_expected, native_entries, "producer")},
            "consumer": {"commit": consumer["source_commit"], "tree_sha": consumer_tree_sha,
                         "files": checked(app_expected, app_entries, "consumer")}}


def verify_handoff(contract: dict, handoff_path: Path | None, expected_sha256: str | None,
                   context: dict | None, artifact: Path, apple_receipt_sha256: str,
                   native_recipe: Path | None = None) -> dict:
    # Import lazily so preparation and this validator share the reviewed path/hash
    # helpers without initializing a circular module import.
    from prepare_binding import MAX_RECEIPT, digest, file_hash, read_json, safe_file

    if (contract.get("native_prerequisite_mode") != "validated-same-run-handoff"
            or contract.get("native_prerequisite_cleared") is not False
            or handoff_path is None or context is None
            or not isinstance(expected_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)):
        raise ValueError("diagnostic is held without a validated native handoff")
    basic_keys = {"repository", "repository_id", "run_id", "source_commit", "consumer_attempt", "needs"}
    if (set(context) not in (basic_keys, basic_keys | {"producer_context"})
            or not re.fullmatch(r"[^/\s]+/[^/\s]+", context["repository"])
            or not re.fullmatch(r"[0-9a-f]{40}", context["source_commit"])
            or any(type(context[k]) is not int or context[k] < 1 for k in ("repository_id", "run_id", "consumer_attempt"))
            or context["needs"] != NEEDS):
        raise ValueError("successful same-run consumer context is required")
    handoff_path = Path(handoff_path)
    handoff = read_json(safe_file(handoff_path.parent, handoff_path.name), expected_sha256)
    if handoff.get("schema") != 1 or handoff.get("context") != context:
        raise ValueError("trusted native handoff consumer context differs")
    producer_context = context.get("producer_context", {
        **{name: context[name] for name in ("repository", "repository_id", "run_id", "source_commit")},
        "run_attempt": context["consumer_attempt"]})
    mode = "retained-producer" if "producer_context" in context else "same-run"
    if (set(producer_context) != {"repository", "repository_id", "run_id", "source_commit", "run_attempt"}
            or producer_context["repository"] != context["repository"]
            or producer_context["repository_id"] != context["repository_id"]
            or any(type(producer_context[k]) is not int or producer_context[k] < 1 for k in ("run_id", "run_attempt"))
            or not isinstance(producer_context["source_commit"], str)
            or not re.fullmatch(r"[0-9a-f]{40}", producer_context["source_commit"])
            or handoff.get("mode") != mode or handoff.get("producer_context") != producer_context):
        raise ValueError("one explicit independently supplied producer context is required")
    if contract["retained_producer"].get("mode") != "explicit-runtime-inputs" or native_recipe is None:
        raise ValueError("explicit runtime producer context and current recipe are required")
    source_match = verify_source_match(contract, native_recipe, handoff["api_source_commit"],
                                       handoff["api_source_tree"], producer_context,
                                       consumer=context, consumer_commit=handoff["api_consumer_commit"],
                                       consumer_tree=handoff["api_consumer_tree"])
    required = contract["same_run_requirements"]
    if set(handoff.get("artifacts", {})) != set(required):
        raise ValueError("all five exact native producer artifacts are required")
    producers, ids, roots = {}, set(), set()
    for lane, requirement in required.items():
        row = handoff["artifacts"][lane]
        attempt, metadata = row["producer_attempt"], row["api_metadata"]
        if type(attempt) is not int or not 1 <= attempt <= producer_context["run_attempt"]:
            raise ValueError("native producer attempt must be explicit and within its selected run")
        run = metadata["workflow_run"]
        identity = metadata["id"]
        expected_name = requirement["artifact_prefix"] + lane + "-" + producer_context["source_commit"] + "-" + str(attempt)
        api_url = "https://api.github.com/repos/" + context["repository"] + "/actions/artifacts/" + str(identity)
        if (type(identity) is not int or identity < 1 or identity in ids
                or metadata.get("name") != expected_name or metadata.get("expired") is not False
                or metadata.get("url") != api_url
                or run.get("id") != producer_context["run_id"] or run.get("head_sha") != producer_context["source_commit"]
                or run.get("repository_id") != context["repository_id"]
                or run.get("head_repository_id") != context["repository_id"]
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", metadata.get("digest", ""))
                or type(metadata.get("size_in_bytes")) is not int or metadata["size_in_bytes"] <= 0):
            raise ValueError("native artifact API identity differs from the trusted caller context")
        job = row["producer_job"]
        job_query = ("https://api.github.com/repos/" + context["repository"] + "/actions/runs/"
                     + str(producer_context["run_id"]) + "/attempts/" + str(attempt) + "/jobs")
        if (type(job.get("id")) is not int or job["id"] < 1
                or row.get("producer_job_query") != job_query
                or job.get("url") != "https://api.github.com/repos/" + context["repository"] + "/actions/jobs/" + str(job["id"])
                or job.get("name") != requirement["job_name"]
                or job.get("run_id") != producer_context["run_id"]
                or ("run_attempt" in job and job["run_attempt"] != attempt)
                or job.get("head_sha") != producer_context["source_commit"]
                or job.get("status") != "completed" or job.get("conclusion") != "success"):
            raise ValueError("successful exact producer job metadata is required")
        ids.add(identity)
        archive = safe_file(handoff_path.parent, row["archive_file"])
        if archive.stat().st_size != metadata["size_in_bytes"] or file_hash(archive) != metadata["digest"][7:]:
            raise ValueError("native artifact ZIP differs from its API size or digest")
        extracted = _directory(handoff_path.parent, row["extracted_root"])
        if extracted.resolve() in roots:
            raise ValueError("native artifact extraction roots must be distinct")
        roots.add(extracted.resolve())
        checked = {}
        with zipfile.ZipFile(archive) as zipped:
            members = {}
            for member in zipped.infolist():
                if member.filename in members:
                    raise ValueError("native artifact ZIP contains duplicate member names")
                members[member.filename] = member

            def authenticated_json(name):
                member = members.get(name)
                if (member is None or member.is_dir() or member.file_size > MAX_RECEIPT
                        or stat.S_ISLNK(member.external_attr >> 16)):
                    raise ValueError("native artifact receipt ZIP entry is absent or invalid")
                with zipped.open(member) as stream:
                    data = stream.read(MAX_RECEIPT + 1)
                if len(data) != member.file_size or len(data) > MAX_RECEIPT:
                    raise ValueError("native artifact receipt ZIP size differs")
                value = read_json(safe_file(extracted, name), digest(data))
                checked[name] = digest(data)
                return value

            run_context = authenticated_json("evidence/run-context.json")
            lane_field = "profile" if requirement["job_id"] == "component-fixtures" else "proof"
            if (run_context.get(lane_field) != lane
                    or run_context.get("source_commit") != producer_context["source_commit"]
                    or str(run_context.get("run_id")) != str(producer_context["run_id"])
                    or str(run_context.get("run_attempt")) != str(attempt)):
                raise ValueError("authenticated producer context differs from selected lane/run/attempt")
            output = requirement["output_directory"]
            kind = requirement["receipt_kind"]
            filename = "apple-build-evidence.json" if kind == "apple" else "test-evidence.json"
            receipt = authenticated_json(output + "/" + filename)
            if receipt.get("profile_sha256") != requirement["profile_sha256"]:
                raise ValueError("native source profile differs from the reviewed producer")
            if kind == "apple":
                if ((extracted / output).resolve() != artifact.resolve(strict=True)
                        or checked[output + "/" + filename] != apple_receipt_sha256):
                    raise ValueError("selected Apple artifact or receipt differs from authenticated producer")
                # artifact_inputs performs the existing two-slice/source/provider/
                # six-link-probe, retained header comparison and opaque inventory checks.
                from prepare_binding import artifact_inputs
                artifact_inputs(artifact, apple_receipt_sha256, contract)
            else:
                expected_suites = requirement["suites"]
                if kind == "host":
                    if (receipt.get("profile_kind") != "host-only-native-tests"
                            or receipt.get("expected_fixture_count") != requirement["expected_count"]
                            or receipt.get("observed_fixture_count") != requirement["expected_count"]):
                        raise ValueError("host native fixture aggregate differs")
                elif (receipt.get("passed") != requirement["expected_count"]
                        or receipt.get("artifact_or_product_activation") is not False
                        or receipt.get("header_probe_linked_or_executed") is not False):
                    raise ValueError("native fixture aggregate or scope differs")
                if kind == "component":
                    if receipt.get("profile") != lane:
                        raise ValueError("component producer profile differs")
                else:
                    if receipt.get("source_commit") != contract["native_upstream_commit"]:
                        raise ValueError("native upstream source commit differs")
                if kind == "transcript":
                    if (receipt.get("suite") != expected_suites[0]
                            or receipt.get("features") != requirement["features"]
                            or receipt.get("apple_or_device_compatibility") is not False):
                        raise ValueError("synthetic native transcript selection differs")
                    suites = [dict(receipt["suite"], passed=receipt["passed"],
                                   status_file=receipt["status_file"], log_file=receipt["log_file"])]
                else:
                    suites = receipt.get("tests", [])
                observed = [(item.get("package"), item.get("filter"), item.get("passed")) for item in suites]
                expected = [(item["package"], item["filter"], item["expected_passed"]) for item in expected_suites]
                if observed != expected:
                    raise ValueError("native fixture suite inventory differs")
                for suite in suites:
                    _success(authenticated_json(output + "/" + suite["status_file"]))
                for audit_name in ("vendor-input-audit.json", "derived-vendor-input-audit.json", "workspace-input-audit.json"):
                    if authenticated_json(output + "/" + audit_name).get("original_inputs_unchanged") is not True:
                        raise ValueError("native producer original inputs changed")
                if kind != "host" and authenticated_json(output + "/provider-input-audit.json").get("unchanged") is not True:
                    raise ValueError("native producer provider inputs changed")
        producers[lane] = {"job_id": requirement["job_id"], "producer_attempt": attempt,
                           "producer_job_id": job["id"], "producer_job_name": job["name"],
                           "producer_job_query": job_query,
                           "artifact_id": identity, "artifact_name": expected_name,
                           "archive_sha256": metadata["digest"][7:], "checked_receipts": checked,
                           "profile_sha256": requirement["profile_sha256"]}
    return {"handoff_sha256": expected_sha256, "context": context, "producer_context": producer_context,
            "source_match": source_match,
            "apple_artifact_root": str(artifact.resolve(strict=True)),
            "apple_receipt_sha256": apple_receipt_sha256, "producers": producers}
