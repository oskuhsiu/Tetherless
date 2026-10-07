"""Bound compiler-generated text to exact archive bytes and member visibility.

This module never reads native formats or executes retained tools. The same
bounded text/receipt validation runs in the producer and the offline consumer.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import PurePosixPath
import re

from apply_patch import VerificationError, canonical_json
from bounded_process import MAX_LOG_BYTES
import rust_symbol_reader

FLAGS = ["--defined-only", "--format=darwin", "--print-file-name", "--quiet"]
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024
MAX_RECORDS = 250000
NAME = r"[_A-Za-z.$][_A-Za-z0-9.$]*"
TARGETS = {"aarch64-apple-ios", "aarch64-apple-ios-sim"}


def need(value, message):
    if not value:
        raise VerificationError("symbol visibility: " + message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(raw):
    return {"sha256": digest(raw), "bytes": len(raw)}


def _path(value):
    need(isinstance(value, str) and value.isprintable() and ":" not in value
         and "(" not in value and ")" not in value and "\\" not in value,
         "ambiguous archive path")
    path = PurePosixPath(value)
    need(path.is_absolute() and path.as_posix() == value and ".." not in path.parts,
         "noncanonical archive path")
    return value


def _archive(value):
    need(isinstance(value, dict) and set(value) == {"source", "sha256", "bytes"},
         "archive identity fields differ")
    _path(value["source"])
    need(isinstance(value["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", value["sha256"])
         and type(value["bytes"]) is int and 0 < value["bytes"] <= MAX_ARCHIVE_BYTES,
         "archive hash/size differs")


def _json(raw):
    need(isinstance(raw, bytes) and 0 < len(raw) <= MAX_JSON_BYTES, "JSON size differs")
    def pairs(rows):
        result = {}
        for key, value in rows:
            need(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs)
    need(isinstance(value, dict), "JSON is not an object")
    return value


def _kind(section, descriptor, address):
    # These are visibility-bearing llvm-nm Darwin records, not diagnostics.
    # Weak is external; it can never establish locality. Common definitions
    # have an explicit alignment. Bitcode definitions have the LTO address.
    normal = re.fullmatch(r"\([_A-Za-z][_A-Za-z0-9]*,[_A-Za-z][_A-Za-z0-9]*\)", section)
    if section == "(common)":
        match = re.fullmatch(r"\(alignment 2\^([0-9]|[1-5][0-9]|6[0-3])\) (private external|external)", descriptor)
        need(match and address != "----------------", "malformed common definition")
        return "external"
    need(normal, "unknown definition section")
    if address == "----------------":
        need(section in {"(LTO,CODE)", "(LTO,RODATA)"}, "non-LTO missing address")
    else:
        need(not section.startswith("(LTO,"), "unexpected LTO address")
    if descriptor in {"non-external", "non-external [cold func]"}:
        need(address != "----------------", "unresolved local definition")
        return "local"
    if descriptor in {"external", "private external", "external [cold func]", "private external [cold func]"}:
        return "external"
    if descriptor in {"weak external", "weak private external"}:
        return "weak"
    raise VerificationError("symbol visibility: unknown or malformed visibility descriptor")


def parse_archive(raw, archive):
    """Preserve all member/name records, including repeated member basenames."""
    _path(archive)
    need(isinstance(raw, bytes) and 0 < len(raw) <= MAX_LOG_BYTES and raw.endswith(b"\n"),
         "scan is empty, oversized or lacks final LF")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise VerificationError("symbol visibility: scan is not strict UTF-8") from error
    rows = text.split("\n")[:-1]
    need(0 < len(rows) <= MAX_RECORDS, "definition record count exceeds bound")
    pattern = re.compile(re.escape(archive) + r":([^:()\\/\x00-\x20\x7f]+): ([0-9a-fA-F]{16}|-{16}) (\([^)]*\)) (.*?) (" + NAME + r")")
    members, externals = {}, []
    for row in rows:
        match = pattern.fullmatch(row)
        need(match is not None, "malformed/member-unqualified definition record")
        member, address, section, descriptor, name = match.groups()
        need(member.isascii() and member not in {".", ".."}, "ambiguous archive member")
        kind = _kind(section, descriptor, address)
        members.setdefault(member, {}).setdefault(name, []).append(kind)
        if kind != "local":
            externals.append(name)
    need(externals and len(set(externals)) == len(externals), "empty exports or duplicate external definitions")
    return {"members": members, "external_symbols": sorted(externals), "scan_sha256": digest(raw)}


def exported(raw):
    """Accept names and exact archive-member headings; reject diagnostics.

    --quiet suppresses empty-member warnings, not llvm-nm member headings.
    The visibility scan independently binds the complete external name set.
    """
    need(isinstance(raw, bytes) and 0 < len(raw) <= MAX_LOG_BYTES and raw.endswith(b"\n"),
         "external scan is empty, oversized or lacks final LF")
    try:
        rows = raw.decode("ascii").split("\n")[:-1]
    except UnicodeDecodeError as error:
        raise VerificationError("symbol visibility: non-ASCII external scan") from error
    symbols = []
    for row in rows:
        if row == "" or re.fullmatch(r"[^:/()\\\x00-\x20\x7f]+\.o:", row):
            continue
        need(re.fullmatch(NAME, row) is not None, "malformed external symbol name")
        symbols.append(row)
    need(symbols and len(set(symbols)) == len(symbols), "empty scan or duplicate external definitions")
    return set(symbols)


def _success(status, command, log_bytes):
    need(status.get("schema") == 1 and status.get("command") == command
         and status.get("outcome") == "success" and status.get("returncode") == 0
         and status.get("output_complete") is True and status.get("output_truncated") is False
         and status.get("stop_reason") is None and status.get("error_type") is None
         and status.get("output_bytes_over_limit_observed") == 0
         and type(status.get("log_bytes")) is int and status["log_bytes"] == log_bytes
         and status.get("max_log_bytes") == MAX_LOG_BYTES
         and status.get("cleanup", {}).get("direct_child_reaped") is True
         and status.get("cleanup", {}).get("group_empty") is True,
         "command lacks matching complete successful output/join")


def load_evidence(read, *, target, reader, archives, context, links=()):
    """read(relative_name, bound) supplies hash-authenticated retained bytes.

    Validate the two visibility scans, two clean external scans and each reached
    link. A product caller supplies all eight links; a pre-link producer caller
    supplies none. A failed/old diagnostic capture is never accepted here.
    """
    need(target in TARGETS and set(archives) == {"rust", "c"}, "target/archive roles differ")
    for row in archives.values():
        _archive(row)
    need(archives["rust"]["source"] != archives["c"]["source"], "archive roles alias")
    need(isinstance(context, dict) and set(context) == {"source_manifest_sha256", "recipe_lock_sha256"}
         and all(isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) for v in context.values()),
         "source/recipe context differs")
    rust_symbol_reader.validate_receipt(reader)
    observed = {}
    def data(name, limit):
        raw = read(name, limit)
        need(isinstance(raw, bytes) and len(raw) <= limit, "retained file exceeds bound")
        observed[name] = identity(raw)
        return raw
    inputs = _json(data("linkage-observation/inputs.json", MAX_JSON_BYTES))
    need(inputs.get("schema") == 2 and inputs.get("target") == target
         and inputs.get("diagnostic_only") is False and inputs.get("ownership_acceptance_changed") is True
         and inputs.get("native_payloads_executed") is False
         and inputs.get("archive_byte_limit_each") == MAX_ARCHIVE_BYTES
         and inputs.get("symbol_reader") == reader and inputs.get("observation_flags") == FLAGS
         and inputs.get("source_context") == context and set(inputs.get("archives", {})) == set(archives),
         "capture/source/toolchain contract differs")
    for role, expected in archives.items():
        row = inputs["archives"][role]
        need({key: row.get(key) for key in expected} == expected
             and row.get("retained") == role + "-staticlib.a", "capture archive identity differs")
        _path(row.get("canonical_source"))
    snapshot = {role: {place: {key: row[key] for key in ("sha256", "bytes")}
                      for place in ("source", "retained")} for role, row in archives.items()}
    operations = []
    for role in ("rust", "c"):
        operations.append(("linkage-observation/" + role + "-defined-members.txt",
                           [reader["llvm_nm"]["path"], *FLAGS, archives[role]["source"]], None))
    for role in ("rust", "c"):
        operations.append(("04-" + role + "-export-symbols.txt",
                           rust_symbol_reader.scan_command(reader, archives[role]["source"]), None))
    need(len(links) <= 8 and len({(v["group"], v["language"]) for v in links}) == len(links),
         "duplicate or excessive link operations")
    for link in links:
        need(link["group"] in {"host", "mixed_provider", "pairing", "result_constants"}
             and link["language"] in {"c", "swift"}, "unreviewed link operation")
        name = "05-link-" + link["group"] + "-" + link["language"]
        operations.append((name + ".txt", link["command"], name + ".map" if link["group"] == "mixed_provider" else None))
    scans = {}
    scan_identity = None
    for index, (name, command, map_name) in enumerate(operations, 1):
        basename = PurePosixPath(name).name
        raw = data(name, MAX_LOG_BYTES)
        status_raw = data(name + ".status.json", MAX_JSON_BYTES)
        status = _json(status_raw)
        _success(status, command, len(raw))
        receipt_name = "linkage-observation/" + f"{index:02d}-" + basename[:-4] + ".json"
        operation = _json(data(receipt_name, MAX_JSON_BYTES))
        need(operation.get("schema") == 1 and operation.get("diagnostic_only") is False
             and operation.get("command") == command and operation.get("command_completed") is True
             and operation.get("inputs_unchanged") is True and operation.get("retention_errors") == []
             and operation.get("before") == snapshot and operation.get("after") == snapshot
             and "primary_error_type" not in operation, "operation receipt/source snapshots differ")
        log_path = operation.get("log")
        need(isinstance(log_path, str) and PurePosixPath(log_path).is_absolute()
             and PurePosixPath(log_path).name == basename, "operation log path differs")
        outputs = {basename: raw, basename + ".status.json": status_raw}
        if map_name:
            outputs[map_name] = data(map_name, MAX_LOG_BYTES)
        need(set(operation.get("outputs", {})) == set(outputs), "operation output inventory differs")
        for output_name, output in outputs.items():
            expected_output = {"path": str(PurePosixPath(log_path).parent / output_name), **identity(output)}
            need(operation["outputs"][output_name] == expected_output, "operation output bytes/paths differ")
        if index <= 2:
            role = ("rust", "c")[index - 1]
            scans[role] = {**archives[role], **parse_archive(raw, archives[role]["source"])}
        elif index <= 4:
            role = ("rust", "c")[index - 3]
            need(exported(raw) == set(scans[role]["external_symbols"]),
                 "member visibility and external scans disagree")
        if index == 4:
            scan_identity = digest(canonical_json(observed))
    need(not set(scans["rust"]["external_symbols"]) & set(scans["c"]["external_symbols"]),
         "archive external namespaces overlap")
    # Keep all candidates for any global name, while retaining duplicate local
    # rows for ambiguity checks. Raw complete scans remain in the product.
    relevant = set(scans["rust"]["external_symbols"]) | set(scans["c"]["external_symbols"])
    for scan in scans.values():
        scan["members"] = {member: {name: kinds for name, kinds in names.items() if name in relevant}
                           for member, names in scan["members"].items() if relevant & set(names)}
    return {"schema": 1, "target": target, "context": context, "archives": scans,
            "evidence_sha256": scan_identity}


def rebind(visibility, *, archives):
    """Rebase only after the caller verifies byte-identical local archive files."""
    need(set(archives) == {"rust", "c"} and visibility.get("schema") == 1, "rebind contract differs")
    result = copy.deepcopy(visibility)
    for role, row in archives.items():
        _archive(row)
        prior = visibility["archives"][role]
        need(all(prior[key] == row[key] for key in ("sha256", "bytes")), "rebound archive bytes differ")
        result["archives"][role]["source"] = row["source"]
    need(archives["rust"]["source"] != archives["c"]["source"], "rebound archive roles alias")
    return result
