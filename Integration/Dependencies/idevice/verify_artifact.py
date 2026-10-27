#!/usr/bin/env python3
"""Verify a local candidate bundle against an independently trusted manifest hash."""
import argparse
from pathlib import Path

from apply_patch import VerificationError
from build_xcframework import verify_artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    try:
        verify_artifact(args.bundle, args.manifest, args.manifest_sha256)
    except (VerificationError, OSError, KeyError, ValueError) as exc:
        parser.exit(1, f"idevice artifact verification failed: {exc}\n")
    print("Verified exact artifact file inventory and SHA256 manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
