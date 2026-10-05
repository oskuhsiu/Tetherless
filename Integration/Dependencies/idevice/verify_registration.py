#!/usr/bin/env python3
"""Read-only integrity verification for disabled pairing-source candidate profiles."""
import argparse
import json
from pathlib import Path
import tomllib

from apply_patch import HERE, VerificationError, git_blob, load_lock, read_json, safe_path, sha256, verify_source

PROFILES = ("acquisition-only", "combined")
RECEIPTS = {
    "registration/receipts/acquisition-stack-independent-review.json": "e36166d16d94e648000e82b3064240f565305cea1b931d81dc477f100c5291cc",
    "registration/receipts/acquisition-stack-repair.json": "2bb6b71abc3e4876390c814705e665ef9b7ca83bc7dd3d3b5b85d35840cf2554",
    "registration/receipts/provider-contract.json": "2f4e49207716cc79c8561d517011fdc7d5bf775cfe55d612f40380de2e36302e",
    "registration/receipts/helper-plist-key-types.json": "0cd5cf4b8f18e96c7fd08b7f4f1e195145d2e690eae749c946d2521ef045a21e",
    "registration/receipts/contributory-acquisition.json": "8eabd1496f2944178ed7897e25f4ef11640b049229b3e20dfe03580df8e93e07",
    "registration/receipts/host-generation.json": "6ea4370a0ec3c9470ff2c6690c576bc93b063cf010be9d14df5928e82949818a",
}
EXPECTED_COUNTS = {"host-only": (3, 20), "acquisition-only": (11, 74), "combined": (14, 94)}


def verify(root: Path = HERE, source: Path | None = None) -> dict:
    registry = read_json(root / "registration/registration.json")
    tree = {e["path"]: e for e in read_json(root / "source-tree.json")}
    original_ffi = tomllib.loads((root / "upstream/ffi/Cargo.toml").read_text())
    for name, expected in RECEIPTS.items():
        if sha256(safe_path(root, name).read_bytes()) != expected:
            raise VerificationError("reviewed source receipt mismatch: " + name)
    result = {}
    for name in PROFILES:
        relative = "candidate-profiles/" + name + ".json"
        data = (root / relative).read_bytes()
        if sha256(data) != registry["profiles"][name]["sha256"]:
            raise VerificationError("candidate profile identity mismatch: " + name)
        profile = load_lock(root, relative)
        if profile["activation"]["enabled"]:
            raise VerificationError("registration cannot enable artifact/application activation")
        if not profile["patch_complete"] or not profile["activation"].get("test_only_execution_authorized"):
            raise VerificationError("component source staging must be explicitly test-only")
        if profile["activation"]["consumer_integration_allowed"]:
            raise VerificationError("consumer integration is outside registration")
        if not profile.get("registered_source_complete"):
            raise VerificationError("candidate source registration is incomplete")
        seen = set()
        for edit in profile["edits"]:
            path = edit["path"]
            if path in seen or path not in ("ffi/src/lib.rs", "ffi/Cargo.toml"):
                raise VerificationError("unexpected or duplicate shared source edit")
            seen.add(path)
            before = safe_path(root / "upstream", path).read_bytes()
            if git_blob(before) != tree[path]["sha"] or sha256(before) != edit["before_sha256"]:
                raise VerificationError("shared source preimage mismatch: " + path)
            if before.count(edit["old"].encode()) != 1:
                raise VerificationError("shared source anchor is not unique")
            after = before.replace(edit["old"].encode(), edit["new"].encode(), 1)
            if sha256(after) != edit["after_sha256"]:
                raise VerificationError("shared source postimage mismatch: " + path)
            if path == "ffi/Cargo.toml":
                manifest = tomllib.loads(after.decode())
                if manifest["features"]["default"] != original_ffi["features"]["default"]:
                    raise VerificationError("upstream default FFI features changed")
                expected = dict(original_ffi["dependencies"])
                expected["plist"] = {"version": original_ffi["dependencies"]["plist"],
                    "features": ["enable_unstable_features_that_may_break_with_minor_version_bumps"]}
                if manifest["dependencies"] != expected:
                    raise VerificationError("unregistered manifest dependency change")
        for overlay in profile["overlays"]:
            path = overlay["path"]
            if path in seen or path.endswith("Cargo.lock"):
                raise VerificationError("duplicate overlay or lockfile modification")
            seen.add(path)
            data = safe_path(root / "overlay", path).read_bytes()
            if sha256(data) != overlay["sha256"]:
                raise VerificationError("registered overlay hash mismatch: " + path)
            if overlay["kind"] == "add":
                if path in tree:
                    raise VerificationError("new source would replace upstream")
            elif overlay["kind"] == "replace":
                before = safe_path(root / "upstream", path).read_bytes()
                if sha256(before) != overlay["before_sha256"] or git_blob(before) != tree[path]["sha"]:
                    raise VerificationError("registered replacement preimage mismatch: " + path)
            else:
                raise VerificationError("unsupported registration operation")
        filters = [(suite["package"], suite["filter"]) for suite in profile["native_test_filters"]]
        count = sum(suite["expected_passed"] for suite in profile["native_test_filters"])
        if len(filters) != len(set(filters)) or (len(profile["overlays"]), count) != EXPECTED_COUNTS[name]:
            raise VerificationError("registered fixture/overlay inventory differs")
        if count != profile["fixture_inventory"]["authored_count"] or profile["fixture_inventory"]["executed"]:
            raise VerificationError("incorrect native fixture evidence claim")
        for probe_set in profile["probe_sets"].values():
            for probe in probe_set.values():
                if sha256(safe_path(root, probe["path"]).read_bytes()) != probe["sha256"]:
                    raise VerificationError("native link-probe source hash mismatch")
        openssl = profile["activation"].get("openssl")
        if openssl:
            if sha256(safe_path(root, openssl["contract_path"]).read_bytes()) != openssl["contract_sha256"]:
                raise VerificationError("OpenSSL input contract mismatch")
            if (openssl["actual_target_bytes_receipt"] != "registration/receipts/provider-contract.json"
                    or openssl["actual_target_bytes_receipt_sha256"] != RECEIPTS["registration/receipts/provider-contract.json"]
                    or openssl["single_provider_linkage_receipt"] is not None):
                raise VerificationError("component input identity is distinct from unproved native provider linkage")
        result[name] = {"overlays": len(profile["overlays"]), "authored_fixture_count": count,
                        "profile_sha256": sha256((root / relative).read_bytes()), "enabled": False}
    if sha256((root / "source-lock.json").read_bytes()) != registry["baseline_main_source_lock_sha256"]:
        raise VerificationError("baseline main source lock was changed")
    if source is not None:
        checked = verify_source(source, list(tree.values()))
        result["pristine_source"] = {"verified_blobs": len(checked), "verified_bytes": sum(len(d) for _, d, _ in checked)}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(source=args.source), sort_keys=True, indent=2))
    except (VerificationError, OSError, KeyError, ValueError) as exc:
        parser.exit(1, f"candidate registration verification failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
