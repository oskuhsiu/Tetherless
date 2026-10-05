#!/usr/bin/env python3
"""One same-host, same-signed-artifact comparison. No product or account operations."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import struct
import zlib
import sys
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'Integration'))
import document_fixture_app as producer
import simulator_environment as environment
import simulator_signing as signing
import ui_document_fixture as fixture

OUTPUT = ROOT / '.generated/document-picker-runtime'
EVIDENCE = OUTPUT / 'evidence'
DEVELOPER = '/Applications/Xcode_26.3.app/Contents/Developer'
DEVICE_TYPE = 'com.apple.CoreSimulator.SimDeviceType.iPhone-SE-3rd-generation'
RUNTIMES = ('com.apple.CoreSimulator.SimRuntime.iOS-26-2',
            'com.apple.CoreSimulator.SimRuntime.iOS-18-6')
RECIPIENT = 'org.tetherless.Tetherless.RuntimeRecipient'
TEAM = 'XYZ0123456'


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


@contextmanager
def working_at(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def digest(path: Path) -> str:
    with path.open('rb') as file:
        value = hashlib.sha256()
        for block in iter(lambda: file.read(1_048_576), b''):
            value.update(block)
        return value.hexdigest()


def command(args: list[str], directory: Path, name: str, timeout: int,
            *, bounded: bool = False) -> dict:
    """Retain every command status, including failures before any native build.

    Existing bounded capture is for probes/provider queries; compiler/test logs
    and exported stdout are retained whole, with deadlines but no excerpt filter.
    """
    path = directory / (name + '.log')
    if path.exists():
        raise FileExistsError('Refusing to replace command evidence: ' + name)
    result = {'command': args, 'startedAt': now(), 'timeoutSeconds': timeout}
    if bounded:
        result.update(environment.capture(args, path, timeout))
    else:
        with path.open('xb') as output:
            try:
                result['exitCode'] = subprocess.run(args, stdout=output, stderr=subprocess.STDOUT,
                                                    timeout=timeout, check=False).returncode
            except subprocess.TimeoutExpired:
                result['timeout'] = True
            except OSError as error:
                result['errorType'] = type(error).__name__
        result.update(originalBytes=path.stat().st_size, retainedBytes=path.stat().st_size,
                      truncated=False)
    result.update(finishedAt=now(), file=path.name, sha256=digest(path))
    manifest = directory / 'commands.json'
    records = json.loads(manifest.read_text()) if manifest.exists() else []
    records.append(result)
    save(manifest, records)
    return result


def require(result: dict) -> None:
    if result.get('exitCode') != 0 or result.get('timeout') or result.get('errorType') or result.get('truncated'):
        raise RuntimeError('Command did not complete with intact output: ' + result['file'])


def probe(args: list[str], directory: Path, name: str, timeout: int = 30) -> str:
    result = command(args, directory, name, timeout, bounded=True)
    require(result)
    return (directory / result['file']).read_text().strip()


def select_runtimes(payload: dict) -> dict:
    """Exact installed versions and device type only; never choose a fallback."""
    types = [item for item in payload['devicetypes'] if item.get('identifier') == DEVICE_TYPE]
    if len(types) != 1:
        raise ValueError('The exact SE 3 device type is unavailable or ambiguous')
    selected = {}
    for identifier in RUNTIMES:
        matches = [item for item in payload['runtimes'] if item.get('identifier') == identifier]
        version = identifier.rsplit('iOS-', 1)[1].replace('-', '.')
        if (len(matches) != 1 or matches[0].get('isAvailable') is not True or
                matches[0].get('version') != version or not matches[0].get('buildversion')):
            raise ValueError('Required installed runtime is unavailable or mismatched: ' + identifier)
        selected[identifier] = matches[0]
    return selected


def validate_toolchain(values: dict, image: dict) -> None:
    expected = {'architecture': 'arm64', 'developer': DEVELOPER,
                'xcode': 'Xcode 26.3\nBuild version 17C529', 'sdkVersion': '26.2'}
    if any(values.get(key) != value for key, value in expected.items()):
        raise ValueError('Observed compiler/SDK/architecture differs from the experiment contract')
    if os.environ.get('DEVELOPER_DIR') != DEVELOPER:
        raise ValueError('DEVELOPER_DIR must name the reviewed installed Xcode')
    if (not image.get('ImageOS') or not image.get('ImageVersion') or image.get('RUNNER_ARCH') != 'ARM64' or
            not re.search(r'ProductVersion:\s+15\.', values.get('macOS', '')) or
            not values.get('sdkPath', '').startswith(DEVELOPER + '/')):
        raise ValueError('Runner image/macOS/SDK identity is missing or unexpected')


def preflight() -> dict:
    directory = EVIDENCE / 'preflight'
    directory.mkdir()
    record = {'status': 'incomplete', 'startedAt': now(), 'productAccepted': False,
              'sourceCommit': os.environ.get('GITHUB_SHA'),
              'image': {key: os.environ.get(key) for key in ('ImageOS', 'ImageVersion', 'RUNNER_ARCH')},
              'commands': {}, 'values': {}}
    save(directory / 'manifest.json', record)
    probes = {'architecture': ['uname', '-m'], 'macOS': ['sw_vers'],
              'developer': ['xcode-select', '-p'], 'xcode': ['xcodebuild', '-version'],
              'sdkVersion': ['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version'],
              'sdkBuild': ['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-build-version'],
              'sdkPath': ['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'],
              'sdkInventory': ['xcodebuild', '-showsdks'],
              'projectSyntax': ['plutil', '-lint', str(HERE / 'RuntimePicker.xcodeproj/project.pbxproj')],
              'simulatorInventory': ['xcrun', 'simctl', 'list', '--json'],
              'python': [sys.executable, '--version'],
              'xcodebuildHelp': ['xcodebuild', '-help'],
              'simctlHelp': ['xcrun', 'simctl', 'help'],
              'simctlCreateHelp': ['xcrun', 'simctl', 'help', 'create'],
              'xcresultHelp': ['xcrun', 'xcresulttool', 'export', 'diagnostics', '--help']}
    try:
        # Do not short circuit a failed probe before its command/error manifest
        # (and the independent host identity probes) are retained.
        for key, args in probes.items():
            record['commands'][key] = command(args, directory, key, 90 if key == 'simulatorInventory' else 30,
                                               bounded=True)
            save(directory / 'manifest.json', record)
        for key, result in record['commands'].items():
            require(result)
            record['values'][key] = (directory / result['file']).read_text().strip()
        if not re.fullmatch('[0-9a-f]{40}', record['sourceCommit'] or ''):
            raise ValueError('Missing exact CI source commit')
        validate_toolchain(record['values'], record['image'])
        record['runtimes'] = select_runtimes(json.loads(record['values']['simulatorInventory']))
        record['status'] = 'accepted'
        return record
    except Exception as error:
        record.update(status='refused', errorType=type(error).__name__, error=str(error))
        raise
    finally:
        record['finishedAt'] = now()
        save(directory / 'manifest.json', record)


def case_directory(runtime: str) -> Path:
    return EVIDENCE / runtime.rsplit('.', 1)[1]


def allocate(runtime: str) -> str:
    directory = case_directory(runtime)
    directory.mkdir()
    name = 'Tetherless-CI-' + str(uuid.uuid4()).upper()
    value = environment.identifier(probe(['xcrun', 'simctl', 'create', name, DEVICE_TYPE, runtime],
                                         directory, 'create', 60))
    with working_at(directory):
        save(environment.OWNER, {'schema': 1, 'id': value, 'name': name, 'runtime': runtime,
             'deviceType': DEVICE_TYPE, 'templateName': 'iPhone SE (3rd generation)',
             'sourceCommit': os.environ['GITHUB_SHA']})
        device = environment.owned_device(json.loads(probe(
            ['xcrun', 'simctl', 'list', 'devices', 'available', '--json'], directory, 'owned-after-create')))
        if device.get('state') != 'Shutdown':
            raise RuntimeError('Fresh owned device is not shutdown before compilation')
    return value


def tree(path: Path) -> dict:
    """Hash all signed bundle contents, including resources and symlink identity."""
    if path.is_symlink() or not path.is_dir():
        raise ValueError('Expected a regular artifact directory')
    result = {}
    for item in sorted(path.rglob('*')):
        key = str(item.relative_to(path))
        if item.is_symlink():
            if not item.resolve().is_relative_to(path.resolve()):
                raise ValueError('Artifact symlink escapes its bundle')
            result[key] = {'symlink': os.readlink(item)}
        elif item.is_file():
            result[key] = {'bytes': item.stat().st_size, 'sha256': digest(item)}
    if not result:
        raise ValueError('Empty artifact directory')
    return result


def freeze(bundles: dict[str, Path], xctestrun: Path) -> dict:
    return {'bundles': {name: tree(path) for name, path in bundles.items()},
            'xctestrunSHA256': digest(xctestrun)}


def build(device: str, preflight_record: dict) -> tuple[dict[str, Path], Path, dict]:
    directory = EVIDENCE / 'build'
    directory.mkdir()
    derived = OUTPUT / 'Derived'
    source_app = OUTPUT / 'producer/DocumentFixture.app'
    entitlements = producer.build_inputs(source_app, TEAM + '.' + RECIPIENT)
    sdk = preflight_record['values']['sdkPath']
    # The reviewed producer, payload, target, entitlements and host-signing
    # construction are reused directly. Never invoke its product-install wrapper.
    require(command(['xcrun', '--sdk', 'iphonesimulator', 'swiftc', '-parse-as-library',
        '-swift-version', '6', '-target', producer.target('arm64'), '-sdk', sdk,
        '-framework', 'UIKit', '-module-name', 'DocumentFixture',
        '-Xlinker', '-sectcreate', '-Xlinker', '__TEXT', '-Xlinker', '__entitlements',
        '-Xlinker', str(entitlements), '-Xlinker', '-rpath', '-Xlinker', '/usr/lib/swift',
        str(ROOT / 'Integration/UITestSupport/DocumentFixtureApp.swift'), '-o',
        str(source_app / 'DocumentFixture')], directory, 'producer-compile', 120))
    require(command(producer.signing_command(source_app), directory, 'producer-sign', 30))
    require(command(['xcodebuild', 'build-for-testing', '-project', str(HERE / 'RuntimePicker.xcodeproj'),
        '-scheme', 'RuntimePickerTests', '-configuration', 'Debug', '-destination',
        'platform=iOS Simulator,id=' + device + ',arch=arm64', '-derivedDataPath', str(derived),
        '-parallel-testing-enabled', 'NO', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES',
        'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGNING_REQUIRED=YES', 'CODE_SIGN_IDENTITY=-',
        'CODE_SIGN_STYLE=Manual', 'AD_HOC_CODE_SIGNING_ALLOWED=YES', 'DEVELOPMENT_TEAM=' + TEAM],
        directory, 'build-for-testing', 600))
    products = derived / 'Build/Products'
    runs = list(products.glob('*.xctestrun'))
    if len(runs) != 1:
        raise RuntimeError('Expected exactly one unchanged built xctestrun file')
    bundles = {'producer': source_app, 'recipient': products / 'Debug-iphonesimulator/RuntimeRecipient.app',
               'runner': products / 'Debug-iphonesimulator/RuntimePickerTests-Runner.app'}
    inspections = {}
    save(directory / 'signatures.json', inspections)
    with working_at(directory):
        for name, app in bundles.items():
            inspections[name] = {'status': 'incomplete'}
            save(directory / 'signatures.json', inspections)
            info = plistlib.loads((app / 'Info.plist').read_bytes())
            versions = {key: info.get(key) for key in ('CFBundleVersion', 'CFBundleShortVersionString')}
            if any(not isinstance(value, str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+){0,2}', value)
                   for value in versions.values()):
                raise ValueError('Missing or invalid built bundle version')
            if name != 'runner' and versions != {'CFBundleVersion': '1', 'CFBundleShortVersionString': '1.0'}:
                raise ValueError('Unexpected diagnostic app version')
            if name == 'recipient' and (info.get('LSSupportsOpeningDocumentsInPlace') is not True
                                       or info.get('UIFileSharingEnabled') is True):
                raise ValueError('Recipient must support original documents without publishing its own')
            executable = app / info['CFBundleExecutable']
            if probe(['xcrun', 'lipo', '-archs', str(executable)], directory, name + '-architecture') != 'arm64':
                raise ValueError('Built app or runner is not thin arm64')
            if name == 'runner':
                # Xcode copies its prebuilt XCTRunner and signs it. The product
                # parser's app-specific linked-identity assertion does not apply
                # to that toolchain executable; inspect, retain, never modify it.
                if info['CFBundleIdentifier'] != 'org.tetherless.Tetherless.RuntimePickerTests.xctrunner':
                    raise ValueError('Unexpected generated UI-runner identity')
                require(command(['codesign', '--verify', '--strict', str(app)], directory, 'runner-signature', 30))
                require(command(['codesign', '--display', '--entitlements', '-', '--xml', str(app)],
                                directory, 'runner-entitlements', 30))
                inspections[name] = {'signatureVerified': True, 'bundleID': info['CFBundleIdentifier'],
                                     'scope': 'Xcode-generated runner; linked product identity not inferred'}
            else:
                inspections[name] = (producer.inspect_signature(app, TEAM + '.' + RECIPIENT) if name == 'producer'
                                     else signing.inspect(app, TEAM))
            inspections[name]['bundleVersions'] = versions
            save(directory / 'signatures.json', inspections)
    test_binary = bundles['runner'] / 'PlugIns/RuntimePickerTests.xctest/RuntimePickerTests'
    if probe(['xcrun', 'lipo', '-archs', str(test_binary)], directory, 'test-bundle-architecture') != 'arm64':
        raise ValueError('UI-test executable is not thin arm64')
    frozen = freeze(bundles, runs[0])
    save(directory / 'artifact-hashes.json', frozen)
    return bundles, runs[0], frozen


def selection_observed(value: dict) -> bool:
    return (isinstance(value, dict) and type(value.get('schema')) is int and value.get('schema') == 1 and value.get('productAccepted') is False and
            value.get('selectedBytesRead') is False and value.get('protocolViolation') is False and
            value.get('evidenceWriteFailed') is False and isinstance(value.get('presentations'), list) and
            all(isinstance(item, dict) and type(item.get('callbackCount')) is int
                and item.get('dismissed') is True for item in value['presentations']) and
            value['presentations'] == [
                {'outcome': outcome, 'callbackCount': 1, 'dismissed': True}
                for outcome in ('cancelled', 'cancelled', 'selectedFileURL')])


def provider_commands(device: str, start: str, end: str) -> dict[str, list[str]]:
    predicates = {
        'resolver': 'process == "ResolverService"',
        'local-provider': 'process == "LocalStorageFileProvider"',
        'document-manager': '(process == "DocumentManager" OR process == "DocumentManagerUICore" OR '
            'subsystem BEGINSWITH "com.apple.DocumentManager" OR '
            'senderImagePath CONTAINS "/DocumentManagerUICore.framework/")',
        'recipient-system': 'process == "RuntimeRecipient"',
        'fileprovider': 'process == "fileproviderd"',
        'filecoordination': 'process == "filecoordinationd"',
    }
    exclude = ' AND NOT (subsystem BEGINSWITH "com.apple.apsd" OR eventMessage CONTAINS "com.apple.apsd")'
    return {name: ['xcrun', 'simctl', 'spawn', device, 'log', 'show', '--start', start, '--end', end,
                   '--timezone', 'UTC', '--style', 'compact', '--info', '--debug', '--predicate', '(' + predicate + ')' + exclude]
            for name, predicate in predicates.items()}


def container(device: str, bundle: str, kind: str, directory: Path, name: str) -> Path:
    value = Path(probe(['xcrun', 'simctl', 'get_app_container', device, bundle, kind], directory, name))
    if not value.is_absolute() or value.is_symlink() or not value.is_dir():
        raise ValueError('Unexpected installed container')
    return value


def stdout_inventory(directory: Path) -> list[dict]:
    entries = []
    for path in sorted((directory / 'diagnostics').rglob('StandardOutputAndStandardError-*')):
        if path.is_symlink() or not path.is_file():
            raise ValueError('Unexpected stdout export type')
        entries.append({'file': str(path.relative_to(directory)), 'bytes': path.stat().st_size,
                        'sha256': digest(path), 'truncated': False,
                        'recipient': re.fullmatch('StandardOutputAndStandardError-' + re.escape(RECIPIENT)
                                                   + r'(?:-[^/]+)?\.txt', path.name) is not None})
    return entries


def verify_screenshot(data: bytes) -> None:
    # The observed XCTest screenshots are ordinary noninterlaced 8-bit RGB/RGBA
    # PNGs. Validate bounds, CRCs and decompression, not merely a filename/header.
    if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data) > 20_971_520:
        raise ValueError('Invalid screenshot PNG')
    offset = 8; dimensions = None; compressed = bytearray(); ended = False
    while offset + 12 <= len(data):
        length, kind = struct.unpack_from('>I4s', data, offset)
        end = offset + 12 + length
        if end > len(data): raise ValueError('Truncated screenshot chunk')
        payload = data[offset + 8:end - 4]
        if zlib.crc32(kind + payload) & 0xffffffff != struct.unpack_from('>I', data, end - 4)[0]:
            raise ValueError('Corrupt screenshot chunk')
        if offset == 8:
            if kind != b'IHDR' or length != 13: raise ValueError('Missing screenshot dimensions')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
            if not (0 < width <= 4096 and 0 < height <= 4096 and depth == 8 and color in (2, 6)
                    and compression == filtering == interlace == 0):
                raise ValueError('Unexpected screenshot format')
            dimensions = (width, height, 3 if color == 2 else 4)
        if kind == b'IDAT': compressed.extend(payload)
        if kind == b'IEND':
            ended = length == 0 and end == len(data)
            break
        offset = end
    if not ended or dimensions is None or not compressed: raise ValueError('Incomplete screenshot')
    width, height, channels = dimensions
    row = 1 + width * channels
    inflater = zlib.decompressobj()
    pixels = inflater.decompress(compressed, row * height + 1)
    if (len(pixels) != row * height or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail
            or any(pixels[index] > 4 for index in range(0, len(pixels), row))):
        raise ValueError('Invalid screenshot pixel stream')


def attachment_evidence(directory: Path, device: str) -> dict:
    root = directory / 'attachments'
    path = root / 'manifest.json'
    if path.is_symlink() or path.stat().st_size > 1_048_576:
        raise ValueError('Invalid attachment manifest')
    manifest = json.loads(path.read_text())
    if not isinstance(manifest, list): raise ValueError('Unexpected attachment manifest schema')
    groups = [group for group in manifest if group.get('testIdentifier') ==
              'RuntimePickerTests/testCrossContainerSelection()']
    if len(groups) != 1: raise ValueError('Missing or ambiguous standalone test attachments')
    evidence = {'files': []}
    for prefix, suffix in [('after-single-file-activation', '.png'),
                           ('after-single-file-activation-hierarchy', '.txt'),
                           ('runtime-selection-result', '.txt')]:
        matches = [item for item in groups[0]['attachments'] if item.get('suggestedHumanReadableName', '').startswith(prefix + '_')
                   and item['suggestedHumanReadableName'].endswith(suffix)]
        if len(matches) != 1 or matches[0].get('deviceId') != device:
            raise ValueError('Missing/ambiguous/wrong-device attachment: ' + prefix)
        name = matches[0].get('exportedFileName', '')
        if not name or Path(name).name != name or not name.endswith(suffix):
            raise ValueError('Invalid attachment file reference')
        path = root / name
        if path.is_symlink() or not 0 < path.stat().st_size <= 20_971_520:
            raise ValueError('Missing, empty or oversized attachment')
        data = path.read_bytes()
        if suffix == '.png':
            verify_screenshot(data)
        else:
            text = data.decode('utf-8').strip()
            if prefix.endswith('-hierarchy'):
                # XCUIApplication can export a direct Application/Window tree;
                # element descriptions may add Attributes/Element subtree wrappers.
                if (not re.search(r'(?m)^(?:Attributes:\s*)?Application, [^\n]+', text)
                        or not re.search(r'(?m)^\s+Window(?: \([^\n)]*\))?, [^\n]+', text)):
                    raise ValueError('Invalid accessibility hierarchy attachment')
            else:
                if not re.fullmatch(r'waitCompleted=(true|false); outcome=(idle|waiting|selectedFileURL|invalidSelection|cancelled|not-visible); pickerVisible=(true|false); productAccepted=false', text):
                    raise ValueError('Invalid selection result attachment')
                evidence['selectionResultPassed'] = text == 'waitCompleted=true; outcome=selectedFileURL; pickerVisible=false; productAccepted=false'
        evidence['files'].append({'name': prefix, 'file': name, 'bytes': len(data),
                                  'sha256': hashlib.sha256(data).hexdigest()})
    evidence['complete'] = True
    return evidence


def inspect_case(runtime: str, device: str, bundles: dict[str, Path], xctestrun: Path,
                 frozen: dict) -> dict:
    directory = case_directory(runtime)
    result = {'runtime': runtime, 'simulatorID': device, 'sourceCommit': os.environ['GITHUB_SHA'],
              'startedAt': now(), 'sourceBundleID': producer.BUNDLE, 'recipientBundleID': RECIPIENT,
              'productAccepted': False, 'selectionObserved': False,
              'diagnosticPassed': False, 'errors': [], 'stage': 'artifact-identity'}
    save(directory / 'result.json', result)
    start = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    with working_at(directory):
        try:
            if freeze(bundles, xctestrun) != frozen:
                raise RuntimeError('Built signed artifacts changed before runtime case')
            result['artifactsUnchangedBefore'] = True
            result['stage'] = 'owned-readiness'
            environment.owned_device(environment.listing())
            require(command([sys.executable, str(ROOT / 'Integration/simulator_smoke.py'), 'prepare',
                             '--simulator', device], directory, 'readiness', 600))
            result['stage'] = 'source-install'
            require(command(['xcrun', 'simctl', 'install', device, str(bundles['producer'])],
                            directory, 'source-install', 120))
            result['stage'] = 'ui'
            test = command(['xcodebuild', 'test-without-building', '-xctestrun', str(xctestrun),
                '-destination', 'platform=iOS Simulator,id=' + device + ',arch=arm64',
                '-resultBundlePath', str(directory / 'picker.xcresult'), '-parallel-testing-enabled', 'NO',
                '-maximum-concurrent-test-simulator-destinations', '1'], directory, 'ui', 300)
            result['testCommand'] = test
            require(test)
            result['stage'] = 'postconditions'
        except Exception as error:
            result['failedStage'] = result['stage']
            result['errors'].append({'stage': result['stage'], 'type': type(error).__name__, 'error': str(error)})
        finally:
            end = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            save(directory / 'result.json', result)
            # Every postcondition/collector is independent. An assertion, missing
            # container, exporter or log query cannot skip source preservation.
            def retain(name, operation):
                try:
                    result[name] = operation()
                except Exception as error:
                    result['errors'].append({'stage': name, 'type': type(error).__name__, 'error': str(error)})
                save(directory / 'result.json', result)

            retain('sourceVerification', lambda: fixture.verify(container(device, producer.BUNDLE, 'data',
                                                            directory, 'source-container')))
            def observation():
                path = container(device, RECIPIENT, 'data', directory, 'recipient-container') / 'Library/Caches/RuntimeObservation.json'
                if path.is_symlink() or path.stat().st_size > 65536:
                    raise ValueError('Invalid observation file')
                raw = path.read_bytes()
                (directory / 'recipient-observation.json').write_bytes(raw)
                value = json.loads(raw)
                result['selectionObserved'] = selection_observed(value)
                return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
            retain('observation', observation)
            retain('artifactsUnchangedAfter', lambda: freeze(bundles, xctestrun) == frozen)
            def installed_identity():
                actual = {}
                for name, app in bundles.items():
                    bundle = plistlib.loads((app / 'Info.plist').read_bytes())['CFBundleIdentifier']
                    actual[name] = tree(container(device, bundle, 'app', directory, name + '-installed-container'))
                    save(directory / 'installed-artifact-hashes.json', actual)
                return actual == frozen['bundles']
            retain('installedArtifactsIdentical', installed_identity)
            try:
                environment.owned_device(environment.listing())
                retain('device-log-help', lambda: command(['xcrun', 'simctl', 'spawn', device, 'log', 'help', 'show'],
                                                         directory, 'device-log-help', 30, bounded=True))
                for name, args in provider_commands(device, start, end).items():
                    retain(name, lambda args=args, name=name: command(args, directory, name, 30, bounded=True))
            except Exception as error:
                result['errors'].append({'stage': 'provider-ownership', 'type': type(error).__name__})
            for kind in ('diagnostics', 'attachments'):
                if (directory / 'picker.xcresult').exists():
                    retain('export-' + kind, lambda kind=kind: command(['xcrun', 'xcresulttool', 'export', kind,
                        '--path', str(directory / 'picker.xcresult'), '--output-path', str(directory / kind)],
                        directory, 'export-' + kind, 120))
            # Retain the ENTIRE export, including the primary recipient's complete
            # stdout/stderr. Missing stdout is an explicit evidence gap, not silence.
            result['stdout'] = []
            retain('stdout', lambda: stdout_inventory(directory))
            recipient_stdout = [item for item in result['stdout'] if item['recipient']]
            result['recipientStdoutRetained'] = bool(recipient_stdout) and all(item['bytes'] > 0 for item in recipient_stdout)
            retain('attachmentEvidence', lambda: attachment_evidence(directory, device))
            collected = [result.get(key, {}) for key in (*provider_commands(device, start, end),
                                                       'device-log-help', 'export-diagnostics', 'export-attachments')]
            result['collectionComplete'] = result.get('attachmentEvidence', {}).get('complete') is True and all(item.get('exitCode') == 0 and not item.get('truncated')
                and not item.get('timeout') and not item.get('errorType') for item in collected)
            result['diagnosticPassed'] = (result['collectionComplete'] and not result['errors'] and result['selectionObserved'] and
                result.get('sourceVerification', {}).get('originalPreserved') is True and
                result.get('artifactsUnchangedAfter') is True and result.get('installedArtifactsIdentical') is True and
                result['recipientStdoutRetained'] and result.get('attachmentEvidence', {}).get('selectionResultPassed') is True)
            result.update(finishedAt=now(), stage='finished')
            save(directory / 'result.json', result)
    return result


def shutdown_all() -> None:
    for runtime in RUNTIMES:
        directory = case_directory(runtime)
        if not (directory / environment.OWNER).exists():
            continue
        with working_at(directory):
            # This existing helper validates live ownership and does nothing if
            # already shut down. Never delete a device or reset a shared service.
            name = 'shutdown' if not (directory / 'shutdown.log').exists() else 'cleanup-shutdown'
            if (directory / (name + '.log')).exists():
                raise FileExistsError('Cleanup evidence already exists')
            result = command([sys.executable, str(ROOT / 'Integration/simulator_environment.py'), 'shutdown'],
                             directory, name, 90)
            require(result)


def run() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=False)
    summary = {'status': 'incomplete', 'startedAt': now(), 'productAccepted': False, 'cases': []}
    save(EVIDENCE / 'comparison.json', summary)
    try:
        identity = preflight()
        devices = {runtime: allocate(runtime) for runtime in RUNTIMES}
        bundles, xctestrun, frozen = build(devices[RUNTIMES[0]], identity)
        for runtime in RUNTIMES:
            summary['cases'].append(inspect_case(runtime, devices[runtime], bundles, xctestrun, frozen))
            save(EVIDENCE / 'comparison.json', summary)
            # Keep only one owned Simulator booted at a time on this same host.
            with working_at(case_directory(runtime)):
                require(command([sys.executable, str(ROOT / 'Integration/simulator_environment.py'), 'shutdown'],
                                case_directory(runtime), 'case-shutdown', 90))
        summary['status'] = 'diagnostic-passed' if all(case['diagnosticPassed'] for case in summary['cases']) else 'diagnostic-failed'
    except Exception as error:
        summary.update(status='incomplete', errorType=type(error).__name__, error=str(error))
    finally:
        try:
            shutdown_all()
        except Exception as error:
            summary['cleanupError'] = {'type': type(error).__name__, 'error': str(error)}
        summary['finishedAt'] = now()
        save(EVIDENCE / 'comparison.json', summary)
    return 0 if summary['status'] == 'diagnostic-passed' and 'cleanupError' not in summary else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', 'cleanup'))
    args = parser.parse_args()
    if args.action == 'cleanup':
        shutdown_all()
    else:
        sys.exit(run())
