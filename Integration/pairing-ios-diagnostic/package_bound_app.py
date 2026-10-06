#!/usr/bin/env python3
"""Retain one complete unsigned diagnostic App, bound to its exact compile evidence.

No signing, upload, installation, binary execution or capability activation occurs.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import zipfile

import prepare_binding as prepare
from fetch_retained_handoff import identities, require
from native_handoff import NEEDS, verify_handoff
from run_compile import audit_bound_inputs

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_spec = importlib.util.spec_from_file_location('bound_unsigned_packager', HERE.parent / 'package_unsigned.py')
packager = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(packager)
delivery = packager.delivery
AUDITS = ('bound-input-audit.json', 'recipe-input-audit.json', 'native-handoff-audit.json')


def directory(path: Path) -> Path:
    """Reject symlink traversal within caller-selected, absolute workspace paths."""
    require(path.is_absolute(), 'absolute workspace path required')
    for part in (path, *path.parents):
        require(not part.is_symlink(), 'workspace path traverses a symlink')
    require(path.is_dir(), 'required workspace directory is missing')
    return path


def read_json(path: Path, expected: str | None = None) -> dict:
    directory(path.parent)
    data = delivery.metadata_bytes(path)
    if expected is not None:
        require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected),
                'independent expected hash is missing or invalid')
        require(hashlib.sha256(data).hexdigest() == expected, 'evidence hash differs: ' + path.name)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate evidence JSON key')
            result[key] = value
        return result
    value = json.loads(data, object_pairs_hook=unique)
    require(isinstance(value, dict), 'evidence JSON must be an object')
    return value


def app_inventory(app: Path) -> list[dict]:
    """No source-tree exclusions: retain every regular file and safe symlink."""
    packager.validate_app(app)
    budget, rows = delivery.Budget(), []
    def visit(root, depth=0):
        require(depth <= delivery.MAX_DEPTH, 'App inventory exceeds traversal budget')
        for path in delivery.bounded_children(root):
            name = delivery.safe_name(path.relative_to(app).as_posix())
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode):
                budget.add(0)
                visit(path, depth + 1)
            elif stat.S_ISLNK(mode):
                target = os.readlink(path)
                data = target.encode('utf-8')
                budget.add(len(data))
                rows.append({'path': name, 'type': 'symlink', 'target': target,
                             'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
            else:
                require(stat.S_ISREG(mode), 'App contains a special file')
                identity = delivery.file_identity(path)
                budget.add(identity['size'])
                rows.append({'path': name, 'type': 'file', 'executableBits': mode & 0o111, **identity})
    visit(app)
    return sorted(rows, key=lambda row: row['path'])


def archive_executable_bits(archive: Path) -> dict[str, int]:
    # The generic byte inventory does not record modes. Bound this second central-
    # directory read too, and keep the extra metadata in the wrapper inventory.
    class BoundedReader:
        def __init__(self, stream):
            self.stream = stream
        def read(self, size=-1):
            require(size <= delivery.MAX_ARCHIVE_READ, 'ZIP metadata read exceeds budget')
            data = self.stream.read(delivery.MAX_ARCHIVE_READ + 1 if size < 0 else size)
            require(len(data) <= delivery.MAX_ARCHIVE_READ, 'ZIP metadata read exceeds budget')
            return data
        def seek(self, *args):
            return self.stream.seek(*args)
        def tell(self):
            return self.stream.tell()
        def seekable(self):
            return self.stream.seekable()
    modes = {}
    with delivery.open_regular(archive) as stream, zipfile.ZipFile(BoundedReader(stream)) as zipped:
        require(len(zipped.infolist()) <= delivery.MAX_FILES, 'archive member count exceeded')
        for member in zipped.infolist():
            if member.is_dir():
                continue
            name = delivery.safe_name(member.filename)
            require(name not in modes, 'duplicate archive path in executable metadata')
            modes[name] = (member.external_attr >> 16) & 0o111
    return modes


def verify_inventory(archive: Path, expected: list[dict]) -> dict:
    inventory = delivery.archive_inventory(archive)
    containers = inventory['containers']
    top = [row for row in containers if row['path'] == archive.name]
    require(len(top) == 1, 'IPA must contain exactly one outer inventory')
    prefix = 'Payload/Tetherless.app/'
    modes = archive_executable_bits(archive)
    actual = []
    for row in top[0]['files']:
        require(row['path'].startswith(prefix), 'IPA contains payload outside the selected App')
        copied = dict(row, path=row['path'][len(prefix):])
        if row['type'] == 'file':
            copied['executableBits'] = modes[row['path']]
        actual.append(copied)
    require(sorted(actual, key=lambda row: row['path']) == expected,
            'IPA full App file/symlink inventory or executable bits differ from compiled App')
    # The generic inventory intentionally records other Info.plist files (including
    # storyboards). Only direct bundle-root metadata defines this canonical list.
    bundles = []
    for container in containers:
        for row in container['bundles']:
            root = PurePosixPath(row['path'])
            if (PurePosixPath(row['infoPath']).parent == root
                    and root.suffix in {'.app', '.appex', '.framework', '.bundle'}):
                bundles.append({'container': container['path'], **row})
    return {'inventory': inventory, 'bundles': bundles}


def publish_directory(source: Path, target: Path) -> None:
    """Atomic, exclusive directory admission; unsupported filesystems fail closed.

    macOS renamex_np(RENAME_EXCL) and Linux renameat2(RENAME_NOREPLACE) reject
    even a racing empty destination. Never fall back to overwriting rename().
    """
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        rename = libc.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        arguments = [os.fsencode(source), os.fsencode(target), 0x00000004]
    elif sys.platform.startswith('linux'):
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        arguments = [-100, os.fsencode(source), -100, os.fsencode(target), 1]
    else:
        raise ValueError('atomic exclusive directory admission is unsupported on this platform')
    rename.restype = ctypes.c_int
    if rename(*arguments) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(target))


def package_bound(configuration: str, env, *, repository: Path = ROOT) -> Path:
    require(configuration in ('Debug', 'Release'), 'unsupported diagnostic configuration')
    repository = directory(repository.absolute())
    consumer, producer = identities(env)
    require(all(env[key] == 'success' for key in ('COMPONENT_FIXTURES_RESULT', 'NATIVE_PROOFS_RESULT')),
            'authenticated producer groups must have succeeded')
    context = dict(consumer, needs=dict(NEEDS), producer_context=producer)
    hashes = {}
    for key in ('BINDING_RECEIPT_SHA256', 'HANDOFF_SHA256', 'APPLE_RECEIPT_SHA256'):
        value = env[key]
        require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value),
                'independent expected hash is missing or invalid: ' + key)
        hashes[key] = value
    work = directory(repository / '.pairing-consumer')
    prepared = directory(work / 'diagnostic')
    compile_root = directory(work / ('compile-' + configuration.lower()))
    evidence = directory(compile_root / 'evidence')
    derived = directory(compile_root / 'DerivedData')
    source_packages = directory(derived / 'SourcePackages')
    app = directory(derived / ('Build/Products/' + configuration + '-iphoneos/SideStore.app'))
    destination = work / 'packages' / configuration
    require(not destination.exists() and not destination.is_symlink(), 'package output already exists')
    contract_path = repository / 'Integration/pairing-ios-diagnostic/input-contract.json'
    contract = read_json(contract_path)
    binding_path = prepared / 'TETHERLESS_PAIRING_DIAGNOSTIC_BINDING.json'
    handoff_path = work / 'handoff/handoff.json'
    compile_path = evidence / 'diagnostic-compile-evidence.json'
    binding = read_json(binding_path, hashes['BINDING_RECEIPT_SHA256'])
    read_json(handoff_path, hashes['HANDOFF_SHA256'])
    compile_evidence = read_json(compile_path)
    require(type(binding.get('schema')) is int and binding['schema'] == 1
            and binding.get('diagnostic_root') == str(prepared)
            and binding.get('mode') == 'diagnostic-only'
            and binding.get('native_or_app_build_executed') is False,
            'binding is outside the diagnostic contract')
    require(binding.get('contract_sha256') == delivery.file_identity(contract_path)['sha256'],
            'binding input contract changed')
    for value in (binding, compile_evidence):
        require(value.get('runtime_capability_gates_changed') is False
                and value.get('consumer_or_product_activation') is False,
                'evidence is outside the closed capability contract')
    require(type(compile_evidence.get('schema')) is int and compile_evidence['schema'] == 1
            and compile_evidence.get('mode') == 'diagnostic-only'
            and compile_evidence.get('configuration') == configuration
            and compile_evidence.get('app_binary_executed') is False,
            'compile evidence configuration or diagnostic scope differs')
    require(compile_evidence.get('binding_receipt_sha256') == hashes['BINDING_RECEIPT_SHA256'],
            'compile binding receipt differs')
    native = binding['native_handoff']
    require(native.get('context') == context and native.get('producer_context') == producer
            and native.get('handoff_sha256') == hashes['HANDOFF_SHA256']
            and native.get('apple_receipt_sha256') == hashes['APPLE_RECEIPT_SHA256']
            and compile_evidence.get('native_handoff') == native,
            'consumer/producer context or compile native handoff differs')
    audits = compile_evidence.get('input_audits', {})
    require(set(audits) == set(AUDITS), 'all three compile input audits are required')
    for name in AUDITS:
        require(isinstance(audits[name], dict) and audits[name].get('original_inputs_unchanged') is True
                and read_json(evidence / name) == audits[name], 'compile input audit differs: ' + name)
    observations = compile_evidence['observations']
    require(observations.get('configuration') == configuration
            and observations.get('ios_binaries_executed') is False
            and observations.get('consumer_or_product_activation') is False,
            'compiler observation configuration or scope differs')
    link = observations['link']
    info = packager.validate_app(app)
    executable = app / info['CFBundleExecutable']
    require(link.get('output') == str(executable), 'App executable path differs from compile link observation')
    executable_identity = delivery.file_identity(executable)
    require(type(link.get('output_size')) is int and link['output_size'] > 0
            and executable_identity == {'size': link['output_size'], 'sha256': link.get('output_sha256')},
            'App executable size/hash differs from compile link observation')
    link_map = evidence / 'link-maps/SideStore-arm64.map'
    directory(link_map.parent)
    require(delivery.file_identity(link_map)['sha256'] == compile_evidence['link_map_sha256'],
            'compile link map changed')
    recipe = repository / 'Integration/Dependencies/idevice'
    artifact = directory(work / 'handoff/apple-producer/apple-producer-output')
    def validate_inputs():
        require(verify_handoff(contract, handoff_path, hashes['HANDOFF_SHA256'], context,
                               artifact, hashes['APPLE_RECEIPT_SHA256'], recipe) == native,
                'authenticated native handoff changed')
        require(audit_bound_inputs(binding, contract)['original_inputs_unchanged'] is True,
                'current bound inputs changed')
        require(prepare.verify_recipe_inputs(recipe, contract) == binding['native_recipe']
                and prepare.artifact_inputs(artifact, hashes['APPLE_RECEIPT_SHA256'], contract) == binding['native_artifact'],
                'current native recipe or artifact changed')
    validate_inputs()
    original = app_inventory(app)
    retained = {'binding-receipt.json': binding_path, 'native-handoff.json': handoff_path,
                'diagnostic-compile-evidence.json': compile_path, 'input-contract.json': contract_path,
                'SideStore-arm64.map': link_map, **{name: evidence / name for name in AUDITS}}
    retained_identity = {name: delivery.file_identity(path) for name, path in retained.items()}
    destination.parent.mkdir(exist_ok=True)
    directory(destination.parent)
    with tempfile.TemporaryDirectory(prefix='.bound-package-', dir=destination.parent) as temporary:
        staged = Path(temporary) / 'candidate'
        ipa = packager.package(app, staged, consumer['source_commit'], configuration,
                               repository=repository, prepared=prepared, source_packages=source_packages)
        generic_identity = {path.name: delivery.file_identity_large(path)
                            for path in sorted(staged.iterdir()) if path.name != 'SHA256SUMS'}
        expected_checksums = ''.join(f"{row['sha256']}  {name}\n" for name, row in generic_identity.items())
        require(delivery.metadata_bytes(staged / 'SHA256SUMS').decode('utf-8') == expected_checksums,
                'generic package checksums are incomplete or changed')
        checked = verify_inventory(ipa, original)
        require(checked['inventory']['artifact'] == {'path': ipa.name, **generic_identity[ipa.name]},
                'IPA changed during full inventory verification')
        require(read_json(staged / 'ipa-inventory.json') == checked['inventory'], 'retained IPA inventory changed')
        manifest = read_json(staged / 'manifest.json')
        require(manifest.get('sourceCommit') == consumer['source_commit']
                and manifest.get('configuration') == configuration
                and manifest.get('deviceValidated') is False and manifest.get('releaseReady') is False
                and manifest.get('ipa') == checked['inventory']['artifact'],
                'generic manifest context or IPA identity differs')
        for name, source in retained.items():
            identity = retained_identity[name]
            try:
                with delivery.open_regular(source) as stream, (staged / name).open('xb') as target:
                    digest = delivery.digest_stream(stream, identity['size'], target)
            except ValueError as error:
                raise ValueError('retained evidence changed: ' + name) from error
            require(digest == identity['sha256'], 'retained evidence changed: ' + name)
        delivery.write_json(staged / 'compiled-app-inventory.json', {'schema': 1,
            'compiledApp': str(app), 'archiveRoot': 'Payload/Tetherless.app', 'files': original})
        inputs = read_json(staged / 'inputs.json')
        declarations = [{key: row[key] for key in ('path', 'type', 'size', 'sha256')}
                        for row in inputs['files'] if row['type'] == 'file'
                        and PurePosixPath(row['path']).suffix in ('.entitlements', '.xcent')]
        binding_receipt = {'schema': 1, 'mode': 'diagnostic-only', 'configuration': configuration,
            'consumer': consumer, 'producer': producer, 'native_handoff': native,
            'evidence': retained_identity, 'compile_link_observation': link,
            'compiledApp': {'path': str(app), 'executable': info['CFBundleExecutable'], **executable_identity},
            'compiledAppInventory': delivery.file_identity(staged / 'compiled-app-inventory.json'),
            'ipa': checked['inventory']['artifact'],
            'genericManifest': delivery.file_identity(staged / 'manifest.json'),
            'canonicalBundles': checked['bundles'],
            'entitlementDeclarations': {'effectiveSigningRightsEstablished': False, 'files': declarations,
                'inventorySource': 'inputs.json:files', 'generatedDerivedDataXcent': 'not-collected',
                'scope': 'Source/build-input declarations only; no effective signing entitlements are asserted.'},
            'unsigned': True, 'deviceValidated': False, 'releaseReady': False,
            'runtime_capability_gates_changed': False, 'app_binary_executed': False,
            'notice': 'One configuration only. Both Debug and Release must pass; packaging is not native/device acceptance.'}
        delivery.write_json(staged / 'package-binding.json', binding_receipt)
        # Recheck the live app and every source receipt after packaging; no executable fallback.
        require(app_inventory(app) == original, 'compiled App changed during packaging')
        validate_inputs()
        require({name: delivery.file_identity(path) for name, path in retained.items()} == retained_identity,
                'compile/binding evidence changed during packaging')
        (staged / 'SHA256SUMS').write_text(''.join(
            f"{delivery.file_identity_large(path)['sha256']}  {path.name}\n"
            for path in sorted(staged.iterdir()) if path.name != 'SHA256SUMS'), encoding='utf-8')
        require({name: delivery.file_identity_large(staged / name) for name in generic_identity} == generic_identity,
                'generic package changed before final publication')
        directory(destination.parent)
        publish_directory(staged, destination)
    return destination / 'Tetherless-unsigned.ipa'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration', required=True, choices=('Debug', 'Release'))
    args = parser.parse_args()
    try:
        archive = package_bound(args.configuration, os.environ)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.exit(1, str(error) + '\n')
    print(archive)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
