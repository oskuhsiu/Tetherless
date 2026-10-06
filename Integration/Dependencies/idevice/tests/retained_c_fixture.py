"""Synthetic opaque complete handoff data; never a selected or native-built artifact."""
from __future__ import annotations
import copy
import io
import json
import plistlib
import tarfile
import zipfile
from pathlib import PurePosixPath
import retained_c_provider as c


def raw(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def zipped(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items(): z.writestr(name, data)
    return out.getvalue()


def tree_for(files):
    rows = [{'path': name, 'mode': '100644', 'type': 'blob', 'sha': c.git_blob(data), 'size': len(data)} for name, data in files.items()]
    parents = {p.as_posix() for name in files for p in PurePosixPath(name).parents if p.as_posix() != '.'}
    hashes = {}
    for parent in sorted(parents | {''}, key=lambda p: (len(PurePosixPath(p).parts), p), reverse=True):
        children = [r for r in rows if str(PurePosixPath(r['path']).parent) == (parent or '.')]
        children.sort(key=lambda r: (PurePosixPath(r['path']).name + ('/' if r['type'] == 'tree' else '')).encode())
        data = b''.join((r['mode'].lstrip('0') + ' ' + PurePosixPath(r['path']).name).encode() + b'\0' + bytes.fromhex(r['sha']) for r in children)
        import hashlib
        value = hashlib.sha1(b'tree ' + str(len(data)).encode() + b'\0' + data).hexdigest(); hashes[parent] = value
        if parent: rows.append({'path': parent, 'mode': '040000', 'type': 'tree', 'sha': value})
    return {'sha': hashes[''], 'truncated': False, 'tree': sorted(rows, key=lambda r:r['path'])}


def status(command, data):
    return {'schema': 1, 'command': command, 'outcome': 'success', 'returncode': 0,
        'output_complete': True, 'output_truncated': False, 'stop_reason': None, 'log_bytes': len(data),
        'cleanup': {'direct_child_reaped': True, 'group_empty': True}}


def map_text(library, symbols, rust_library=None, rust_symbols=()):
    objects = [(1, library + '(glue.o)'), (2, library + '(ed.o)'), (3, library + '(other.o)')]
    if rust_library: objects.append((4, rust_library + '(rust.o)'))
    text = '# Object files:\n' + ''.join('[ %d] %s\n' % row for row in objects) + '# Sections:\n# Address Size Segment Section\n0x1000 0x20 __TEXT __text\n# Symbols:\n'
    for symbol in sorted(symbols):
        owner = 1 if symbol in c.GLUE else 2 if symbol in c.ED else 3
        text += '0x00000001 0x00000004 [ %d] %s\n' % (owner, symbol)
    for symbol in rust_symbols: text += '0x00000001 0x00000004 [ 4] ' + symbol + '\n'
    return text + '# Dead Stripped Symbols:\n'


def make_fixture():
    selection = {'repository': c.REPOSITORY, 'repository_id': 42, 'source_commit': 'a'*40,
        'workflow_path': c.WORKFLOW, 'head_branch': c.BRANCH, 'run_id': 1001, 'run_attempt': 1,
        'job_id': 1002, 'artifact_id': 1003, 'archive_sha256': '0'*64, 'size_in_bytes': 1}
    root = 'https://api.github.com/repos/' + c.REPOSITORY + '/'
    run = {'id':1001, 'head_sha':'a'*40, 'run_attempt':1, 'path':c.WORKFLOW, 'head_branch':c.BRANCH,
        'event':'push', 'repository':{'id':42,'full_name':c.REPOSITORY}, 'head_repository':{'id':42,'full_name':c.REPOSITORY},
        'status':'completed','conclusion':'success'}
    job = {'id':1002,'name':'c-provider','url':root+'actions/jobs/1002','run_id':1001,'head_sha':'a'*40,
        'run_attempt':1,'status':'completed','conclusion':'success'}
    identity = {'schema':1, **{k:selection[k] for k in ('repository','source_commit','run_id','run_attempt','job_id','workflow_path')},
        'job_name':'c-provider','status_at_acquisition':'in_progress','success_at_acquisition':False,
        'later_api_success_verification_required':True}
    framework = c.digest(b'opaque fixture external framework; not executable')
    contract = {'commit':'b'*40, 'targets':{}, 'entries':[]}
    for sdk,target in [('iphoneos','aarch64-apple-ios'),('iphonesimulator','aarch64-apple-ios-sim')]:
        name = sdk+'/OpenSSL.framework/OpenSSL'
        contract['targets'][target] = {'framework_binary':name,'framework_root':sdk+'/OpenSSL.framework'}
        contract['entries'].append({'path':name,'sha256':framework})
    namespace = {'schema':1,'root_commit':c.SOURCE_PINS['root'][1],'identifiers':c.C_IDENTIFIERS}
    recipe = {'recipe/libimobiledevice/NOTICE.md':b'Synthetic fixture notice\n',
        'recipe/libimobiledevice/namespace-contract.json':raw(namespace),
        'recipe/idevice/split-provider/target-inputs.json':raw(contract),
        'recipe/idevice/xcframework_operation.py':b'# Synthetic wrapper source, never imported\n',
        'recipe/'+c.WORKFLOW:b'# Synthetic workflow, never run\n','recipe/LICENSE':b'Synthetic license\n'}
    pristine, source_receipt, commits = {}, {'schema':1,'sources':{}}, {}
    for key,(repo,sha) in c.SOURCE_PINS.items():
        contents = {'fixture.c':b'/* Synthetic '+key.encode()+b' source, never compiled */\n'}
        tree = tree_for(contents); commits[key] = {'repository':repo,'commit':sha,'tree':tree['sha']}
        recipe['recipe/libimobiledevice/provenance/'+key+'-tree.json'] = raw(dict(tree,sha=sha))
        inventory = {}
        for name,data in contents.items():
            pristine['pristine/'+key+'/'+name] = data
            inventory[name] = {'git_blob':c.git_blob(data),'sha256':c.digest(data),'bytes':len(data),'mode':'100644'}
        source_receipt['sources'][key] = {'repository':repo,'commit':sha,'tree':tree['sha'],'files':inventory}
    recipe['recipe/libimobiledevice/provenance/commits.json'] = raw(commits)
    pristine['pristine/source-receipt.json'] = raw(source_receipt)
    source = io.BytesIO()
    with tarfile.open(fileobj=source,mode='w:') as t:
        for name,data in {**recipe,**pristine}.items():
            i=tarfile.TarInfo(name);i.size=len(data);i.mode=0o644;t.addfile(i,io.BytesIO(data))
    source=source.getvalue()
    source_files = {('Integration/Dependencies/'+n.removeprefix('recipe/')) if n.startswith(('recipe/libimobiledevice/','recipe/idevice/')) else n.removeprefix('recipe/'):v for n,v in recipe.items()}
    tree=tree_for(source_files);tree['url']=root+'git/trees/'+tree['sha']
    commit={'sha':'a'*40,'tree':{'sha':tree['sha']},'url':root+'git/commits/'+'a'*40}
    headers={'plist/plist.h':b'/* opaque fixture public plist header */\n',
        'libimobiledevice/module.modulemap':b'module libimobiledevice { export * }\n',
        'libimobiledevice/libimobiledevice.h':b'/* opaque fixture public C header */\n'}
    metas=[];xc={};old={}
    for sdk,identifier,variant in [('iphoneos','ios-arm64',''),('iphonesimulator','ios-arm64-simulator','simulator')]:
        m={'LibraryIdentifier':identifier,'LibraryPath':'libimobiledevice.a','HeadersPath':'Headers','SupportedPlatform':'ios','SupportedArchitectures':['arm64']}
        if variant:m['SupportedPlatformVariant']=variant
        metas.append(m)
        xc[identifier+'/libimobiledevice.a']=('opaque fixture '+sdk+' library; not executable').encode()
        old['libimobiledevice.xcframework/'+identifier+'/libimobiledevice.a']=b'opaque fixture baseline library'
        for name,data in headers.items():
            xc[identifier+'/Headers/'+name]=data
            old['libimobiledevice.xcframework/'+identifier+'/Headers/'+name]=data
    xc['Info.plist']=plistlib.dumps({'AvailableLibraries':metas})
    old['libimobiledevice.xcframework/Info.plist']=xc['Info.plist'];old_zip=zipped(old)
    outer={'inputs/action-identity.json':raw(identity),'inputs/original-c-provider.zip':old_zip}
    outer.update({'inputs/'+n:v for n,v in pristine.items()})
    outer['work/evidence/recipe-inputs.json']=raw({n.removeprefix('recipe/'):{'sha256':c.digest(v),'bytes':len(v)} for n,v in recipe.items()})
    outer['work/evidence/final-input-audit.json']=raw({'schema':1,'all_passed':True,'primary_failure_preserved':True,
        'checks':{n:{'passed':True} for n in ('pristine_source','openssl_inputs','original_c_iphoneos','original_c_iphonesimulator','recipe_inputs','derived_sources_iphoneos','derived_sources_iphonesimulator','toolchain_inputs')}})
    outer['work/evidence/run-context.json']=raw({'source_commit':'a'*40,'run_id':'1001','run_attempt':'1','job':'c-provider',
        'new_derivation':True,'consumer_admitted':False,'ios_binaries_executed':False})
    toolchain={'xcode':'Xcode 26.3\nBuild version 17C529',**{sdk+'_'+key:value for sdk in ('iphoneos','iphonesimulator') for key,value in [('sdk_version','26.2'),('sdk_build','23C57')]}}
    outer['work/evidence/toolchain.json']=raw(toolchain)
    serial=0
    def command(label,argv,data=b''):
        nonlocal serial
        serial+=1;name='work/evidence/%03d-'%serial+label+'.txt'
        outer[name]=data;outer[name+'.status.json']=raw(status(argv,data))
    host={'outcome':'passed','plain':{'outcome':'passed'},'asan':{'outcome':'passed'},'commands':[]}
    for name in ('plain-run','asan-run','asan-probe-compile','asan-probe-run'):
        log='logs/'+name+'.log';argv=['/fixture/host-'+name]
        host['commands'].append({'name':name,'argv':argv,'log':log,'receipt':log+'.status.json'})
        outer['work/host-tests/'+log]=b'';outer['work/host-tests/'+log+'.status.json']=raw(status(argv,b''))
    outer['work/host-tests/result.json']=raw(host)
    old_symbols=c.GLUE|c.REQUIRED_C;symbols=old_symbols|c.ED
    slices=[]
    for sdk,identifier,target,triple in [('iphoneos','ios-arm64','aarch64-apple-ios','arm64-apple-ios13.0'),('iphonesimulator','ios-arm64-simulator','aarch64-apple-ios-sim','arm64-apple-ios13.0-simulator')]:
        library='/fixture/'+sdk+'/libimobiledevice.a';header='/fixture/'+sdk+'/include'
        old_nm='\n'.join(sorted(old_symbols))+'\n';new_nm='\n'.join(sorted(symbols))+'\n'
        nm=['/usr/bin/xcrun','nm','-arch','arm64','-g','-U','-j']
        command(sdk+'-old-nm',nm+['/fixture/old/'+sdk+'.a'],old_nm.encode());command(sdk+'-new-nm',nm+[library],new_nm.encode())
        symbol_receipt=c.historical_c_symbol_receipt(old_nm,new_nm)
        outer['work/evidence/'+sdk+'-symbols.json']=raw(symbol_receipt)
        command(sdk+'-path',['/usr/bin/xcrun','--sdk',sdk,'--show-sdk-path'],('/fixture/'+sdk+'.sdk\n').encode())
        command(sdk+'-clang-path',['/usr/bin/xcrun','--sdk',sdk,'--find','clang'],b'/fixture/clang\n')
        command(sdk+'-swiftc',['/usr/bin/xcrun','--find','swiftc'],b'/fixture/swiftc\n')
        links=[]
        for language in ('c','swift'):
            text=map_text(library,symbols);proof=c.link_ownership(text,library,symbols)
            prior={'schema':1,'required_live_symbols':len(symbols),'owners':proof['owners'],
                'ed25519_sha512_member':library+'(ed.o)','glue_sha512_member':library+'(glue.o)','map_sha256':proof['map_sha256']}
            links.append({'language':language,'output_sha256':'e'*64,'executed':False,'ownership':prior})
            outer['work/evidence/'+sdk+'-'+language+'.map']=text.encode();outer['work/evidence/'+sdk+'-'+language+'-ownership.json']=raw(prior)
            probe='/fixture/Integration/Dependencies/libimobiledevice/probes/'+('provider.c' if language=='c' else 'provider.swift')
            argv=['/fixture/clang' if language=='c' else '/fixture/swiftc','-target',triple,
                '-isysroot' if language=='c' else '-sdk','/fixture/'+sdk+'.sdk','-I',header,'-I',header+'/libimobiledevice',probe,
                '-Xlinker','-force_load','-Xlinker',library,'-Xlinker','-u','-Xlinker',
                '_tetherless_c_provider_probe' if language=='c' else '_tetherless_c_provider_swift_probe',
                '-Xlinker','-map','-Xlinker','/fixture/evidence/'+sdk+'-'+language+'.map',
                '-framework','CoreFoundation','-framework','SystemConfiguration',
                '-F','/fixture/openssl/'+sdk,'-framework','OpenSSL','-o','/fixture/'+sdk+'/probe-'+language]
            command(sdk+'-link-'+language,argv)
        prefix=target.upper().replace('-','_')+'_'
        openssl={'target':target,'kind':'apple-framework-consumer','contract_sha256':c.digest(raw(contract)),
            'source_commit':'b'*40,'source_root':'/fixture/openssl','final_link_arguments':['-F','/fixture/openssl/'+sdk,'-framework','OpenSSL'],'framework_binary_sha256':framework,'native_libraries':[],
            'native_execution':False,'product_activation':False,'environment':{prefix+'OPENSSL_LIBS':''}}
        slices.append({'sdk':sdk,'target':triple,'library':library,'headers':header,
            'library_sha256':c.digest(xc[identifier+'/libimobiledevice.a']),'header_inventory':c.inventory(headers),
            'symbols':symbol_receipt,'links':links,'openssl':openssl,'system_frameworks':['-framework','CoreFoundation','-framework','SystemConfiguration']})
    op=['/fixture/python3','-I','/fixture/Integration/Dependencies/idevice/xcframework_operation.py']+[v for row in slices for v in (row['library'],row['headers'])]+['/fixture/product/libimobiledevice.xcframework']
    xcode=['/usr/bin/xcodebuild','-create-xcframework']+[v for row in slices for v in ('-library',row['library'],'-headers',row['headers'])]+['-output',op[-1]]
    operation={'schema':1,'operation_source':'Integration/Dependencies/idevice/xcframework_operation.py',
        'operation_sha256':c.digest(recipe['recipe/idevice/xcframework_operation.py']),'operation_command':op,
        'operation_command_sha256':c.digest(json.dumps(op,separators=(',',':')).encode()),'xcodebuild_command':xcode,
        'xcodebuild_command_sha256':c.digest(json.dumps(xcode,separators=(',',':')).encode()),'timeout_seconds':900,'ios_payloads_executed':False}
    command('create-xcframework',op);outer['work/evidence/xcframework-operation.json']=raw(operation)
    receipt={'schema':1,'source_commit':'a'*40,'run_id':'1001','run_attempt':'1','action_identity':identity,
        'all_c_globals_unique':True,'all_public_headers_unchanged':True,'consumer_admitted':False,
        'rust_mixed_provider_verified':False,'ios_binaries_executed':False,'openssl_bundled':False,
        'system_frameworks':['CoreFoundation','SystemConfiguration'],'slices':slices,'toolchain':toolchain,
        'namespace_contract_sha256':c.digest(raw(namespace)),'source_receipt_sha256':c.digest(raw(source_receipt)),
        'matching_source_sha256':c.digest(source),'xcframework_files':c.inventory(xc),'xcframework_operation':operation}
    product={'producer-receipt.json':raw(receipt),'matching-source.tar':source,'NOTICE.md':recipe['recipe/libimobiledevice/NOTICE.md'],
        **{'libimobiledevice.xcframework/'+n:v for n,v in xc.items()}}
    inner=zipped(product);outer['work/libimobiledevice-derived-candidate.zip']=inner
    outer['work/evidence/product-digest.json']=raw({'sha256':c.digest(inner),'bytes':len(inner)})
    archive=zipped(outer);selection.update(archive_sha256=c.digest(archive),size_in_bytes=len(archive))
    artifact={'id':1003,'expired':False,'name':'c-provider-'+'a'*40+'-1','url':root+'actions/artifacts/1003',
        'archive_download_url':root+'actions/artifacts/1003/zip','size_in_bytes':len(archive),'digest':'sha256:'+c.digest(archive),
        'workflow_run':{'id':1001,'head_sha':'a'*40,'repository_id':42,'head_repository_id':42}}
    return {'selection':selection,'run':run,'job':job,'artifact':artifact,'commit':commit,'tree':tree,
        'archive':archive,'outer':outer,'product':product,'original_digest':c.digest(old_zip)}


class FixtureAPI:
    def __init__(self,f): self.f=f;self.calls=[]
    def get(self,path):
        self.calls.append(path);f=self.f
        routes={'actions/runs/1001':f['run'],'actions/runs/1001/attempts/1/jobs?per_page=100&page=1':{'total_count':1,'jobs':[f['job']]},
            'actions/jobs/1002':f['job'],'actions/runs/1001/artifacts?per_page=100&page=1':{'total_count':1,'artifacts':[f['artifact']]},
            'actions/artifacts/1003':f['artifact'],'git/commits/'+'a'*40:f['commit'],'git/trees/'+f['tree']['sha']+'?recursive=1':f['tree']}
        return copy.deepcopy(routes[path])
    def download(self,id,path,size):
        assert id==1003 and size==len(self.f['archive']);path.write_bytes(self.f['archive'])
