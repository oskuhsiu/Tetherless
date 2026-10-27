#!/usr/bin/env python3
"""Inspect a CI Simulator product without signing or repairing it.

Xcode puts host entitlements in the ad-hoc signature and simulated iOS
entitlements in Mach-O __TEXT,__entitlements. Inspect both, not source xcent
files. Scope: the thin 64-bit iOS Simulator executable built by this workflow.
This is not device authorization, runtime Keychain access or CMS attestation.
"""
import argparse
import hashlib
import json
import mmap
from pathlib import Path
import plistlib
import struct
import subprocess

MAX_ENTITLEMENTS = 1_048_576


def validate(info, entitlements, team):
    if not isinstance(info, dict) or not isinstance(entitlements, dict):
        raise ValueError('Expected property-list dictionaries')
    bundle = info.get('CFBundleIdentifier', '')
    if not isinstance(team, str) or not team.isalnum() or len(team) != 10:
        raise ValueError('Invalid expected team')
    if not isinstance(bundle, str) or not (
            bundle == 'org.tetherless.Tetherless' or bundle.startswith('org.tetherless.Tetherless.')):
        raise ValueError('Unexpected simulator bundle identity')
    expected = team + '.' + bundle
    identifiers = [entitlements[k] for k in ('application-identifier', 'com.apple.application-identifier')
                   if k in entitlements]
    if not identifiers or any(identifier != expected for identifier in identifiers):
        raise ValueError('Missing or mismatched simulator application-identifier')
    return {'bundleID': bundle, 'applicationIdentifier': expected,
            'keychainIdentityPresent': True, 'deviceValidated': False,
            'appleLoginValidated': False, 'unattendedRenewalValidated': False,
            'runtimeKeychainAccessValidated': False}


def simulator_entitlements(binary):
    """Read the linked section with exact bounds; no scan/fallback to source files."""
    if len(binary) < 32 or binary[:4] != b'\xcf\xfa\xed\xfe':
        raise ValueError('Expected a thin little-endian 64-bit Mach-O')
    _, cpu, _, kind, count, commands_size, _, _ = struct.unpack_from('<8I', binary)
    if cpu not in (0x01000007, 0x0100000c) or kind != 2:
        raise ValueError('Expected an arm64/x86_64 executable')
    end = 32 + commands_size
    if count > 4096 or commands_size > 16_777_216 or end > len(binary):
        raise ValueError('Invalid Mach-O command bounds')
    offset = 32
    sections = []
    platforms = []
    for _ in range(count):
        if offset + 8 > end:
            raise ValueError('Truncated Mach-O command')
        command, size = struct.unpack_from('<II', binary, offset)
        if size < 8 or size % 8 or offset + size > end:
            raise ValueError('Invalid Mach-O command size')
        if command == 0x32:  # LC_BUILD_VERSION
            if size < 24:
                raise ValueError('Truncated build version')
            platforms.append(struct.unpack_from('<I', binary, offset + 8)[0])
        if command == 0x19:  # LC_SEGMENT_64
            if size < 72:
                raise ValueError('Truncated segment')
            segment_name = binary[offset + 8:offset + 24].rstrip(b'\0')
            file_offset, file_size = struct.unpack_from('<QQ', binary, offset + 40)
            section_count = struct.unpack_from('<I', binary, offset + 64)[0]
            if size != 72 + section_count * 80:
                raise ValueError('Invalid section table')
            for index in range(section_count):
                start = offset + 72 + 80 * index
                name = binary[start:start + 16].rstrip(b'\0')
                owner = binary[start + 16:start + 32].rstrip(b'\0')
                if name == b'__entitlements' and owner == b'__TEXT':
                    length = struct.unpack_from('<Q', binary, start + 40)[0]
                    location = struct.unpack_from('<I', binary, start + 48)[0]
                    flags = struct.unpack_from('<I', binary, start + 64)[0]
                    if (segment_name != owner or flags & 0xff != 0 or
                            not 0 < length <= MAX_ENTITLEMENTS or location < end or
                            location < file_offset or location + length > file_offset + file_size or
                            location + length > len(binary)):
                        raise ValueError('Invalid simulated entitlement section')
                    sections.append(bytes(binary[location:location + length]))
        offset += size
    if offset != end or platforms != [7] or len(sections) != 1:
        raise ValueError('Expected one iOS Simulator platform and entitlement section')
    payload = sections[0]
    # A NUL terminator is allowed; non-XML content is never guessed or fabricated.
    entitlements = plistlib.loads(payload.rstrip(b'\0'))
    if not isinstance(entitlements, dict):
        raise ValueError('Simulated entitlements must be a dictionary')
    return entitlements, hashlib.sha256(payload).hexdigest()


def inspect(app, team, evidence=None):
    evidence = evidence if evidence is not None else {}
    evidence['failureStage'] = 'bundleMetadata'
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    executable = info.get('CFBundleExecutable')
    if (not isinstance(executable, str) or not executable or executable in ('.', '..') or
            '/' in executable or '\\' in executable or '\0' in executable):
        raise ValueError('Invalid executable path')
    path = app / executable
    if path.is_symlink() or not path.is_file():
        raise ValueError('Expected a regular executable')
    evidence['failureStage'] = 'hostSignature'
    subprocess.run(['/usr/bin/codesign', '--verify', '--strict', str(app)],
                   check=True, capture_output=True, timeout=30)
    evidence['signatureVerified'] = True
    evidence['failureStage'] = 'hostEntitlementFormat'
    # Current codesign defaults to a human-readable abstract representation.
    result = subprocess.run(['/usr/bin/codesign', '--display', '--entitlements', '-', '--xml', str(app)],
                            check=True, capture_output=True, timeout=30)
    if len(result.stdout) > MAX_ENTITLEMENTS:
        raise ValueError('Oversized host entitlements')
    host = plistlib.loads(result.stdout) if result.stdout.strip() else {}
    if not isinstance(host, dict):
        raise ValueError('Invalid host entitlements')
    evidence['hostEntitlementCount'] = len(host)
    evidence['failureStage'] = 'simulatedEntitlements'
    with path.open('rb') as file:
        with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as binary:
            entitlements, digest = simulator_entitlements(binary)
    evidence.update(validate(info, entitlements, team))
    evidence['entitlementSource'] = 'Mach-O __TEXT,__entitlements'
    evidence['simulatedEntitlementsSHA256'] = digest
    evidence['failureStage'] = None
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path)
    parser.add_argument('--team', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evidence = {'signatureVerified': False, 'keychainIdentityPresent': False,
                'deviceValidated': False, 'appleLoginValidated': False,
                'runtimeKeychainAccessValidated': False, 'unattendedRenewalValidated': False}
    try:
        inspect(args.app, args.team, evidence)
    except Exception as error:
        evidence['errorType'] = type(error).__name__
        raise
    finally:
        args.output.write_text(json.dumps(evidence, indent=2) + '\n')


if __name__ == '__main__':
    main()
