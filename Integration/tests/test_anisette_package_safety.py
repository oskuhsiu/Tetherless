import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('oda_package', ROOT/'anisette_package_safety.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
REVIEW = Path(os.environ.get('TETHERLESS_AUTH_REVIEW_ROOT', ROOT.parent/'Vendor/SideStore'))
SOURCE = REVIEW/module.SOURCE

class AnisettePackageSafetyTests(unittest.TestCase):
    def test_unknown_input_does_not_create_generated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/module.SOURCE
            path.parent.mkdir(parents=True); path.write_text('unreviewed')
            with self.assertRaises(ValueError): module.apply(root)
            self.assertEqual(list(path.parent.iterdir()), [path])
            self.assertEqual(path.read_text(), 'unreviewed')

    def test_stage_is_part_of_native_preparation(self):
        text = (ROOT/'network_safety.py').read_text()
        self.assertIn('"anisette_package_safety.py"', text)
        self.assertLess(text.index('"authentication_privacy.py"'), text.index('"anisette_package_safety.py"'))

    @unittest.skipUnless(SOURCE.is_file(), 'Pinned source unavailable; actual transform still required by native CI')
    def test_checksum_precedes_every_download_cache_write(self):
        raw = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(), module.EXPECTED)
        text = module.patch(raw.decode())
        body = text.split('public func downloadAndCacheLibs(')[1].split('private func resolveZipData')[0]
        self.assertLess(body.index('AnisettePackageInput.digest'), body.index('resolveZipData(from:'))
        self.assertLess(body.index('AnisettePackageInput.verify'), body.index('fm.createDirectory'))
        self.assertLess(body.index('AnisettePackageInput.verify'), body.index('zipData.write'))
        self.assertLess(body.index('AnisettePackageInput.verify'), body.index('SafeArchive.extract'))
        self.assertIn('defer { admission.release() }', body)
        self.assertNotIn('isCaching', text)
        self.assertNotIn('Proceeding with extraction', text)
        self.assertNotIn('ignoreUnknownCharacters', text)
        self.assertEqual(text.count('try await boundedODAPackageData('), 4)
        for name, end in [('fetchServerList(', 'fetchODAInfo('), ('fetchODAInfo(', 'fetchODAData('), ('resolveZipData(', 'setupFromRemote(')]:
            # Select declarations, not calls in earlier methods.
            prefix = 'public func ' if name != 'resolveZipData(' else 'private func '
            body = text.split(prefix+name)[1].split('    '+ ('private func ' if end=='fetchODAData(' else 'public func ')+end)[0]
            self.assertNotIn('URLSession.shared.data', body)

    @unittest.skipUnless(SOURCE.is_file(), 'Pinned source unavailable; actual transform still required by native CI')
    def test_checked_copy_and_reapplication_fail_without_modification(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); path=root/module.SOURCE
            path.parent.mkdir(parents=True); path.write_bytes(SOURCE.read_bytes())
            module.apply(root)
            self.assertEqual((path.parent/'TetherlessAnisetteHTTPDownload.swift').read_text(),
                             (ROOT.parent/'Sources/TetherlessCore/HTTPDownload.swift').read_text().replace('HTTPDownload','ODAHTTPDownload'))
            self.assertEqual((path.parent/'TetherlessAnisettePackageInput.swift').read_bytes(),
                             (ROOT.parent/'Sources/TetherlessCore/AnisettePackageInput.swift').read_bytes())
            before = {p.name:p.read_bytes() for p in path.parent.iterdir()}
            with self.assertRaises(ValueError): module.apply(root)
            self.assertEqual(before, {p.name:p.read_bytes() for p in path.parent.iterdir()})
            compiler = shutil.which('swiftc')
            if compiler:
                p=subprocess.run([compiler,'-frontend','-parse',str(path)],capture_output=True,text=True,timeout=30)
                self.assertEqual(p.returncode,0,p.stderr)

    def test_exact_namespaced_transfer_compiles_and_rejects_unsafe_url(self):
        compiler = shutil.which('swiftc')
        if not compiler: self.skipTest('Swift compiler unavailable; transfer not compiled')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'HTTP.swift').write_text((ROOT.parent/'Sources/TetherlessCore/HTTPDownload.swift').read_text().replace('HTTPDownload','ODAHTTPDownload'))
            (root/'Main.swift').write_text('''
import Foundation
@main struct Main {
    static func main() async throws {
        let fm=FileManager.default
        let before=Set(try fm.contentsOfDirectory(atPath:fm.temporaryDirectory.path).filter{$0.hasPrefix("tetherless-oda-")})
        do {
            _ = try await boundedODAPackageData(from:URL(string:"http://example.invalid/library.zip")!,maximumBytes:4096)
            fatalError("Insecure transport was accepted")
        } catch ODAHTTPDownloadFailure.invalidURL {}
        let after=Set(try fm.contentsOfDirectory(atPath:fm.temporaryDirectory.path).filter{$0.hasPrefix("tetherless-oda-")})
        precondition(before == after)
        print("PASS")
    }
}
''')
            p=subprocess.run([compiler,'-swift-version','6',str(root/'HTTP.swift'),str(ROOT.parent/'Sources/TetherlessCore/AnisettePackageInput.swift'),
                              str(ROOT/'Overrides/AnisettePackageTransfer.swift'),str(root/'Main.swift'),'-o',str(root/'test')],capture_output=True,text=True,timeout=45)
            self.assertEqual(p.returncode,0,p.stderr)
            p=subprocess.run([str(root/'test')],capture_output=True,text=True,timeout=15)
            self.assertEqual(p.returncode,0,p.stderr); self.assertEqual(p.stdout,'PASS\n')
