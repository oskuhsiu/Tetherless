"""Real pinned OCI metadata and synthetic archive checks; no package execution."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]/'tool-setup'
sys.path.insert(0,str(HERE))
import bottle_metadata as metadata

class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.lock=json.loads((HERE/'formula-lock.json').read_bytes())
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve(strict=True)

    def altered(self,name,mutation):
        data=json.loads((HERE/'bottle-manifests'/(name+'.json')).read_bytes());mutation(data)
        path=self.root/(name+'.json');path.write_text(json.dumps(data)+'\n')
        return path,metadata.digest(path)

    def selected(self,data,name='m4'):
        ref=self.lock['formulas'][name]['version']+'.arm64_sequoia'
        return next(m for m in data['manifests'] if m['annotations']['org.opencontainers.image.ref.name']==ref)

    def test_all_four_actual_manifests_authenticate_expected_runtime_closure(self):
        actual=metadata.verify_retained_manifests(self.lock)
        self.assertEqual(set(actual),{'m4','autoconf','automake','libtool'})
        expected={'m4':set(),'autoconf':{'m4'},'automake':{'m4','autoconf'},'libtool':{'m4'}}
        for name,row in actual.items():
            self.assertEqual({d['full_name'] for d in row['tab']['runtime_dependencies']},expected[name])
            self.assertEqual(row['platform']['architecture'],'arm64')
            self.assertEqual(row['platform']['os'],'darwin')

    def test_shared_autoconf_bottle_hash_still_selects_exact_platform_reference(self):
        data=json.loads((HERE/'bottle-manifests/autoconf.json').read_bytes())
        digest=self.lock['formulas']['autoconf']['bottle_sha256']
        self.assertGreater(len([m for m in data['manifests'] if m['annotations']['sh.brew.bottle.digest']==digest]),1)
        row=metadata.verify_manifest(HERE/'bottle-manifests/autoconf.json','autoconf',self.lock)
        self.assertEqual(row['image_ref'],'2.73.arm64_sequoia')

    def test_changed_manifest_bytes_fail_before_metadata_use(self):
        path,_=self.altered('m4',lambda data:data.update(unreviewed=True))
        with self.assertRaisesRegex(ValueError,'manifest identity differs'):
            metadata.verify_manifest(path,'m4',self.lock)

    def test_missing_or_duplicate_matching_descriptor_is_rejected(self):
        for duplicate in (False,True):
            def mutate(data):
                selected=self.selected(data)
                if duplicate:data['manifests'].append(copy.deepcopy(selected))
                else:data['manifests'].remove(selected)
            path,sha=self.altered('m4',mutate)
            with patch.dict(metadata.MANIFEST_SHA256,{'m4':sha}),self.assertRaisesRegex(ValueError,'one exact bottle'):
                metadata.verify_manifest(path,'m4',self.lock)

    def test_extra_runtime_package_missing_metadata_and_wrong_version_rejected(self):
        def change_tab(data,value):
            selected=self.selected(data,'autoconf');tab=json.loads(selected['annotations']['sh.brew.tab'])
            tab['runtime_dependencies']=value;selected['annotations']['sh.brew.tab']=json.dumps(tab)
        real=metadata.verify_manifest(HERE/'bottle-manifests/autoconf.json','autoconf',self.lock)['tab']['runtime_dependencies']
        cases=[None,[],real+[{'full_name':'unexpected','version':'1'}],real+real,
               [{**real[0],'version':'999'}],[{**real[0],'compatibility_version':True}]]
        for value in cases:
            path,sha=self.altered('autoconf',lambda data:change_tab(data,value))
            with patch.dict(metadata.MANIFEST_SHA256,{'autoconf':sha}),self.assertRaises(ValueError):
                metadata.verify_manifest(path,'autoconf',self.lock)

    def test_missing_and_multiple_owned_cached_manifests_rejected(self):
        cache=self.root/'cache';downloads=cache/'downloads';downloads.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'one owned cached'):
            metadata.cached_manifest(cache,'m4',self.lock)
        raw=(HERE/'bottle-manifests/m4.json').read_bytes()
        for prefix in ('first','second'):(downloads/(prefix+'--m4-1.4.21.bottle_manifest.json')).write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'one owned cached'):
            metadata.cached_manifest(cache,'m4',self.lock)

class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve(strict=True);self.output=self.root/'evidence';self.output.mkdir()
        self.cache=self.root/'cache';(self.cache/'downloads').mkdir(parents=True)
        self.lock=json.loads((HERE/'formula-lock.json').read_bytes())

    def fixture(self,receipt_count=0,receipt_deps=None):
        path=self.cache/'m4.bottle.tar.gz'
        with tarfile.open(path,'w:gz') as tar:
            info=tarfile.TarInfo('m4/1.4.21/bin/m4');raw=b'synthetic text; never executed';info.size=len(raw);tar.addfile(info,io.BytesIO(raw))
            for _ in range(receipt_count):
                raw=json.dumps({'runtime_dependencies':receipt_deps or []}).encode()
                info=tarfile.TarInfo('m4/1.4.21/INSTALL_RECEIPT.json');info.size=len(raw);tar.addfile(info,io.BytesIO(raw))
        self.lock['formulas']['m4']['bottle_sha256']=metadata.digest(path)
        data=json.loads((HERE/'bottle-manifests/m4.json').read_bytes())
        selected=next(m for m in data['manifests'] if m['annotations']['org.opencontainers.image.ref.name']=='1.4.21.arm64_sequoia')
        selected['annotations']['sh.brew.bottle.digest']=metadata.digest(path)
        selected['annotations']['sh.brew.bottle.size']=str(path.stat().st_size)
        manifest=self.cache/'downloads/fixture--m4-1.4.21.bottle_manifest.json';manifest.write_text(json.dumps(data)+'\n')
        return path,manifest,metadata.digest(manifest)

    def inspect(self,path):return metadata.inspect_bottle(path,'m4',self.lock,self.cache,self.output)

    def test_receipt_free_archive_requires_authenticated_tab_and_is_retained(self):
        path,manifest,sha=self.fixture()
        with patch.dict(metadata.MANIFEST_SHA256,{'m4':sha}):result=self.inspect(path)
        self.assertEqual(result['state'],'verified');self.assertEqual(result['receipt_paths'],[])
        self.assertEqual(result['runtime_dependencies'],[]);self.assertTrue(result['inventory_complete'])
        self.assertEqual(Path(result['retained_bottle']).read_bytes(),path.read_bytes())
        self.assertEqual((self.output/'m4-bottle-manifest.json').read_bytes(),manifest.read_bytes())
        metadata.audit_bottle_inputs({'m4':result})

    def test_missing_manifest_retains_archive_and_complete_inventory_then_fails(self):
        path,manifest,_=self.fixture();manifest.unlink()
        with self.assertRaisesRegex(ValueError,'one owned cached'):self.inspect(path)
        evidence=json.loads((self.output/'m4-bottle-inspection.json').read_bytes())
        self.assertEqual(evidence['state'],'failed');self.assertEqual(evidence['receipt_paths'],[])
        self.assertTrue(evidence['inventory_complete']);self.assertTrue(Path(evidence['retained_bottle']).is_file())

    def test_changed_bottle_hash_is_rejected_and_recorded_before_retention(self):
        path,_,_=self.fixture();path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'bottle byte identity'):self.inspect(path)
        evidence=json.loads((self.output/'m4-bottle-inspection.json').read_bytes())
        self.assertEqual(evidence['state'],'failed');self.assertNotIn('retained_bottle',evidence)

    def test_duplicate_embedded_receipts_still_fail_with_inventory(self):
        path,_,sha=self.fixture(receipt_count=2)
        with patch.dict(metadata.MANIFEST_SHA256,{'m4':sha}),self.assertRaisesRegex(ValueError,'duplicate embedded'):
            self.inspect(path)
        self.assertEqual(len(json.loads((self.output/'m4-bottle-inspection.json').read_bytes())['receipt_paths']),2)

    def test_embedded_runtime_receipt_cannot_disagree_with_authenticated_tab(self):
        path,_,sha=self.fixture(receipt_count=1,receipt_deps=[{'full_name':'unexpected','version':'1'}])
        with patch.dict(metadata.MANIFEST_SHA256,{'m4':sha}),self.assertRaisesRegex(ValueError,'runtime metadata differ'):
            self.inspect(path)

    def test_cached_bottle_or_manifest_mutation_fails_final_audit(self):
        path,manifest,sha=self.fixture()
        with patch.dict(metadata.MANIFEST_SHA256,{'m4':sha}):result=self.inspect(path)
        for target in (path,manifest):
            original=target.read_bytes();target.write_bytes(original+b'changed')
            with self.assertRaisesRegex(ValueError,'verified bottle input changed'):
                metadata.audit_bottle_inputs({'m4':result})
            target.write_bytes(original)

    def test_evidence_write_failure_preserves_primary_bottle_error(self):
        path,_,_=self.fixture();path.write_bytes(path.read_bytes()+b'changed')
        with patch.object(metadata,'write',side_effect=OSError('synthetic evidence failure')):
            with self.assertRaisesRegex(ValueError,'bottle byte identity') as caught:self.inspect(path)
        self.assertIn('synthetic evidence failure',caught.exception.__notes__[0])

    def test_evidence_write_failure_after_validation_still_fails(self):
        path,_,sha=self.fixture()
        with patch.dict(metadata.MANIFEST_SHA256,{'m4':sha}), \
             patch.object(metadata,'write',side_effect=OSError('synthetic evidence failure')), \
             self.assertRaisesRegex(OSError,'synthetic evidence failure'):
            self.inspect(path)

if __name__=='__main__':unittest.main()
