import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('cache_patch', ROOT/'anisette_cache_safety.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
REVIEW = Path(os.environ.get('TETHERLESS_CACHE_REVIEW_ROOT', ROOT.parent/'.generated/SideStore'))
SOURCE = REVIEW/module.SOURCE

class AnisetteCacheSafetyTests(unittest.TestCase):
    def test_invalid_source_and_destination_do_not_mutate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/module.SOURCE
            source.parent.mkdir(parents=True); source.write_text('unreviewed')
            with self.assertRaises(ValueError): module.apply(root)
            self.assertEqual(list(source.parent.iterdir()), [source])
            self.assertEqual(source.read_text(), 'unreviewed')

    def test_installed_after_package_boundary(self):
        text = (ROOT/'network_safety.py').read_text()
        self.assertLess(text.index('"anisette_package_safety.py"'), text.index('"anisette_cache_safety.py"'))

    @unittest.skipUnless(SOURCE.is_file(), 'Prepared pinned cache input unavailable; native CI still required')
    def test_real_transformation_and_byte_identical_cache(self):
        raw = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(), module.EXPECTED)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/module.SOURCE
            source.parent.mkdir(parents=True); source.write_bytes(raw)
            module.apply(root)
            text = source.read_text()
            self.assertNotIn('AnisetteClient.validateLibrariesExist', text)
            self.assertNotIn('self.localProvider', text)
            self.assertIn('try libraryCache(at: libDir).pinCurrent()', text)
            self.assertIn('guard let pinned = try pinLibraries()', text)
            self.assertIn('libraryDirectoryResolver: { pinned.directory }', text)
            self.assertIn('SafeArchive.extract(at: archive, toDirectory: staging', text)
            body = text.split('public func downloadAndCacheLibs(')[1].split('private func resolveZipData(')[0]
            self.assertLess(body.index('AnisettePackageInput.verify'), body.index('.install(archive:'))
            self.assertLess(body.index('AnisettePackageInput.verify'), body.index('fm.createDirectory'))
            for name in ['AnisetteLibraryCache', 'PrivateFileStore', 'LibraryCacheMaintenance']:
                self.assertEqual((source.parent/('Tetherless'+name+'.swift')).read_bytes(),
                                 (ROOT.parent/'Sources/TetherlessCore'/(name+'.swift')).read_bytes())
            self.assertEqual(text.count('return LibraryPinnedAnisetteClient(client: client, generation: pinned)'), 2)
            wrapper = (ROOT.parent/'Integration/Overrides/LibraryPinnedAnisetteClient.swift').read_bytes()
            self.assertEqual((source.parent/'LibraryPinnedAnisetteClient.swift').read_bytes(), wrapper)
            self.assertIn('defer { withExtendedLifetime(lifetime) {} }', wrapper.decode())
            self.assertIn('try libraryCache(at: remoteLibsDir).pruneUnused()', text)
            before = {p.name:p.read_bytes() for p in source.parent.iterdir()}
            with self.assertRaises(ValueError): module.apply(root)
            self.assertEqual(before, {p.name:p.read_bytes() for p in source.parent.iterdir()})
            compiler = shutil.which('swiftc')
            if compiler:
                result = subprocess.run([compiler,'-frontend','-parse',str(source)],capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stderr)

    @unittest.skipUnless(SOURCE.is_file(), 'Prepared pinned cache input unavailable; native CI still required')
    def test_unexpected_generated_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/module.SOURCE
            source.parent.mkdir(parents=True); source.write_bytes(SOURCE.read_bytes())
            target = source.parent/'TetherlessPrivateFileStore.swift'; target.write_text('preserve')
            before = {p.name:p.read_bytes() for p in source.parent.iterdir()}
            with self.assertRaises(ValueError): module.apply(root)
            self.assertEqual(before, {p.name:p.read_bytes() for p in source.parent.iterdir()})
