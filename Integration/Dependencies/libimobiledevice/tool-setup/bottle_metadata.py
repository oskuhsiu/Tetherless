"""Authenticate retained Homebrew OCI tabs and inspect bottles without execution."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile

HERE=Path(__file__).resolve().parent
MANIFEST_SHA256={
    'm4':'1cefcb897b62a20fb5398e5298d71dbb9c4a4e5eda38bfab8a29ddfd13ae2909',
    'autoconf':'2ad7776399477f44bf3bb208daa7625f374e98364453ec51041bc4162fe768e2',
    'automake':'31e552ff7c996235c7d5f3a0da8d9e8ae85af17fdc8fa8f4dedd28393a6e3692',
    'libtool':'10d17fd9c2f413dcb78ebaad54e13c796a54a6c68ac278b92d4adaa474e75752',
}

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')

def runtime_names(name,lock):
    result=set();pending=list(lock['formulas'][name]['dependencies'])
    while pending:
        dep=pending.pop()
        if dep not in MANIFEST_SHA256 or dep==name:raise ValueError('bottle dependency outside approved closure')
        if dep not in result:
            result.add(dep);pending.extend(lock['formulas'][dep]['dependencies'])
    return result

def verify_manifest(path,name,lock):
    if name not in MANIFEST_SHA256:raise ValueError('unapproved bottle manifest')
    if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=4*1024*1024:
        raise ValueError('bottle manifest file/bound mismatch')
    if digest(path)!=MANIFEST_SHA256[name]:raise ValueError('bottle manifest identity differs')
    data=json.loads(path.read_bytes());row=lock['formulas'][name]
    if data.get('schemaVersion')!=2 or data.get('mediaType','application/vnd.oci.image.index.v1+json')!='application/vnd.oci.image.index.v1+json':
        raise ValueError('unexpected bottle manifest schema')
    ref=row['version']+'.'+lock['bottle_tag']
    if row['bottle_rebuild']:ref+='.'+str(row['bottle_rebuild'])
    matches=[m for m in data.get('manifests',[]) if m.get('annotations',{}).get('sh.brew.bottle.digest')==row['bottle_sha256']
             and m.get('annotations',{}).get('org.opencontainers.image.ref.name')==ref]
    if len(matches)!=1:raise ValueError('one exact bottle digest and platform reference required')
    selected=matches[0];platform=selected.get('platform',{})
    if selected.get('mediaType')!='application/vnd.oci.image.manifest.v1+json' or platform.get('architecture')!='arm64' or platform.get('os')!='darwin':
        raise ValueError('bottle manifest platform differs')
    annotations=selected['annotations'];tab=json.loads(annotations['sh.brew.tab'])
    deps=tab.get('runtime_dependencies')
    if not isinstance(deps,list):raise ValueError('authenticated bottle runtime metadata missing')
    names=[dep.get('full_name') for dep in deps]
    if len(names)!=len(set(names)) or set(names)!=runtime_names(name,lock):
        raise ValueError('bottle runtime dependency closure differs')
    for dep in deps:
        expected=lock['formulas'][dep['full_name']]
        wanted={'version':expected['version'],'revision':expected['revision'],
                'bottle_rebuild':expected['bottle_rebuild'],'pkg_version':expected['version'],
                'compatibility_version':expected['compatibility_version'],
                'declared_directly':dep['full_name'] in row['dependencies']}
        if any(type(dep.get(key)) is not type(value) or dep[key]!=value for key,value in wanted.items()):
            raise ValueError('bottle runtime dependency identity differs')
    return {'path':str(path),'sha256':MANIFEST_SHA256[name],'bytes':path.stat().st_size,
            'image_ref':ref,'descriptor_digest':selected['digest'],'platform':platform,
            'bottle_bytes':int(annotations['sh.brew.bottle.size']),'tab':tab}

def verify_retained_manifests(lock):
    if set(lock['formulas'])!=set(MANIFEST_SHA256):raise ValueError('four bottle manifests required')
    return {name:verify_manifest(HERE/'bottle-manifests'/(name+'.json'),name,lock) for name in MANIFEST_SHA256}

def cached_manifest(cache,name,lock):
    row=lock['formulas'][name];version=row['version']
    if row['bottle_rebuild']:version+='-'+str(row['bottle_rebuild'])
    # The observed official Bottle resource names this file explicitly.
    matches=list((cache/'downloads').glob('*--'+name+'-'+version+'.bottle_manifest.json'))
    if len(matches)!=1:raise ValueError('one owned cached bottle manifest required')
    path=matches[0]
    if not path.resolve(strict=True).is_relative_to(cache.resolve(strict=True)):
        raise ValueError('cached bottle manifest outside owned cache')
    return verify_manifest(path,name,lock)

def inspect_bottle(path,name,lock,cache,output):
    row=lock['formulas'][name]
    evidence=output/(name+'-bottle-inspection.json')
    report={'schema':1,'name':name,'state':'inspecting','path':str(path),'expected_sha256':row['bottle_sha256']}
    primary=None
    try:
        if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=64*1024*1024:
            raise ValueError('bottle file/bound mismatch')
        report.update(bytes=path.stat().st_size,sha256=digest(path))
        if report['sha256']!=row['bottle_sha256']:raise ValueError('bottle byte identity mismatch')
        retained=output/'retained-bottles';retained.mkdir(exist_ok=True)
        destination=retained/(name+'--'+row['version']+'.bottle.tar.gz')
        if destination.exists():raise ValueError('retained bottle output must be fresh')
        shutil.copyfile(path,destination);report['retained_bottle']=str(destination)
        if digest(destination)!=report['sha256']:raise ValueError('retained bottle copy differs')
        inventory=[];receipts=[];unpacked=0
        report['members']=inventory;report['receipt_paths']=[]
        with tarfile.open(path,'r:gz') as archive:
            for member in archive:
                unpacked+=member.size
                if len(inventory)>=20000 or unpacked>256*1024*1024:raise ValueError('bottle inventory bound')
                part=PurePosixPath(member.name)
                if part.is_absolute() or '..' in part.parts:raise ValueError('unsafe bottle member path')
                inventory.append({'name':member.name,'size':member.size,'type':member.type.decode('ascii'),'linkname':member.linkname})
                if member.name.endswith('/INSTALL_RECEIPT.json'):
                    report['receipt_paths'].append(member.name)
                    if member.name!=name+'/'+row['version']+'/INSTALL_RECEIPT.json' or not member.isfile() or member.size>1024*1024:
                        raise ValueError('unexpected embedded bottle receipt')
                    receipts.append(json.load(archive.extractfile(member)))
        report['inventory_complete']=True
        if len(receipts)>1:raise ValueError('duplicate embedded bottle receipts')
        manifest=cached_manifest(cache,name,lock);report['manifest']=manifest
        if manifest['bottle_bytes']!=report['bytes']:raise ValueError('manifest bottle size differs')
        shutil.copyfile(Path(manifest['path']),output/(name+'-bottle-manifest.json'))
        if receipts and receipts[0].get('runtime_dependencies')!=manifest['tab']['runtime_dependencies']:
            raise ValueError('embedded and authenticated manifest runtime metadata differ')
        report['runtime_dependencies']=manifest['tab']['runtime_dependencies']
        report['metadata_format']='authenticated-oci-sh.brew.tab'
        report['state']='verified'
        return report
    except BaseException as error:
        primary=error
        report['state']='failed';report['error']={'type':type(error).__name__,'text':str(error)}
        raise
    finally:
        try:write(evidence,report)
        except Exception as error:
            if primary is None:raise
            primary.add_note('bottle evidence write failed: '+str(error))

def audit_bottle_inputs(bottles):
    for report in bottles.values():
        for path,expected in [(report['path'],report['sha256']),
                              (report['manifest']['path'],report['manifest']['sha256'])]:
            if digest(Path(path))!=expected:raise ValueError('verified bottle input changed')
