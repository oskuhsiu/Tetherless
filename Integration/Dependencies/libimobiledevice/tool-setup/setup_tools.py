#!/usr/bin/env python3
"""UNAPPROVED PROPOSAL. Four-formula setup for the disposable CI runner only.

No command runs without the explicit approved-CI gate. That gate records a
controller decision; it never replaces the owner's actual permission.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'idevice'))
from bounded_process import capture_helper_command
sys.path.insert(0,str(HERE))
from bottle_metadata import inspect_bottle, verify_retained_manifests, audit_bottle_inputs

PREFIX=Path('/opt/homebrew')
BREW=PREFIX/'bin/brew'
NAMES=('m4','autoconf','automake','libtool')
TOOL_FORMULAS={'m4':'m4','autoconf':'autoconf','autoheader':'autoconf',
              'automake':'automake','aclocal':'automake','glibtoolize':'libtool'}
FLAGS={name:'1' for name in ('HOMEBREW_NO_AUTO_UPDATE','HOMEBREW_NO_INSTALL_UPGRADE',
       'HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK','HOMEBREW_NO_INSTALL_CLEANUP',
       'HOMEBREW_NO_AUTOREMOVE','HOMEBREW_NO_ANALYTICS','HOMEBREW_NO_ENV_HINTS',
       'HOMEBREW_NO_BOOTSNAP','HOMEBREW_NO_GITHUB_API','HOMEBREW_NO_SUDO',
       'HOMEBREW_NO_COLOR','HOMEBREW_NO_EMOJI')}
# Homebrew 6.0.22, commit 08e85c4e42f5d8f1ea17c36cb59cf61c2ccb26c3.
# This API loader omits compatibility_version from its generated Formula class.
# A null CLI field is admissible only with this exact reader and independently
# authenticated formula source that still declares the locked integer value.
API_COMPATIBILITY_READER={
    'Library/Homebrew/brew.rb':'29d15cf96a6cc2f75173097d17f676504e4b566a6feee3b9bf83acb8e45e724f',
    'Library/Homebrew/cmd/info.rb':'49824eab5ac1ec459221c595a813c0f60ba0fd2d0ce00b6e93837eeddceb8af8',
    'Library/Homebrew/formula.rb':'165371769ddca7d4236f0aa194ea553fe5223d89c7a57cdc44407bc6a033b7b8',
    'Library/Homebrew/formulary.rb':'3358a123b148e7ec5920a1238927a2cbdd7bf0423241fa27b9f2b6665f944294',
}


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,data):path.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')

def require_formula_compatibility(name,expected):
    source=(HERE/'metadata-sources'/(name+'.rb')).read_bytes()
    if hashlib.sha256(source).hexdigest()!=expected['ruby_source_sha256']:
        raise ValueError('reviewed official formula text changed')
    declarations=re.findall(rb'^  compatibility_version ([0-9]+)[ \t]*$',source,re.MULTILINE)
    wanted=expected['compatibility_version']
    if type(wanted) is not int or len(declarations)!=1 or int(declarations[0])!=wanted:
        raise ValueError('authenticated formula compatibility declaration differs: '+name)


def load_lock():
    lock=json.loads((HERE/'formula-lock.json').read_bytes())
    if set(lock['formulas'])!=set(NAMES) or lock['install_order']!=list(NAMES) or lock['bottle_tag']!='arm64_sequoia':
        raise ValueError('four-formula scope changed')
    for name,row in lock['formulas'].items():
        require_formula_compatibility(name,row)
        if not set(row['dependencies'])<=set(NAMES):raise ValueError('formula dependency outside approval scope')
    verify_retained_manifests(lock)
    return lock


def require_approved_ci(approved,env):
    if not approved or env.get('C_TOOL_SETUP_OWNER_APPROVED')!='true':
        raise PermissionError('unapproved proposal: owner-approved CI source required')
    wanted={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'macOS',
            'RUNNER_ARCH':'ARM64','GITHUB_REPOSITORY':'oskuhsiu/Tetherless',
            'GITHUB_REF':'refs/heads/verify/staged-pairing-native',
            'DEVELOPER_DIR':'/Applications/Xcode_26.3.app/Contents/Developer'}
    if any(env.get(k)!=v for k,v in wanted.items()):raise PermissionError('setup limited to the approved disposable GitHub runner')
    if env.get('GITHUB_EVENT_NAME') not in ('push','workflow_dispatch'):raise PermissionError('unexpected C workflow event')
    if not re.fullmatch('[0-9a-f]{40}',env.get('GITHUB_SHA','')):raise PermissionError('missing exact source identity')
    if platform.system()!='Darwin' or platform.machine()!='arm64':raise PermissionError('wrong setup host')


def validate_metadata(data,lock,*,compatibility_reader=None):
    if not isinstance(data,dict) or data.get('casks')!=[]:raise ValueError('formula-only metadata required')
    rows=data.get('formulae',[])
    if len(rows)!=4 or {r['name'] for r in rows}!=set(NAMES):raise ValueError('unexpected selected formula set')
    result={}
    for row in rows:
        name=row['name'];expected=lock['formulas'][name]
        if row['tap']!='homebrew/core' or row['full_name']!=name:raise ValueError('unapproved formula tap/name')
        for key in ('revision','version_scheme','keg_only'):
            if row[key]!=expected[key]:raise ValueError('formula identity drift: '+name+' '+key)
        if row['versions']['stable']!=expected['version'] or not row['versions']['bottle']:
            raise ValueError('selected stable/bottle version drift')
        if row['ruby_source_checksum']['sha256']!=expected['ruby_source_sha256'] or row['ruby_source_path']!=expected['ruby_source_path']:
            raise ValueError('formula source changed')
        require_formula_compatibility(name,expected)
        observed=row['compatibility_version']  # A missing field is never an omission profile.
        if observed is None:
            if compatibility_reader!=API_COMPATIBILITY_READER:
                raise ValueError('null formula compatibility requires the authenticated API reader: '+name)
        elif type(observed) is not int or observed!=expected['compatibility_version']:
            raise ValueError('formula identity drift: '+name+' compatibility_version')
        for key in ('build_dependencies','test_dependencies','recommended_dependencies','optional_dependencies','requirements','conflicts_with','link_overwrite'):
            if row.get(key)!=[]:raise ValueError('unapproved dependency/requirement/overwrite: '+name+' '+key)
        if sorted(row['dependencies'])!=sorted(expected['dependencies']) or row['uses_from_macos']!=expected['uses_from_macos']:
            raise ValueError('dependency closure changed')
        if row.get('disabled') or row.get('deprecated') or row.get('post_install_defined') or row.get('post_install_steps')!=[]:
            raise ValueError('unexpected lifecycle or post-install behavior')
        source=row['urls']['stable']
        if source['url']!=expected['source_url'] or source['checksum']!=expected['source_sha256']:
            raise ValueError('source tarball identity changed')
        stable=row['bottle']['stable'];bottle=stable['files'][lock['bottle_tag']]
        if stable['rebuild']!=expected['bottle_rebuild'] or stable['root_url']!='https://ghcr.io/v2/homebrew/core':
            raise ValueError('bottle origin/rebuild changed')
        if any(bottle[k]!=expected['bottle_'+k] for k in ('url','sha256')) or bottle['cellar']!=expected['cellar']:
            raise ValueError('selected arm64 Sequoia bottle changed')
        result[name]=row
    return result


def runtime_guard(brew=BREW):
    if not brew.is_file() or not os.access(brew,os.X_OK):raise ValueError('existing Homebrew required; never bootstrap it')
    binary=brew.resolve(strict=True);root=binary.parent.parent
    if not binary.is_relative_to(PREFIX):raise ValueError('Homebrew outside expected prefix')
    library=root/'Library/Homebrew';version_file=library/'vendor/portable-ruby-version'
    version=version_file.read_text().strip()
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:_[0-9]+)?',version):raise ValueError('unrecognized portable Ruby identity')
    expected=library/'vendor/portable-ruby'/version;current=library/'vendor/portable-ruby/current'
    if not current.is_dir() or not current.samefile(expected):raise ValueError('Homebrew runtime missing or would upgrade; outside four-formula scope')
    required=[binary,version_file,library/'utils/ruby.sh',library/'Gemfile.lock',current/'bin/ruby',current/'bin/bundle',Path('/usr/bin/perl')]
    if any(not p.is_file() for p in required) or not os.access(current/'bin/ruby',os.X_OK):
        raise ValueError('existing Ruby/Bundler/macOS Perl required; no bootstrap permitted')
    reader_sources=[root/path for path in API_COMPATIBILITY_READER]
    if any(not p.is_file() for p in reader_sources):raise ValueError('existing Homebrew metadata reader sources required')
    required += reader_sources
    return root,{str(p):digest(p) for p in required}


def cellar_inventory(prefix=PREFIX):
    result={}
    cellar=prefix/'Cellar'
    for formula in sorted(cellar.iterdir()):
        if not formula.is_dir() or formula.is_symlink() or not re.fullmatch('[A-Za-z0-9@+_.-]+',formula.name):
            raise ValueError('unexpected Homebrew Cellar entry')
        versions={}
        for version in sorted(formula.iterdir()):
            if not version.is_dir() or version.is_symlink():raise ValueError('unexpected keg entry')
            receipt=version/'INSTALL_RECEIPT.json'
            if not receipt.is_file():raise ValueError('existing keg receipt missing')
            versions[version.name]=digest(receipt)
        result[formula.name]=versions
    return result


def verify_existing_tools(lock):
    result={}
    for name,row in lock['existing_tools'].items():
        path=Path(row['path'])
        if not path.is_file() or digest(path)!=row['sha256']:raise ValueError('existing tool drift: '+name)
        result[name]={'path':str(path),'sha256':row['sha256'],'version':row['version']}
    return result


def sandbox_policy(homebrew_root,existing,offline):
    rules=['(version 1)','(allow default)']
    if offline:rules.append('(deny network*)')
    # Per-process restrictions only. Protect Homebrew/runtime and every unrelated
    # existing keg; no global OS/network setting is changed.
    protected=[homebrew_root/'Library',homebrew_root/'.git']
    protected += [PREFIX/'Cellar'/name for name in existing if name not in NAMES]
    for path in protected:rules.append('(deny file-write* (subpath '+json.dumps(str(path))+'))')
    rules.append('(deny file-write* (literal '+json.dumps(str(homebrew_root/'bin/brew'))+'))')
    return ' '.join(rules)


def bottle_commands(name):
    if name not in NAMES:raise ValueError('unapproved formula name')
    # Homebrew makes --force-bottle and --bottle-tag mutually exclusive.
    return ([BREW,'fetch','--formula','--bottle-tag=arm64_sequoia',name],
            [BREW,'--cache','--bottle-tag=arm64_sequoia',name])


def setup(args):
    require_approved_ci(args.execute_approved,os.environ)
    lock=load_lock();work=args.output.resolve()
    if work.exists():raise ValueError('setup evidence root must be fresh')
    work.mkdir(parents=True)
    for name in ('home','cache','logs','tmp'):(work/name).mkdir()
    report={'schema':1,'scope':'four approved formulas on disposable GitHub CI only','state':'preparing',
            'source_commit':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],
            'run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],'selected':lock,'commands':[],
            'native_C_build_started':False,'authorization':'parent must obtain owner permission before publishing this source'}
    write(work/'setup-receipt.json',report)
    env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin','HOME':str(work/'home'),'TMPDIR':str(work/'tmp'),
         'LANG':'en_US.UTF-8','LC_ALL':'en_US.UTF-8','CI':'1','NONINTERACTIVE':'1',
         'DEVELOPER_DIR':os.environ['DEVELOPER_DIR'],
         'HOMEBREW_CACHE':str(work/'cache'),'HOMEBREW_LOGS':str(work/'logs'),**FLAGS}
    before={};runtime={};homebrew_root=None;bottles={}
    def run(command,label,offline=False,seconds=180):
        index=len(report['commands'])+1;log=work/('%02d-%s.txt'%(index,label))
        protected=['/usr/bin/sandbox-exec','-p',sandbox_policy(homebrew_root,before,offline),*[str(x) for x in command]]
        report['commands'].append({'argv':protected,'log':log.name,'status':log.name+'.status.json','offline':offline})
        write(work/'setup-receipt.json',report)
        capture_helper_command(protected,source=work,env=env,log=log,timeout_seconds=seconds)
        return log.read_text().strip()
    try:
        homebrew_root,runtime=runtime_guard();report['existing_homebrew_runtime']=runtime
        compatibility_reader={path:runtime.get(str(homebrew_root/path)) for path in API_COMPATIBILITY_READER}
        report['compatibility_reader']={'expected':API_COMPATIBILITY_READER,'observed':compatibility_reader}
        before=cellar_inventory();report['cellar_before']=before
        report['existing_tools_before']=verify_existing_tools(lock)
        for name in NAMES:
            if name in before and set(before[name])!={lock['formulas'][name]['version']}:
                raise ValueError('existing target version would require an upgrade/replacement: '+name)
        # No network and no Homebrew/runtime writes: missing runtime gems cannot
        # silently bootstrap before the approved formula operations.
        # Homebrew 6.0.22 initializes its API cache even for config. Disable API
        # lookup only for this offline diagnostic, never for formula operations.
        report['brew_config']=run(['/usr/bin/env','HOMEBREW_NO_INSTALL_FROM_API=1',
                                   BREW,'config'],'brew-config',offline=True)
        version=run(['/usr/bin/sw_vers','-productVersion'],'macos-version',offline=True)
        if version!='15.7.9':raise ValueError('setup runner version changed')
        build=run(['/usr/bin/sw_vers','-buildVersion'],'macos-build',offline=True)
        if build!='24G830':raise ValueError('setup runner build changed')
        # The first supported metadata read populates the fresh cache and can
        # print download progress to stderr. Retain that merged output in full;
        # only the subsequent offline read is parsed and accepted as metadata.
        run([BREW,'info','--json=v2','--formula',*NAMES],'acquire-selected-metadata')
        metadata_text=run([BREW,'info','--json=v2','--formula',*NAMES],
                          'selected-metadata',offline=True)
        metadata=json.loads(metadata_text)  # Never discard warnings or arbitrary prefixes.
        validate_metadata(metadata,lock,compatibility_reader=compatibility_reader)
        report['metadata_compatibility']={row['name']:{'observed':row['compatibility_version'],
            'source_declared':lock['formulas'][row['name']]['compatibility_version'],
            'formula_source_sha256':row['ruby_source_checksum']['sha256']} for row in metadata['formulae']}
        write(work/'selected-metadata.json',metadata)
        report['bottles']=bottles
        missing=[name for name in NAMES if name not in before]
        for name in missing:
            fetch_command,cache_command=bottle_commands(name)
            run(fetch_command,'fetch-'+name,seconds=300)
            value=run(cache_command,'cache-'+name)
            if len(value.splitlines())!=1:raise ValueError('unrecognized bottle cache response')
            path=Path(value).resolve(strict=True)
            if not path.is_relative_to(work/'cache'):raise ValueError('bottle outside fresh owned cache')
            bottles[name]=inspect_bottle(path,name,lock,work/'cache',work)
        report['bottles']=bottles;report['state']='verified-bottles';write(work/'setup-receipt.json',report)
        # Standard fetch can retain official sources for these same formulas.
        # Installation still requires each selected bottle's authenticated bytes.
        # Revalidate the selected four-formula closure offline just before install.
        validated_again=json.loads(run([BREW,'info','--json=v2','--formula',*NAMES],
                                       'metadata-before-install',offline=True))
        validate_metadata(validated_again,lock,compatibility_reader=compatibility_reader)
        write(work/'metadata-before-install.json',validated_again)
        audit_bottle_inputs(bottles)
        # Install offline with normal dependency handling and --force-bottle.
        # Missing bottles/additional assets fail; no source build is accepted.
        if missing:
            run([BREW,'install','--formula','--force-bottle','--no-ask',*missing],'install-four-formulas',offline=True,seconds=600)
        after=cellar_inventory();report['cellar_after']=after
        if {k:v for k,v in after.items() if k not in NAMES}!={k:v for k,v in before.items() if k not in NAMES}:
            raise ValueError('unrelated installed formula state changed')
        installed={}
        for name in NAMES:
            row=lock['formulas'][name]
            if set(after.get(name,{}))!={row['version']}:raise ValueError('installed formula version differs')
            receipt=json.loads((PREFIX/'Cellar'/name/row['version']/'INSTALL_RECEIPT.json').read_bytes())
            if receipt.get('poured_from_bottle') is not True:raise ValueError('source-built formula not accepted')
            installed[name]={'version':row['version'],'receipt':receipt,'receipt_sha256':after[name][row['version']]}
        report['installed']=installed
        report['tool_binaries']={}
        for tool,name in TOOL_FORMULAS.items():
            path=(PREFIX/'opt'/name/'bin'/tool).resolve(strict=True)
            if not path.is_relative_to(PREFIX/'Cellar'/name/lock['formulas'][name]['version']):raise ValueError('installed tool path differs')
            text=run([path,'--version'],'version-'+tool,offline=True)
            if not text.splitlines()[0].endswith(' '+lock['formulas'][name]['version']):raise ValueError('installed tool version differs')
            report['tool_binaries'][tool]={'path':str(path),'sha256':digest(path),'version_output':text}
        report['state']='complete'
    except BaseException as error:
        report['state']='failed';report['error']={'type':type(error).__name__,'text':str(error)}
        raise
    finally:
        report['final_audit']={}
        try:
            audit_bottle_inputs(bottles);report['final_audit']['bottle_inputs_unchanged']=True
        except Exception as audit_error:
            report['final_audit']['bottle_inputs_unchanged']=False
            report['bottle_input_audit_error']={'type':type(audit_error).__name__,'text':str(audit_error)}
        for path,expected in runtime.items():
            try:report['final_audit'][path]=digest(Path(path))==expected
            except OSError:report['final_audit'][path]=False
        try:
            final_cellar=cellar_inventory();report['final_cellar']=final_cellar
            report['final_audit']['unrelated_formula_state_unchanged']=({k:v for k,v in final_cellar.items() if k not in NAMES}=={k:v for k,v in before.items() if k not in NAMES})
        except Exception as audit_error:
            report['final_audit']['unrelated_formula_state_unchanged']=False
            report['final_cellar_error']={'type':type(audit_error).__name__,'text':str(audit_error)}
        try:report['final_audit']['existing_tools_unchanged']=verify_existing_tools(lock)==report.get('existing_tools_before')
        except Exception:report['final_audit']['existing_tools_unchanged']=False
        if report['state']=='complete' and not all(report['final_audit'].values()):
            report['state']='failed';report['error']={'type':'ValueError','text':'setup final integrity audit failed'}
        write(work/'setup-receipt.json',report)
    if report['state']!='complete':raise ValueError('setup final integrity audit failed')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--execute-approved',action='store_true',help='only after owner approval and publication of owner-approved workflow source')
    setup(p.parse_args())
if __name__=='__main__':main()
