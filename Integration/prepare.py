#!/usr/bin/env python3
"""Prepare a disposable, pinned native tree without modifying Vendor/SideStore.

This integrates compilation and narrow correctness fixes only. It does NOT
connect RenewalEngine to iOS or prove unattended refresh is implemented.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

BASELINE = "0dd743f75afc358b0ba4a002feb5f19474492371"
PROFILE_PATH = "SideStore/Core/Operations/PipelineOperations/RefreshAppOperation.swift"
INTENT_PATH = "AltStore/Intents/App Intents/RefreshAllAppsIntent.swift"
BLOBS = {
    PROFILE_PATH: "bf23bf8b2d98364f7f3e94aaae27ae626439c2f1",
    INTENT_PATH: "11b9bfb6ae823fd6acee0fe31c21be283b45eb52",
    "AltStore.xcodeproj/project.pbxproj": "a511c447bd71311bffb6d116a3cb0025a75561d4",
}


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("Upstream patch anchor changed or duplicated; review required")
    return source.replace(old, new, 1)


def patch_profile(source: str) -> str:
    # FetchProvisioningProfilesOperation keys the main entry by targetBundleIdentifier,
    # not dictionary order and not necessarily the original/resigned bundle ID.
    source = replace_once(
        source,
        "        installedApp.update(provisioningProfile: profiles.values.first!)",
        "        let mainProfile = try ProfileSelection.requireMainProfile(\n"
        "            in: profiles, bundleID: self.context.targetBundleIdentifier)\n"
        "        installedApp.update(provisioningProfile: mainProfile)",
    )
    # Validate before mutating the device as well as when updating Core Data.
    return replace_once(
        source,
        "        self.setProgress(10)",
        "        _ = try ProfileSelection.requireMainProfile(\n"
        "            in: profiles, bundleID: self.context.targetBundleIdentifier)\n"
        "        self.setProgress(10)",
    )


def patch_intent(source: str) -> str:
    # Preserve the original thrown error; never strand the continuation when the
    # operation initializer fails. Foreground fallback is intentionally NOT
    # presented as the new unattended entry point; it remains a pending gate.
    source = replace_once(
        source,
        "            let operation = try? AppManager.shared.backgroundRefresh",
        "            let operation: BackgroundRefreshAppsOperation\n"
        "            do {\n"
        "                operation = try AppManager.shared.backgroundRefresh",
    )
    return replace_once(
        source,
        '            guard let operation else {\n'
        '                debugLog("[RefreshAllAppsIntent] backgroundRefresh instance is nil")\n'
        '                return \n'
        '            }',
        '            } catch {\n'
        '                continuation.resume(throwing: error)\n'
        '                return\n'
        '            }',
    )


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True).strip()


def prepare(root: Path) -> Path:
    vendor = root / "Vendor/SideStore"
    if git(vendor, "rev-parse", "HEAD") != BASELINE:
        raise ValueError("Unexpected upstream revision; do not track a moving branch")
    if git(vendor, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Upstream tree is dirty; refusing to copy unreviewed changes")
    statuses = git(vendor, "submodule", "status", "--recursive")
    if any(line.startswith(("-", "+", "U")) for line in statuses.splitlines()):
        raise ValueError("Dependencies must be initialized at their recorded revisions")
    for path, expected in BLOBS.items():
        if git_blob((vendor / path).read_bytes()) != expected:
            raise ValueError(f"Unreviewed source content: {path}")
    output = root / ".generated/SideStore"
    if output.exists() or output.is_symlink():
        raise ValueError("Output exists; preserve/review it, then remove .generated/SideStore explicitly")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.is_symlink():
        raise ValueError("Generated directory must not be a symlink")
    shutil.copytree(vendor, output, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", ".build", "DerivedData", "xcuserdata"))
    try:
        for path, patch in ((PROFILE_PATH, patch_profile), (INTENT_PATH, patch_intent)):
            destination = output / path
            destination.write_text(patch(destination.read_text()), encoding="utf-8")
        # This folder is automatically included in the pinned native app target.
        shutil.copytree(root / "Sources/TetherlessCore", output / "SideStore/TetherlessCore")
        sample = output / "CodeSigning.xcconfig.sample"
        if sample.exists():
            shutil.copyfile(sample, output / "CodeSigning.xcconfig")
        (output / "TETHERLESS_PREPARATION.json").write_text(json.dumps({
            "upstream": BASELINE,
            "reviewed_blobs": BLOBS,
            "runtime_adapter_integrated": False,
            "device_validated": False,
        }, indent=2) + "\n")
    except Exception:
        # Keep an unsuccessful output for diagnosis, but never call it prepared.
        raise
    return output


if __name__ == "__main__":
    print(prepare(Path(__file__).resolve().parents[1]))
