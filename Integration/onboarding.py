#!/usr/bin/env python3
"""Install reviewed onboarding and guard launch and retained replay entry points."""
import hashlib
from pathlib import Path
import sys

PATH = 'SideStore/Views/Onboarding/OnboardingView.swift'
EXPECTED = '56514522543aba52542748d3e8af5cf6f3142da7'
REPLAY = 'SideStore/Views/Settings/Diagnostics/DeveloperOptionsView.swift'
REPLAY_HASH = '89d816d31cf8f7a412bb7e97359804f99e7cc36f'
LAUNCH = 'AltStore/LaunchViewController.swift'
LAUNCH_HASH = '2a346285bf51112d58be7e2b67900f985ce6dd41'

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

def patch_launch(text):
    # Both presentation and startup completion must use the same eligibility.
    # Guarding only presentation would leave an older OS waiting for a wizard
    # that was never embedded, stranding the launch screen.
    old = 'if !UserDefaults.standard.hasCompletedOnboarding {'
    if text.count(old) != 2:
        raise ValueError('Onboarding launch/completion anchors changed')
    return text.replace(old,
        'if #available(iOS 17.0, *), !UserDefaults.standard.hasCompletedOnboarding {')

def apply(root: Path):
    sources = {}
    for path, expected in [(PATH, EXPECTED), (REPLAY, REPLAY_HASH), (LAUNCH, LAUNCH_HASH)]:
        raw = (root/path).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != expected: raise ValueError('Unreviewed onboarding source: ' + path)
        sources[path] = raw
    # Validate every hash and transform before mutating any generated source.
    replay = patch_replay(sources[REPLAY].decode())
    launch = patch_launch(sources[LAUNCH].decode())
    replacement = (Path(__file__).with_name('Overrides') / 'OnboardingView.swift').read_bytes()
    (root/PATH).write_bytes(replacement)
    (root/REPLAY).write_text(replay)
    (root/LAUNCH).write_text(launch)

if __name__ == '__main__': apply(Path(sys.argv[1]))
