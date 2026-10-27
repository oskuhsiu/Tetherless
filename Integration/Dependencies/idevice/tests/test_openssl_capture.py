from pathlib import Path
import hashlib
import importlib.util
import json
import tempfile
import tarfile
import unittest

HERE=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('retain_openssl_inputs',HERE/'retain_openssl_inputs.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class OpenSSLCaptureTests(unittest.TestCase):
    def fixture(self,root):
        source=root/'source';source.mkdir();data=b'public fixture';p=source/'header.h';p.write_bytes(data);p.chmod(0o644)
        manifest={'repository':'fixture','commit':'fixture','tree':'fixture','scope':'unit test',
                  'entries':[{'path':'header.h','mode':'100644','size':len(data),
                              'git_blob':hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()}]}
        return source,manifest

    def test_pinned_inventory(self):
        manifest=m.load_manifest();entries=manifest['entries']
        self.assertEqual(len(entries),447)
        self.assertEqual(sum(x['size'] for x in entries),40574701)
        self.assertEqual(manifest['commit'],'fdc9231384f37f053dffe058fd6dfc6c5072dae5')
        self.assertEqual(len({x['path'] for x in entries}),len(entries))
        for x in entries:self.assertNotIn(x['path'].split('/')[0],['.git','keys'])

    def test_capture_preserves_input_and_records_observed_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,manifest=self.fixture(root);before=(source/'header.h').read_bytes();out=root/'capture'
            receipt=m.capture(source,out,manifest)
            self.assertEqual((out/'inputs/header.h').read_bytes(),before)
            self.assertEqual((source/'header.h').read_bytes(),before)
            self.assertEqual(receipt['entries'][0]['sha256'],hashlib.sha256(before).hexdigest())
            self.assertEqual(json.loads((out/'receipt.json').read_text()),receipt)
            self.assertFalse(receipt['binary_execution']);self.assertFalse(receipt['product_activation'])
            with self.assertRaises(ValueError):m.capture(source,out,manifest)

    def test_archive_round_trip_preserves_bytes_names_and_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,manifest=self.fixture(root)
            data=b'opaque library fixture';p=source/'library';p.write_bytes(data);p.chmod(0o755)
            manifest['entries'].append({'path':'library','mode':'100755','size':len(data),
                'git_blob':hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()})
            out=root/'capture';receipt=m.capture(source,out,manifest);archive=root/'capture.tar'
            m.archive_capture(out,archive,receipt)
            with tarfile.open(archive,'r:') as tar:
                self.assertEqual(tar.getnames(),['inputs/header.h','inputs/library','receipt.json'])
                for entry in receipt['entries']:
                    name='inputs/'+entry['path'];member=tar.getmember(name)
                    self.assertTrue(member.isfile());self.assertEqual(member.mode,int(entry['mode'][-3:],8))
                    body=tar.extractfile(member).read()
                    self.assertEqual(hashlib.sha256(body).hexdigest(),entry['sha256'])
                self.assertEqual(json.loads(tar.extractfile('receipt.json').read()),receipt)
            with self.assertRaises(ValueError):m.archive_capture(out,archive,receipt)

    def test_tampering_does_not_publish_output(self):
        for kind in ['size','content','missing','mode','symlink']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);source,manifest=self.fixture(root);p=source/'header.h';out=root/'capture'
                if kind=='size':p.write_bytes(b'short')
                if kind=='content':p.write_bytes(b'PUBLIC FIXTURE')
                if kind=='missing':p.unlink()
                if kind=='mode':p.chmod(0o755)
                if kind=='symlink':
                    p.rename(source/'target');p.symlink_to('target')
                with self.assertRaises((ValueError,OSError)):m.capture(source,out,manifest)
                self.assertFalse(out.exists())

    def test_invalid_paths_and_duplicates_rejected_before_copy(self):
        for path in ['/outside','../outside','a/../outside','./header.h','']:
            with self.subTest(path=path),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);source,manifest=self.fixture(root);manifest['entries'][0]['path']=path
                with self.assertRaises(ValueError):m.capture(source,root/'capture',manifest)
                self.assertFalse((root/'capture.partial').exists())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,manifest=self.fixture(root);manifest['entries']*=2
            with self.assertRaises(ValueError):m.capture(source,root/'capture',manifest)


if __name__=='__main__':unittest.main()
