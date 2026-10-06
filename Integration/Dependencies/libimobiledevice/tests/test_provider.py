import copy
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import namespace as ns
import symbols
import source_inputs
import build_provider

class NamespaceTests(unittest.TestCase):
    def test_pinned_retained_bytes(self):
        self.assertGreaterEqual(len(ns.verify_retained_sources()),58)
    def test_exact_six_and_thirty(self):
        rows=ns.load_contract()['files']
        self.assertEqual(len(rows),6);self.assertEqual(sum(x['tokens'] for x in rows.values()),30)
        self.assertEqual({x.rsplit('/',1)[1] for x in rows},{'add_scalar.c','keypair.c','sha512.c','sha512.h','sign.c','verify.c'})
    def test_literals_comments_static_and_context_not_changed(self):
        data=b'#include "sha512.h"\n// sha512\n/*sha512_init*/\nsha512_context sha512_compress; sha512(&x); "sha512";\'x\';\n'
        after,count=ns.transform(data)
        self.assertEqual(count,1);self.assertEqual(ns.transform(after,True),(data,1))
        self.assertIn(b'sha512_context sha512_compress',after)
        self.assertIn(b'#include "sha512.h"',after)
    def fixture(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        root=Path(t.name).resolve(strict=True)/'root';shutil.copytree(HERE/'upstream/root',root)
        return root
    def test_real_transform_and_inverse(self):
        root=self.fixture();before={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
        receipt=ns.apply_to_directory(root)
        changed=[]
        for name,data in before.items():
            after=(root/name).read_bytes()
            if data!=after:
                changed.append(name);self.assertEqual(ns.transform(after,True)[0],data)
        self.assertEqual(set(changed),set(ns.load_contract()['files']))
        self.assertTrue(receipt['inverse_identifier_only'])
    def test_reapplication_rejected(self):
        root=self.fixture();ns.apply_to_directory(root)
        with self.assertRaises(ValueError):ns.apply_to_directory(root)
    def test_algorithm_mutation_rejected_before_writes(self):
        root=self.fixture();p=root/'3rd_party/ed25519/sha512.c';p.write_bytes(p.read_bytes()+b'\n')
        first=root/'3rd_party/ed25519/add_scalar.c';before=first.read_bytes()
        with self.assertRaises(ValueError):ns.apply_to_directory(root)
        self.assertEqual(first.read_bytes(),before)
    def test_missing_unchanged_caller_rejected(self):
        root=self.fixture();(root/'3rd_party/ed25519/key_exchange.c').unlink()
        with self.assertRaises(ValueError):ns.apply_to_directory(root)
    def test_extra_caller_rejected(self):
        root=self.fixture();(root/'3rd_party/ed25519/extra.c').write_text('sha512(0,0,0);')
        with self.assertRaises(ValueError):ns.apply_to_directory(root)
    def test_source_symlink_rejected(self):
        root=self.fixture();p=root/'3rd_party/ed25519/sha512.c';p.unlink();p.symlink_to(HERE/'upstream/root/3rd_party/ed25519/sha512.c')
        with self.assertRaises(ValueError):ns.apply_to_directory(root)
    def test_full_provenance_and_submodule_gitlinks(self):
        for n in source_inputs.SOURCES:self.assertTrue(source_inputs.source_inventory(n))
        root=json.loads((HERE/'provenance/root-tree.json').read_text())
        self.assertEqual({x['path']:x['sha'] for x in root['tree'] if x['type']=='commit'},
            {'Dependencies/libimobiledevice-glue':source_inputs.SOURCES['glue'][1],
             'Dependencies/libplist':source_inputs.SOURCES['plist'][1],
             'Dependencies/libusbmuxd':source_inputs.SOURCES['usbmuxd'][1]})
    def test_path_escape_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for p in ['../x','/x','x/../y','x\\y']:
                with self.assertRaises(ValueError):source_inputs.safe_file(Path(d).resolve(strict=True),p)

class TreeMetadataTests(unittest.TestCase):
    def root(self):return json.loads((HERE/'provenance/root-tree.json').read_text())
    def test_all_nested_trees_match_authenticated_commit(self):
        for key in source_inputs.SOURCES:
            data=json.loads((HERE/'provenance'/(key+'-tree.json')).read_text())
            self.assertEqual(source_inputs.verify_tree_metadata(key,data)['commit'],source_inputs.SOURCES[key][1])
    def test_dropped_nested_file_rejected(self):
        data=self.root();data['tree']=[x for x in data['tree'] if x['path']!='3rd_party/ed25519/sign.c']
        with self.assertRaises(ValueError):source_inputs.verify_tree_metadata('root',data)
    def test_changed_nested_blob_rejected(self):
        data=self.root();next(x for x in data['tree'] if x['path']=='3rd_party/ed25519/sign.c')['sha']='a'*40
        with self.assertRaises(ValueError):source_inputs.verify_tree_metadata('root',data)
    def test_duplicate_entry_rejected(self):
        data=self.root();data['tree'].append(data['tree'][0])
        with self.assertRaises(ValueError):source_inputs.verify_tree_metadata('root',data)
    def test_changed_gitlink_rejected(self):
        data=self.root();next(x for x in data['tree'] if x['type']=='commit')['sha']='a'*40
        with self.assertRaises(ValueError):source_inputs.verify_tree_metadata('root',data)

    def test_unreachable_orphan_blob_rejected(self):
        data=self.root();row=next(x.copy() for x in data['tree'] if x['type']=='blob');row['path']='not_in_root_tree/orphan.c';data['tree'].append(row)
        with self.assertRaises(ValueError):source_inputs.verify_tree_metadata('root',data)
    def test_unreachable_orphan_tree_rejected(self):
        data=self.root();data['tree'].append({'path':'missing/tree','type':'tree','mode':'040000','sha':'4b825dc642cb6eb9a060e54bf8d69288fbee4904'})
        with self.assertRaises(ValueError):source_inputs.verify_tree_metadata('root',data)
    def test_unsupported_entry_mode_rejected(self):
        data=self.root();data['tree'][0]['mode']='120000'
        with self.assertRaises(ValueError):source_inputs.verify_tree_metadata('root',data)
    def test_unsupported_entry_type_rejected(self):
        data=self.root();data['tree'][0]['type']='unknown'
        with self.assertRaises(ValueError):source_inputs.verify_tree_metadata('root',data)
    def test_unsafe_tree_path_rejected(self):
        data=self.root();data['tree'][0]['path']='../escape'
        with self.assertRaises(ValueError):source_inputs.verify_tree_metadata('root',data)

class SymbolTests(unittest.TestCase):
    def old(self):return '\n'.join(sorted(symbols.REQUIRED|symbols.GLUE))+'\n'+ '\n'.join(sorted(symbols.GLUE))
    def new(self):return '\n'.join(sorted(symbols.REQUIRED|symbols.GLUE|symbols.ED))
    def test_old_collision_new_unique(self):
        receipt=symbols.compare(self.old(),self.new());self.assertTrue(receipt['internal_global_definitions_unique'])
    def test_unchanged_collision_rejected(self):
        with self.assertRaises(ValueError):symbols.compare(self.old(),self.old())
    def test_extra_duplicate_new_rejected(self):
        with self.assertRaises(ValueError):symbols.compare(self.old(),self.new()+'\n_sha512')
    def test_incomplete_new_namespace_rejected(self):
        with self.assertRaises(ValueError):symbols.compare(self.old(),self.new().replace('_tetherless_c_ed25519_sha512_init',''))
    def test_missing_public_symbol_rejected(self):
        with self.assertRaises(ValueError):symbols.compare(self.old(),self.new().replace('_plist_free',''))
    def test_extra_public_symbol_rejected(self):
        with self.assertRaises(ValueError):symbols.compare(self.old(),self.new()+'\n_extraneous')
    def test_diagnostic_not_filtered(self):
        for bad in ['error: archive malformed','000 T _symbol','/tmp/unknown']:
            with self.assertRaises(ValueError):symbols.exported(self.new()+'\n'+bad)
    def test_empty_nm_rejected(self):
        with self.assertRaises(ValueError):symbols.exported('')
    def map_fixture(self, temp_parent=None):
        t=tempfile.TemporaryDirectory(dir=temp_parent);self.addCleanup(t.cleanup)
        # Match production's canonical owned build root, including macOS temp aliases.
        lib=Path(t.name).resolve(strict=True)/'libimobiledevice.a';lib.write_bytes(b'fixture')
        text='# Object files:\n[ 1] '+str(lib)+'[41](sha512.o)\n[ 2] '+str(lib)+'[81](sha512.o)\n[ 3] '+str(lib)+'(api.o)\n# Symbols:\n'
        for name in sorted(symbols.REQUIRED|symbols.GLUE|symbols.ED):
            owner=1 if name in symbols.ED else 2 if name in symbols.GLUE else 3
            text+='0x1000 0x40 [ %s] %s\n'%(owner,name)
        return lib,text
    def test_map_owns_all_globals_and_both_families(self):
        lib,text=self.map_fixture();r=symbols.link_ownership(text,lib,symbols.REQUIRED|symbols.GLUE|symbols.ED);self.assertNotEqual(r['ed25519_sha512_member'],r['glue_sha512_member'])
    def test_owned_fixture_canonicalizes_symlinked_temporary_root(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve(strict=True);real=root/'real';real.mkdir();alias=root/'alias';alias.symlink_to(real,target_is_directory=True)
            lib,text=self.map_fixture(alias)
            self.assertEqual(lib,lib.resolve(strict=True))
            self.assertTrue(lib.is_relative_to(real))
            symbols.link_ownership(text,lib,symbols.REQUIRED|symbols.GLUE|symbols.ED)
    def test_raw_alias_map_is_still_rejected_by_production_owner_check(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve(strict=True);real=root/'real';real.mkdir();alias=root/'alias';alias.symlink_to(real,target_is_directory=True)
            lib,text=self.map_fixture(alias)
            noncanonical=text.replace(str(real),str(alias))
            with self.assertRaisesRegex(ValueError,'wrong archive owner'):
                symbols.link_ownership(noncanonical,lib,symbols.REQUIRED|symbols.GLUE|symbols.ED)
    def test_dead_stripped_symbol_not_accepted(self):
        lib,text=self.map_fixture();text=text.replace('0x1000 0x40 [ 2] _sha512\n','# Dead Stripped Symbols:\n0x1000 0x40 [ 2] _sha512\n')
        with self.assertRaises(ValueError):symbols.link_ownership(text,lib,symbols.REQUIRED|symbols.GLUE|symbols.ED)
    def test_wrong_library_map_rejected(self):
        lib,text=self.map_fixture();text=text.replace(str(lib),str(lib)+'wrong')
        with self.assertRaises(ValueError):symbols.link_ownership(text,lib,symbols.REQUIRED|symbols.GLUE|symbols.ED)
    def test_duplicate_live_map_symbol_rejected(self):
        lib,text=self.map_fixture();text+='0x1000 0x40 [ 2] _sha512\n'
        with self.assertRaises(ValueError):symbols.link_ownership(text,lib,symbols.REQUIRED|symbols.GLUE|symbols.ED)
    def test_collapsed_context_owner_rejected(self):
        lib,text=self.map_fixture();text=text.replace('0x1000 0x40 [ 2]','0x1000 0x40 [ 1]')
        with self.assertRaises(ValueError):symbols.link_ownership(text,lib,symbols.REQUIRED|symbols.GLUE|symbols.ED)

class RealMapSectionTests(unittest.TestCase):
    def setUp(self):
        raw=(HERE/'tests/fixtures/iphoneos-c-run37507597771.map').read_bytes()
        self.assertEqual(len(raw),214129)
        self.assertEqual(ns.sha256(raw),'53ea72932edfcb53555b9fe5affa5d477af2f2cb277b62b229760177d7b289d0')
        names=(HERE/'tests/fixtures/iphoneos-symbols-run37507597771.json').read_bytes()
        self.assertEqual(ns.sha256(names),'965c2b62539bdb90b3cc412e8bb48f615ca2324e2adde51eecbb10a6d3607d64')
        self.required=set(json.loads(names)['symbols']);self.assertEqual(len(self.required),829)
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.library=Path(temporary.name).resolve(strict=True)/'libimobiledevice.a'
        self.library.write_bytes(b'owned path fixture only; no native archive execution')
        original='/Users/runner/work/Tetherless/Tetherless/.c-provider/work/iphoneos/libimobiledevice.a'
        self.assertEqual(raw.decode().count(original),81)
        # Rebase only the 81 exact archive paths for the local canonical file.
        # The retained native fixture itself and all map rows remain unchanged.
        self.text=raw.decode().replace(original,str(self.library))

    def check(self,text):return symbols.link_ownership(text,self.library,self.required)

    def test_actual_map_sections_and_all_829_owners_pass(self):
        result=self.check(self.text)
        self.assertEqual(result['required_live_symbols'],829)
        self.assertEqual({result['owners'][name] for name in symbols.ED},{'41'})
        self.assertEqual({result['owners'][name] for name in symbols.GLUE},{'81'})

    def test_layout_table_rejects_malformed_or_live_symbol_rows(self):
        row='0x100004000\t0x000480E4\t__TEXT\t__text'
        self.assertTrue(row in self.text,'native section row missing from fixture')
        for bad in ('malformed section','0x1 0x2 __TEXT __text extra','0x1 0x2 [ 41] _sha512'):
            with self.subTest(row=bad),self.assertRaisesRegex(ValueError,'unparsed link-map section row'):
                self.check(self.text.replace(row,bad,1))

    def test_unknown_section_marker_does_not_disable_object_checks(self):
        with self.assertRaisesRegex(ValueError,'malformed or duplicate map object'):
            self.check(self.text.replace('# Sections:','# Sections: unexpected',1))

    def test_sections_cannot_restart_after_live_symbols(self):
        with self.assertRaisesRegex(ValueError,'unexpected link-map sections transition'):
            self.check(self.text.replace('# Symbols:\n','# Symbols:\n# Sections:\n',1))

    def test_malformed_or_duplicate_objects_still_fail(self):
        for row in ('malformed object','[  2] '+str(self.library)+'(duplicate.o)'):
            with self.subTest(row=row),self.assertRaisesRegex(ValueError,'malformed or duplicate map object'):
                self.check(self.text.replace('# Sections:\n',row+'\n# Sections:\n',1))

    def test_missing_required_global_still_fails(self):
        changed,count=re.subn(r'(?m)([ \t])_afc_client_free$',r'\1_omitted_afc_client_free',self.text)
        self.assertEqual(count,1)
        with self.assertRaisesRegex(ValueError,'required global missing'):
            self.check(changed)

    def test_duplicate_required_live_global_still_fails(self):
        with self.assertRaisesRegex(ValueError,'ambiguous required map symbol'):
            self.check(self.text+'0x1000 0x40 [ 8] _afc_client_free\n')

    def test_wrong_archive_owner_still_fails(self):
        owner=str(self.library)+'(idevice.o)';self.assertTrue(owner in self.text,'native archive owner missing from fixture')
        with self.assertRaisesRegex(ValueError,'wrong archive owner'):
            self.check(self.text.replace(owner,str(self.library)+'wrong(idevice.o)',1))

    def test_sha_family_owner_collapse_still_fails(self):
        lines=[];changed=0
        for line in self.text.splitlines():
            if line.split() and line.split()[-1] in symbols.GLUE:
                line,count=re.subn(r'\[\s*81\]','[ 41]',line);changed+=count
            lines.append(line)
        self.assertEqual(changed,4)
        with self.assertRaisesRegex(ValueError,'two distinct real members'):
            self.check('\n'.join(lines)+'\n')


class BuildContractTests(unittest.TestCase):
    def test_only_new_workflow_trigger(self):
        w=(HERE.parents[2]/'.github/workflows/c-provider-native.yml').read_text()
        self.assertIn('branches: [verify/staged-pairing-native]',w)
        self.assertIn("if: github.ref == 'refs/heads/verify/staged-pairing-native'",w)
        self.assertNotIn("'Integration/Dependencies/idevice/**'",w)
        self.assertNotIn('brew install',w);self.assertNotIn('brew upgrade',w)
        self.assertIn('(deny network*)',w)
    def test_early_failure_retains_context_log_and_pipefail(self):
        workflow=(HERE.parents[2]/'.github/workflows/c-provider-native.yml').read_text()
        block=workflow.split('      - name: Portable contract checks\n',1)[1].split('      - name:',1)[0]
        body=block.split('        run: |\n',1)[1]
        script='\n'.join(line[10:] if line.startswith('          ') else line for line in body.splitlines())
        for failure in ('portable','host'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as d:
                root=Path(d).resolve(strict=True)
                env={'PATH':os.environ['PATH'],'GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123',
                     'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'c-provider','LANG':'C','LC_ALL':'C'}
                if 'TMPDIR' in os.environ:env['TMPDIR']=os.environ['TMPDIR']
                if failure=='host':
                    # One synthetic passing test reaches the missing host-suite error.
                    tests=root/'Integration/Dependencies/libimobiledevice/tests';tests.mkdir(parents=True)
                    (tests/'test_fixture.py').write_text('import unittest\nclass Fixture(unittest.TestCase):\n    def test_pass(self): self.assertTrue(True)\n')
                # Missing suite paths deliberately fail before any native work.
                run=subprocess.run(['/bin/bash','-c',script],cwd=root,env=env,
                                   stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=15)
                self.assertNotEqual(run.returncode,0)
                evidence=root/'.c-provider/evidence'
                self.assertEqual(json.loads((evidence/'early-run-context.json').read_text())['source_commit'],'a'*40)
                self.assertTrue((evidence/'portable-contracts.log').read_text())
                if failure=='portable':self.assertFalse((evidence/'host-contracts.log').exists())
                else:self.assertTrue((evidence/'host-contracts.log').read_text())
                self.assertIn('            .c-provider/evidence/',workflow)
    def test_force_load_and_declared_frameworks_retained(self):
        b=(HERE/'build_provider.py').read_text()
        for required in ['-force_load','CoreFoundation','SystemConfiguration','link_ownership','internal_global_definitions_unique']:
            self.assertIn(required,b if required!='internal_global_definitions_unique' else (HERE/'symbols.py').read_text())
        declared=(HERE/'upstream/root/src/Makefile.am').read_text()
        self.assertIn('-framework CoreFoundation -framework SystemConfiguration',declared)
    def test_no_old_binary_mutation_or_rust_recipe_edit(self):
        b=(HERE/'build_provider.py').read_text()
        self.assertNotIn('objcopy',b);self.assertNotIn('nmedit',b);self.assertNotIn('strip -',b)
        self.assertIn('consumer_admitted',b);self.assertIn('rust_mixed_provider_verified',b)
    def test_same_openssl_provider_contract(self):
        b=(HERE/'build_provider.py').read_text();self.assertIn('split-provider/provider_inputs.py',b)
        w=(HERE.parents[2]/'.github/workflows/c-provider-native.yml').read_text()
        self.assertIn('fdc9231384f37f053dffe058fd6dfc6c5072dae5',w)
    def test_apple_fingerprint_locked(self):
        b=(HERE/'build_provider.py').read_text()
        for value in ['17C529','23C57','24G830','clang-1700.6.4.2','arm64-apple-ios13.0-simulator']:
            self.assertIn(value,b)
    def test_module_map_is_original(self):
        expected=(HERE/'tests/fixtures/original-c-module.modulemap').read_bytes()
        self.assertEqual(len(expected),927)
        self.assertEqual(ns.sha256(expected),'1c39555aa48cea5eba2067701be79640b7a134809d8abf59970b0abaf88fd66c')
        self.assertEqual(build_provider.module_map_bytes(),expected)

    def test_module_map_reproduces_literal_and_upstream_printf(self):
        recipe=(HERE/'upstream/root/justfile').read_bytes()
        literal=recipe.split(b"export MODULEMAP := '''\n",1)[1].split(b"'''",1)[0]
        output=subprocess.run(['/usr/bin/printf','%s\n',literal.decode('utf-8')],
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=5).stdout
        self.assertEqual(build_provider.module_map_bytes(),output)
        self.assertTrue(output.endswith(b'}\n\n'))

    def test_missing_final_linefeed_still_fails_exact_header_inventory(self):
        expected=(HERE/'tests/fixtures/original-c-module.modulemap').read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve(strict=True);old=root/'old';new=root/'new';old.mkdir();new.mkdir()
            (old/'module.modulemap').write_bytes(expected)
            (new/'module.modulemap').write_bytes(build_provider.module_map_bytes())
            self.assertEqual(build_provider.inventory(new),build_provider.inventory(old))
            (new/'module.modulemap').write_bytes(expected[:-1])
            self.assertNotEqual(build_provider.inventory(new),build_provider.inventory(old))

if __name__=='__main__':unittest.main()
