#!/usr/bin/env python3
"""Close authenticated inputs before the separate offline build; no installs."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import urllib.request
import re
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'idevice'))
from bounded_process import capture_helper_command
from mixed_provider import ARCHIVE_URL, prepare
from source_inputs import retain_sources
from build_provider import load_openssl, write

def action_identity():
    """Read only current own-run metadata. Never retain token or response headers."""
    repo=os.environ.get('GITHUB_REPOSITORY')
    if repo != 'oskuhsiu/Tetherless': raise ValueError('unexpected producer repository')
    run=os.environ['GITHUB_RUN_ID']; attempt=os.environ['GITHUB_RUN_ATTEMPT']
    commit=os.environ['GITHUB_SHA']
    if not run.isdigit() or not attempt.isdigit() or not re.fullmatch('[a-f0-9]{40}',commit):
        raise ValueError('invalid Actions identity')
    def read(endpoint):
        request=urllib.request.Request('https://api.github.com/repos/'+repo+endpoint,
            headers={'Authorization':'Bearer '+os.environ['GH_READ_TOKEN'],
                     'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
        with urllib.request.urlopen(request,timeout=30) as response:
            raw=response.read(1024*1024+1)
        if len(raw)>1024*1024: raise ValueError('Actions response exceeded bound')
        return json.loads(raw)
    run_info=read('/actions/runs/'+run)
    jobs=read('/actions/runs/'+run+'/attempts/'+attempt+'/jobs?per_page=100')
    if (run_info['head_sha']!=commit or run_info['head_branch']!='verify/staged-pairing-native'
            or str(run_info['run_attempt'])!=attempt or run_info['path']!='.github/workflows/c-provider-native.yml'
            or run_info['event'] not in ('push','workflow_dispatch')):
        raise ValueError('Actions source/ref/attempt identity mismatch')
    selected=[j for j in jobs['jobs'] if j['name']=='c-provider' and j['head_sha']==commit and j['run_attempt']==int(attempt)]
    if len(selected)!=1 or jobs['total_count']>100: raise ValueError('ambiguous producer job identity')
    job=selected[0]
    return {'schema':1,'repository':repo,'source_commit':commit,'run_id':int(run),
            'run_attempt':int(attempt),'job_id':job['id'],'job_name':job['name'],
            'workflow_path':'.github/workflows/c-provider-native.yml','run_url':run_info['html_url'],
            'job_url':job['html_url'],'status_at_acquisition':job['status'],
            'success_at_acquisition':False,'later_api_success_verification_required':True}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--acquisition',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    destination=args.output.resolve()
    if destination.exists(): raise ValueError('acquisition output must be new')
    destination.mkdir(parents=True)
    write(destination/'action-identity.json',action_identity())
    receipt=retain_sources(args.acquisition.resolve(strict=True),destination/'pristine')
    source=args.acquisition.resolve(strict=True)/'openssl'
    provider=load_openssl()
    verified=provider.verify_inputs(source)
    # Retain only verified build-relevant bytes and license. Never stage signing material.
    openssl=destination/'openssl'
    for name,row in verified.items():
        provider._copy_verified(source,row,openssl/name)
    provider.verify_inputs(openssl)
    write(destination/'openssl-verified.json',{'commit':provider.COMMIT,'contract_sha256':provider.CONTRACT_SHA256,
          'files':verified,'binary_execution':False,'signature_admission':False})
    env={'PATH':'/usr/bin:/bin','HOME':str(destination),'LANG':'C','LC_ALL':'C'}
    archive=destination/'original-c-provider.zip'
    capture_helper_command(['/usr/bin/curl','--proto','=https','--proto-redir','=https','--tlsv1.2',
        '--fail','--location','--max-time','180','--max-filesize','8388608',
        '--output',str(archive),ARCHIVE_URL],source=destination,env=env,
        log=destination/'original-c-acquisition.txt',timeout_seconds=210)
    prepare(archive,destination/'old-provider')
    write(destination/'closed-inputs.json',{'schema':1,'source_commits':{k:v['commit'] for k,v in receipt['sources'].items()},
        'openssl_commit':provider.COMMIT,'original_c_archive_authenticated':True,
        'next_phase':'offline rebuild; new derivation unaccepted','native_binaries_executed':False})
if __name__=='__main__':main()
