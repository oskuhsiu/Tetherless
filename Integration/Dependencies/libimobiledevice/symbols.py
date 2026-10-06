"""Strict, bounded ordinary nm/link-map text acceptance; no binary parser."""
from __future__ import annotations
from collections import Counter
import re
from pathlib import Path
from namespace import IDENTIFIERS, sha256

MAX_TEXT = 32 * 1024 * 1024
REQUIRED = {'_plist_new_dict', '_plist_free', '_plist_array_set_item', '_afc_client_free',
            '_lockdownd_client_free', '_idevice_free'}
GLUE = {'_' + n for n in IDENTIFIERS}
ED = {'_' + n for n in IDENTIFIERS.values()}


def exported(text: str, *, unique=True) -> set[str]:
    if len(text.encode()) > MAX_TEXT:
        raise ValueError('nm output too large')
    names = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.endswith(':'):
            continue
        if not re.fullmatch(r'[_A-Za-z.$][_A-Za-z0-9.$]*', line):
            raise ValueError('unexpected nm output: ' + line[:120])
        names.append(line)
    counts = Counter(names)
    if not names or (unique and any(v != 1 for v in counts.values())):
        raise ValueError('empty scan or duplicated C global definitions: ' + ','.join(k for k,v in counts.items() if v != 1))
    return set(names)


def compare(old_text: str, new_text: str) -> dict:
    old, new = exported(old_text, unique=False), exported(new_text)
    if new != old | ED or not REQUIRED | GLUE | ED <= new or ED & old:
        raise ValueError('C global exports differ from exact old-plus-four contract')
    return {'schema': 1, 'global_count': len(new), 'symbols': sorted(new),
            'internal_global_definitions_unique': True, 'exact_old_plus_four': True,
            'nm_sha256': sha256(new_text.encode()), 'old_nm_sha256': sha256(old_text.encode())}


def link_ownership(text: str, library: Path, required: set[str]) -> dict:
    if len(text.encode()) > MAX_TEXT:
        raise ValueError('link map too large')
    objects, symbols = {}, {}
    section = None
    for line in text.splitlines():
        if line.startswith('# Object files:'):
            section = 'objects'
        elif line == '# Sections:':
            if section != 'objects':
                raise ValueError('unexpected link-map sections transition')
            section = 'sections'
        elif line.startswith('# Symbols:'):
            section = 'symbols'
        elif line.startswith('# Dead Stripped Symbols:'):
            section = None
        elif line.startswith('#'):
            continue
        elif section == 'objects' and line.strip():
            m = re.fullmatch(r'\[\s*(\d+)\]\s+(.+)', line)
            if not m or m[1] in objects:
                raise ValueError('malformed or duplicate map object')
            objects[m[1]] = m[2]
        elif section == 'sections' and line.strip():
            if not re.fullmatch(r'0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+[_A-Za-z.$][_A-Za-z0-9.$]*\s+[_A-Za-z.$][_A-Za-z0-9.$]*', line):
                raise ValueError('unparsed link-map section row')
        elif section == 'symbols' and line.strip():
            m = re.fullmatch(r'0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+(.+)', line)
            if not m:
                raise ValueError('unparsed live link-map row')
            if m[2] in required:
                if m[2] in symbols:
                    raise ValueError('ambiguous required map symbol')
                symbols[m[2]] = m[1]
    if set(symbols) != required:
        raise ValueError('required global missing from live map: ' + ','.join(sorted(required-set(symbols))))
    # Accept the two Apple map archive member spellings, never a substring path.
    prefix = str(library.resolve(strict=True))
    for name, owner in symbols.items():
        obj = objects.get(owner, '')
        if not re.fullmatch(re.escape(prefix) + r'(?:\[\d+\])?\([^()]+\)', obj):
            raise ValueError('required global has wrong archive owner: ' + name)
    ed_owners = {symbols[x] for x in ED}
    glue_owners = {symbols[x] for x in GLUE}
    if len(ed_owners) != 1 or len(glue_owners) != 1 or ed_owners & glue_owners:
        raise ValueError('SHA512 families are not owned by two distinct real members')
    return {'schema': 1, 'required_live_symbols': len(required), 'owners': symbols,
            'ed25519_sha512_member': objects[next(iter(ed_owners))],
            'glue_sha512_member': objects[next(iter(glue_owners))],
            'map_sha256': sha256(text.encode())}
