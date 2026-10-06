"""Authenticate pinned source trees and retain pristine bytes before offline builds."""
from __future__ import annotations
import json
import hashlib
import re
from pathlib import Path, PurePosixPath
import shutil
import stat
from namespace import HERE, git_blob, sha256, code_references

SOURCES = {
    'root': ('SideStore/libimobiledevice-xcframework', '0f88f7bbd1aa9713d8c8c2255df31f2b25ff9d8a'),
    'plist': ('libimobiledevice/libplist', '32428abacb909988e8e960a8845a6430b17b6a60'),
    'glue': ('libimobiledevice/libimobiledevice-glue', 'da770a7687f35fbb981db4d7b47b1b032cd5c2c7'),
    'usbmuxd': ('libimobiledevice/libusbmuxd', '93eb168bf6b07472d17781328c21df0c60300524'),
}


def safe_file(root: Path, name: str) -> Path:
    p = PurePosixPath(name)
    if not p.parts or p.is_absolute() or p.as_posix() != name or '\\' in name or '..' in p.parts:
        raise ValueError('unsafe source path')
    path = root
    for part in p.parts:
        path /= part
        if path.is_symlink():
            raise ValueError('source symlink')
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('nonregular source')
    return path


def verify_tree_metadata(key, data):
    commit=json.loads((HERE/'provenance/commits.json').read_bytes())[key]
    if commit['commit']!=SOURCES[key][1] or commit['repository']!=SOURCES[key][0]:
        raise ValueError('source commit metadata differs')
    entries=data['tree']
    if len({x['path'] for x in entries})!=len(entries):raise ValueError('duplicate Git tree entry')
    expected={'':commit['tree'],**{x['path']:x['sha'] for x in entries if x['type']=='tree'}}
    for row in entries:
        path=PurePosixPath(row['path']);parent=str(path.parent)
        if (not path.parts or path.is_absolute() or path.as_posix()!=row['path'] or
                '..' in path.parts or '\\' in row['path'] or
                (parent!='.' and parent not in expected)):
            raise ValueError('unreachable or unsafe Git tree entry')
        allowed={'blob':('100644','100755'),'tree':('040000',),'commit':('160000',)}
        if row['type'] not in allowed or row['mode'] not in allowed[row['type']] or not re.fullmatch('[a-f0-9]{40}',row['sha']):
            raise ValueError('unsupported Git entry type/mode/hash')
        if row['type']=='blob' and (type(row['size']) is not int or not 0<=row['size']<=16*1024*1024):
            raise ValueError('source blob size outside bound')
    for parent,wanted in expected.items():
        children=[x for x in entries if str(PurePosixPath(x['path']).parent)==(parent or '.')]
        children.sort(key=lambda x:(PurePosixPath(x['path']).name+('/' if x['type']=='tree' else '')).encode())
        raw=b''.join((x['mode'].lstrip('0')+' '+PurePosixPath(x['path']).name).encode()+b'\0'+bytes.fromhex(x['sha']) for x in children)
        actual=hashlib.sha1(b'tree '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if actual!=wanted:raise ValueError('incomplete or changed Git tree metadata: '+key+'/'+parent)
    if key=='root':
        links={x['path']:x['sha'] for x in entries if x['type']=='commit'}
        wanted={'Dependencies/libplist':SOURCES['plist'][1], 'Dependencies/libimobiledevice-glue':SOURCES['glue'][1], 'Dependencies/libusbmuxd':SOURCES['usbmuxd'][1]}
        if links!=wanted:raise ValueError('root submodule pins differ')
    return commit


def source_inventory(key: str) -> list[dict]:
    data = json.loads((HERE / 'provenance' / (key + '-tree.json')).read_bytes())
    if data.get('truncated') is not False or data['sha'] != SOURCES[key][1]:
        raise ValueError('source tree provenance changed')
    verify_tree_metadata(key,data)
    rows = [row for row in data['tree'] if row['type'] == 'blob']
    if len({x['path'] for x in rows}) != len(rows) or any(x['mode'] not in ('100644', '100755') for x in rows):
        raise ValueError('source file modes or duplicates')
    return rows


def retain_sources(acquisition: Path, output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise ValueError('source capture destination must be new')
    output.mkdir(parents=True)
    manifests, references = {}, {}
    for key, (repository, commit) in SOURCES.items():
        source = acquisition / key
        if source.is_symlink():
            raise ValueError('source root symlink')
        rows = source_inventory(key)
        expected = {row['path'] for row in rows}
        actual = set()
        for p in source.rglob('*'):
            rel = p.relative_to(source).as_posix()
            if rel == '.git' or rel.startswith('.git/'):
                continue
            if p.is_symlink():
                raise ValueError('unexpected acquisition symlink')
            if p.is_file():
                actual.add(rel)
        if actual != expected:
            raise ValueError('missing or unlisted acquired sources: ' + key)
        retained = {}
        for row in rows:
            path = safe_file(source, row['path'])
            data = path.read_bytes()
            if len(data) != row['size'] or git_blob(data) != row['sha'] or bool(path.stat().st_mode & 0o111) != (row['mode'] == '100755'):
                raise ValueError('source identity mismatch: ' + key + '/' + row['path'])
            destination = output / key / row['path']
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            destination.chmod(int(row['mode'][-3:], 8))
            retained[row['path']] = {'git_blob': row['sha'], 'sha256': sha256(data), 'bytes': len(data), 'mode': row['mode']}
            if path.suffix in ('.c', '.h'):
                refs = code_references(data)
                if refs:
                    references[key + '/' + row['path']] = refs
        manifests[key] = {'repository': repository, 'commit': commit,
                          'tree':json.loads((HERE/'provenance/commits.json').read_bytes())[key]['tree'],'files': retained}
    receipt = {'schema': 1, 'sources': manifests, 'complete_sha512_reference_scan': references,
               'source_changed': False, 'network_acquisition_complete': True}
    (output / 'source-receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    return receipt


def verify_retained(root: Path) -> dict:
    receipt = json.loads((root / 'source-receipt.json').read_bytes())
    for key in SOURCES:
        rows = {r['path']: r for r in source_inventory(key)}
        files = receipt['sources'][key]['files']
        if set(files) != set(rows):
            raise ValueError('source receipt inventory')
        actual = {p.relative_to(root/key).as_posix() for p in (root/key).rglob('*') if p.is_file()}
        if actual != set(rows):
            raise ValueError('retained source inventory')
        for name, row in rows.items():
            path = safe_file(root/key, name); data = path.read_bytes()
            if git_blob(data) != row['sha'] or sha256(data) != files[name]['sha256']:
                raise ValueError('retained source changed')
    return receipt
