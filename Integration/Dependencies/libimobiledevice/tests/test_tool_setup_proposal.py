"""UNAPPROVED setup proposal tests. No brew, downloads, installs or native tools."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import tarfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('c_tool_setup_proposal',HERE/'tool-setup/setup_tools.py')
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)


def selected_metadata(lock):
    rows=[]
    for name,row in lock['formulas'].items():
        item={'name':name,'full_name':name,'tap':'homebrew/core','versions':{'stable':row['version'],'bottle':True},
              'ruby_source_checksum':{'sha256':row['ruby_source_sha256']},'ruby_source_path':row['ruby_source_path'],
              'dependencies':row['dependencies'],'uses_from_macos':row['uses_from_macos'],
              'disabled':False,'deprecated':False,'post_install_defined':False,'post_install_steps':[],
              'urls':{'stable':{'url':row['source_url'],'checksum':row['source_sha256']}},
              'bottle':{'stable':{'rebuild':row['bottle_rebuild'],'root_url':'https://ghcr.io/v2/homebrew/core',
                        'files':{'arm64_sequoia':{'url':row['bottle_url'],'sha256':row['bottle_sha256'],'cellar':row['cellar']}}}}}
        for key in ('revision','version_scheme','compatibility_version','keg_only'):item[key]=row[key]
        for key in ('build_dependencies','test_dependencies','recommended_dependencies','optional_dependencies','requirements','conflicts_with','link_overwrite'):item[key]=[]
        rows.append(item)
    return {'formulae':rows,'casks':[]}

class ApprovalAndScopeTests(unittest.TestCase):
    def env(self):
        return {'C_TOOL_SETUP_OWNER_APPROVED':'true','GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted',
                'RUNNER_OS':'macOS','RUNNER_ARCH':'ARM64','GITHUB_REPOSITORY':'oskuhsiu/Tetherless',
                'GITHUB_REF':'refs/heads/verify/staged-pairing-native','GITHUB_EVENT_NAME':'push',
                'GITHUB_SHA':'a'*40,'DEVELOPER_DIR':'/Applications/Xcode_26.3.app/Contents/Developer'}
    def test_unapproved_setup_stops_before_any_tool_or_output(self):
        with tempfile.TemporaryDirectory() as d:
            output=Path(d).resolve(strict=True)/'absent'
            with patch.object(setup,'capture_helper_command') as command,patch.object(setup,'runtime_guard') as runtime:
                with self.assertRaises(PermissionError):setup.setup(SimpleNamespace(execute_approved=False,output=output))
                command.assert_not_called();runtime.assert_not_called();self.assertFalse(output.exists())
    def test_cli_flag_is_not_enough_without_approved_ci_context(self):
        with self.assertRaises(PermissionError):setup.require_approved_ci(True,{})
    def test_exact_approved_context_only(self):
        env=self.env()
        with patch.object(setup.platform,'system',return_value='Darwin'),patch.object(setup.platform,'machine',return_value='arm64'):
            setup.require_approved_ci(True,env)
            for key,value in [('GITHUB_EVENT_NAME','pull_request'),('RUNNER_ENVIRONMENT','self-hosted'),('GITHUB_REF','refs/heads/main'),('GITHUB_REPOSITORY','other/repo'),('C_TOOL_SETUP_OWNER_APPROVED','false')]:
                with self.subTest(key=key),self.assertRaises(PermissionError):setup.require_approved_ci(True,{**env,key:value})
    def test_read_only_formula_pin_and_dependency_closure(self):
        lock=setup.load_lock();self.assertEqual(set(lock['formulas']),set(setup.NAMES))
        self.assertEqual(lock['formulas']['autoconf']['uses_from_macos'],['perl'])
        self.assertEqual(lock['formulas']['automake']['dependencies'],['autoconf'])
        self.assertEqual(lock['formulas']['libtool']['dependencies'],['m4'])
    def test_no_auto_upgrade_update_cleanup_or_sudo_flags(self):
        for name in ('HOMEBREW_NO_AUTO_UPDATE','HOMEBREW_NO_INSTALL_UPGRADE','HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK','HOMEBREW_NO_INSTALL_CLEANUP','HOMEBREW_NO_SUDO'):
            self.assertEqual(setup.FLAGS[name],'1')
    def test_workflow_preserves_existing_push_without_new_dispatch_input(self):
        text=(HERE.parents[2]/'.github/workflows/c-provider-native.yml').read_text()
        self.assertIn('branches: [verify/staged-pairing-native]',text)
        self.assertNotIn('owner_approved_four_tool_setup',text)
        self.assertIn("C_TOOL_SETUP_OWNER_APPROVED: 'true'",text)
        self.assertIn('must obtain owner approval before publishing',text)
        self.assertIn('.c-provider/tool-setup/*.txt.status.json',text)
        self.assertIn('(deny network*)',text)

    def test_tag_specific_fetch_cache_vectors_never_mix_exclusive_flags(self):
        for name in setup.NAMES:
            fetch,cache=setup.bottle_commands(name)
            self.assertEqual(fetch,[setup.BREW,'fetch','--formula','--bottle-tag=arm64_sequoia',name])
            self.assertEqual(cache,[setup.BREW,'--cache','--bottle-tag=arm64_sequoia',name])
            self.assertNotIn('--force-bottle',fetch);self.assertNotIn('--force-bottle',cache)
        with self.assertRaises(ValueError):setup.bottle_commands('unexpected')

class FormulaMetadataTests(unittest.TestCase):
    def setUp(self):self.lock=setup.load_lock();self.data=selected_metadata(self.lock)
    def test_exact_metadata_passes(self):self.assertEqual(set(setup.validate_metadata(self.data,self.lock)),set(setup.NAMES))
    def test_extra_formula_or_cask_rejected(self):
        for field in ('formulae','casks'):
            data=copy.deepcopy(self.data);data[field].append(data['formulae'][0])
            with self.assertRaises(ValueError):setup.validate_metadata(data,self.lock)
    def test_dependency_expansion_rejected(self):
        for field in ('dependencies','build_dependencies','test_dependencies','recommended_dependencies','optional_dependencies','requirements'):
            data=copy.deepcopy(self.data);data['formulae'][0][field]=['unexpected']
            with self.subTest(field=field),self.assertRaises(ValueError):setup.validate_metadata(data,self.lock)
    def test_versions_formula_source_bottle_and_postinstall_drift_rejected(self):
        mutations=[lambda r:r['versions'].update(stable='999'),lambda r:r.update(tap='other/tap'),
                   lambda r:r['ruby_source_checksum'].update(sha256='a'*64),lambda r:r.update(post_install_defined=True),
                   lambda r:r['bottle']['stable']['files']['arm64_sequoia'].update(sha256='a'*64),
                   lambda r:r['urls']['stable'].update(checksum='a'*64)]
        for mutation in mutations:
            data=copy.deepcopy(self.data);mutation(data['formulae'][0])
            with self.assertRaises(ValueError):setup.validate_metadata(data,self.lock)

class RuntimeAndBottleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve(strict=True)
    def test_missing_homebrew_refuses_bootstrap(self):
        with self.assertRaises(ValueError):setup.runtime_guard(self.root/'absent')
    def test_runtime_update_cannot_be_implicitly_covered(self):
        root=self.root/'brew';(root/'bin').mkdir(parents=True);brew=root/'bin/brew';brew.write_text('fixture, never run');brew.chmod(0o755)
        vendor=root/'Library/Homebrew/vendor';vendor.mkdir(parents=True);(vendor/'portable-ruby-version').write_text('4.0.1\n')
        with patch.object(setup,'PREFIX',root),self.assertRaisesRegex(ValueError,'runtime missing or would upgrade'):
            setup.runtime_guard(brew)
    def bottle(self,deps):
        path=self.root/'bottle.tar.gz';data=json.dumps({'runtime_dependencies':deps}).encode()
        with tarfile.open(path,'w:gz') as tar:
            info=tarfile.TarInfo('m4/1.4.21/INSTALL_RECEIPT.json');info.size=len(data);tar.addfile(info,io.BytesIO(data))
        row={'version':'1.4.21','bottle_sha256':setup.digest(path)}
        return path,row
    def test_authenticated_synthetic_bottle_metadata_only(self):
        path,row=self.bottle([]);self.assertEqual(setup.inspect_bottle(path,'m4',row)['runtime_dependencies'],[])
    def test_extra_bottle_runtime_dependency_rejected_before_install(self):
        path,row=self.bottle([{'full_name':'unexpected','version':'1'}])
        with self.assertRaisesRegex(ValueError,'outside four-formula'):setup.inspect_bottle(path,'m4',row)
    def test_bottle_hash_drift_rejected(self):
        path,row=self.bottle([]);row['bottle_sha256']='a'*64
        with self.assertRaises(ValueError):setup.inspect_bottle(path,'m4',row)
    def test_sandbox_protects_runtime_and_unrelated_kegs(self):
        text=setup.sandbox_policy(Path('/opt/homebrew'),{'pkgconf':{},'m4':{}},True)
        self.assertIn('(deny network*)',text);self.assertIn('/opt/homebrew/Library',text);self.assertIn('/opt/homebrew/Cellar/pkgconf',text)
        self.assertNotIn('/opt/homebrew/Cellar/m4',text)
    def test_existing_tool_hash_drift_rejected(self):
        p=self.root/'make';p.write_bytes(b'changed')
        with self.assertRaises(ValueError):setup.verify_existing_tools({'existing_tools':{'make':{'path':str(p),'sha256':'a'*64,'version':'1'}}})


class StartupCacheTests(unittest.TestCase):
    def exercise(self,fail_label=None,offline_json_prefix=''):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name).resolve(strict=True);work=root/'setup';brewroot=root/'homebrew';brewroot.mkdir()
        runtime=brewroot/'runtime';runtime.write_text('existing-runtime')
        metadata=selected_metadata(setup.load_lock());before={'pkgconf':{'3.0.7':'unchanged-receipt'}}
        commands=[];cache_ready=False
        primary=ValueError('synthetic failure at '+str(fail_label))
        stop=ValueError('stop before first bottle acquisition')
        def capture(command,**kwargs):
            nonlocal cache_ready
            argv=[str(x) for x in command];log=kwargs['log'];label=log.stem.split('-',1)[1]
            commands.append({'argv':argv,'env':dict(kwargs['env']),'label':label})
            offline='(deny network*)' in argv[2]
            value='controlled fixture output\n'
            if label=='brew-config':
                # Actual 6.0.22 startup behavior with a fresh owned cache:
                # API initialization precedes config unless disabled for it.
                if 'HOMEBREW_NO_INSTALL_FROM_API=1' not in argv:
                    raise ValueError('curl: (6) Could not resolve host: formulae.brew.sh; HTTP status: 000')
                self.assertTrue(offline)
            elif label=='macos-version':value='15.7.9\n'
            elif label=='macos-build':value='24G830\n'
            elif label=='acquire-selected-metadata':
                self.assertFalse(offline);cache_ready=True
                value='==> Downloading Homebrew API data\nJSON API packages.arm64_sequoia.jws.json\n'+json.dumps(metadata)+'\n'
            elif label=='selected-metadata':
                self.assertTrue(offline);self.assertTrue(cache_ready)
                value=offline_json_prefix+json.dumps(metadata)+'\n'
            log.write_text(value)
            log.with_name(log.name+'.status.json').write_text(json.dumps({'synthetic_fixture':True})+'\n')
            if label==fail_label:raise primary
            if label.startswith('fetch-'):raise stop
        env={'GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1',
             'DEVELOPER_DIR':'/Applications/Xcode_26.3.app/Contents/Developer'}
        with patch.dict(os.environ,env,clear=True),patch.object(setup,'require_approved_ci'), \
             patch.object(setup,'runtime_guard',return_value=(brewroot,{str(runtime):setup.digest(runtime)})), \
             patch.object(setup,'cellar_inventory',return_value=before), \
             patch.object(setup,'verify_existing_tools',return_value={'fixture':'unchanged'}), \
             patch.object(setup,'capture_helper_command',side_effect=capture):
            with self.assertRaises(ValueError) as caught:
                setup.setup(SimpleNamespace(execute_approved=True,output=work))
        return work,commands,json.loads((work/'setup-receipt.json').read_bytes()),caught.exception,primary,stop

    def test_fresh_cache_diagnostic_then_acquisition_then_strict_offline_metadata(self):
        work,commands,report,error,_,stop=self.exercise()
        self.assertIs(error,stop)
        self.assertEqual([row['label'] for row in commands],['brew-config','macos-version','macos-build',
                          'acquire-selected-metadata','selected-metadata','fetch-m4'])
        self.assertEqual(commands[0]['argv'][3:],['/usr/bin/env','HOMEBREW_NO_INSTALL_FROM_API=1',str(setup.BREW),'config'])
        for row in commands:
            self.assertNotIn('HOMEBREW_NO_INSTALL_FROM_API',row['env'])
            if row['label']!='brew-config':self.assertNotIn('HOMEBREW_NO_INSTALL_FROM_API=1',row['argv'])
            self.assertEqual(row['env']['HOMEBREW_NO_AUTO_UPDATE'],'1')
            self.assertIn('/Library',row['argv'][2])
        for row in commands[3:5]:
            self.assertEqual(row['argv'][3:],[str(setup.BREW),'info','--json=v2','--formula',*setup.NAMES])
        self.assertIn('Downloading Homebrew API data',(work/'04-acquire-selected-metadata.txt').read_text())
        self.assertEqual(json.loads((work/'selected-metadata.json').read_bytes()),selected_metadata(setup.load_lock()))
        self.assertTrue(all(report['final_audit'].values()))

    def test_config_failure_stops_before_any_network_command(self):
        _,commands,report,error,primary,_=self.exercise(fail_label='brew-config')
        self.assertIs(error,primary);self.assertEqual(len(commands),1)
        self.assertTrue(all(row['offline'] for row in report['commands']))
        self.assertTrue(all(report['final_audit'].values()))

    def test_metadata_acquisition_failure_stops_before_offline_validation_and_bottles(self):
        work,commands,report,error,primary,_=self.exercise(fail_label='acquire-selected-metadata')
        self.assertIs(error,primary)
        self.assertEqual(commands[-1]['label'],'acquire-selected-metadata')
        self.assertFalse((work/'selected-metadata.json').exists())
        self.assertTrue(all(report['final_audit'].values()))

    def test_offline_metadata_prefix_is_rejected_without_stripping_or_bottle_fetch(self):
        work,commands,report,error,_,_=self.exercise(offline_json_prefix='unexpected warning\n')
        self.assertIsInstance(error,json.JSONDecodeError)
        self.assertEqual(commands[-1]['label'],'selected-metadata')
        self.assertFalse((work/'selected-metadata.json').exists())
        self.assertTrue(all(report['final_audit'].values()))


class PartialFailureEvidenceTests(unittest.TestCase):
    def test_partial_install_retains_after_state_and_primary_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve(strict=True);work=root/'setup';brewroot=root/'homebrew';brewroot.mkdir()
            runtime=brewroot/'runtime';runtime.write_text('existing-runtime')
            lock=setup.load_lock();metadata=selected_metadata(lock)
            before={'pkgconf':{'3.0.7':'unchanged-receipt'}}
            after={**before,'m4':{'1.4.21':'partially-installed-approved-formula'}}
            primary=ValueError('synthetic partial install failure')
            captured=[]
            def capture(command,**kwargs):
                captured.append(command)
                log=kwargs['log'];label=log.stem
                value='controlled fixture output\n'
                if 'macos-version' in label:value='15.7.9\n'
                elif 'macos-build' in label:value='24G830\n'
                elif 'metadata' in label:value=json.dumps(metadata)+'\n'
                elif 'cache-' in label:
                    formula=label.rsplit('cache-',1)[1];path=work/'cache'/(formula+'.bottle.tar.gz')
                    path.write_bytes(b'synthetic asset placeholder, never executed');value=str(path)+'\n'
                log.write_text(value);log.with_name(log.name+'.status.json').write_text(json.dumps({'synthetic_fixture':True})+'\n')
                if 'install-four-formulas' in label:raise primary
            env={'GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1',
                 'DEVELOPER_DIR':'/Applications/Xcode_26.3.app/Contents/Developer'}
            with patch.dict(os.environ,env,clear=True),patch.object(setup,'require_approved_ci'), \
                 patch.object(setup,'runtime_guard',return_value=(brewroot,{str(runtime):setup.digest(runtime)})), \
                 patch.object(setup,'cellar_inventory',side_effect=[before,after]), \
                 patch.object(setup,'verify_existing_tools',return_value={'fixture':'unchanged'}), \
                 patch.object(setup,'inspect_bottle',return_value={'synthetic_verified_metadata':True}), \
                 patch.object(setup,'capture_helper_command',side_effect=capture):
                with self.assertRaises(ValueError) as result:
                    setup.setup(SimpleNamespace(execute_approved=True,output=work))
            self.assertIs(result.exception,primary)
            report=json.loads((work/'setup-receipt.json').read_bytes())
            self.assertEqual(report['state'],'failed');self.assertEqual(report['final_cellar'],after)
            self.assertTrue(report['final_audit']['unrelated_formula_state_unchanged'])
            self.assertEqual(report['error']['text'],str(primary))
            install=[row for row in report['commands'] if 'install-four-formulas' in row['log']]
            self.assertEqual(len(install),1);self.assertTrue(install[0]['offline'])
            self.assertEqual(install[0]['argv'][-4:],list(setup.NAMES))
            self.assertTrue(any('metadata-before-install' in row['log'] and row['offline'] for row in report['commands']))

if __name__=='__main__':unittest.main()
