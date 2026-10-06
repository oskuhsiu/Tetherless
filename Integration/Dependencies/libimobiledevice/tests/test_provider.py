import copy
import importlib.util
import json
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
        root=Path(t.name)/'root';shutil.copytree(HERE/'upstream/root',root)
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
                with self.assertRaises(ValueError):source_inputs.safe_file(Path(d),p)

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
    def map_fixture(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);lib=Path(t.name)/'libimobiledevice.a';lib.write_bytes(b'fixture')
        text='# Object files:\n[ 1] '+str(lib)+'[41](sha512.o)\n[ 2] '+str(lib)+'[81](sha512.o)\n[ 3] '+str(lib)+'(api.o)\n# Symbols:\n'
        for name in sorted(symbols.REQUIRED|symbols.GLUE|symbols.ED):
            owner=1 if name in symbols.ED else 2 if name in symbols.GLUE else 3
            text+='0x1000 0x40 [ %s] %s\n'%(owner,name)
        return lib,text
    def test_map_owns_all_globals_and_both_families(self):
        lib,text=self.map_fixture();r=symbols.link_ownership(text,lib,symbols.REQUIRED|symbols.GLUE|symbols.ED);self.assertNotEqual(r['ed25519_sha512_member'],r['glue_sha512_member'])
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

class BuildContractTests(unittest.TestCase):
    def test_only_new_workflow_trigger(self):
        w=(HERE.parents[2]/'.github/workflows/c-provider-native.yml').read_text()
        self.assertIn('branches: [verify/staged-pairing-native]',w)
        self.assertIn("if: github.ref == 'refs/heads/verify/staged-pairing-native'",w)
        self.assertNotIn("'Integration/Dependencies/idevice/**'",w)
        self.assertNotIn('brew install',w);self.assertNotIn('brew upgrade',w)
        self.assertIn('(deny network*)',w)
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
        j=(HERE/'upstream/root/justfile').read_text();m=j.split("export MODULEMAP := '''\n",1)[1].split("\n'''",1)[0]
        self.assertTrue(m.startswith('module libimobiledevice [system]'))
        self.assertIn('header "../plist/plist.h"',m)

if __name__=='__main__':unittest.main()
