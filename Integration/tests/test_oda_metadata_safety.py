import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('oda_metadata', ROOT/'oda_metadata_safety.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
REVIEW = Path(os.environ.get('TETHERLESS_METADATA_REVIEW_ROOT', ROOT.parent/'.generated/SideStore'))
SOURCE = REVIEW/module.SOURCE

class ODAMetadataIntegrationTests(unittest.TestCase):
    def test_preparation_orders_metadata_after_all_manager_transforms(self):
        text = (ROOT/'network_safety.py').read_text()
        self.assertLess(text.index('"anisette_cache_safety.py"'), text.index('"oda_metadata_safety.py"'))
        self.assertIn('try ODAMetadata.decode(data)', (ROOT/'Overrides/ValidatedODAMetadata.swift').read_text())

    def test_unknown_input_never_partially_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/module.SOURCE
            source.parent.mkdir(parents=True); source.write_text('unreviewed')
            with self.assertRaises(ValueError): module.apply(root)
            self.assertEqual({p.name:p.read_text() for p in source.parent.iterdir()}, {source.name:'unreviewed'})

    @unittest.skipUnless(SOURCE.is_file(), 'Exact prepared metadata input unavailable; native CI required')
    def test_real_transformation_all_routes_and_source_identity(self):
        raw = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(), module.EXPECTED)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/module.SOURCE
            source.parent.mkdir(parents=True); source.write_bytes(raw)
            module.apply(root)
            text = source.read_text()
            body=text.split('public func fetchServerList(')[1].split('public func downloadAndCacheLibs(')[0]
            self.assertNotIn('JSONDecoder',body)
            self.assertNotIn('try?',body)
            for name in ['servers', 'select', 'package']: self.assertIn('try ValidatedODAMetadata.'+name+'(',body)
            self.assertEqual(body.count('try await boundedODAPackageData('),3)
            self.assertEqual((source.parent/'TetherlessODAMetadata.swift').read_bytes(),
                             (ROOT.parent/'Sources/TetherlessCore/ODAMetadata.swift').read_bytes())
            self.assertEqual((source.parent/'ValidatedODAMetadata.swift').read_bytes(),
                             (ROOT/'Overrides/ValidatedODAMetadata.swift').read_bytes())
            before={p.name:p.read_bytes() for p in source.parent.iterdir()}
            with self.assertRaises(ValueError): module.apply(root)
            self.assertEqual(before,{p.name:p.read_bytes() for p in source.parent.iterdir()})
            p=subprocess.run(['swiftc','-frontend','-parse',str(source)],capture_output=True,text=True,timeout=30)
            self.assertEqual(p.returncode,0,p.stderr)

    @unittest.skipUnless(SOURCE.is_file(), 'Exact prepared metadata input unavailable; native CI required')
    def test_generated_destination_collision_preserves_all_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/module.SOURCE
            source.parent.mkdir(parents=True); source.write_bytes(SOURCE.read_bytes())
            (source.parent/'ValidatedODAMetadata.swift').write_text('preserve')
            before={p.name:p.read_bytes() for p in source.parent.iterdir()}
            with self.assertRaises(ValueError): module.apply(root)
            self.assertEqual(before,{p.name:p.read_bytes() for p in source.parent.iterdir()})

    @unittest.skipUnless(SOURCE.is_file(), 'Exact prepared metadata input unavailable; native CI required')
    def test_actual_native_models_and_adapter_compile_and_reject_fallback(self):
        compiler=shutil.which('swiftc')
        if not compiler: self.skipTest('Swift compiler unavailable')
        # Compile actual model declarations from the pinned prepared source,
        # not mock substitutes for ODAInfo/ODAValue/AnisetteServerData.
        text=SOURCE.read_text().split('public final class AnisetteDataManager:')[0]
        text=text.replace('import Crypto\n','').replace('import AnisetteKit\n','')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'Models.swift').write_text(text)
            (root/'Main.swift').write_text(r'''
import Foundation
@main struct Main {
    static func main() throws {
        let source=URL(string:"https://example.invalid/list.json")!
        let fallback=URL(string:"https://fallback.invalid/package.json")!
        let sha=String(repeating:"a",count:64)
        let good=Data("{\"s\":\"\(sha)\",\"l\":\"UEsDBA==\"}".utf8)
        let package=try ValidatedODAMetadata.package(good)
        precondition(package.sha256 == sha && package.base64Payload == "UEsDBA==")
        let direct=try ValidatedODAMetadata.select(good,source:source,fallback:fallback)
        guard case .package = direct else { fatalError("Lost package") }
        let absent=try ValidatedODAMetadata.select(Data("{\"servers\":[]}".utf8),source:source,fallback:fallback)
        guard case .reference(let chosen) = absent, chosen == fallback else { fatalError("Explicit fallback lost") }
        let bad=Data("{\"oda\":false}".utf8)
        do { _=try ValidatedODAMetadata.select(bad,source:source,fallback:fallback); fatalError("Malformed data used fallback") }
        catch ODAMetadataFailure.invalidSchema {}
        do { _=try ValidatedODAMetadata.select(Data("{\"oda\":\"http://unsafe.invalid\"}".utf8),source:source,fallback:fallback); fatalError("Unsafe reference used fallback") }
        catch ODAMetadataFailure.invalidURL {}
        let list=try ValidatedODAMetadata.servers(Data("{\"servers\":[],\"oda\":\"../package.json\"}".utf8),source:source)
        guard case .path(let reference) = list.oda, reference == "https://example.invalid/package.json" else { fatalError("Relative resolution failed") }
        print("PASS")
    }
}
''')
            p=subprocess.run([compiler,'-swift-version','6',str(root/'Models.swift'),
                str(ROOT.parent/'Sources/TetherlessCore/ODAMetadata.swift'),
                str(ROOT.parent/'Sources/TetherlessCore/AnisettePackageInput.swift'),
                str(ROOT/'Overrides/ValidatedODAMetadata.swift'),str(root/'Main.swift'),'-o',str(root/'test')],
                capture_output=True,text=True,timeout=45)
            self.assertEqual(p.returncode,0,p.stderr)
            p=subprocess.run([str(root/'test')],capture_output=True,text=True,timeout=15)
            self.assertEqual(p.returncode,0,p.stderr); self.assertEqual(p.stdout,'PASS\n')
