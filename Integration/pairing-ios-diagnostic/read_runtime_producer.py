#!/usr/bin/env python3
"""Validate the reviewed runtime selection before emitting fixed runner variables."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import sys

MAX_CONTEXT = 4096
CONTEXT = Path(__file__).resolve().parent / "runtime-producer.json"
FIELDS = {"producer_run_id": "PRODUCER_RUN_ID", "producer_source_commit": "PRODUCER_SOURCE_COMMIT",
          "producer_run_attempt": "PRODUCER_RUN_ATTEMPT"}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate runtime context field")
        result[key] = value
    return result


def read_context(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("a regular runtime-producer.json selection is required")
    with path.open("rb") as stream:
        raw = stream.read(MAX_CONTEXT + 1)
    if len(raw) > MAX_CONTEXT:
        raise ValueError("runtime context exceeds 4096 bytes")
    context = json.loads(raw, object_pairs_hook=unique_object)
    if (not isinstance(context, dict) or set(context) != {"schema", *FIELDS}
            or type(context["schema"]) is not int or context["schema"] != 1):
        raise ValueError("runtime context must contain exactly the schema 1 producer selection")
    for name in ("producer_run_id", "producer_run_attempt"):
        if type(context[name]) is not int or context[name] < 1:
            raise ValueError("runtime producer IDs and attempt must be positive integers")
    commit = context["producer_source_commit"]
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("runtime producer source must be a full lowercase Git SHA")
    return {variable: str(context[name]) for name, variable in FIELDS.items()}


def emit_context(path, github_env):
    values = read_context(path)
    # All fields are fully validated first. Neither names nor delimiters come from JSON.
    payload = "".join(name + "=" + value + "\n" for name, value in values.items())
    with github_env.open("a", encoding="utf-8") as stream:
        stream.write(payload)


def main():
    try:
        emit_context(CONTEXT, Path(os.environ["GITHUB_ENV"]))
    except (ValueError, KeyError, OSError) as error:
        print("Runtime producer selection rejected: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
