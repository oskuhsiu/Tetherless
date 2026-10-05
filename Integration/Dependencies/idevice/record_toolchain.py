#!/usr/bin/env python3
"""Record an installed candidate toolchain for review; never install or build."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

from apply_patch import HERE, VerificationError, canonical_json
from build_xcframework import file_hash, native_environment, run, toolchain_commands, verify_toolchain


def record(destination: Path) -> str:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise VerificationError("toolchain recording requires arm64 macOS")
    if destination.exists():
        raise VerificationError("do not overwrite a previously reviewed toolchain lock")
    config = json.loads((HERE / "toolchain-lock.template.json").read_bytes())
    rustup = shutil.which("rustup")
    if not rustup:
        raise VerificationError("preinstalled official rustup is missing; no bootstrap is performed")
    env = dict(os.environ, RUSTUP_AUTO_INSTALL="0")
    for name in ("cargo", "rustc", "cmake", "ninja"):
        if name in ("cargo", "rustc"):
            path = subprocess.check_output([rustup, "which", "--toolchain", "1.98.1", name], env=env, text=True).strip()
        else:
            path = shutil.which(name)
            if not path:
                raise VerificationError(f"preinstalled build prerequisite is missing: {name}")
        executable = Path(path).resolve(strict=True)
        config["executables"][name] = {"path": str(executable), "sha256": file_hash(executable)}
    with tempfile.TemporaryDirectory(prefix="idevice-toolchain-observation-") as temporary:
        work = Path(temporary)
        clean_env, binaries = native_environment(config, work)
        config["observations"] = {key: run(command, cwd=work, env=clean_env)
                                  for key, command in toolchain_commands(binaries).items()}
        verify_toolchain(config, work, clean_env, binaries)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(canonical_json(config))
    return file_hash(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(record(args.output))
    except (VerificationError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"idevice toolchain observation failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
