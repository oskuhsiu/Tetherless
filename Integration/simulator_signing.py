#!/usr/bin/env python3
"""Check the actual simulator build's identity, not its source .entitlements file.

No signing key or Apple account is used. This check is not device signing,
Apple authorization or a substitute for the real UI/Keychain tests.
"""
import argparse
import json
from pathlib import Path
import plistlib
import subprocess


def validate(info, entitlements, team):
    bundle = info.get('CFBundleIdentifier', '')
    if not isinstance(bundle, str) or not (
            bundle == 'org.tetherless.Tetherless' or bundle.startswith('org.tetherless.Tetherless.')):
        raise ValueError('Unexpected simulator bundle identity')
    expected = team + '.' + bundle
    identifiers = [entitlements[k] for k in ('application-identifier', 'com.apple.application-identifier')
                   if k in entitlements]
    if not identifiers or any(identifier != expected for identifier in identifiers):
        raise ValueError('Missing or mismatched simulator application-identifier')
    # A matching application-identifier supplies an app-local Keychain group;
    # an explicit keychain-access-groups array is not required for our queries.
    return {'bundleID': bundle, 'applicationIdentifier': expected,
            'keychainIdentityPresent': True, 'deviceValidated': False,
            'appleLoginValidated': False, 'unattendedRenewalValidated': False}


def inspect(app, team):
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    # Validate a signature actually exists. Never sign here or fill in missing
    # entitlements to make the evidence pass.
    subprocess.run(['/usr/bin/codesign', '--verify', '--strict', str(app)],
                   check=True, capture_output=True, timeout=30)
    result = subprocess.run(['/usr/bin/codesign', '--display', '--entitlements', '-', str(app)],
                            check=True, capture_output=True, timeout=30)
    entitlements = plistlib.loads(result.stdout)
    return validate(info, entitlements, team)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path)
    parser.add_argument('--team', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evidence = {'signatureVerified': False, 'keychainIdentityPresent': False,
                'deviceValidated': False, 'appleLoginValidated': False,
                'unattendedRenewalValidated': False}
    try:
        evidence.update(inspect(args.app, args.team))
        evidence['signatureVerified'] = True
    finally:
        # A rejected build still leaves false-by-default evidence. No raw
        # Keychain query, data, credential or signing material is collected.
        args.output.write_text(json.dumps(evidence, indent=2) + '\n')


if __name__ == '__main__':
    main()
