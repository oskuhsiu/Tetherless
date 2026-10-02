#!/usr/bin/env python3
"""Install the reviewed iOS onboarding replacement; no auth/test bypass flags."""
import hashlib
from pathlib import Path
import sys

PATH = 'SideStore/Views/Onboarding/OnboardingView.swift'
EXPECTED = '56514522543aba52542748d3e8af5cf6f3142da7'

def apply(root: Path):
    destination = root / PATH
    raw = destination.read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if actual != EXPECTED:
        raise ValueError('Unreviewed onboarding source')
    replacement = Path(__file__).with_name('Overrides') / 'OnboardingView.swift'
    destination.write_bytes(replacement.read_bytes())

if __name__ == '__main__': apply(Path(sys.argv[1]))
