#!/usr/bin/env python3
"""Bounded, read-only delivery evidence. This is not an SBOM or attestation.

Never runs dependency code, interprets Mach-O/certificates, or accesses credentials.
Only the selected source trees, existing build inputs and final IPA are inspected.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import selectors
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import urlsplit
import zipfile

MAX_FILES = 150_000
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 6 * 1024 * 1024 * 1024
MAX_DEPTH = 64
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_NESTED_IPA_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_READ = 32 * 1024 * 1024
MAX_GIT_BYTES = 32 * 1024 * 1024
EXCLUDED = {'.git', '.build', '.swiftpm', '__pycache__', 'DerivedData', 'xcuserdata',
            '.DS_Store', '.env', '.aws', '.ssh', '.gnupg', 'node_modules', '.cache',
            '.generated', 'artifacts', 'build', 'native-build.log'}
SECRET_SUFFIXES = {'.p12', '.p8', '.key', '.mobileprovision', '.mobiledevicepairing', '.pem'}
GATES = {
    'corresponding-source': 'Available inputs are preserved; complete corresponding source, producer source and LGPL relinking materials are not established.',
    'linked-components-and-notices': 'Lock membership and file inventory do not establish the linked Rust/C graph or complete notices and attribution.',
    'binary-provenance': 'Publisher hashes and observed bytes are not independent rebuilds or verified build attestations.',
    'unicorn-license-basis': 'The grant for the exact combined Unicorn/AGPLv3 binary remains unresolved.',
    'adi-authenticity-and-use-basis': 'Independent authentication, admissible input and acquisition/use basis remain unresolved; no ADI rights clearance is implied.',
    'native-and-device-acceptance': 'Packaging does not validate device install, launch, physical renewal or unattended renewal.',
    'durable-delivery': 'CI retention is temporary; no durable release/source hosting or stable release is established.',
}


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode()


def write_json(path: Path, value: object) -> None:
    path.write_bytes(canonical(value))


def safe_name(name: str) -> str:
    if not name or '\\' in name or '\x00' in name or name.startswith('/'):
        raise ValueError('Unsafe relative input path')
    parts = name.rstrip('/').split('/')
    if len(parts) > MAX_DEPTH or any(p in ('', '.', '..') or any(ord(c) < 32 for c in p) for p in parts):
        raise ValueError('Unsafe relative input path')
    return '/'.join(parts)


def safe_link(name: str, target: str) -> None:
    if not target or target.startswith('/') or '\\' in target or any(ord(c) < 32 for c in target):
        raise ValueError('Unsafe link target')
    stack = list(PurePosixPath(name).parent.parts)
    for part in target.split('/'):
        if part == '..':
            if not stack:
                raise ValueError('Link escapes its input root')
            stack.pop()
        elif part not in ('', '.'):
            stack.append(part)


class Budget:
    def __init__(self):
        self.files = 0
        self.bytes = 0

    def add(self, size: int) -> None:
        self.files += 1
        self.bytes += size
        if size < 0 or size > MAX_FILE_BYTES or self.files > MAX_FILES or self.bytes > MAX_TOTAL_BYTES:
            raise ValueError('Delivery inventory exceeds its size/count budget')


def digest_stream(stream, size: int, sink=None) -> str:
    digest = hashlib.sha256()
    count = 0
    while chunk := stream.read(1024 * 1024):
        count += len(chunk)
        if count > size:
            raise ValueError('Input grew or archive size differs from metadata')
        digest.update(chunk)
        if sink is not None:
            sink.write(chunk)
    if count != size:
        raise ValueError('Input was truncated or changed while reading')
    return digest.hexdigest()


def open_regular(path: Path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    result = os.fdopen(fd, 'rb')
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        result.close()
        raise ValueError('Expected a regular input file')
    return result


def file_identity(path: Path) -> dict:
    with open_regular(path) as stream:
        before = os.fstat(stream.fileno())
        if before.st_size > MAX_FILE_BYTES:
            raise ValueError('Input exceeds per-file budget')
        digest = digest_stream(stream, before.st_size)
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Input changed while hashing')
    return {'size': before.st_size, 'sha256': digest}


def metadata_bytes(path: Path) -> bytes:
    with open_regular(path) as stream:
        data = stream.read(MAX_METADATA_BYTES + 1)
    if len(data) > MAX_METADATA_BYTES:
        raise ValueError('Metadata exceeds size budget')
    return data


def private_path(name: str) -> bool:
    p = PurePosixPath(name)
    return (any(part in {'.git', '.aws', '.ssh', '.gnupg', '.env'} or part.startswith('.env.') for part in p.parts)
            or p.suffix.lower() in SECRET_SUFFIXES - {'.pem'})


def is_excluded(name: str) -> bool:
    p = PurePosixPath(name)
    return (any(part in EXCLUDED or part.startswith('.env.') for part in p.parts)
            or p.suffix.lower() in SECRET_SUFFIXES or p.name == 'CodeSigning.xcconfig')


def bounded_output(command: list[str], limit: int, timeout: float = 30) -> bytes:
    """Cap subprocess stdout while it runs, and reap it on overflow or timeout."""
    chunks, total = [], 0
    deadline = time.monotonic() + timeout
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            try:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise subprocess.TimeoutExpired(command, timeout)
                    chunk = os.read(process.stdout.fileno(), min(64 * 1024, limit + 1 - total))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit:
                        raise ValueError('Git metadata exceeds size budget')
                    chunks.append(chunk)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                status = process.wait(timeout=remaining)
                if status:
                    raise subprocess.CalledProcessError(status, command)
            except BaseException:
                process.kill()
                process.wait()
                raise
    return b''.join(chunks)


def git(root: Path, *args: str) -> bytes:
    # No shell, hooks, dependency scripts, network or credential configuration reads.
    return bounded_output(['git', '-c', 'core.fsmonitor=false', '-C', str(root), *args], MAX_GIT_BYTES)


def revision(root: Path) -> str:
    result = git(root, 'rev-parse', '--verify', 'HEAD').decode().strip()
    if not re.fullmatch('[0-9a-f]{40}', result):
        raise ValueError('Expected a complete Git revision')
    return result


def collect_git(root: Path, label: str, sources: list, repositories: list, omissions: list,
                budget: Budget, expected: str | None = None, depth: int = 0) -> None:
    if depth > 8 or root.is_symlink() or not root.is_dir():
        raise ValueError('Unsafe or excessive source repository nesting')
    head = revision(root)
    if expected is not None and head != expected:
        raise ValueError('Source checkout does not match the requested commit/gitlink')
    repositories.append({'path': label, 'revision': head, 'expectedRevision': expected})
    records = git(root, 'ls-tree', '-r', '-z', '--full-tree', head).split(b'\0')
    for record in sorted(r for r in records if r):
        fields, raw_name = record.split(b'\t', 1)
        mode, kind, oid = fields.decode().split()
        if (mode == '160000' and kind != 'commit') or (mode != '160000' and kind != 'blob'):
            raise ValueError('Unexpected source tree entry')
        name = safe_name(raw_name.decode('utf-8'))
        if is_excluded(name):
            budget.add(0)
            omissions.append({'path': f'{label}/{name}', 'reason': 'private-or-generated-path-policy'})
            continue
        path = root / name
        # No symlink directory traversal, including gitlink ancestors.
        for parent in path.relative_to(root).parents:
            if (root / parent).is_symlink():
                raise ValueError('Source path traverses a symlink directory')
        if mode == '160000':
            budget.add(0)
            collect_git(path, f'{label}/{name}', sources, repositories, omissions, budget, oid, depth + 1)
            continue
        entry = collect_file(root, name, label, budget)
        entry['gitBlob'] = oid
        entry['gitMode'] = mode
        # Preserve actual working bytes and distinguish them from the committed tree,
        # regardless of staged changes to file content, mode or gitlinks.
        if entry['type'] == 'file':
            actual = git(root, 'hash-object', '--no-filters', '--', name).decode().strip()
        else:
            data = entry['target'].encode()
            actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        entry['matchesGitBlob'] = actual == oid
        if not entry['matchesGitBlob']:
            omissions.append({'path': entry['path'], 'reason': 'working-bytes-differ-from-commit'})
        observed_mode = '120000' if entry['type'] == 'symlink' else ('100755' if entry['executable'] else '100644')
        entry['matchesGitMode'] = observed_mode == mode
        if not entry['matchesGitMode']:
            omissions.append({'path': entry['path'], 'reason': 'working-mode-differs-from-commit'})
        sources.append(entry)


def collect_file(root: Path, name: str, label: str, budget: Budget) -> dict:
    path = root / name
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        target = os.readlink(path)
        safe_link(name, target)
        if not path.resolve(strict=True).is_relative_to(root.resolve()):
            raise ValueError('Source link escapes its input root')
        budget.add(len(target.encode()))
        return {'path': f'{label}/{name}', 'type': 'symlink', 'target': target,
                'sha256': hashlib.sha256(target.encode()).hexdigest(), 'size': len(target.encode()),
                'origin': label, '_local': path}
    if not stat.S_ISREG(mode):
        raise ValueError('Special files are not delivery inputs')
    identity = file_identity(path)
    budget.add(identity['size'])
    return {'path': f'{label}/{name}', 'type': 'file', **identity,
            'executable': bool(mode & 0o111), 'origin': label, '_local': path}


def bounded_children(directory: Path) -> list[Path]:
    children = []
    for path in directory.iterdir():
        children.append(path)
        if len(children) > MAX_FILES:
            raise ValueError('Directory entry count exceeded')
    return sorted(children)


def collect_tree(root: Path, label: str, entries: list, omissions: list, budget: Budget) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Input tree must be an existing regular directory')
    def visit(directory: Path, depth: int = 0):
        if depth > MAX_DEPTH:
            raise ValueError('Input tree exceeds depth budget')
        for path in bounded_children(directory):
            name = safe_name(path.relative_to(root).as_posix())
            if is_excluded(name):
                budget.add(0)
                # The generated config is an exact known build input only if it is the sample.
                if name == 'CodeSigning.xcconfig' and not path.is_symlink():
                    sample = root / 'CodeSigning.xcconfig.sample'
                    if sample.is_file() and not sample.is_symlink() and file_identity(path) == file_identity(sample):
                        entries.append(collect_file(root, name, label, budget))
                        continue
                omissions.append({'path': f'{label}/{name}', 'reason': 'private-or-generated-path-policy'})
                continue
            if path.is_dir() and not path.is_symlink():
                budget.add(0)
                visit(path, depth + 1)
            else:
                entries.append(collect_file(root, name, label, budget))
    visit(root)


def public_entry(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if not k.startswith('_')}


def write_tar(path: Path, entries: list) -> dict:
    """Stable order, owner/mode/mtime and gzip header; verify every archived byte."""
    with path.open('xb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|', format=tarfile.PAX_FORMAT) as archive:
            for entry in sorted(entries, key=lambda e: e['path']):
                info = tarfile.TarInfo(entry['path'])
                info.mtime = info.uid = info.gid = 0
                info.uname = info.gname = ''
                if entry['type'] == 'symlink':
                    if os.readlink(entry['_local']) != entry['target']:
                        raise ValueError('Link changed before archiving')
                    info.type = tarfile.SYMTYPE
                    info.mode = 0o777
                    info.linkname = entry['target']
                    archive.addfile(info)
                else:
                    info.size = entry['size']
                    info.mode = 0o755 if entry.get('executable') else 0o644
                    with open_regular(entry['_local']) as source:
                        class HashingReader:
                            def __init__(self):
                                self.digest = hashlib.sha256()
                            def read(self, size):
                                data = source.read(size)
                                self.digest.update(data)
                                return data
                        reader = HashingReader()
                        archive.addfile(info, reader)
                        if reader.digest.hexdigest() != entry['sha256']:
                            raise ValueError('Archived bytes do not match input inventory')
                    if file_identity(entry['_local']) != {'size': entry['size'], 'sha256': entry['sha256']}:
                        raise ValueError('Input changed while archiving')
    return {'path': path.name, **file_identity_large(path)}


def file_identity_large(path: Path) -> dict:
    with open_regular(path) as source:
        size = os.fstat(source.fileno()).st_size
        if size > MAX_TOTAL_BYTES:
            raise ValueError('Artifact exceeds total size budget')
        return {'size': size, 'sha256': digest_stream(source, size)}


def public_location(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return None
    return value


def dependency_metadata(entries: list, repositories: list) -> dict:
    locks = []
    for entry in entries:
        if entry['type'] != 'file' or PurePosixPath(entry['path']).name not in ('Package.resolved', 'Cargo.lock'):
            continue
        record = {'path': entry['path'], 'sha256': entry['sha256']}
        if entry['path'].endswith('Package.resolved'):
            payload = json.loads(metadata_bytes(entry['_local']))
            pins = payload.get('pins', payload.get('object', {}).get('pins', []))
            if not isinstance(pins, list) or len(pins) > 2000:
                raise ValueError('Unexpected Swift lock format')
            record['pins'] = []
            for pin in pins:
                state = pin.get('state', {})
                observed = [repo['path'] for repo in repositories if repo['revision'] == state.get('revision')]
                record['pins'].append({'identity': pin.get('identity', pin.get('package')),
                    'observedCheckoutPaths': observed,
                    'revisionObservation': 'observed' if observed else 'not-observed',
                    'location': public_location(pin.get('location', pin.get('repositoryURL'))),
                    'state': {k: state[k] for k in ('revision', 'version', 'branch') if k in state}})
        else:
            record['scope'] = 'Lock bytes retained; membership does not prove linkage'
        locks.append(record)
    return {'repositories': repositories, 'lockfiles': locks,
            'scope': 'Observed Git and lock metadata; binary producers and linked dependency closure remain incomplete'}


def toolchain() -> dict:
    # Fixed official tool invocations only. Select version tokens, never hostnames/env/full paths.
    commands = {
        'xcode': (['xcodebuild', '-version'], r'(?:Xcode|Build version) [A-Za-z0-9.]+'),
        'swift': (['xcrun', 'swift', '--version'], r'(?:Apple )?Swift version [A-Za-z0-9.+-]+(?: \([A-Za-z0-9 .+-]+\))?'),
        'clang': (['xcrun', 'clang', '--version'], r'Apple clang version [A-Za-z0-9.+-]+(?: \([A-Za-z0-9 .+-]+\))?'),
        'iphoneosSDK': (['xcrun', '--sdk', 'iphoneos', '--show-sdk-version'], r'^\d+(?:\.\d+)*$'),
        'iphoneosSDKBuild': (['xcrun', '--sdk', 'iphoneos', '--show-sdk-build-version'], r'^[A-Za-z0-9.]+$'),
        'macOS': (['sw_vers', '-productVersion'], r'^\d+(?:\.\d+)*$'),
        'macOSBuild': (['sw_vers', '-buildVersion'], r'^[A-Za-z0-9.]+$'),
        'git': (['git', '--version'], r'git version [A-Za-z0-9.+-]+'),
    }
    result = {'python': {'status': 'observed', 'versions': [sys.version.split()[0]]}}
    for name, (command, pattern) in commands.items():
        try:
            run = subprocess.run(command, check=True, capture_output=True, text=True, timeout=20)
            versions = re.findall(pattern, run.stdout.strip(), re.MULTILINE)
            result[name] = {'status': 'observed' if versions else 'unavailable', 'versions': versions}
        except (OSError, subprocess.SubprocessError):
            result[name] = {'status': 'unavailable', 'versions': []}
    return result


def archive_inventory(path: Path) -> dict:
    """Inventory ZIP bytes without extracting or executing any payload."""
    budget = Budget()
    containers = []
    class BoundedZipReader:
        # zipfile reads its central directory in one call. Cap that allocation too,
        # before infolist() can allocate records for an attacker-controlled count.
        def __init__(self, stream):
            self.stream = stream
        def read(self, size=-1):
            if size > MAX_ARCHIVE_READ:
                raise ValueError('ZIP metadata read exceeds budget')
            data = self.stream.read(MAX_ARCHIVE_READ + 1 if size < 0 else size)
            if len(data) > MAX_ARCHIVE_READ:
                raise ValueError('ZIP metadata read exceeds budget')
            return data
        def seek(self, *args):
            return self.stream.seek(*args)
        def tell(self):
            return self.stream.tell()
        def seekable(self):
            return self.stream.seekable()
    def inspect(stream, container: str, depth: int = 0):
        if depth > 3:
            raise ValueError('Nested IPA depth exceeded')
        with zipfile.ZipFile(BoundedZipReader(stream)) as archive:
            members = archive.infolist()
            if len(members) > MAX_FILES:
                raise ValueError('Archive member count exceeded')
            files, bundles, nested, names = [], [], [], set()
            for member in sorted(members, key=lambda m: m.filename):
                name = safe_name(member.filename)
                if private_path(name):
                    raise ValueError('Private/signing material must not enter the unsigned archive')
                if name in names:
                    raise ValueError('Duplicate archive path')
                names.add(name)
                budget.add(member.file_size)
                if member.flag_bits & 1:
                    raise ValueError('Encrypted archive member is not inspectable')
                if member.is_dir():
                    continue
                mode = member.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if kind not in (0, stat.S_IFREG, stat.S_IFLNK):
                    raise ValueError('Unsupported archive entry type')
                is_link = kind == stat.S_IFLNK
                capture = name.lower().endswith('.ipa') or PurePosixPath(name).name == 'Info.plist' or is_link or name.lower().endswith('.pem')
                limit = MAX_NESTED_IPA_BYTES if name.lower().endswith('.ipa') else MAX_METADATA_BYTES
                if capture and member.file_size > limit:
                    raise ValueError('Nested archive or metadata exceeds budget')
                buffer = io.BytesIO() if capture else None
                with archive.open(member) as source:
                    digest = digest_stream(source, member.file_size, buffer)
                record = {'path': name, 'type': 'symlink' if is_link else 'file',
                          'size': member.file_size, 'sha256': digest}
                data = buffer.getvalue() if buffer is not None else None
                if name.lower().endswith('.pem') and data is not None and b'PRIVATE KEY' in data:
                    raise ValueError('Private key must not enter the unsigned archive')
                if is_link:
                    target = data.decode('utf-8')
                    safe_link(name, target)
                    record['target'] = target
                elif name.lower().endswith('.ipa'):
                    child = f'{container}!/{name}'
                    nested.append({'path': name, 'container': child, 'sha256': digest})
                    inspect(io.BytesIO(data), child, depth + 1)
                elif PurePosixPath(name).name == 'Info.plist':
                    try:
                        info = plistlib.loads(data)
                    except (ValueError, plistlib.InvalidFileException):
                        info = None
                    if isinstance(info, dict):
                        suffixes = {'.app', '.appex', '.framework', '.bundle'}
                        roots = [p for p in PurePosixPath(name).parents if p.suffix in suffixes]
                        if roots:
                            bundle = roots[0]
                            bundles.append({'path': str(bundle), 'infoPath': name,
                                'bundleIdentifier': info.get('CFBundleIdentifier'),
                                'executable': info.get('CFBundleExecutable'),
                                'version': info.get('CFBundleShortVersionString'), 'build': info.get('CFBundleVersion'),
                                'type': bundle.suffix[1:]})
                files.append(record)
            containers.append({'path': container, 'files': files, 'bundles': bundles, 'nestedIPAs': nested})
    with open_regular(path) as stream:
        inspect(stream, path.name)
    return {'schemaVersion': 1, 'artifact': {'path': path.name, **file_identity_large(path)},
            'containers': sorted(containers, key=lambda c: c['path']),
            'scope': 'Byte and plist inventory only; no linked-symbol, signing, entitlements, vulnerability or provenance verification'}


def notice_entry(entry: dict) -> bool:
    name = PurePosixPath(entry['path']).name.lower()
    return ('/docs/supply-chain/' in entry['path'] or name.startswith(('license', 'licence', 'copying', 'notice', 'authors', 'copyright'))
            or name in ('readme', 'readme.md', 'readme.txt'))



def prior_review(repository: Path) -> dict:
    root = repository / 'docs/supply-chain'
    if not root.is_dir():
        return {'status': 'unavailable'}
    if root.is_symlink():
        raise ValueError('Prior review root must not be a symlink')
    hashes = json.loads(metadata_bytes(root / 'review-file-hashes.json'))
    if not isinstance(hashes, dict) or len(hashes) > 2000:
        raise ValueError('Unexpected prior review hash manifest')
    for name, expected in hashes.items():
        path = root / safe_name(name)
        if any(parent.is_symlink() for parent in [path, *path.parents] if parent.is_relative_to(root)):
            raise ValueError('Prior review path must not traverse a symlink')
        if file_identity(path)['sha256'] != expected:
            raise ValueError('Prior review copy differs from its recorded hash')
    inventory = json.loads(metadata_bytes(root / 'inventory.json'))
    return {'status': 'hash-consistent-prior-review', 'baseline': inventory.get('baseline'),
            'manifestPath': 'repository/docs/supply-chain/review-file-hashes.json',
            'sha256': file_identity(root / 'review-file-hashes.json')['sha256'],
            'scope': 'Historical review at its own baseline; not final artifact provenance or license clearance'}


def snapshot_prepared(root: Path, output: Path, commit: str) -> None:
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('A complete source commit is required')
    sidecar = output.with_name(output.name + '.json')
    if any(path.exists() or path.is_symlink() for path in (output, sidecar)):
        raise ValueError('Snapshot archive or manifest already exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.is_symlink():
        raise ValueError('Snapshot output parent must not be a symlink')
    entries, omissions = [], []
    collect_tree(root, 'prepared', entries, omissions, Budget())
    with tempfile.TemporaryDirectory(prefix='.tetherless-snapshot-', dir=output.parent) as temporary:
        staged = Path(temporary)
        staged_archive, staged_sidecar = staged / output.name, staged / sidecar.name
        identity = write_tar(staged_archive, entries)
        write_json(staged_sidecar, {
            'sourceCommit': commit, 'status': 'candidate-incomplete', 'archive': identity,
            'files': [public_entry(e) for e in sorted(entries, key=lambda e: e['path'])],
            'omissions': omissions, 'scope': 'Prepared bytes before compilation, all file extensions; not complete corresponding source'})
        published = []
        try:
            # Exclusive hard-link publication never overwrites a target created
            # after the initial check. Both complete files exist before publication.
            for source, target in ((staged_archive, output), (staged_sidecar, sidecar)):
                os.link(source, target)
                published.append((source, target))
        except BaseException:
            for source, target in reversed(published):
                if target.exists() and not target.is_symlink() and os.path.samestat(source.stat(), target.stat()):
                    target.unlink()
            raise


def create_evidence(output: Path, ipa: Path, repository: Path, prepared: Path,
                    source_packages: Path, commit: str) -> dict:
    entries, repositories, omissions, missing = [], [], [], []
    budget = Budget()
    collect_git(repository, 'repository', entries, repositories, omissions, budget, commit)
    collect_tree(prepared, 'prepared', entries, omissions, budget)
    checkouts = source_packages / 'checkouts'
    if checkouts.is_symlink():
        raise ValueError('Package checkout root must not be a symlink')
    if checkouts.is_dir():
        for checkout in bounded_children(checkouts):
            if checkout.is_symlink() or not checkout.is_dir():
                raise ValueError('Unexpected package checkout entry')
            collect_git(checkout, f'swift-packages/{safe_name(checkout.name)}', entries, repositories, omissions, budget)
    else:
        missing.append('Swift package checkout source is unavailable')
    # Preserve exact manifests/resources/build scripts of all file extensions. Binary input
    # bytes are hashed separately; absent producer source is never substituted by binaries.
    binary_inputs = []
    artifacts = source_packages / 'artifacts'
    if artifacts.is_dir():
        collect_tree(artifacts, 'binary-inputs', binary_inputs, omissions, budget)
    else:
        missing.append('Resolved binary artifact inputs are unavailable')
    for entry in binary_inputs:
        entry['includedInSourceBundle'] = False
    source_manifest = {
        'schemaVersion': 1, 'sourceCommit': commit, 'status': 'candidate-incomplete',
        'files': [public_entry(e) for e in sorted(entries, key=lambda e: e['path'])],
        'binaryInputs': [public_entry(e) for e in sorted(binary_inputs, key=lambda e: e['path'])],
        'dependencies': dependency_metadata(entries, repositories),
        'repositoryBytesMatchRecordedBlobs': all(e.get('matchesGitBlob', True) for e in entries),
        'repositoryMatchesRecordedTree': all(e.get('matchesGitBlob', True) and e.get('matchesGitMode', True) for e in entries),
        'priorReview': prior_review(repository),
        'omissions': sorted(omissions, key=lambda e: e['path']), 'missingEvidence': missing,
        'scope': 'Available tracked repository/submodule/package bytes and prepared tree. Not complete corresponding source. Binary inputs are inventoried, not redistributed.'}
    write_json(output / 'inputs.json', source_manifest)
    write_json(output / 'toolchain.json', toolchain())
    write_json(output / 'ipa-inventory.json', archive_inventory(ipa))
    source_bundle = write_tar(output / 'available-source.tar.gz', entries)
    notices = [entry for entry in entries if notice_entry(entry)]
    notice_bundle = write_tar(output / 'available-notices.tar.gz', notices)
    write_json(output / 'notices.json', {'status': 'candidate-incomplete',
        'files': [public_entry(e) for e in sorted(notices, key=lambda e: e['path'])],
        'scope': 'Available license, notice, attribution and README texts plus prior review. No clearance or completeness assertion.'})
    artifacts = [source_bundle, notice_bundle]
    for name in ('inputs.json', 'toolchain.json', 'ipa-inventory.json', 'notices.json'):
        artifacts.append({'path': name, **file_identity_large(output / name)})
    return {'schemaVersion': 2, 'candidateStatus': 'candidate-incomplete',
            'releaseReady': False, 'artifacts': artifacts,
            'releaseGates': [{'id': key, 'status': 'unresolved', 'reason': value} for key, value in GATES.items()],
            'evidenceClaim': 'Unsigned candidate byte inventory, not an SBOM, signed provenance, license clearance or release authorization'}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Preserve prepared review inputs before native compilation')
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    snapshot_prepared(args.prepared, args.output, args.commit)
