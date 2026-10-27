from pathlib import Path
import importlib.util
import hashlib
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('ipa_input', ROOT/'ipa_input_safety.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
REVIEW=Path(os.environ.get('TETHERLESS_IPA_REVIEW_ROOT',ROOT.parent/'.generated/SideStore'))

class IPAInputIntegrationTests(unittest.TestCase):
    def test_unknown_source_fails_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); p=root/m.SOURCE; p.parent.mkdir(parents=True); p.write_text('unknown')
            with self.assertRaises(ValueError): m.apply(root)
            self.assertEqual(p.read_text(),'unknown')

    def test_native_external_access_ends_after_only_the_snapshot_copy(self):
        text=(ROOT/'Native/NativeIPAInput.swift').read_text()
        self.assertIn('startAccessingSecurityScopedResource()',text)
        self.assertIn('defer { if scoped { source.stopAccessingSecurityScopedResource() } }',text)
        self.assertIn('options: .withoutChanges',text)
        self.assertIn('IPAInputSnapshot.create(from: authorized, at: destination, check: check)',text)
        self.assertNotIn('unzip',text)
        self.assertLess(text.index('coordinationError == nil'),text.index('try copied.get()'))
        self.assertNotIn('print(',text)

    @unittest.skipUnless((REVIEW/m.SOURCE).exists(),'Prepared IPA input unavailable; native CI still required')
    def test_exact_native_input_uses_same_snapshot_and_no_second_source_copy(self):
        raw=(REVIEW/m.SOURCE).read_bytes()
        self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),m.EXPECTED)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); p=root/m.SOURCE; p.parent.mkdir(parents=True); p.write_bytes(raw)
            m.apply(root); text=p.read_text()
            body=text.split('func downloadIPA(')[1].split('func downloadFile(')[0]
            self.assertEqual(body.count('NativeIPAInput.snapshot('),1)
            self.assertIn('unzipAppBundle(at: input,',body)
            self.assertIn('self.context.ipaURL = input',body)
            self.assertNotIn('copyItem',body)
            self.assertNotIn('resourceValues(',body)
            self.assertIn('external: sourceURL.isFileURL',body)
            self.assertLess(body.index('guard let application'),body.index('self.context.ipaURL = input'))
            self.assertIn('if !sourceURL.isFileURL { try? FileManager.default.removeItem(at: fileURL) }',body)
            result=subprocess.run(['swiftc','-frontend','-parse',str(p),str(ROOT/'Native/NativeIPAInput.swift')],
                                   capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_input_transform_runs_after_network_and_before_remaining_pipeline(self):
        text=(ROOT/'network_safety.py').read_text()
        self.assertLess(text.index('file.write_text(patch_download'),text.index('"ipa_input_safety.py"'))
        self.assertLess(text.index('"ipa_input_safety.py"'),text.index('"auth_safety.py"'))

if __name__=='__main__':unittest.main()
