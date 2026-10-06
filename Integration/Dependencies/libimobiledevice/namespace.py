"""Exact source-only Ed25519 SHA512 isolation. No binary rewriting or algorithm edits."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
IDENTIFIERS = {name: 'tetherless_c_ed25519_' + name for name in
               ('sha512', 'sha512_init', 'sha512_update', 'sha512_final')}
# Consume comments/literals first. Include filenames and quoted text are untouched.
TOKENS = re.compile(rb'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_][A-Za-z_0-9]*', re.S)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def transform(data: bytes, inverse: bool = False) -> tuple[bytes, int]:
    mapping = {k.encode(): v.encode() for k, v in IDENTIFIERS.items()}
    if inverse:
        mapping = {v: k for k, v in mapping.items()}
    count = 0
    def replace(match):
        nonlocal count
        token = match.group()
        if token in mapping:
            count += 1
            return mapping[token]
        return token
    return TOKENS.sub(replace, data), count


def code_references(data: bytes, names=None) -> list[str]:
    wanted = {x.encode() for x in (names or IDENTIFIERS)}
    return [m.group().decode() for m in TOKENS.finditer(data) if m.group() in wanted]


def load_contract() -> dict:
    return json.loads((HERE / 'namespace-contract.json').read_text())


def verify_retained_sources() -> dict:
    observed = {}
    for key in ('root', 'plist', 'glue', 'usbmuxd'):
        tree = json.loads((HERE / 'provenance' / (key + '-tree.json')).read_text())
        if tree.get('truncated') is not False:
            raise ValueError('incomplete source tree: ' + key)
        entries = {x['path']: x for x in tree['tree'] if x['type'] == 'blob'}
        for file in sorted((HERE / 'upstream' / key).rglob('*')):
            if file.is_symlink():
                raise ValueError('source symlink')
            if file.is_file():
                rel = file.relative_to(HERE / 'upstream' / key).as_posix()
                row, raw = entries[rel], file.read_bytes()
                if len(raw) != row['size'] or git_blob(raw) != row['sha']:
                    raise ValueError('retained source differs: ' + key + '/' + rel)
                observed[key + '/' + rel] = {'git_blob': row['sha'], 'sha256': sha256(raw), 'bytes': len(raw)}
    return observed


def apply_to_directory(root: Path) -> dict:
    """Root is the main libimobiledevice checkout, not the four-source parent."""
    root = root.resolve(strict=True)
    contract = load_contract()
    staged = {}
    for rel, row in contract['files'].items():
        path = root / rel
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root.parent):
            raise ValueError('patch path is not a regular owned file')
        before = path.read_bytes()
        if sha256(before) != row['before_sha256'] or git_blob(before) != row['before_git_blob']:
            raise ValueError('patch preimage mismatch: ' + rel)
        after, count = transform(before)
        if (count != row['tokens'] or sha256(after) != row['after_sha256'] or
                git_blob(after) != row['after_git_blob'] or transform(after, True) != (before, count)):
            raise ValueError('identifier-only inverse proof failed: ' + rel)
        staged[rel] = after
    # Authenticate and scan the entire bundled subtree, including non-edited callers.
    tree = json.loads((HERE / 'provenance/root-tree.json').read_text())
    expected = {x['path']: x for x in tree['tree'] if x['type'] == 'blob' and
                x['path'].startswith('3rd_party/ed25519/')}
    actual = {p.relative_to(root).as_posix() for p in (root / '3rd_party/ed25519').rglob('*') if p.is_file()}
    if actual != set(expected):
        raise ValueError('incomplete or additional Ed25519 source')
    references = {}
    for rel, row in expected.items():
        p = root / rel
        if p.is_symlink() or git_blob(p.read_bytes()) != row['sha']:
            raise ValueError('Ed25519 source identity mismatch: ' + rel)
        if p.suffix in ('.c', '.h'):
            refs = code_references(p.read_bytes())
            if refs:
                references[rel] = refs
            if code_references(staged.get(rel, p.read_bytes())):
                raise ValueError('unrenamed Ed25519 reference: ' + rel)
    if set(references) != set(contract['files']) or sum(map(len, references.values())) != 30:
        raise ValueError('caller inventory differs')
    for rel, data in staged.items():
        (root / rel).write_bytes(data)
    return {'schema': 1, 'contract_sha256': sha256((HERE / 'namespace-contract.json').read_bytes()),
            'changed_files': contract['files'], 'tokens_changed': 30,
            'all_ed25519_callers_covered': True, 'inverse_identifier_only': True,
            'context_layouts_unchanged': True, 'algorithm_bodies_unchanged': True,
            'binary_rewriting': False}
