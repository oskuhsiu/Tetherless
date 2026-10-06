#!/usr/bin/env python3
"""New isolated two-slice C derivation. Build offline; no consumer admission."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import sys
import tarfile
import zipfile

HERE = Path(__file__).resolve().parent
SIBLING = HERE.parent / 'idevice'
REPOSITORY = HERE.parents[2]
sys.path.insert(0, str(SIBLING))
from bounded_process import capture_helper_command
from mixed_provider import prepare as prepare_old, verify as verify_old
from namespace import apply_to_directory, sha256, git_blob, code_references, load_contract, verify_retained_sources
from source_inputs import retain_sources, verify_retained, source_inventory, safe_file, SOURCES
from symbols import compare, exported, link_ownership

APPLE = {'xcode': 'Xcode 26.3\nBuild version 17C529', 'macos_version': '15.7.9',
         'macos_build': '24G830', 'sdk_version': '26.2', 'sdk_build': '23C57',
         'clang': 'Apple clang version 17.0.0 (clang-1700.6.4.2)',
         'swift': 'Apple Swift version 6.2.4 (swiftlang-6.2.4.1.4 clang-1700.6.4.2)'}
DEVELOPER = '/Applications/Xcode_26.3.app/Contents/Developer'
TARGETS = [('iphoneos', 'arm64-apple-ios13.0', 'aarch64-apple-ios'),
           ('iphonesimulator', 'arm64-apple-ios13.0-simulator', 'aarch64-apple-ios-sim')]
FRAMEWORKS = ['-framework', 'CoreFoundation', '-framework', 'SystemConfiguration']


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def inventory(root):
    rows = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise ValueError('unexpected output/source symlink: ' + str(p))
        if p.is_file():
            rows[p.relative_to(root).as_posix()] = {'sha256': sha256(p.read_bytes()), 'bytes': p.stat().st_size}
    return rows


def recipe_inventory():
    rows={}
    for root,key in [(HERE,'libimobiledevice'),(SIBLING,'idevice')]:
        for p in sorted(root.rglob('*')):
            if '__pycache__' in p.parts or any(x.startswith('.test-output-') for x in p.parts): continue
            if p.is_symlink(): raise ValueError('recipe symlink')
            if p.is_file(): rows[key+'/'+p.relative_to(root).as_posix()]={'sha256':sha256(p.read_bytes()),'bytes':p.stat().st_size}
    for rel in ['.github/workflows/c-provider-native.yml','LICENSE']:
        p=REPOSITORY/rel
        if p.is_symlink():raise ValueError('recipe auxiliary symlink')
        rows[rel]={'sha256':sha256(p.read_bytes()),'bytes':p.stat().st_size}
    return rows


def closure_inventory(prefix):
    rows={};total=0
    for p in sorted(prefix.rglob('*')):
        rel=p.relative_to(prefix).as_posix()
        if p.is_symlink(): rows[rel]={'symlink':os.readlink(p)}
        elif p.is_file():
            total+=p.stat().st_size
            if total>128*1024*1024: raise ValueError('tool installation closure over quota')
            rows[rel]={'sha256':sha256(p.read_bytes()),'bytes':p.stat().st_size}
    return rows


def audit_derived_sources(sources):
    contract=load_contract(); references={};count=0
    for key in SOURCES:
        for row in source_inventory(key):
            p=safe_file(sources/key,row['path']);raw=p.read_bytes()
            changed=contract['files'].get(row['path']) if key=='root' else None
            expected=changed['after_git_blob'] if changed else row['sha']
            if git_blob(raw)!=expected:raise ValueError('compiled source changed: '+key+'/'+row['path'])
            count+=1
            if p.suffix in ('.c','.h'):
                refs=code_references(raw)
                if refs:references[key+'/'+row['path']]=refs
    return {'preserved_source_files':count,'complete_original_sha512_reference_scan':references,
            'only_registered_identifier_changes':True}


def final_audits(args):
    evidence=args.work.resolve()/'evidence'
    report={'schema':1,'checks':{},'primary_failure_preserved':True}
    def check(name,operation):
        try:
            operation();report['checks'][name]={'passed':True}
        except Exception as error:
            report['checks'][name]={'passed':False,'error_type':type(error).__name__,'error':str(error)}
    check('pristine_source',lambda:verify_retained(args.source.resolve(strict=True)))
    check('openssl_inputs',lambda:load_openssl().verify_inputs(args.openssl.resolve(strict=True)))
    for sdk,_,target in TARGETS:
        check('original_c_'+sdk,lambda sdk=sdk,target=target:verify_old(args.old_provider.resolve(strict=True),{'sdk':sdk,'rust':target}))
    def recipe():
        expected=json.loads((evidence/'recipe-inputs.json').read_bytes())
        if recipe_inventory()!=expected:raise ValueError('recipe inputs changed during build')
    check('recipe_inputs',recipe)
    for sdk,_,_ in TARGETS:
        prepared=args.work.resolve()/sdk/'sources'
        if prepared.exists():check('derived_sources_'+sdk,lambda prepared=prepared:audit_derived_sources(prepared))
    def toolchain():
        observed=json.loads((evidence/'toolchain.json').read_bytes())
        for name,row in observed['tools'].items():
            if sha256(Path(row['path']).read_bytes())!=row['sha256']:raise ValueError('tool changed: '+name)
        for prefix,rows in observed['tool_installation_closures'].items():
            if closure_inventory(Path(prefix))!=rows:raise ValueError('tool installation closure changed: '+prefix)
        if sha256((args.work.resolve()/'tool-macros/pkg.m4').read_bytes())!=observed['pkg_m4_sha256']:
            raise ValueError('copied pkg-config macro changed')
    check('toolchain_inputs',toolchain)
    report['all_passed']=all(x['passed'] for x in report['checks'].values())
    write(evidence/'final-input-audit.json',report)
    return report


class Runner:
    def __init__(self, work):
        self.work = work
        self.evidence = work/'evidence'
        self.evidence.mkdir(parents=True)
        self.env = {'PATH': '/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                    'HOME': str(work/'home'), 'TMPDIR': str(work/'tmp'),
                    'LANG': 'en_US.UTF-8', 'LC_ALL': 'en_US.UTF-8',
                    'DEVELOPER_DIR': DEVELOPER, 'ZERO_AR_DATE': '1',
                    'SOURCE_DATE_EPOCH': '1787737542'}
        for name in ('home', 'tmp'):
            (work/name).mkdir()
        self.serial = 0
    def run(self, command, label, cwd=None, env=None, seconds=900):
        self.serial += 1
        log = self.evidence / ('%03d-%s.txt' % (self.serial, label))
        capture_helper_command([str(x) for x in command], source=cwd or self.work,
            env=env or self.env, log=log, timeout_seconds=seconds)
        # Complete log, never a supervisor's bounded summary tail.
        data = log.read_bytes()
        if len(data) > 32*1024*1024:
            raise ValueError('retained log over quota')
        return data.decode('utf-8').strip()


def load_openssl():
    path = SIBLING/'split-provider/provider_inputs.py'
    spec = importlib.util.spec_from_file_location('c_provider_openssl', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_preinstalled_tool(name,command,path):
    # Homebrew m4 is keg-only. Never silently replace Autoconf's GNU dependency
    # with the older /usr/bin/m4 or install/relink a missing dependency.
    found='/opt/homebrew/opt/m4/bin/m4' if name=='m4' else shutil.which(command,path=path)
    if not found or not Path(found).is_file():
        raise ValueError('required preinstalled tool missing; installation not authorized: '+name)
    resolved=Path(found).resolve(strict=True)
    if name=='m4' and not str(resolved).startswith('/opt/homebrew/Cellar/m4/'):
        raise ValueError('m4 must resolve to the existing Homebrew GNU m4 installation')
    return resolved


def fingerprint(r):
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('requires existing arm64 macOS runner')
    observations = {}
    for key, cmd in [('xcode',['/usr/bin/xcodebuild','-version']),
            ('macos_version',['/usr/bin/sw_vers','-productVersion']),
            ('macos_build',['/usr/bin/sw_vers','-buildVersion']),
            ('clang',['/usr/bin/xcrun','clang','--version']),
            ('swift',['/usr/bin/xcrun','swiftc','--version'])]:
        observations[key] = r.run(cmd, 'toolchain-'+key, seconds=60)
        if (observations[key] if key not in ('clang','swift') else observations[key].splitlines()[0]) != APPLE[key]:
            raise ValueError('Apple toolchain drift: '+key)
    for sdk, _, _ in TARGETS:
        for key, flag in [('sdk_version','--show-sdk-version'), ('sdk_build','--show-sdk-build-version')]:
            value = r.run(['/usr/bin/xcrun','--sdk',sdk,flag], sdk+'-'+key, seconds=60)
            observations[sdk+'_'+key] = value
            if value != APPLE[key]:
                raise ValueError('SDK drift: '+sdk+' '+key)
    for flag,expected in [('--show-sdk-version','26.2'),('--show-sdk-build-version','25C58')]:
        value=r.run(['/usr/bin/xcrun','--sdk','macosx',flag],'host-'+flag[2:],seconds=60)
        observations['host_'+flag[2:]]=value
        if value!=expected: raise ValueError('host SDK drift')
    paths, tools, closures = {}, {}, {}
    commands = {'autoconf':'autoconf','autoheader':'autoheader','automake':'automake',
                'aclocal':'aclocal','glibtoolize':'glibtoolize','pkg-config':'pkg-config',
                'm4':'m4','make':'make'}
    for name, command in commands.items():
        path = resolve_preinstalled_tool(name,command,r.env['PATH'])
        paths[name] = str(path)
        version = r.run([path,'--version'], 'tool-'+name, seconds=60)
        if name=='m4':
            match=re.search(r'^m4 \(GNU M4\) ([0-9]+)\.([0-9]+)\.([0-9]+)',version)
            if not match or tuple(map(int,match.groups())) < (1,4,16):
                raise ValueError('GNU m4 is absent or older than the accepted generator minimum')
        tools[name] = {'path':str(path),'sha256':sha256(path.read_bytes()),'version':version}
        if str(path).startswith('/opt/homebrew/Cellar/'):
            parts = path.parts
            prefix = Path(*parts[:6])
            # Freeze the selected tool's scripts/macros, not ambient Homebrew state.
            if str(prefix) not in closures:
                closures[str(prefix)] = closure_inventory(prefix)
    pkg = Path(paths['pkg-config']).parent.parent / 'share/aclocal/pkg.m4'
    if not pkg.is_file():
        raise ValueError('authenticated pkg-config macro not found in selected installation')
    macros = r.work/'tool-macros'; macros.mkdir()
    shutil.copyfile(pkg,macros/'pkg.m4')
    paths['macro_dir'] = str(macros)
    observations.update({'runner_image_os':os.environ.get('ImageOS'), 'runner_image_version':os.environ.get('ImageVersion'),
                         'tools':tools,'tool_installation_closures':closures,
                         'tool_pins_status':'first observed derivation; not an immutable runner label',
                         'pkg_m4_sha256':sha256(pkg.read_bytes())})
    write(r.evidence/'toolchain.json', observations)
    return paths, observations


def generated_version(source):
    text = (source/'NEWS').read_text()
    match = re.search(r'^Version\s+([0-9]+\.[0-9]+\.[0-9]+)', text, re.M)
    if not match:
        raise ValueError('pinned NEWS has no numeric release baseline')
    return match[1]+'-tetherless-c1'


def autotools(r, source, prefix, tools, env, options, stages):
    # Original autogen.sh does not set -e; invoke each equivalent stage separately
    # so a failed generator cannot be obscured by a later configure success.
    source.joinpath('.tarball-version').write_text(generated_version(source)+'\n')
    for name,args in [('glibtoolize',['--force','--copy']),
                      ('aclocal',['-I','m4','--system-acdir='+tools['macro_dir']]),
                      ('autoheader',[]),('automake',['--add-missing','--copy']),('autoconf',[])]:
        r.run([tools[name],*args], source.name+'-'+name, source, env)
    # Config tests are cross-target compile/link only, never phone execution.
    r.run(['/bin/sh',str(source/'configure'),'--prefix='+str(prefix),
           '--host=aarch64-apple-darwin','--build=arm64-apple-darwin',
           '--enable-static','--disable-shared',*options],source.name+'-configure',source,env)
    for directory, action in stages:
        r.run([tools['make'],'-C',directory,'-j3',action],source.name+'-'+directory+'-'+action,source,env,1200)


def build(args):
    work = args.work.resolve()
    if work.exists() or work.is_symlink():
        raise ValueError('build work must be fresh')
    work.mkdir(parents=True)
    args._work_created=True
    r = Runner(work)
    write(r.evidence/'recipe-inputs.json',recipe_inventory())
    write(r.evidence/'run-context.json', {'source_commit':os.environ.get('GITHUB_SHA'),
        'run_id':os.environ.get('GITHUB_RUN_ID'),'run_attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),
        'job':os.environ.get('GITHUB_JOB'),'new_derivation':True,'consumer_admitted':False,'ios_binaries_executed':False})
    verify_retained_sources()
    tools, observations = fingerprint(r)
    pristine = args.source.resolve(strict=True)
    source_receipt = verify_retained(pristine)
    provider = load_openssl()
    provider.verify_inputs(args.openssl.resolve(strict=True))
    old_root = args.old_provider.resolve(strict=True)
    baseline_headers = None
    records, exported_sets = [], []
    host = work/'host-sources'
    shutil.copytree(pristine,host)
    write(r.evidence/'namespace-host.json',apply_to_directory(host/'root'))
    # Host fixture binaries run only on the CI host. Native slices below never run.
    r.run([sys.executable, HERE/'host_tests.py','--source',host,'--output',work/'host-tests',
           '--cc',r.run(['/usr/bin/xcrun','--find','clang'],'find-host-clang',seconds=60),
           '--sdk',r.run(['/usr/bin/xcrun','--sdk','macosx','--show-sdk-path'],'host-sdk-path',seconds=60)],'host-tests',seconds=600)
    for sdk, triple, target in TARGETS:
        slice_dir=work/sdk; slice_dir.mkdir()
        sources=slice_dir/'sources'; shutil.copytree(pristine,sources)
        patch=apply_to_directory(sources/'root'); write(r.evidence/(sdk+'-namespace.json'),patch)
        prefix=slice_dir/'install'; prefix.mkdir()
        openssl=provider.prepare_inputs(args.openssl.resolve(strict=True),slice_dir/'openssl',target)
        write(r.evidence/(sdk+'-openssl.json'),openssl)
        sdkpath=r.run(['/usr/bin/xcrun','--sdk',sdk,'--show-sdk-path'],sdk+'-path',seconds=60)
        cc=r.run(['/usr/bin/xcrun','--sdk',sdk,'--find','clang'],sdk+'-clang-path',seconds=60)
        cxx=r.run(['/usr/bin/xcrun','--sdk',sdk,'--find','clang++'],sdk+'-clangxx-path',seconds=60)
        env=r.env.copy()
        flags=['-target',triple,'-isysroot',sdkpath,'-O3','-fPIC','-DHAVE_STPNCPY=1']
        env.update({'CC':cc,'CXX':cxx,'CFLAGS':shlex.join(flags),'CXXFLAGS':shlex.join(flags),
                    'LDFLAGS':shlex.join(['-target',triple,'-isysroot',sdkpath,'-L'+str(prefix/'lib')]),
                    'PKG_CONFIG':tools['pkg-config'],'PKG_CONFIG_LIBDIR':str(prefix/'lib/pkgconfig'),
                    'PKG_CONFIG_PATH':str(prefix/'lib/pkgconfig'),'PKG_CONFIG_SYSROOT_DIR':'','CPPFLAGS':'','ACLOCAL_PATH':'',
                    'M4':tools['m4'],'AUTOCONF':tools['autoconf'],'AUTOHEADER':tools['autoheader'],
                    'AUTOMAKE':tools['automake'],'ACLOCAL':tools['aclocal'],
                    'libtatsu_CFLAGS':' ','libtatsu_LIBS':' ',
                    'openssl_CFLAGS':'-I'+str(slice_dir/'openssl/include'),
                    'openssl_LIBS':shlex.join(openssl['final_link_arguments'])})
        write(r.evidence/(sdk+'-effective-build-environment.json'),env)
        plans=[('plist',['--without-cython','--without-tools','--without-tests'],[('libcnary','all'),('src','all'),('include','all'),('src','install'),('include','install')]),
               ('glue',[],[('src','all'),('include','all'),('src','install'),('include','install')]),
               ('usbmuxd',[],[('src','all'),('include','all'),('src','install'),('include','install')]),
               ('root',['--without-cython','--without-readline','--with-openssl','--without-gnutls','--without-mbedtls','--enable-debug','--enable-wireless-pairing'],
                [('3rd_party','all'),('common','all'),('src','all'),('include','all'),('src','install'),('include','install')])]
        for name,options,stages in plans:
            autotools(r,sources/name,prefix,tools,env,options,stages)
            shutil.copyfile(sources/name/'config.log',r.evidence/(sdk+'-'+name+'-config.log'))
            shutil.copyfile(sources/name/'config.h',r.evidence/(sdk+'-'+name+'-config.h'))
        write(r.evidence/(sdk+'-derived-source-audit.json'),audit_derived_sources(sources))
        config=(sources/'root/config.h').read_text()
        if '#define HAVE_WIRELESS_PAIRING 1' not in config or '#define HAVE_OPENSSL 1' not in config:
            raise ValueError('required C features missing')
        components=[prefix/'lib'/name for name in ('libimobiledevice-1.0.a','libplist-2.0.a','libimobiledevice-glue-1.0.a','libusbmuxd-2.0.a')]
        library=slice_dir/'libimobiledevice.a'
        r.run(['/usr/bin/xcrun','libtool','-static','-o',library,*components],sdk+'-merge')
        # Keep exact upstream public/module header bytes, never provider-private Ed headers.
        headers=prefix/'include'
        module=(HERE/'upstream/root/justfile').read_text().split("export MODULEMAP := '''\n",1)[1].split("\n'''",1)[0]+'\n'
        (headers/'libimobiledevice/module.modulemap').write_text(module)
        old=verify_old(old_root,{'sdk':sdk,'rust':target})
        old_header_inventory=inventory(Path(old['headers']))
        current_headers=inventory(headers)
        if current_headers != old_header_inventory:
            write(r.evidence/(sdk+'-header-difference.json'),{'old':old_header_inventory,'new':current_headers})
            raise ValueError('public header/module inventory differs from original C provider')
        if baseline_headers is not None and current_headers != baseline_headers:
            raise ValueError('C public headers differ across slices')
        baseline_headers=current_headers
        old_symbols=r.run(['/usr/bin/xcrun','nm','-arch','arm64','-g','-U','-j',old['library']],sdk+'-old-nm')
        new_symbols=r.run(['/usr/bin/xcrun','nm','-arch','arm64','-g','-U','-j',library],sdk+'-new-nm')
        symbol_receipt=compare(old_symbols,new_symbols); exported_sets.append(symbol_receipt['symbols'])
        write(r.evidence/(sdk+'-symbols.json'),symbol_receipt)
        links=[]
        for language,source,entry in [('c','provider.c','tetherless_c_provider_probe'),('swift','provider.swift','tetherless_c_provider_swift_probe')]:
            output=slice_dir/('probe-'+language); map_path=r.evidence/(sdk+'-'+language+'.map')
            compiler=cc if language=='c' else r.run(['/usr/bin/xcrun','--find','swiftc'],sdk+'-swiftc',seconds=60)
            command=[compiler,'-target',triple]
            command += ['-isysroot',sdkpath] if language=='c' else ['-sdk',sdkpath]
            command += ['-I',str(headers),'-I',str(headers/'libimobiledevice'),str(HERE/'probes'/source),
                        '-Xlinker','-force_load','-Xlinker',str(library),'-Xlinker','-u','-Xlinker','_'+entry,
                        '-Xlinker','-map','-Xlinker',str(map_path),*FRAMEWORKS,*openssl['final_link_arguments'],'-o',str(output)]
            r.run(command,sdk+'-link-'+language)
            ownership=link_ownership(map_path.read_text(),library,set(symbol_receipt['symbols']))
            write(r.evidence/(sdk+'-'+language+'-ownership.json'),ownership)
            links.append({'language':language,'output_sha256':sha256(output.read_bytes()),'executed':False,'ownership':ownership})
        provider.audit_inputs(openssl)
        records.append({'sdk':sdk,'target':triple,'library':str(library),'library_sha256':sha256(library.read_bytes()),
                        'headers':str(headers),'header_inventory':current_headers,'symbols':symbol_receipt,
                        'component_archives':{p.name:sha256(p.read_bytes()) for p in components},'links':links,
                        'openssl':openssl,'system_frameworks':FRAMEWORKS})
    if exported_sets[0] != exported_sets[1]:
        raise ValueError('C complete exports differ across slices')
    product=work/'product'; product.mkdir()
    command=['/usr/bin/xcodebuild','-create-xcframework']
    for record in records:
        command+=['-library',record['library'],'-headers',record['headers']]
    xc=product/'libimobiledevice.xcframework'
    command+=['-output',str(xc)]
    r.run(command,'create-xcframework')
    import plistlib
    info=plistlib.loads((xc/'Info.plist').read_bytes())
    rows=info['AvailableLibraries']
    if len(rows)!=2 or {(x['SupportedPlatform'],x.get('SupportedPlatformVariant',''),tuple(x['SupportedArchitectures'])) for x in rows} != {('ios','',('arm64',)),('ios','simulator',('arm64',))}:
        raise ValueError('unexpected packaged slice identities')
    for row in rows:
        record=records[1 if row.get('SupportedPlatformVariant')=='simulator' else 0]
        base=xc/row['LibraryIdentifier']
        if sha256((base/row['LibraryPath']).read_bytes()) != record['library_sha256'] or inventory(base/row['HeadersPath']) != record['header_inventory']:
            raise ValueError('packaged archive/header identity changed')
    # Matching source and notices travel beside the new archive, not inside app payloads.
    with tarfile.open(product/'matching-source.tar','x:') as tar:
        for base,arc in [(pristine,'pristine'),(HERE,'recipe/libimobiledevice'),(SIBLING,'recipe/idevice')]:
            for p in sorted(base.rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts and not any(x.startswith('.test-output-') for x in p.parts):
                    if p.is_symlink(): raise ValueError('source bundle symlink')
                    info=tarfile.TarInfo(arc+'/'+p.relative_to(base).as_posix()); info.size=p.stat().st_size
                    info.mode=0o755 if p.stat().st_mode&0o111 else 0o644; info.mtime=0
                    with p.open('rb') as f:tar.addfile(info,f)
        for rel in ['.github/workflows/c-provider-native.yml','LICENSE']:
            p=REPOSITORY/rel;info=tarfile.TarInfo('recipe/'+rel);info.size=p.stat().st_size;info.mode=0o644;info.mtime=0
            with p.open('rb') as f:tar.addfile(info,f)
    shutil.copyfile(HERE/'NOTICE.md',product/'NOTICE.md')
    receipt={'schema':1,'scope':'new C-only producer candidate; not Rust/consumer/device acceptance',
             'source_commit':os.environ.get('GITHUB_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID'),
             'run_attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),'action_identity':json.loads((pristine.parent/'action-identity.json').read_bytes()),
             'slices':records,'toolchain':observations,
             'namespace_contract_sha256':sha256((HERE/'namespace-contract.json').read_bytes()),
             'source_receipt_sha256':sha256((pristine/'source-receipt.json').read_bytes()),
             'matching_source_sha256':sha256((product/'matching-source.tar').read_bytes()),
             'xcframework_files':inventory(xc),'all_c_globals_unique':True,'all_public_headers_unchanged':True,
             'consumer_admitted':False,'rust_mixed_provider_verified':False,'ios_binaries_executed':False,
             'openssl_bundled':False,'system_frameworks':['CoreFoundation','SystemConfiguration']}
    verify_retained(pristine)
    for name,row in observations['tools'].items():
        if sha256(Path(row['path']).read_bytes()) != row['sha256']:
            raise ValueError('tool changed while building: '+name)
    for prefix,rows in observations['tool_installation_closures'].items():
        for rel,row in rows.items():
            p=Path(prefix)/rel
            if 'symlink' in row:
                if not p.is_symlink() or os.readlink(p)!=row['symlink']: raise ValueError('tool symlink changed')
            elif p.is_symlink() or sha256(p.read_bytes())!=row['sha256']: raise ValueError('tool closure changed')
    write(product/'producer-receipt.json',receipt)
    with zipfile.ZipFile(work/'libimobiledevice-derived-candidate.zip','x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(product.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(product).as_posix())
    write(r.evidence/'product-digest.json',{'sha256':sha256((work/'libimobiledevice-derived-candidate.zip').read_bytes()),'bytes':(work/'libimobiledevice-derived-candidate.zip').stat().st_size})
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--openssl',type=Path,required=True)
    p.add_argument('--old-provider',type=Path,required=True)
    p.add_argument('--work',type=Path,required=True)
    args=p.parse_args()
    primary=None
    try:
        build(args)
    except BaseException as error:
        primary=error
        raise
    finally:
        # Failure audit must not hide an earlier compiler/link/source failure.
        try:
            audit=final_audits(args) if getattr(args,'_work_created',False) else {'all_passed':True}
            if not audit['all_passed'] and primary is None:
                raise ValueError('final input integrity audit failed')
        except Exception:
            if primary is None:raise
if __name__=='__main__':
    main()
