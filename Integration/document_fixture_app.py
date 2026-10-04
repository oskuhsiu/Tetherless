#!/usr/bin/env python3
"""Build an isolated Simulator document source; never patch or seed the product.

The fixture creates its one invalid public plist inside the Simulator with a
coordinated write AFTER Xcode has installed/launched the test. It has no network,
account, pairing or backend-success fixture. This is not a product component.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import subprocess

import simulator_environment as environment
from ui_document_fixture import PAYLOAD, NAME

BUNDLE = 'org.tetherless.testdocuments'
DISPLAY_NAME = 'Tetherless Test Documents'
ROOT = Path(__file__).parent
OUTPUT = Path('.generated/DocumentFixture.app')
MANIFEST = Path('native-ui-document-fixture.json')
LOG = Path('native-document-fixture-build.log')


def target(architecture: str) -> str:
    if architecture not in ('arm64', 'x86_64'):
        raise ValueError('Unsupported Simulator runner architecture')
    return architecture + '-apple-ios17.0-simulator'


def build_inputs(output: Path, application_identifier: str) -> Path:
    # Match the test product's team, not its app group/Keychain permissions.
    team = application_identifier.split('.')[0]
    if not re.fullmatch(r'[A-Z0-9]{10}', team):
        raise ValueError('Missing tested signing identity')
    output.mkdir(parents=True, exist_ok=False)
    info = dict(CFBundleIdentifier=BUNDLE, CFBundleDisplayName=DISPLAY_NAME,
                CFBundleName='DocumentFixture', CFBundleExecutable='DocumentFixture',
                CFBundlePackageType='APPL', CFBundleVersion='1', CFBundleShortVersionString='1.0',
                CFBundleSupportedPlatforms=['iPhoneSimulator'], MinimumOSVersion='17.0',
                UIDeviceFamily=[1], LSRequiresIPhoneOS=True,
                UIFileSharingEnabled=True, LSSupportsOpeningDocumentsInPlace=True,
                UILaunchScreen={})
    (output/'Info.plist').write_bytes(plistlib.dumps(info))
    (output/'InvalidPairingFixture.plist').write_bytes(PAYLOAD)
    entitlement = output.parent/'DocumentFixture.entitlements'
    with entitlement.open('xb') as f:
        f.write(plistlib.dumps({'application-identifier': team + '.' + BUNDLE,
                               'get-task-allow': True}))
    return entitlement


def command(args: list[str], timeout: int) -> None:
    # Own log only; never overwrite product smoke evidence or retry a command.
    with LOG.open('a') as f:
        f.write('$ ' + ' '.join(args) + '\n'); f.flush()
        try:
            p = subprocess.run(args, stdout=f, stderr=subprocess.STDOUT,
                               timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            f.write('\nTIMEOUT\n'); raise
    if p.returncode:
        raise subprocess.CalledProcessError(p.returncode, args)


def install() -> None:
    if platform.system() != 'Darwin':
        raise RuntimeError('Actual Simulator fixture requires a macOS runner')
    if MANIFEST.exists():
        raise FileExistsError('Fixture manifest already exists; refusing another install')
    device = environment.owned_device(environment.listing())
    smoke = json.loads(Path('native-launch-evidence.json').read_text())
    signing = json.loads(Path('native-simulator-signing.json').read_text())
    if (device.get('state') != 'Booted' or smoke.get('simulatorID') != device['udid'] or
            smoke.get('sourceCommit') != os.environ.get('GITHUB_SHA') or
            not smoke.get('installed') or not signing.get('signatureVerified')):
        raise RuntimeError('Expected owned, running Simulator and verified product')
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'],
                                  text=True, timeout=30).strip()
    entitlement = build_inputs(OUTPUT, signing['applicationIdentifier'])
    source = ROOT/'UITestSupport/DocumentFixtureApp.swift'
    command(['xcrun', '--sdk', 'iphonesimulator', 'swiftc', '-parse-as-library',
             '-swift-version', '6', '-target', target(platform.machine()), '-sdk', sdk,
             '-framework', 'UIKit', '-module-name', 'DocumentFixture',
             '-Xlinker', '-sectcreate', '-Xlinker', '__TEXT', '-Xlinker', '__entitlements',
             '-Xlinker', str(entitlement), '-Xlinker', '-rpath', '-Xlinker', '/usr/lib/swift', str(source), '-o', str(OUTPUT/'DocumentFixture')], 120)
    command(['codesign', '--force', '--sign', '-', '--entitlements', str(entitlement), str(OUTPUT)], 30)
    command(['codesign', '--verify', '--strict', str(OUTPUT)], 30)
    command(['xcrun', 'simctl', 'install', device['udid'], str(OUTPUT)], 120)
    # Do not launch or warm the picker. XCTest launches the source app exactly
    # once, observes documentReady, then tests the unchanged product picker.
    record = {'schema': 2, 'sourceCommit': smoke['sourceCommit'], 'simulatorID': device['udid'],
              'sourceBundleID': BUNDLE, 'sourceDisplayName': DISPLAY_NAME,
              'name': NAME, 'bytes': len(PAYLOAD), 'sha256': hashlib.sha256(PAYLOAD).hexdigest(),
              'producerSourceSHA256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'scope': 'separate public-document app only; no product state',
              'sourceAppInstalled': True, 'documentCreationObserved': False,
              'uiResult': 'not-observed'}
    with MANIFEST.open('x') as f:
        json.dump(record, f, indent=2); f.write('\n')


if __name__ == '__main__':
    install()
