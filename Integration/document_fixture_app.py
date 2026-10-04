#!/usr/bin/env python3
"""Build an isolated Simulator document source; never patch or seed the product.

The fixture creates its one invalid public plist inside the Simulator with a
coordinated write AFTER Xcode has installed/launched the test. It has no network,
account, pairing or backend-success fixture. This is not a product component.
"""
from __future__ import annotations
import hashlib
import json
import mmap
import os
from pathlib import Path
import platform
import plistlib
import re
import subprocess

import simulator_environment as environment
from ui_document_fixture import PAYLOAD, NAME
from simulator_signing import simulator_entitlements, MAX_ENTITLEMENTS

BUNDLE = 'org.tetherless.testdocuments'
DISPLAY_NAME = 'Tetherless Test Documents'
ROOT = Path(__file__).parent
OUTPUT = Path('.generated/DocumentFixture.app')
MANIFEST = Path('native-ui-document-fixture.json')
LOG = Path('native-document-fixture-build.log')
SIGNING = Path('native-document-fixture-signing.json')


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
    # Simulator iOS entitlements belong only in the linked __TEXT section.
    # Match this runner's working Xcode product: no host privileges in its
    # ad-hoc signature. Applying iOS application-identifier/get-task-allow to
    # the host signature accompanied the observed taskgated startup rejection.
    with host_entitlements(output).open('xb') as f:
        f.write(plistlib.dumps({}))
    return entitlement


def host_entitlements(output: Path) -> Path:
    return output.parent/'DocumentFixture.host.entitlements'


def signing_command(output: Path) -> list[str]:
    return ['codesign', '--force', '--sign', '-', '--entitlements',
            str(host_entitlements(output)), '--timestamp=none',
            '--generate-entitlement-der', str(output)]


def inspect_signature(output: Path, application_identifier: str) -> dict:
    """Inspect the actual signed bundle, not the source entitlement files.

    Code-sign verification is necessary but does not prove taskgated accepted
    process launch. The unchanged XCTest must still launch the producer and
    observe its documentReady label.
    """
    info = plistlib.loads((output/'Info.plist').read_bytes())
    if (info.get('CFBundleIdentifier') != BUNDLE or
            info.get('CFBundleExecutable') != 'DocumentFixture'):
        raise ValueError('Unexpected document-source executable identity')
    command(['codesign', '--verify', '--strict', str(output)], 30)
    result = subprocess.check_output(['codesign', '--display', '--entitlements', '-',
                                      '--xml', str(output)], timeout=30)
    if len(result) > MAX_ENTITLEMENTS:
        raise ValueError('Oversized document-source host entitlements')
    host = plistlib.loads(result) if result.strip() else {}
    if host != {}:
        raise ValueError('Document source must not carry host privilege entitlements')
    binary = output/'DocumentFixture'
    if binary.is_symlink() or not binary.is_file():
        raise ValueError('Expected regular document-source executable')
    with binary.open('rb') as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as data:
            simulated, digest = simulator_entitlements(data)
            executable_digest = hashlib.sha256(data).hexdigest()
    expected = {'application-identifier': application_identifier.split('.')[0] + '.' + BUNDLE,
                'get-task-allow': True}
    if simulated != expected:
        raise ValueError('Document-source simulated entitlement mismatch')
    return {'schema': 1, 'bundleID': BUNDLE, 'signatureVerified': True,
            'hostEntitlementCount': 0, 'simulatedIdentityVerified': True,
            'simulatedEntitlementsSHA256': digest,
            'executableSHA256': executable_digest, 'runtimeLaunchObserved': False,
            'scope': 'document-source bundle signature inspection, not runtime acceptance'}


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
    if MANIFEST.exists() or SIGNING.exists():
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
    command(signing_command(OUTPUT), 30)
    signature = inspect_signature(OUTPUT, signing['applicationIdentifier'])
    signature['sourceCommit'] = smoke['sourceCommit']
    with SIGNING.open('x') as f:
        json.dump(signature, f, indent=2); f.write('\n')
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
