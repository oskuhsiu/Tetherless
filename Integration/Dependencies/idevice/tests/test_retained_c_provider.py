"""Fail-closed synthetic handoff fixtures; no native tools, network or selected artifact."""
from __future__ import annotations
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
import retained_c_provider as c
import acquire_retained_c_provider as a
from retained_c_fixture import make_fixture, FixtureAPI, raw, zipped, map_text, tree_for

class RetainedCProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.fixture=make_fixture()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='retained C fixture ');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.f=copy.deepcopy(self.fixture)
        self.selection=self.root/'selection.json';self.selection.write_bytes(raw({'schema':1,'selection':self.f['selection']}))
        self.baseline=patch.object(c,'ARCHIVE_SHA256',self.f['original_digest']);self.baseline.start();self.addCleanup(self.baseline.stop)
    def acquire(self):
        return a.acquire(FixtureAPI(self.f),self.f['selection'],self.root/'retained',selection_path=self.selection)
    def verify(self,sha):
        return c.verify(self.root/'retained',{'sdk':'iphoneos','rust':'aarch64-apple-ios'},expected_handoff_sha256=sha,selection_path=self.selection)
    def test_complete_synthetic_outer_api_source_and_product_roundtrip(self):
        result=self.acquire();row=self.verify(result['handoff_sha256'])
        self.assertEqual(row['symbols'],sorted(c.REQUIRED_C|c.ED|c.GLUE))
        self.assertEqual(row['header_inventory'].keys(),{'plist/plist.h','libimobiledevice/module.modulemap','libimobiledevice/libimobiledevice.h'})
        self.assertTrue(Path(row['library']).is_file());self.assertFalse(row['binary_format_inspected'])
    def test_unselected_context_cannot_supply_placeholder_identity(self):
        self.selection.write_bytes(raw({'schema':1,'selection':None}))
        with self.assertRaisesRegex(ValueError,'no successful C producer'): c.load_selection(self.selection)
    def test_unselected_blocks_before_api_token_or_output(self):
        self.selection.write_bytes(raw({'schema':1,'selection':None}))
        with patch.object(sys,'argv',['acquire_retained_c_provider.py','--output',str(self.root/'out')]),patch.object(a,'load_selection',side_effect=lambda: c.load_selection(self.selection)),patch.object(a,'ActionsRead') as transport:
            with self.assertRaises(SystemExit):a.main()
            transport.assert_not_called();self.assertFalse((self.root/'out').exists())
    def test_missing_outer_final_audit_or_product_is_rejected(self):
        for name in ('work/evidence/final-input-audit.json','work/libimobiledevice-derived-candidate.zip'):
            with self.subTest(name=name):
                outer=dict(self.f['outer']);outer.pop(name)
                with self.assertRaises(ValueError):c.validate_product(outer,self.f['selection'],self.f['commit'],self.f['tree'])
    def test_failed_missing_or_extra_final_audit_check(self):
        for mutate in ('failed','missing','extra'):
            with self.subTest(mutate=mutate):
                outer=dict(self.f['outer']);audit=json.loads(outer['work/evidence/final-input-audit.json'])
                if mutate=='failed':audit['checks']['recipe_inputs']['passed']=False
                elif mutate=='missing':audit['checks'].pop('derived_sources_iphonesimulator')
                else:audit['checks']['unknown']={'passed':True}
                outer['work/evidence/final-input-audit.json']=raw(audit)
                with self.assertRaisesRegex(ValueError,'final input audit'):c.validate_product(outer,self.f['selection'],self.f['commit'],self.f['tree'])
    def test_acquisition_identity_cannot_self_assert_final_success(self):
        outer=dict(self.f['outer']);identity=json.loads(outer['inputs/action-identity.json']);identity['success_at_acquisition']=True
        outer['inputs/action-identity.json']=raw(identity)
        with self.assertRaisesRegex(ValueError,'acquisition-time'):c.validate_product(outer,self.f['selection'],self.f['commit'],self.f['tree'])
    def test_job_run_artifact_identity_mutations_fail(self):
        cases=[('run','status','in_progress'),('run','conclusion','failure'),('run','head_branch','main'),('run','path','other.yml'),
            ('run','run_attempt',2),('run','run_attempt',True),('job','conclusion','failure'),('job','id',1004),('job','head_sha','b'*40),
            ('artifact','expired',True),('artifact','digest','sha256:'+'f'*64),('artifact','size_in_bytes',1),('artifact','name','other')]
        for obj,key,value in cases:
            with self.subTest(obj=obj,key=key):
                row=copy.deepcopy(self.f[obj]);row[key]=value
                with self.assertRaises(ValueError):{'run':c.verify_run,'job':c.verify_job,'artifact':c.verify_artifact_metadata}[obj](row,self.f['selection'])
    def test_C_link_command_must_bind_exact_compiler_SDK_probe_archive_map_and_provider(self):
        for fault in ('extra-provider','missing-framework','wrong-probe','wrong-map','wrong-compiler','wrong-sdk'):
            with self.subTest(fault=fault):
                outer=dict(self.f['outer'])
                name=next(n for n in outer if n.endswith('-iphoneos-link-c.txt.status.json'))
                status=json.loads(outer[name]);argv=status['command']
                if fault=='extra-provider':argv += ['-F','/unreviewed/other','-framework','OpenSSL','-lcrypto']
                elif fault=='missing-framework':argv.remove('SystemConfiguration')
                elif fault=='wrong-probe':argv[argv.index('/fixture/Integration/Dependencies/libimobiledevice/probes/provider.c')]='/different/provider.c'
                elif fault=='wrong-map':argv[argv.index('-map')+2]='/different.map'
                elif fault=='wrong-compiler':argv[0]='/different/clang'
                else:argv[argv.index('-isysroot')+1]='/different.sdk'
                outer[name]=raw(status)
                with self.assertRaisesRegex(ValueError,'complete link argv'):c.validate_product(outer,self.f['selection'],self.f['commit'],self.f['tree'])
    def test_selection_no_placeholder_or_bool_numbers(self):
        for key in ('run_id','run_attempt','job_id','artifact_id','repository_id','size_in_bytes'):
            for value in (0,True,'1',None):
                with self.subTest(key=key,value=value):
                    selection=dict(self.f['selection']);selection[key]=value
                    with self.assertRaises(ValueError):c.validate_selection(selection)
    def test_changed_archive_and_caller_hash_fail(self):
        sha=self.acquire()['handoff_sha256']
        with self.assertRaisesRegex(ValueError,'caller handoff hash'):self.verify('f'*64)
        p=self.root/'retained/actions-artifact.zip';p.write_bytes(p.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'outer Actions ZIP'):self.verify(sha)
    def test_all_headers_and_modules_are_bound(self):
        sha=self.acquire()['handoff_sha256'];row=self.verify(sha)
        p=Path(row['headers'])/'libimobiledevice/libimobiledevice.h';p.write_bytes(b'changed unselected header')
        with self.assertRaisesRegex(ValueError,'product bytes'):self.verify(sha)
    def test_extra_file_and_symlink_are_rejected(self):
        sha=self.acquire()['handoff_sha256'];p=self.root/'retained/extra';p.write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError,'extra files'):self.verify(sha)
        p.unlink();p.symlink_to(self.selection)
        with self.assertRaisesRegex(ValueError,'symlink'):self.verify(sha)
    def test_inner_source_is_bound_to_c_commit_not_new_recipe(self):
        other=dict(self.f['commit'],sha='b'*40)
        with self.assertRaisesRegex(ValueError,'source commit identity'):c.validate_product(self.f['outer'],self.f['selection'],other,self.f['tree'])
    def test_git_tree_truncation_omission_and_blob_change_rejected(self):
        for mutate in ('truncated','omit','blob'):
            with self.subTest(mutate=mutate):
                tree=copy.deepcopy(self.f['tree'])
                if mutate=='truncated':tree['truncated']=True
                elif mutate=='omit':tree['tree'].pop()
                else:next(x for x in tree['tree'] if x['type']=='blob')['sha']='f'*40
                with self.assertRaises(ValueError):c.verify_git_tree(tree,self.f['tree']['sha'])
    def test_duplicate_c_exports_rejected(self):
        symbols=sorted(c.ED|c.GLUE|c.REQUIRED_C);text='\n'.join(symbols)
        for bad in (text+'\n'+symbols[0],text+'\n_extra',text.replace(symbols[0],'')):
            with self.assertRaises(ValueError):c.check_symbols(bad,symbols)
    def test_maps_require_live_correct_unambiguous_archive_members(self):
        symbols=c.ED|c.GLUE|c.REQUIRED_C;text=map_text('/fixture/c.a',symbols,'/fixture/rust.a',['_rust'])
        c.link_ownership(text,'/fixture/c.a',symbols,'/fixture/rust.a',['_rust'])
        for bad in (text.replace('/fixture/c.a','/fixture/other.a'),text.replace('_plist_free','_not_plist_free'),text.replace('# Symbols:','# Dead Stripped Symbols:'),text.replace('(ed.o)','(glue.o)').replace('[ 2] _tetherless_c','[ 1] _tetherless_c')):
            with self.assertRaises(ValueError):c.link_ownership(bad,'/fixture/c.a',symbols,'/fixture/rust.a',['_rust'])
    def test_real_failed_C_nm_receipt_preserves_historical_strip_not_raw_hash(self):
        fixture=Path(__file__).parent/'fixtures'
        old=(fixture/'c-provider-failed-37507597771-old-nm.txt').read_text()
        new=(fixture/'c-provider-failed-37507597771-new-nm.txt').read_text()
        expected=json.loads((fixture/'c-provider-failed-37507597771-symbols.json').read_bytes())
        self.assertNotEqual(c.digest(new.encode()),expected['nm_sha256'])
        self.assertEqual(c.historical_c_symbol_receipt(old,new),expected)
        self.assertEqual(expected['global_count'],829)
    def test_map_numeric_alias_unknown_comment_dead_garbage_and_nonrequired_owner_fail(self):
        symbols=c.ED|c.GLUE|c.REQUIRED_C;text=map_text('/fixture/c.a',symbols)
        cases=(text.replace('[ 2]','[ 01]'), text.replace('# Sections:','# Unknown Section: '),
            text+'arbitrary garbage\n', text.replace('# Dead Stripped Symbols:',
                '0x1000 0x10 [ 9999] _nonrequired\n# Dead Stripped Symbols:'),
            text+'<<dead>> 0x10 [ 9999] _nonrequired\n')
        for bad in cases:
            with self.subTest(bad=bad[-100:]),self.assertRaises(ValueError):c.link_ownership(bad,'/fixture/c.a',symbols)
        proof=c.link_ownership(text+'<<dead>> 0x10 [ 3] _not_live\n','/fixture/c.a',symbols)
        self.assertNotIn('_not_live',proof['owners'])
    def test_zip_aliases_traversal_symlink_and_expansion_rejected(self):
        for files in ({'../a':b'x'},{'a':b'x','A':b'y'},{'a':b'x','a/b':b'y'},{'a/../b':b'x'},{'a\\b':b'x'}):
            with self.subTest(files=files),self.assertRaises(ValueError):c.zip_files(zipped(files))
        with self.assertRaises(ValueError):c.zip_files(zipped({'a':b'xx'}),max_expanded=1)
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            i=zipfile.ZipInfo('link');i.external_attr=0o120777<<16;z.writestr(i,'target')
        with self.assertRaises(ValueError):c.zip_files(buf.getvalue())
    def test_observed_failed_C_map_dialect_replays_all829_without_admission(self):
        fixture=Path(__file__).parent/'fixtures'
        context=json.loads((fixture/'c-provider-failed-37507597771-map.json').read_bytes())
        text=(fixture/'c-provider-failed-37507597771-iphoneos-c.map').read_text()
        self.assertEqual(c.digest(text.encode()),context['map_sha256'])
        proof=c.link_ownership(text,context['library'],context['symbols'])
        self.assertEqual(proof['c_required_live_symbols'],829)
        self.assertEqual(proof['owners']['_sha512'],'81')
        self.assertEqual(proof['owners']['_tetherless_c_ed25519_sha512'],'41')
        self.assertEqual(proof['archive_members']['81'],proof['archive_members']['41'])
        for changed in (text.replace('# Sections:','# Unknown:'), text.replace('# Symbols:','# Sections:'),
                        text.replace('0x100004000\t0x000480E4\t__TEXT\t__text','malformed section row')):
            with self.assertRaises(ValueError):c.link_ownership(changed,context['library'],context['symbols'])
    def test_json_duplicate_key_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate JSON'):c.read_json_bytes(b'{"a":1,"a":2}')
    def test_sdk_platform_and_provider_are_bound(self):
        sha=self.acquire()['handoff_sha256'];row=self.verify(sha)
        observations={'sdk_iphoneos_version':'26.2','sdk_iphoneos_build':'23C57','xcode':row['xcode']}
        c.verify_sdk(row,observations)
        with self.assertRaises(ValueError):c.verify_sdk(row,dict(observations,sdk_iphoneos_build='changed'))
        receipt=json.loads(self.f['product']['producer-receipt.json'])['slices'][0]['openssl'];c.verify_provider(row,receipt)
        receipt['framework_binary_sha256']='f'*64
        with self.assertRaises(ValueError):c.verify_provider(row,receipt)

if __name__=='__main__':unittest.main()
