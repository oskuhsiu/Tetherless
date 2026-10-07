"""Bounded offline validation of the entire retained, successful C Actions artifact.

Downloaded recipe/source bytes are authenticated as data, never imported or run.
This reader does not parse native binaries, admit signing, or select an artifact.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import plistlib
import re
import stat
import tarfile
import unicodedata
import zipfile

from apply_patch import VerificationError, canonical_json
from build_xcframework import file_hash
from mixed_provider import ARCHIVE_SHA256

HERE = Path(__file__).resolve().parent
REPOSITORY = 'oskuhsiu/Tetherless'
WORKFLOW = '.github/workflows/c-provider-native.yml'
BRANCH = 'verify/staged-pairing-native'
MAX_ZIP = 256 * 1024 * 1024
MAX_EXPANDED = 1024 * 1024 * 1024
MAX_ENTRIES = 25000
MAX_JSON = 16 * 1024 * 1024
MAX_TEXT = 32 * 1024 * 1024
MAX_SOURCE = 128 * 1024 * 1024
SYSTEM_FRAMEWORKS = ['CoreFoundation', 'SystemConfiguration']
C_IDENTIFIERS = {n: 'tetherless_c_ed25519_' + n for n in ('sha512', 'sha512_init', 'sha512_update', 'sha512_final')}
ED = {'_' + v for v in C_IDENTIFIERS.values()}
GLUE = {'_' + v for v in C_IDENTIFIERS}
REQUIRED_C = {'_plist_new_dict', '_plist_free', '_plist_array_set_item', '_afc_client_free', '_lockdownd_client_free', '_idevice_free'}
SOURCE_PINS = {
    'root': ('SideStore/libimobiledevice-xcframework', '0f88f7bbd1aa9713d8c8c2255df31f2b25ff9d8a'),
    'plist': ('libimobiledevice/libplist', '32428abacb909988e8e960a8845a6430b17b6a60'),
    'glue': ('libimobiledevice/libimobiledevice-glue', 'da770a7687f35fbb981db4d7b47b1b032cd5c2c7'),
    'usbmuxd': ('libimobiledevice/libusbmuxd', '93eb168bf6b07472d17781328c21df0c60300524'),
}


def require(ok, message):
    if not ok:
        raise VerificationError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def _sha(value, length=64):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None


def _number(value):
    return type(value) is int and value > 0


def read_json_bytes(raw):
    require(len(raw) <= MAX_JSON, 'retained C JSON exceeds bound')
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs)
    require(isinstance(value, dict), 'retained C JSON must be an object')
    return value


def safe_file(root, name):
    require(root.is_dir() and not root.is_symlink(), 'retained C root is missing or a symlink')
    path = _path(name)
    current = root
    for part in path.parts:
        current /= part
        require(not current.is_symlink(), 'retained C input contains a symlink')
    require(current.is_file(), 'retained C input is missing: ' + name)
    return current


def _path(name):
    require(isinstance(name, str), 'archive name is not text')
    p = PurePosixPath(name)
    require(bool(name) and p.parts and not p.is_absolute() and p.as_posix() == name
            and all(v not in ('.', '..') for v in p.parts)
            and not any(ord(v) < 32 or v in '\\:' for v in name), 'unsafe retained C archive path')
    return p


def _paths(rows):
    names, spellings, files = set(), {}, set()
    for name, is_dir in rows:
        p = _path(name)
        key = unicodedata.normalize('NFC', name).casefold()
        require(key not in names, 'duplicate or case-colliding retained C path')
        names.add(key)
        for depth in range(1, len(p.parts) + 1):
            spelling = '/'.join(p.parts[:depth])
            folded = unicodedata.normalize('NFC', spelling).casefold()
            require(spellings.setdefault(folded, spelling) == spelling, 'case-colliding retained C directory')
        if not is_dir:
            files.add(key)
    for name in names:
        require(not any(p.as_posix() in files for p in PurePosixPath(name).parents if p.as_posix() != '.'),
                'retained C file/directory collision')


def zip_files(archive, *, max_archive=MAX_ZIP, max_expanded=MAX_EXPANDED):
    if isinstance(archive, Path):
        require(archive.is_file() and not archive.is_symlink() and 0 < archive.stat().st_size <= max_archive,
                'retained C ZIP size/type differs')
        source = archive
    else:
        require(isinstance(archive, bytes) and 0 < len(archive) <= max_archive, 'retained C ZIP bytes exceed bound')
        source = io.BytesIO(archive)
    with zipfile.ZipFile(source) as z:
        entries = z.infolist()
        require(0 < len(entries) <= MAX_ENTRIES and sum(x.file_size for x in entries) <= max_expanded,
                'retained C ZIP expansion budget exceeded')
        _paths([(x.filename.rstrip('/') if x.is_dir() else x.filename, x.is_dir()) for x in entries])
        for x in entries:
            require(stat.S_IFMT(x.external_attr >> 16) in (0, stat.S_IFDIR if x.is_dir() else stat.S_IFREG)
                    and not x.flag_bits & 1 and x.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                    'unsupported retained C ZIP member')
        return {x.filename: z.read(x) for x in entries if not x.is_dir()}


def tar_files(raw):
    require(0 < len(raw) <= MAX_SOURCE, 'C matching source TAR size exceeds bound')
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as t:
        entries = t.getmembers()
        require(0 < len(entries) <= MAX_ENTRIES and sum(x.size for x in entries) <= MAX_SOURCE,
                'C matching source TAR expansion exceeds bound')
        _paths([(x.name, x.isdir()) for x in entries])
        require(all(x.isfile() and set(x.pax_headers) <= {'path'} and x.pax_headers.get('path', x.name) == x.name and x.mode in (0o644, 0o755) for x in entries),
                'C matching source contains unsupported member')
        return {x.name: (t.extractfile(x).read(), x.mode) for x in entries}


def load_selection(path=None):
    path = path or HERE / 'retained-c-provider.json'
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_JSON, 'missing C selection file')
    data = read_json_bytes(path.read_bytes())
    require(data.get('schema') == 1 and data.get('selection') is not None,
            'no successful C producer is selected; native integration is blocked')
    return validate_selection(data['selection'])


def validate_selection(s):
    require(isinstance(s, dict) and set(s) == {'repository', 'repository_id', 'source_commit', 'workflow_path',
        'head_branch', 'run_id', 'run_attempt', 'job_id', 'artifact_id', 'archive_sha256', 'size_in_bytes'},
        'C selection fields differ')
    require(s['repository'] == REPOSITORY and s['workflow_path'] == WORKFLOW and s['head_branch'] == BRANCH
            and all(_number(s[k]) for k in ('repository_id', 'run_id', 'run_attempt', 'job_id', 'artifact_id'))
            and _sha(s['source_commit'], 40) and _sha(s['archive_sha256'])
            and _number(s['size_in_bytes']) and s['size_in_bytes'] <= MAX_ZIP, 'C selection identity differs')
    return s


def verify_run(run, s):
    require(all(_number(run.get(k)) for k in ('id', 'run_attempt'))
            and run.get('id') == s['run_id'] and run.get('head_sha') == s['source_commit']
            and run.get('run_attempt') == s['run_attempt'] and run.get('path') == WORKFLOW
            and run.get('head_branch') == BRANCH and run.get('event') in ('push', 'workflow_dispatch')
            and run.get('repository', {}).get('id') == s['repository_id']
            and run.get('repository', {}).get('full_name') == REPOSITORY
            and run.get('head_repository', {}).get('id') == s['repository_id']
            and run.get('head_repository', {}).get('full_name') == REPOSITORY
            and run.get('status') == 'completed' and run.get('conclusion') == 'success',
            'C producer final run identity or success differs')


def verify_job(job, s):
    url = 'https://api.github.com/repos/' + REPOSITORY + '/actions/jobs/' + str(s['job_id'])
    require(all(_number(job.get(k)) for k in ('id', 'run_id', 'run_attempt'))
            and job.get('id') == s['job_id'] and job.get('name') == 'c-provider'
            and job.get('url') == url and job.get('run_id') == s['run_id']
            and job.get('head_sha') == s['source_commit'] and job.get('run_attempt') == s['run_attempt']
            and job.get('status') == 'completed' and job.get('conclusion') == 'success',
            'C producer final job identity or success differs')


def verify_artifact_metadata(row, s):
    url = 'https://api.github.com/repos/' + REPOSITORY + '/actions/artifacts/' + str(s['artifact_id'])
    run = row.get('workflow_run', {})
    require(all(_number(row.get(k)) for k in ('id', 'size_in_bytes'))
            and row.get('id') == s['artifact_id'] and row.get('expired') is False
            and row.get('name') == 'c-provider-' + s['source_commit'] + '-' + str(s['run_attempt'])
            and row.get('url') == url and row.get('archive_download_url') == url + '/zip'
            and row.get('size_in_bytes') == s['size_in_bytes']
            and row.get('digest') == 'sha256:' + s['archive_sha256']
            and run.get('id') == s['run_id'] and run.get('head_sha') == s['source_commit']
            and run.get('repository_id') == s['repository_id'] and run.get('head_repository_id') == s['repository_id'],
            'C artifact final identity, digest or size differs')


def verify_git_tree(data, expected):
    """Reconstruct every tree object, rejecting truncated/omitted/duplicate entries."""
    require(data.get('truncated') is False and data.get('sha') == expected, 'C Git tree identity differs')
    rows = data.get('tree')
    require(isinstance(rows, list) and len(rows) <= MAX_ENTRIES, 'C Git tree exceeds bound')
    require(len({x['path'] for x in rows}) == len(rows), 'duplicate C Git tree entry')
    trees = {'': expected, **{x['path']: x['sha'] for x in rows if x['type'] == 'tree'}}
    by_parent = {name: [] for name in trees}
    for row in rows:
        p = _path(row['path']); parent = str(p.parent); parent = '' if parent == '.' else parent
        require(parent in trees and row.get('type') in ('tree', 'blob', 'commit') and _sha(row.get('sha'), 40),
                'unreachable C Git tree row')
        allowed = {'tree': ('040000',), 'blob': ('100644', '100755'), 'commit': ('160000',)}
        require(row.get('mode') in allowed[row['type']], 'unsupported C Git tree mode')
        if row['type'] == 'blob':
            require(type(row.get('size')) is int and 0 <= row['size'] <= MAX_SOURCE, 'C Git blob size differs')
        by_parent[parent].append(row)
    for parent, wanted in trees.items():
        children = sorted(by_parent[parent], key=lambda x: (PurePosixPath(x['path']).name + ('/' if x['type'] == 'tree' else '')).encode())
        raw = b''.join((x['mode'].lstrip('0') + ' ' + PurePosixPath(x['path']).name).encode() + b'\0' + bytes.fromhex(x['sha']) for x in children)
        require(hashlib.sha1(b'tree ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == wanted,
                'incomplete or altered C Git tree')
    return {row['path']: row for row in rows if row['type'] == 'blob'}


def verify_source(raw, receipt, commit, tree, s):
    require(commit.get('sha') == s['source_commit'] and _sha(commit.get('tree', {}).get('sha'), 40),
            'C source commit identity differs')
    api_base = 'https://api.github.com/repos/' + REPOSITORY + '/git/'
    require(commit.get('url') == api_base + 'commits/' + s['source_commit']
            and tree.get('url') == api_base + 'trees/' + commit['tree']['sha'], 'C source API origin differs')
    blobs = verify_git_tree(tree, commit['tree']['sha'])
    members = tar_files(raw)
    expected = {}
    for path, row in blobs.items():
        if path.startswith('Integration/Dependencies/libimobiledevice/') or path.startswith('Integration/Dependencies/idevice/'):
            expected['recipe/' + path.removeprefix('Integration/Dependencies/')] = row
        elif path in (WORKFLOW, 'LICENSE'):
            expected['recipe/' + path] = row
    require(expected and {n for n in members if n.startswith('recipe/')} == set(expected),
            'C matching source recipe inventory differs from C commit')
    for name, row in expected.items():
        data, mode = members[name]
        require(len(data) == row['size'] and git_blob(data) == row['sha'] and mode == int(row['mode'][-3:], 8),
                'C matching source recipe is not the C producer commit: ' + name)
    def item(name):
        require(name in members, 'missing C matching source file: ' + name)
        return members[name][0]
    namespace = read_json_bytes(item('recipe/libimobiledevice/namespace-contract.json'))
    require(namespace.get('identifiers') == C_IDENTIFIERS and namespace.get('root_commit') == SOURCE_PINS['root'][1]
            and digest(item('recipe/libimobiledevice/namespace-contract.json')) == receipt['namespace_contract_sha256'],
            'C namespace contract differs')
    pristine = read_json_bytes(item('pristine/source-receipt.json'))
    require(digest(item('pristine/source-receipt.json')) == receipt['source_receipt_sha256']
            and set(pristine.get('sources', {})) == set(SOURCE_PINS), 'C pristine source receipt differs')
    upstream = read_json_bytes(item('recipe/libimobiledevice/provenance/commits.json'))
    expected_pristine = {'pristine/source-receipt.json'}
    for key, (repository, source_commit) in SOURCE_PINS.items():
        identity = upstream[key]
        require(identity['repository'] == repository and identity['commit'] == source_commit, 'C upstream source pin differs')
        metadata = read_json_bytes(item('recipe/libimobiledevice/provenance/' + key + '-tree.json'))
        # Existing upstream API snapshots use the commit in their top-level sha.
        require(metadata.get('sha') == source_commit, 'C upstream metadata commit differs')
        metadata = dict(metadata, sha=identity['tree'])
        files = verify_git_tree(metadata, identity['tree'])
        recorded = pristine['sources'][key]
        require(recorded.get('repository') == repository and recorded.get('commit') == source_commit
                and recorded.get('tree') == identity['tree'] and set(recorded['files']) == set(files),
                'C pristine source inventory differs')
        for name, row in files.items():
            full = 'pristine/' + key + '/' + name; expected_pristine.add(full)
            data, mode = members[full]
            require(len(data) == row['size'] and git_blob(data) == row['sha'] and mode == int(row['mode'][-3:], 8)
                    and recorded['files'][name] == {'git_blob': row['sha'], 'sha256': digest(data), 'bytes': len(data), 'mode': row['mode']},
                    'C pristine source bytes differ: ' + full)
    require(set(members) == set(expected) | expected_pristine, 'unlisted C matching source member')
    return members


def exported(text, *, unique=True):
    require(isinstance(text, str) and len(text.encode()) <= MAX_TEXT, 'C nm output exceeds bound')
    symbols = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.endswith(':'):
            continue
        require(re.fullmatch(r'[_A-Za-z.$][_A-Za-z0-9.$]*', line), 'unexpected nm output')
        symbols.append(line)
    require(symbols and (not unique or len(set(symbols)) == len(symbols)), 'empty scan or duplicate C globals')
    return set(symbols)


def check_symbols(text, expected_symbols):
    actual = exported(text)
    require(isinstance(expected_symbols, list) and expected_symbols == sorted(set(expected_symbols))
            and actual == set(expected_symbols) and REQUIRED_C | ED | GLUE <= actual, 'C full export contract differs')
    return {'schema': 1, 'global_count': len(actual), 'symbols': sorted(actual),
            'internal_global_definitions_unique': True, 'nm_sha256': digest(text.encode())}


def historical_c_symbol_receipt(old_raw, new_raw):
    # C Runner.run historically returned decode().strip() after retaining the
    # complete raw log and supervised byte count. Reproduce exactly that receipt
    # transform; Rust's later raw llvm-nm scan keeps its own independent hash.
    old_text, new_text = old_raw.strip(), new_raw.strip()
    old, new = exported(old_text, unique=False), exported(new_text)
    require(new == old | ED and not old & ED, 'C exports differ from old-plus-four contract')
    return dict(check_symbols(new_text, sorted(new)), exact_old_plus_four=True,
                old_nm_sha256=digest(old_text.encode()))


def _link_map_path(raw):
    # Local build roots can contain Unicode (including our portable fixtures).
    # Preserve strict UTF-8 paths exactly; do not normalize or replace bytes.
    try:
        path = raw.decode('utf-8')
    except UnicodeDecodeError as error:
        raise VerificationError('invalid UTF-8 in map object path') from error
    require(bool(path) and path.isprintable(), 'control byte or character in map object path')
    return path


def parse_link_map(raw):
    """Parse LF-delimited ld bytes; return object paths and ASCII live names.

    ld writes literal-string payloads verbatim, including invalid UTF-8 and
    non-LF control bytes. Only that payload is opaque. Its address, size and
    owner still use the same strict ASCII grammar as ordinary symbol rows.
    Literal strings cannot satisfy an exported symbol. Keep duplicate named
    rows so the ownership verifier can reject every ambiguous required name.
    """
    require(isinstance(raw, bytes), 'mixed-provider map requires raw bytes')
    require(len(raw) <= MAX_TEXT, 'mixed-provider map exceeds bound')
    objects, live, section, seen = {}, [], None, set()
    headings = {b'# Object files:': 'objects', b'# Sections:': 'sections',
                b'# Symbols:': 'symbols', b'# Dead Stripped Symbols:': 'dead'}
    for line in raw.split(b'\n'):
        heading = line.rstrip(b' \t')
        if heading in headings:
            section = headings[heading]
            require(section not in seen and (section == 'objects' or 'objects' in seen)
                    and (section != 'dead' or 'symbols' in seen)
                    and (section not in ('objects', 'sections') or 'symbols' not in seen),
                    'duplicate or out-of-order map section')
            seen.add(section)
        elif line.startswith(b'#'):
            columns = ((section == 'sections' and re.fullmatch(rb'#[ \t]+Address[ \t]+Size[ \t]+Segment[ \t]+Section[ \t]*', line))
                or (section == 'symbols' and re.fullmatch(rb'#[ \t]+Address[ \t]+Size[ \t]+File[ \t]+Name[ \t]*', line))
                or (section == 'dead' and re.fullmatch(rb'#[ \t]+(?:Address[ \t]+)?Size[ \t]+File[ \t]+Name[ \t]*', line)))
            preamble = section is None and re.fullmatch(rb'# Arch: [!-~][ -~]*', line)
            if section is None and line.startswith(b'# Path: '):
                path = _link_map_path(line[len(b'# Path: '):])
                preamble = not path[0].isspace()
            require(columns or preamble, 'unknown link-map section or comment')
            continue
        elif section == 'objects' and line.strip(b' \t'):
            m = re.fullmatch(rb'\[[ \t]*(0|[1-9][0-9]*)\][ \t]+(.+)', line)
            require(m and m[1].decode('ascii') not in objects, 'malformed, noncanonical or duplicate map object')
            objects[m[1].decode('ascii')] = _link_map_path(m[2])
        elif section == 'sections' and line.strip(b' \t'):
            require(re.fullmatch(rb'0x[0-9A-Fa-f]+[ \t]+0x[0-9A-Fa-f]+[ \t]+[A-Za-z_.$][A-Za-z0-9_.$]*[ \t]+[A-Za-z_.$][A-Za-z0-9_.$]*', line),
                    'malformed link-map section row')
        elif section in ('symbols', 'dead') and line.strip(b' \t'):
            prefix = rb'0x[0-9A-Fa-f]+[ \t]+' if section == 'symbols' else rb'<<dead>>[ \t]+'
            m = re.fullmatch(prefix + rb'0x[0-9A-Fa-f]+[ \t]+\[[ \t]*(0|[1-9][0-9]*)\][ \t]+(.+)', line)
            message = ('unparsed live map row or unknown/noncanonical owner' if section == 'symbols'
                       else 'malformed dead-stripped map row or unknown/noncanonical owner')
            require(m is not None and m[1].decode('ascii') in objects, message)
            if not m[2].startswith(b'literal string: '):
                require(re.fullmatch(rb'[ -~]+', m[2]), 'non-ASCII or control byte in map symbol name')
                if section == 'symbols':
                    live.append((m[1].decode('ascii'), m[2].decode('ascii')))
        elif line.strip(b' \t'):
            raise VerificationError('unparsed link-map content outside a known section')
    require({'objects', 'symbols'} <= seen, 'required symbol missing from live map')
    return objects, live


def link_ownership(raw, c_archive, c_symbols, rust_archive=None, rust_symbols=(), *, visibility=None):
    c_required, rust_required = set(c_symbols), set(rust_symbols)
    require(c_required and not c_required & rust_required, 'ambiguous mixed-provider ownership contract')
    required, owners = c_required | rust_required, {}
    objects, live = parse_link_map(raw)
    candidates = {name: [] for name in required}
    for owner, name in live:
        if name in required:
            candidates[name].append(owner)
    require(all(candidates.values()), 'required symbol missing from live map')
    locals_by_name = {}
    if visibility is None:
        # Historical C-only artifacts keep their original strict interpretation.
        # Mixed producers/consumers must supply fully bound visibility evidence.
        for name, rows in candidates.items():
            require(len(rows) == 1, 'ambiguous required live map symbol')
            owners[name] = rows[0]
    else:
        require(visibility.get('schema') == 1 and set(visibility.get('archives', {})) == {'rust', 'c'},
                'mixed-provider visibility contract differs')
        scans = visibility['archives']
        paths = {'c': str(c_archive), 'rust': str(rust_archive)}
        require(all(scans[role]['source'] == path and Path(path).is_absolute() for role, path in paths.items())
                and paths['c'] != paths['rust'], 'visibility belongs to different archive paths')
        require(not set(scans['c']['external_symbols']) & set(scans['rust']['external_symbols'])
                and c_required <= set(scans['c']['external_symbols'])
                and rust_required <= set(scans['rust']['external_symbols']), 'visibility external ownership contract differs')
        for name, rows in candidates.items():
            require(len(rows) == len(set(rows)), 'ambiguous repeated required live map row')
            expected_role = 'c' if name in c_required else 'rust'
            external, local = [], []
            for owner in rows:
                matches = []
                for role, archive in paths.items():
                    match = re.fullmatch(re.escape(archive) + r'(?:\[(?:0|[1-9][0-9]*)\])?\(([^()]+)\)', objects[owner])
                    if match:
                        matches.append((role, match[1]))
                require(len(matches) == 1, 'required symbol belongs to wrong or unknown archive: ' + name)
                role, member = matches[0]
                kinds = scans[role]['members'].get(member, {}).get(name, [])
                require(len(kinds) == 1, 'missing or ambiguous exact member visibility: ' + name)
                kind = kinds[0]
                require(kind in ('local', 'external', 'weak'), 'unknown required symbol visibility')
                if kind == 'local':
                    local.append(owner)
                else:
                    external.append((owner, role, kind))
            require(len(external) == 1, 'ambiguous or missing required external map owner: ' + name)
            owner, role, kind = external[0]
            require(role == expected_role, 'required symbol belongs to wrong archive: ' + name)
            # A sole weak global preserves existing App behavior. It cannot
            # resolve a collision or impersonate a non-external implementation.
            require(not local or kind == 'external', 'weak external cannot resolve local map candidates: ' + name)
            owners[name] = owner
            if local:
                locals_by_name[name] = sorted(local)
    for name, owner in owners.items():
        archive = str(c_archive if name in c_required else rust_archive)
        require(Path(archive).is_absolute() and re.fullmatch(re.escape(archive) + r'(?:\[[0-9]+\])?\([^()]+\)', objects.get(owner, '')),
                'required symbol belongs to wrong archive: ' + name)
    if ED | GLUE <= c_required:
        ed, glue = {owners[n] for n in ED}, {owners[n] for n in GLUE}
        require(len(ed) == len(glue) == 1 and not ed & glue, 'C SHA512 families do not have distinct real members')
    result = {'schema': 1, 'c_required_live_symbols': len(c_required), 'rust_required_live_symbols': len(rust_required),
              'owners': owners, 'archive_members': {k: objects[k] for k in sorted(set(owners.values()))},
              'map_sha256': digest(raw)}
    if visibility is not None:
        result.update(schema=2, visibility_evidence_sha256=visibility['evidence_sha256'],
                      proven_local_candidates=locals_by_name,
                      local_archive_members={k: objects[k] for k in sorted({v for rows in locals_by_name.values() for v in rows})})
    return result


def success(status):
    require(status.get('schema') == 1 and status.get('outcome') == 'success' and status.get('returncode') == 0
            and status.get('output_complete') is True and status.get('output_truncated') is False
            and status.get('stop_reason') is None and status.get('cleanup', {}).get('direct_child_reaped') is True
            and status.get('cleanup', {}).get('group_empty') is True, 'C command lacks successful complete output/join evidence')


def provider_identity(receipt):
    keys = ('target', 'kind', 'contract_sha256', 'source_commit', 'framework_binary_sha256')
    require(receipt.get('kind') == 'apple-framework-consumer' and receipt.get('native_libraries') == []
            and receipt.get('native_execution') is False and receipt.get('product_activation') is False,
            'C OpenSSL receipt is outside the external framework contract')
    prefix = receipt['target'].upper().replace('-', '_') + '_'
    require(receipt.get('environment', {}).get(prefix + 'OPENSSL_LIBS') == '', 'C OpenSSL LIBS is not present-empty')
    return {key: receipt[key] for key in keys}


def verify_provider(mixed, openssl_receipt):
    require(mixed['provider_identity'] == provider_identity(openssl_receipt), 'Rust and C select different OpenSSL providers')


def verify_sdk(mixed, observations):
    sdk = mixed['sdk']
    require(observations.get('sdk_' + sdk + '_version') == mixed['sdk_version']
            and observations.get('sdk_' + sdk + '_build') == mixed['sdk_build']
            and observations.get('xcode') == mixed['xcode'], 'Rust and C target platform/SDK/toolchain differs')


def inventory(files):
    return {name: {'sha256': digest(raw), 'bytes': len(raw)} for name, raw in files.items()}


def _data(files, name):
    require(name in files, 'C artifact lacks required file: ' + name)
    return files[name]


def _json(files, name):
    return read_json_bytes(_data(files, name))


def validate_product(outer, selection, commit, tree):
    s = selection
    audit = _json(outer, 'work/evidence/final-input-audit.json')
    expected_audits = {'pristine_source', 'openssl_inputs', 'original_c_iphoneos', 'original_c_iphonesimulator',
        'recipe_inputs', 'derived_sources_iphoneos', 'derived_sources_iphonesimulator', 'toolchain_inputs'}
    require(audit.get('schema') == 1 and audit.get('all_passed') is True and audit.get('primary_failure_preserved') is True
            and set(audit.get('checks', {})) == expected_audits
            and all(x == {'passed': True} for x in audit['checks'].values()), 'C final input audit incomplete or failed')
    identity = _json(outer, 'inputs/action-identity.json')
    require(all(identity.get(key) == s[key] for key in ('repository', 'source_commit', 'run_id', 'run_attempt', 'job_id', 'workflow_path'))
            and identity.get('job_name') == 'c-provider' and identity.get('status_at_acquisition') == 'in_progress'
            and identity.get('success_at_acquisition') is False
            and identity.get('later_api_success_verification_required') is True,
            'C acquisition-time identity differs; it cannot replace final API success')
    inner = _data(outer, 'work/libimobiledevice-derived-candidate.zip')
    product_digest = _json(outer, 'work/evidence/product-digest.json')
    require(product_digest == {'bytes': len(inner), 'sha256': digest(inner)}, 'C inner candidate ZIP digest differs')
    product = zip_files(inner, max_expanded=MAX_SOURCE + 256 * 1024 * 1024)
    receipt = _json(product, 'producer-receipt.json')
    require(receipt.get('schema') == 1 and receipt.get('source_commit') == s['source_commit']
            and receipt.get('run_id') == str(s['run_id']) and receipt.get('run_attempt') == str(s['run_attempt'])
            and receipt.get('action_identity') == identity and receipt.get('all_c_globals_unique') is True
            and receipt.get('all_public_headers_unchanged') is True and receipt.get('consumer_admitted') is False
            and receipt.get('rust_mixed_provider_verified') is False and receipt.get('ios_binaries_executed') is False
            and receipt.get('openssl_bundled') is False and receipt.get('system_frameworks') == SYSTEM_FRAMEWORKS,
            'C receipt is outside the reviewed isolated scope')
    run_context = _json(outer, 'work/evidence/run-context.json')
    require(run_context.get('source_commit') == s['source_commit'] and run_context.get('run_id') == str(s['run_id'])
            and run_context.get('run_attempt') == str(s['run_attempt']) and run_context.get('job') == 'c-provider'
            and run_context.get('new_derivation') is True and run_context.get('consumer_admitted') is False
            and run_context.get('ios_binaries_executed') is False, 'C build run context differs')
    require(receipt.get('toolchain') == _json(outer, 'work/evidence/toolchain.json'), 'C retained toolchain receipt differs')
    source = _data(product, 'matching-source.tar')
    require(digest(source) == receipt['matching_source_sha256'], 'C matching source digest differs')
    members = verify_source(source, receipt, commit, tree, s)
    require(_data(product, 'NOTICE.md') == members['recipe/libimobiledevice/NOTICE.md'][0], 'C matching source notice differs')
    recipe = {name.removeprefix('recipe/'): {'sha256': digest(raw), 'bytes': len(raw)}
              for name, (raw, _mode) in members.items() if name.startswith('recipe/')}
    require(_json(outer, 'work/evidence/recipe-inputs.json') == recipe, 'C final recipe inventory differs from C commit')
    require(_data(outer, 'inputs/pristine/source-receipt.json') == members['pristine/source-receipt.json'][0],
            'C outer pristine source receipt differs')
    for name, (raw, _mode) in members.items():
        if name.startswith('pristine/'):
            require(_data(outer, 'inputs/' + name) == raw, 'C outer pristine source bytes differ')
    xc = {n.removeprefix('libimobiledevice.xcframework/'): b for n, b in product.items() if n.startswith('libimobiledevice.xcframework/')}
    require(inventory(xc) == receipt.get('xcframework_files') and set(product) == {
        'matching-source.tar', 'NOTICE.md', 'producer-receipt.json'} | {'libimobiledevice.xcframework/' + n for n in xc},
        'C product complete inventory differs')
    original_zip = _data(outer, 'inputs/original-c-provider.zip')
    require(digest(original_zip) == ARCHIVE_SHA256, 'C original comparison archive differs')
    # Same bounded ZIP reader; baseline digest is immutable, not a new selection.
    original = zip_files(original_zip, max_archive=8 * 1024 * 1024, max_expanded=64 * 1024 * 1024)
    info = plistlib.loads(_data(xc, 'Info.plist'))
    old_info = plistlib.loads(_data(original, 'libimobiledevice.xcframework/Info.plist'))
    rows = info.get('AvailableLibraries', [])
    require(len(rows) == 2 and {(r.get('SupportedPlatform'), r.get('SupportedPlatformVariant', ''), tuple(r.get('SupportedArchitectures', []))) for r in rows}
            == {('ios', '', ('arm64',)), ('ios', 'simulator', ('arm64',))}, 'C packaged slices differ')
    slices = receipt.get('slices', [])
    require(len(slices) == 2 and {r.get('sdk') for r in slices} == {'iphoneos', 'iphonesimulator'}, 'C two-slice proof incomplete')
    host = _json(outer, 'work/host-tests/result.json')
    require(host.get('outcome') == 'passed' and host.get('plain', {}).get('outcome') == 'passed'
            and host.get('asan', {}).get('outcome') == 'passed', 'C ordinary and ASan host proofs are required')
    statuses = {name: read_json_bytes(raw) for name, raw in outer.items() if name.endswith(('.txt.status.json', '.log.status.json'))
                and (name.startswith('work/evidence/') or name.startswith('work/host-tests/'))}
    require(statuses, 'C joined command evidence missing')
    host_commands = host.get('commands')
    require(isinstance(host_commands, list) and host_commands and len(host_commands) <= 100,
            'C host command inventory missing')
    for command in host_commands:
        require('work/host-tests/' + command['receipt'] in statuses
                and statuses['work/host-tests/' + command['receipt']].get('command') == command['argv']
                and command['receipt'] == command['log'] + '.status.json', 'C host command evidence differs')
    require({'plain-run', 'asan-run', 'asan-probe-compile', 'asan-probe-run'} <= {x.get('name') for x in host_commands},
            'C host plain/ASan command evidence incomplete')
    for name, status in statuses.items():
        success(status)
        require(len(_data(outer, name.removesuffix('.status.json'))) == status.get('log_bytes'), 'C full command log bytes differ')
    def command_for(label):
        hits = [(name, status) for name, status in statuses.items() if re.fullmatch(r'work/evidence/[0-9]{3}-' + re.escape(label) + r'\.txt.status.json', name)]
        require(len(hits) == 1, 'C missing or duplicate command evidence: ' + label)
        name, status = hits[0]
        return status['command'], _data(outer, name.removesuffix('.status.json')).decode()
    operation = _json(outer, 'work/evidence/xcframework-operation.json')
    operation_args = operation.get('operation_command', [])
    require(len(operation_args) == 8 and isinstance(operation_args[2], str)
            and operation_args[2].endswith('/Integration/Dependencies/idevice/xcframework_operation.py')
            and Path(operation_args[2]).is_absolute(), 'C packaging recipe path differs')
    repository_root = Path(operation_args[2]).parents[3]
    result = {}
    for sdk, target, triple, variant in (('iphoneos', 'aarch64-apple-ios', 'arm64-apple-ios13.0', ''),
                                         ('iphonesimulator', 'aarch64-apple-ios-sim', 'arm64-apple-ios13.0-simulator', 'simulator')):
        row = next(r for r in slices if r['sdk'] == sdk)
        require(row.get('target') == triple and row.get('system_frameworks') == ['-framework', 'CoreFoundation', '-framework', 'SystemConfiguration'],
                'C platform/deployment/framework receipt differs')
        meta = next(r for r in rows if r.get('SupportedPlatformVariant', '') == variant)
        base = meta['LibraryIdentifier'] + '/'; library = base + meta['LibraryPath']; headers = base + meta['HeadersPath'] + '/'
        _path(library); _path(headers.rstrip('/'))
        header_files = {n.removeprefix(headers): b for n, b in xc.items() if n.startswith(headers)}
        require(digest(_data(xc, library)) == row.get('library_sha256') and inventory(header_files) == row.get('header_inventory'),
                'C packaged library or complete public header/module bytes differ')
        olds = [r for r in old_info['AvailableLibraries'] if r.get('SupportedPlatform') == 'ios'
                and r.get('SupportedPlatformVariant', '') == variant and 'arm64' in r['SupportedArchitectures']]
        require(len(olds) == 1, 'C original comparison slice differs')
        old_prefix = 'libimobiledevice.xcframework/' + olds[0]['LibraryIdentifier'] + '/' + olds[0]['HeadersPath'] + '/'
        require(header_files == {n.removeprefix(old_prefix): b for n, b in original.items() if n.startswith(old_prefix)},
                'C public headers or module maps changed from baseline')
        old_command, old_nm = command_for(sdk + '-old-nm'); new_command, new_nm = command_for(sdk + '-new-nm')
        require(new_command == ['/usr/bin/xcrun', 'nm', '-arch', 'arm64', '-g', '-U', '-j', row['library']]
                and old_command[:7] == ['/usr/bin/xcrun', 'nm', '-arch', 'arm64', '-g', '-U', '-j']
                and len(old_command) == 8, 'C nm command identity differs')
        new_symbols = exported(new_nm)
        expected_symbols = historical_c_symbol_receipt(old_nm, new_nm)
        require(row.get('symbols') == expected_symbols and _json(outer, 'work/evidence/' + sdk + '-symbols.json') == expected_symbols,
                'C complete symbol receipt differs')
        links = row.get('links', [])
        require(len(links) == 2 and {x.get('language') for x in links} == {'c', 'swift'}, 'C two-language link proof incomplete')
        for language in ('c', 'swift'):
            link = next(x for x in links if x['language'] == language)
            require(link.get('executed') is False and _sha(link.get('output_sha256')), 'C link execution boundary differs')
            command, _log = command_for(sdk + '-link-' + language)
            sdk_command, sdk_text = command_for(sdk + '-path')
            compiler_command, compiler_text = command_for(sdk + ('-clang-path' if language == 'c' else '-swiftc'))
            require(sdk_command == ['/usr/bin/xcrun', '--sdk', sdk, '--show-sdk-path']
                    and compiler_command == (['/usr/bin/xcrun', '--sdk', sdk, '--find', 'clang'] if language == 'c'
                        else ['/usr/bin/xcrun', '--find', 'swiftc'])
                    and Path(sdk_text.strip()).is_absolute() and Path(compiler_text.strip()).is_absolute(),
                    'C link compiler/SDK discovery command differs')
            library_path, header_path = Path(row['library']), Path(row['headers'])
            require(library_path.is_absolute() and header_path.is_absolute()
                    and '..' not in library_path.parts and '..' not in header_path.parts,
                    'C tested library/header path differs')
            ssl_contract = read_json_bytes(members['recipe/idevice/split-provider/target-inputs.json'][0])
            ssl_source = Path(row['openssl']['source_root'])
            require(ssl_source.is_absolute() and '..' not in ssl_source.parts, 'C OpenSSL source root differs')
            ssl_framework = ssl_source / ssl_contract['targets'][target]['framework_root']
            framework_flags = ['-F', str(ssl_framework.parent), '-framework', 'OpenSSL']
            require(row['openssl'].get('final_link_arguments') == framework_flags, 'C selected OpenSSL link arguments differ')
            probe = repository_root / 'Integration/Dependencies/libimobiledevice/probes' / ('provider.c' if language == 'c' else 'provider.swift')
            entry = '_tetherless_c_provider_probe' if language == 'c' else '_tetherless_c_provider_swift_probe'
            map_path = library_path.parent.parent / 'evidence' / (sdk + '-' + language + '.map')
            output_path = library_path.parent / ('probe-' + language)
            expected_command = [compiler_text.strip(), '-target', triple,
                '-isysroot' if language == 'c' else '-sdk', sdk_text.strip(),
                '-I', str(header_path), '-I', str(header_path / 'libimobiledevice'), str(probe),
                '-Xlinker', '-force_load', '-Xlinker', str(library_path), '-Xlinker', '-u', '-Xlinker', entry,
                '-Xlinker', '-map', '-Xlinker', str(map_path), '-framework', 'CoreFoundation',
                '-framework', 'SystemConfiguration', *framework_flags, '-o', str(output_path)]
            require(command == expected_command, 'C complete link argv differs from tested source/archive/provider contract')
            map_bytes = _data(outer, 'work/evidence/' + sdk + '-' + language + '.map')
            proof = link_ownership(map_bytes, row['library'], new_symbols)
            prior = link.get('ownership', {})
            # Preserve and recompute the original producer's exact ownership receipt.
            expected_prior = {'schema': 1, 'required_live_symbols': len(new_symbols), 'owners': proof['owners'],
                'ed25519_sha512_member': proof['archive_members'][proof['owners'][next(iter(ED))]],
                'glue_sha512_member': proof['archive_members'][proof['owners'][next(iter(GLUE))]], 'map_sha256': proof['map_sha256']}
            require(prior == expected_prior and _json(outer, 'work/evidence/' + sdk + '-' + language + '-ownership.json') == expected_prior,
                    'C original live map ownership receipt differs')
        openssl = provider_identity(row['openssl'])
        require(openssl['target'] == target, 'C OpenSSL target differs')
        openssl_contract = read_json_bytes(members['recipe/idevice/split-provider/target-inputs.json'][0])
        expected_provider = openssl_contract['targets'][target]
        require(openssl['contract_sha256'] == digest(members['recipe/idevice/split-provider/target-inputs.json'][0])
                and openssl['source_commit'] == openssl_contract['commit']
                and openssl['framework_binary_sha256'] == next(e['sha256'] for e in openssl_contract['entries'] if e['path'] == expected_provider['framework_binary']),
                'C external OpenSSL identity differs from authenticated source contract')
        observed = receipt['toolchain']
        require(observed.get('xcode') == 'Xcode 26.3\nBuild version 17C529'
                and observed.get(sdk + '_sdk_version') == '26.2' and observed.get(sdk + '_sdk_build') == '23C57',
                'C selected SDK/Xcode differs from reviewed recipe')
        result[target] = {'library_relative': 'libimobiledevice.xcframework/' + library,
            'headers_relative': 'libimobiledevice.xcframework/' + headers.rstrip('/'),
            'library_sha256': row['library_sha256'], 'header_inventory': row['header_inventory'],
            'header_sha256': digest(_data(header_files, 'plist/plist.h')),
            'module_map_sha256': digest(_data(header_files, 'libimobiledevice/module.modulemap')),
            'symbols': sorted(new_symbols), 'provider_identity': openssl, 'system_frameworks': SYSTEM_FRAMEWORKS,
            'sdk': sdk, 'sdk_version': observed[sdk + '_sdk_version'], 'sdk_build': observed[sdk + '_sdk_build'],
            'xcode': observed['xcode'], 'target': target, 'source_commit': s['source_commit']}
    operation = _json(outer, 'work/evidence/xcframework-operation.json')
    require(operation == receipt.get('xcframework_operation') and operation.get('schema') == 1
            and operation.get('operation_source') == 'Integration/Dependencies/idevice/xcframework_operation.py'
            and operation.get('operation_sha256') == digest(members['recipe/idevice/xcframework_operation.py'][0])
            and operation.get('ios_payloads_executed') is False and operation.get('timeout_seconds') == 900,
            'C XCFramework operation provenance differs')
    args = operation['operation_command']; command = operation['xcodebuild_command']
    expected_arguments = [part for row in slices for part in (row['library'], row['headers'])]
    require(len(args) == 8 and args[1] == '-I' and Path(args[0]).is_absolute()
            and args[2].endswith('/Integration/Dependencies/idevice/xcframework_operation.py')
            and args[3:7] == expected_arguments and Path(args[-1]).is_absolute()
            and command == ['/usr/bin/xcodebuild', '-create-xcframework', '-library', slices[0]['library'],
                '-headers', slices[0]['headers'], '-library', slices[1]['library'], '-headers', slices[1]['headers'], '-output', args[-1]]
            and operation['operation_command_sha256'] == digest(json.dumps(args, separators=(',', ':'), ensure_ascii=False).encode())
            and operation['xcodebuild_command_sha256'] == digest(json.dumps(command, separators=(',', ':'), ensure_ascii=False).encode()),
            'C XCFramework operation command does not use the two tested slices')
    actual_command, _log = command_for('create-xcframework')
    require(actual_command == args, 'C XCFramework successful command differs')
    require(result['aarch64-apple-ios']['symbols'] == result['aarch64-apple-ios-sim']['symbols'], 'C slice export sets differ')
    return product, result


def verify(root, target, *, expected_handoff_sha256, selection_path=None):
    s = load_selection(selection_path)
    require(_sha(expected_handoff_sha256), 'C handoff needs the caller-computed hash')
    handoff_file = safe_file(root, 'handoff.json')
    require(file_hash(handoff_file) == expected_handoff_sha256, 'C caller handoff hash differs')
    handoff = read_json_bytes(handoff_file.read_bytes())
    require(handoff.get('schema') == 1 and handoff.get('selection') == s, 'C handoff selected context differs')
    api = {}
    require(isinstance(handoff.get('api_files'), dict) and handoff['api_files'], 'C retained API inventory missing')
    for name, sha in handoff['api_files'].items():
        require(name.startswith('api/') and _sha(sha), 'C retained API inventory path differs')
        path = safe_file(root, name)
        require(path.stat().st_size <= MAX_JSON and file_hash(path) == sha, 'C retained API evidence changed')
        api[name.removeprefix('api/')] = read_json_bytes(path.read_bytes())
    for name in ('run-before.json', 'run-after.json'):
        verify_run(api[name], s)
    verify_job(api['job.json'], s)
    verify_artifact_metadata(api['artifact.json'], s)
    # Complete retained pagination cannot silently omit the exact job/artifact.
    def pages(stem, key):
        names = sorted(n for n in api if n.startswith(stem + '-'))
        require(names and names == [stem + '-%02d.json' % n for n in range(1, len(names) + 1)] and len(names) <= 20,
                'C retained pagination sequence differs')
        rows, total = [], None
        for name in names:
            page = api[name]; count = page.get('total_count'); items = page.get(key)
            require(type(count) is int and 0 <= count <= 2000 and (total is None or count == total)
                    and isinstance(items, list) and len(items) <= 100, 'C retained pagination count differs')
            total = count; rows.extend(items)
        require(len(rows) == total and all(_number(row.get('id')) for row in rows)
                and len({r['id'] for r in rows}) == len(rows), 'C retained listing incomplete or duplicated')
        return rows
    jobs, artifacts = pages('jobs', 'jobs'), pages('artifacts', 'artifacts')
    require([x for x in jobs if x.get('name') == 'c-provider'] == [api['job.json']]
            and [x for x in artifacts if x.get('id') == s['artifact_id']] == [api['artifact.json']], 'C listed identity differs')
    archive = safe_file(root, 'actions-artifact.zip')
    require(archive.stat().st_size == s['size_in_bytes'] and file_hash(archive) == s['archive_sha256'], 'C outer Actions ZIP digest/size differs')
    outer = zip_files(archive)
    product, targets = validate_product(outer, s, api['source-commit.json'], api['source-tree.json'])
    expected_files = {'product/' + n: digest(raw) for n, raw in product.items()}
    require(handoff.get('product_files') == expected_files, 'C extracted product inventory differs')
    actual = set()
    for p in root.rglob('*'):
        require(not p.is_symlink(), 'C retained tree symlink')
        if p.is_file(): actual.add(p.relative_to(root).as_posix())
    require(actual == set(expected_files) | set(handoff['api_files']) | {'actions-artifact.zip', 'handoff.json'}, 'C retained tree missing or extra files')
    for name, sha in expected_files.items():
        require(file_hash(safe_file(root, name)) == sha, 'C retained product bytes changed')
    require(target.get('rust') in targets and target.get('sdk') == targets[target['rust']]['sdk'], 'C target platform differs')
    result = dict(targets[target['rust']])
    result.update({'archive_sha256': s['archive_sha256'], 'handoff_sha256': expected_handoff_sha256,
        'receipt_sha256': digest(product['producer-receipt.json']),
        'library': str(root / 'product' / result['library_relative']),
        'headers': str(root / 'product' / result['headers_relative']), 'binary_format_inspected': False})
    return result
