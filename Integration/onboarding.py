#!/usr/bin/env python3
"""Install reviewed onboarding and guard every retained replay entry point."""
import hashlib
from pathlib import Path
import sys

PATH = 'SideStore/Views/Onboarding/OnboardingView.swift'
EXPECTED = '56514522543aba52542748d3e8af5cf6f3142da7'
REPLAY = 'SideStore/Views/Settings/Diagnostics/DeveloperOptionsView.swift'
REPLAY_HASH = '89d816d31cf8f7a412bb7e97359804f99e7cc36f'

def patch_replay(text):
    old = '''                            OnboardingView(onFinish: {
                                showOnboardingSheet = false
                            })'''
    if text.count(old) != 1: raise ValueError('Onboarding replay anchor changed')
    return text.replace(old, '''                            if #available(iOS 17.0, *) {
                                OnboardingView(onFinish: {
                                    showOnboardingSheet = false
                                })
                            } else {
                                Text("Tetherless automatic-renewal setup requires iOS 17 or later.")
                            }''', 1)

def apply(root: Path):
    sources = {}
    for path, expected in [(PATH, EXPECTED), (REPLAY, REPLAY_HASH)]:
        raw = (root/path).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != expected: raise ValueError('Unreviewed onboarding source: ' + path)
        sources[path] = raw
    # Validate both inputs before making either change.
    replay = patch_replay(sources[REPLAY].decode())
    replacement = Path(__file__).with_name('Overrides') / 'OnboardingView.swift'
    (root/PATH).write_bytes(replacement.read_bytes())
    (root/REPLAY).write_text(replay)

if __name__ == '__main__': apply(Path(sys.argv[1]))
