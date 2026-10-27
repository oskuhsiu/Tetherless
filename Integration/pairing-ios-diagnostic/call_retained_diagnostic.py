#!/usr/bin/env python3
"""Pass trusted caller identities and hashes independently to diagnostic tools."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

from fetch_retained_handoff import identities, require, sha256

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORK = ROOT / ".pairing-consumer"


def command(phase, env):
    consumer, producer = identities(env)
    for key in ("HANDOFF_SHA256", "APPLE_RECEIPT_SHA256"):
        require(re.fullmatch(r"[0-9a-f]{64}", env[key]), "missing caller-computed hash: " + key)
    for key in ("COMPONENT_FIXTURES_RESULT", "NATIVE_PROOFS_RESULT"):
        require(env[key] == "success", "authenticated producer group did not succeed")
    common = ["--native-handoff", str(WORK / "handoff/handoff.json"),
              "--native-handoff-sha256", env["HANDOFF_SHA256"],
              "--handoff-mode", "retained-producer", "--repository", consumer["repository"],
              "--repository-id", str(consumer["repository_id"]), "--run-id", str(consumer["run_id"]),
              "--source-commit", consumer["source_commit"], "--consumer-attempt", str(consumer["consumer_attempt"]),
              "--producer-run-id", str(producer["run_id"]), "--producer-source-commit", producer["source_commit"],
              "--producer-run-attempt", str(producer["run_attempt"]),
              "--component-fixtures-result", env["COMPONENT_FIXTURES_RESULT"],
              "--native-proofs-result", env["NATIVE_PROOFS_RESULT"],
              "--native-recipe", str(ROOT / "Integration/Dependencies/idevice")]
    if phase == "bind":
        return [sys.executable, str(HERE / "prepare_binding.py"),
                "--prepared-source", str(ROOT / ".generated/SideStore"),
                "--apple-artifact", str(WORK / "handoff/apple-producer/apple-producer-output"),
                "--apple-artifact-receipt-sha256", env["APPLE_RECEIPT_SHA256"],
                "--diagnostic-output", str(WORK / "diagnostic")] + common
    require(phase in ("Debug", "Release"), "unsupported diagnostic phase")
    require(re.fullmatch(r"[0-9a-f]{64}", env["BINDING_RECEIPT_SHA256"]), "missing caller-computed binding hash")
    return [sys.executable, str(HERE / "run_compile.py"),
            "--diagnostic-root", str(WORK / "diagnostic"), "--configuration", phase,
            "--work-dir", str(WORK / ("compile-" + phase.lower())),
            "--toolchain-lock", str(WORK / "handoff/apple-producer/evidence/toolchain-lock.observed.json"),
            "--binding-receipt-sha256", env["BINDING_RECEIPT_SHA256"]] + common


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("bind", "Debug", "Release"))
    args = parser.parse_args()
    try:
        subprocess.run(command(args.phase, os.environ), check=True, cwd=ROOT)
        if args.phase == "bind":
            digest = sha256(WORK / "diagnostic/TETHERLESS_PAIRING_DIAGNOSTIC_BINDING.json")
            with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
                stream.write("binding_receipt_sha256=" + digest + "\n")
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
