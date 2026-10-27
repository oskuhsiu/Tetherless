#!/usr/bin/env python3
"""Read-only packaged IDevice API evidence; never a build or pairing verdict."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import selectors
import signal
import subprocess
import time

FUNCTIONS = ('pairable_host_accept', 'pairable_host_cancel_new',
             'pairable_host_cancel_signal', 'pairable_host_cancel_free')
OPTIONAL_FUNCTIONS = ('pairable_host_accept_with_options',)
ALL_FUNCTIONS = FUNCTIONS + OPTIONAL_FUNCTIONS
EXPECTED_ARCHIVE_SHA256 = '445702d53942597deb4cdec2c4122d16a3f4ac124ce26cd75b68dab3dad92416'
EXPECTED_SOURCE = '3e55c8486b2057e40c1f74aaaa1155c82341cf76'
MAX_ENTRIES = 20000
MAX_HEADER_BYTES = 8 * 1024 * 1024
MAX_TOOL_BYTES = 16 * 1024 * 1024
TOOL_TIMEOUT_SECONDS = 60


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def checked(root, relative):
    """Never follow a package-provided symlink or escape the selected artifact."""
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(x in ('..', '.') for x in path.parts):
        raise ValueError('unsafe package path')
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('package symlink is not inspected')
    if not current.resolve().is_relative_to(root.resolve()):
        raise ValueError('package path escapes artifact')
    return current


def files_under(root):
    pending, count = [root], 0
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                count += 1
                if count > MAX_ENTRIES:
                    raise ValueError('artifact discovery entry limit exceeded')
                if entry.is_symlink():
                    raise ValueError('artifact discovery encountered a symlink')
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    yield Path(entry.path)


def find_frameworks(root):
    # Other package artifacts may contain macOS framework symlinks. Do not
    # traverse unrelated XCFramework bundles just to locate the IDevice target.
    pending, count, found = [root], 0, []
    while pending:
        directory = pending.pop()
        if directory.suffix.lower() == '.xcframework':
            if directory.name.lower() == 'idevice.xcframework':
                found.append(directory)
            continue
        with os.scandir(directory) as entries:
            for entry in entries:
                count += 1
                if count > MAX_ENTRIES:
                    raise ValueError('artifact discovery entry limit exceeded')
                if entry.is_symlink():
                    raise ValueError('artifact discovery encountered a symlink')
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
    return sorted(found)


def declarations(text):
    # Textual declarations only, not a C preprocessor or compile/link test.
    # Mask comments, strings and directives before looking for function syntax.
    def mask(match):
        return ''.join('\n' if char == '\n' else ' ' for char in match.group())
    clean = re.sub(r'"(?:\\.|[^"\\])*"|/\*[\s\S]*?\*/|//[^\n]*', mask, text)
    clean = re.sub(r'^\s*#(?:[^\n]*\\\n)*[^\n]*', mask, clean, flags=re.M)
    found = {name: [] for name in ALL_FUNCTIONS}
    for name in ALL_FUNCTIONS:
        for match in re.finditer(r'\b' + re.escape(name) + r'\s*\(', clean):
            start = max(clean.rfind(';', 0, match.start()), clean.rfind('{', 0, match.start()),
                        clean.rfind('}', 0, match.start())) + 1
            prefix = clean[start:match.start()].strip()
            if not prefix or len(prefix) > 512 or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_\s*]*', prefix):
                continue
            if re.search(r'\b(return|typedef|if|while|for|sizeof)\b', prefix):
                continue
            end = clean.find(';', match.end())
            if end < 0 or end - match.start() > 16384:
                continue
            declaration = clean[start:end + 1].strip()
            if '{' in declaration or '}' in declaration or not re.search(r'\)\s*;$', declaration):
                continue
            found[name].append({'line': clean.count('\n', 0, match.start()) + 1,
                                'declaration': re.sub(r'\s+', ' ', declaration)})
    return found


def defined_exports(text):
    """Parse nm -P records, accepting only exact global defined C symbols."""
    found = set()
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        symbol, kind = fields[0], fields[1]
        if symbol.startswith('_'):
            symbol = symbol[1:]
        # -g -U requests external defined symbols; independently reject U and
        # unknown/local types rather than treating any name occurrence as proof.
        if symbol in ALL_FUNCTIONS and kind == 'T':
            found.add(symbol)
    return found


def run_tool(command):
    # Drain both pipes while the tool runs. Each in-memory buffer is capped;
    # there is no unbounded temporary output file waiting for process exit.
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   stdin=subprocess.DEVNULL, start_new_session=True)
    except OSError as error:
        return {'returncode': None, 'stdout': '', 'stderr': type(error).__name__, 'status': 'unavailable'}
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    deadline = time.monotonic() + TOOL_TIMEOUT_SECONDS
    status, diagnostic = None, ''

    def terminate_group():
        # Kill the group even if its leader exited: a child may still own a pipe.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    try:
        with selectors.DefaultSelector() as selector:
            for name, stream in [('stdout', process.stdout), ('stderr', process.stderr)]:
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map() and status is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    status = 'timeout'
                    break
                for key, _ in selector.select(remaining):
                    buffer = buffers[key.data]
                    try:
                        block = os.read(key.fd, min(65536, MAX_TOOL_BYTES - len(buffer)))
                    except BlockingIOError:
                        continue
                    if not block:
                        selector.unregister(key.fileobj)
                        continue
                    buffer.extend(block)
                    if len(buffer) >= MAX_TOOL_BYTES:
                        status = 'truncated'
                        break
        if status is None:
            try:
                process.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                status = 'timeout'
        if status is not None:
            terminate_group()
        process.wait()
    except (OSError, ValueError) as error:
        status, diagnostic = 'failed', type(error).__name__
        terminate_group()
        process.wait()
    finally:
        process.stdout.close()
        process.stderr.close()
    return {'returncode': None if status == 'timeout' else process.returncode,
            'stdout': buffers['stdout'].decode('utf-8', 'replace'),
            'stderr': buffers['stderr'].decode('utf-8', 'replace') or diagnostic,
            'status': status or ('ok' if process.returncode == 0 else 'failed')}


def load_plist(path):
    if not path.is_file() or path.stat().st_size > MAX_HEADER_BYTES:
        raise ValueError('plist missing, not regular, or exceeds inspection limit')
    value = plistlib.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError('plist is not a dictionary')
    return value


def inspect_slice(framework, library, runner):
    report = {'identifier': library.get('LibraryIdentifier'), 'platform': library.get('SupportedPlatform'),
              'variant': library.get('SupportedPlatformVariant', 'device'), 'status': 'incomplete',
              'headers': [], 'architectures': [], 'issues': []}
    try:
        identifier = library['LibraryIdentifier']
        slice_root = checked(framework, identifier)
        library_path = checked(slice_root, library['LibraryPath'])
        if library_path.suffix == '.framework':
            info = load_plist(checked(library_path, 'Info.plist'))
            binary = checked(library_path, info['CFBundleExecutable'])
            headers = checked(slice_root, library['HeadersPath']) if 'HeadersPath' in library else checked(library_path, 'Headers')
        else:
            binary = library_path
            headers = checked(slice_root, library['HeadersPath'])
        if not binary.is_file() or binary.stat().st_size > 1024 * 1024 * 1024:
            raise ValueError('binary missing or exceeds inspection limit')
        report['binary'] = {'path': str(binary.relative_to(framework)), 'sha256': digest(binary)}
        file_result = runner(['/usr/bin/file', '-b', str(binary)])
        report['binary']['file'] = file_result
        if file_result['status'] != 'ok' or not any(x in file_result['stdout'] for x in ('Mach-O', 'ar archive')):
            report['issues'].append('binary type could not be established with file')
        declared, total = set(), 0
        for path in sorted(files_under(headers)):
            if path.suffix != '.h':
                continue
            size = path.stat().st_size
            total += size
            if size > MAX_HEADER_BYTES or total > 4 * MAX_HEADER_BYTES:
                raise ValueError('header inspection limit exceeded')
            content = path.read_text(encoding='utf-8')
            matches = declarations(content)
            if any(matches.values()):
                report['headers'].append({'path': str(path.relative_to(framework)),
                                          'sha256': digest(path), 'declarations': matches})
                declared.update(name for name, values in matches.items() if values)
        report['missing_declarations'] = sorted(set(FUNCTIONS) - declared)
        report['missing_optional_declarations'] = sorted(set(OPTIONAL_FUNCTIONS) - declared)
        architectures = library.get('SupportedArchitectures')
        if not isinstance(architectures, list) or not 1 <= len(architectures) <= 16:
            raise ValueError('missing or invalid architecture inventory')
        if len(set(architectures)) != len(architectures):
            raise ValueError('duplicate architecture inventory')
        for arch in architectures:
            if not isinstance(arch, str) or not re.fullmatch(r'[A-Za-z0-9_]+', arch):
                raise ValueError('unsafe architecture name')
            result = runner(['/usr/bin/xcrun', 'nm', '-arch', arch, '-g', '-U', '-P', str(binary)])
            exports = defined_exports(result['stdout']) if result['status'] == 'ok' else set()
            report['architectures'].append({'architecture': arch, 'tool_status': result['status'],
                'returncode': result['returncode'], 'diagnostic': result['stderr'][:4096],
                'defined_exports': sorted(exports), 'missing_exports': sorted(set(FUNCTIONS) - exports),
                'missing_optional_exports': sorted(set(OPTIONAL_FUNCTIONS) - exports),
                'matching_nm_records': [line for line in result['stdout'].splitlines()
                    if defined_exports(line)][:128] if result['status'] == 'ok' else [],
                'nm_output_sha256': hashlib.sha256(result['stdout'].encode()).hexdigest()})
        if (not report['issues'] and not report['missing_declarations'] and
                all(x['tool_status'] == 'ok' and not x['missing_exports'] for x in report['architectures'])):
            report['status'] = 'complete'
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['issues'].append(type(error).__name__ + ': ' + str(error))
    return report


def inspect(artifacts_root, runner=run_tool):
    report = {'schema_version': 1, 'inspection_status': 'incomplete', 'build_result': 'not_evaluated',
        'handshake_result': 'not_attempted', 'required_functions': list(FUNCTIONS),
        'optional_functions': list(OPTIONAL_FUNCTIONS), 'candidates': [], 'slices': [], 'issues': [],
        'provenance': {'expected_archive_sha256': EXPECTED_ARCHIVE_SHA256,
            'expected_source_commit': EXPECTED_SOURCE, 'expanded_archive_digest_verified': False,
            'source_binary_equivalence_verified': False},
        'limits': ['Textual declarations and defined symbols do not prove C ABI compatibility or link success.',
                   'No binary is executed; no device connection, PIN, signing or pairing is attempted.',
                   'Inspection does not establish cancellation behavior or same-phone discovery.',
                   'Artifact selection uses the exact IDevice bundle name in the supplied resolved-package directory; cache identity is not independently authenticated.',
                   'Expanded artifact hashes do not revalidate the downloaded ZIP checksum or producer provenance.']}
    root = Path(artifacts_root)
    try:
        # Refuse a symlink in any supplied root component, not just at its leaf.
        absolute = root.absolute()
        if any(path.is_symlink() for path in [absolute, *absolute.parents]):
            raise ValueError('artifact root has a symlink component')
        if not root.is_dir():
            report['issues'].append('resolved SourcePackages artifacts directory is missing')
            return report
        candidates = find_frameworks(root)
        report['candidates'] = [str(x.relative_to(root)) for x in candidates]
        if len(candidates) != 1:
            report['issues'].append('expected exactly one IDevice.xcframework; found ' + str(len(candidates)))
            return report
        framework = candidates[0]
        report['tools'] = {'nm_resolution': runner(['/usr/bin/xcrun', '--find', 'nm']),
                           'nm_arguments': ['-arch', '<declared architecture>', '-g', '-U', '-P'],
                           'file_command': ['/usr/bin/file', '-b', '<packaged binary>']}
        if report['tools']['nm_resolution']['status'] != 'ok':
            report['issues'].append('official Xcode nm could not be resolved')
        info_path = checked(framework, 'Info.plist')
        info = load_plist(info_path)
        report['xcframework_info_sha256'] = digest(info_path)
        libraries = info.get('AvailableLibraries')
        if not isinstance(libraries, list) or not 1 <= len(libraries) <= 32:
            raise ValueError('missing or invalid XCFramework slice inventory')
        for library in libraries:
            if not isinstance(library, dict):
                raise ValueError('invalid XCFramework slice descriptor')
            if library.get('SupportedPlatform') == 'ios' and library.get('SupportedPlatformVariant', 'device') in ('device', 'simulator'):
                report['slices'].append(inspect_slice(framework, library, runner))
        roles = {x['variant'] for x in report['slices']}
        report['missing_platforms'] = sorted({'device', 'simulator'} - roles)
        identifiers = [x['identifier'] for x in report['slices']]
        if len(identifiers) != len(set(identifiers)):
            report['issues'].append('duplicate iOS slice identifiers')
        if not report['missing_platforms'] and not report['issues'] and all(x['status'] == 'complete' for x in report['slices']):
            report['inspection_status'] = 'complete'
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['issues'].append(type(error).__name__ + ': ' + str(error))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.artifacts_root.resolve()):
        parser.error('evidence output must be outside the resolved package artifacts')
    report = inspect(args.artifacts_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Preserve a previous observation rather than silently replacing it.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print('Packaged pairing API inspection: ' + report['inspection_status'] + '. Build and handshake are not evaluated.')
    # Incomplete evidence is recorded, not used to replace the build's outcome.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
