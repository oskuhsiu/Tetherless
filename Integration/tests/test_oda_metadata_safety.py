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
        for raw in ["http://unsafe.invalid", "../package.json#blocked", "//user@unsafe.invalid/package.json", "https://", "https://["] {
            let data=try JSONSerialization.data(withJSONObject:["oda":raw])
            do { _=try ValidatedODAMetadata.select(data,source:source,fallback:fallback); fatalError("Unsafe reference used fallback") }
            catch ODAMetadataFailure.invalidURL {}
            do { _=try ValidatedODAMetadata.servers(data,source:source); fatalError("Unsafe reference reached server model") }
            catch ODAMetadataFailure.invalidURL {}
        }
        let nested=URL(string:"https://example.invalid/catalog/v1/list.json?old=1")!
        let references: [(String,URL,String)] = [
            ("../package.json",source,"https://example.invalid/package.json"),
            ("../../../package.json",source,"https://example.invalid/package.json"),
            ("../package.json",nested,"https://example.invalid/catalog/package.json"),
            ("../../../../package.json",nested,"https://example.invalid/package.json"),
            ("../packages/.",source,"https://example.invalid/packages/"),
            ("../packages/..",source,"https://example.invalid/"),
            ("../../pkg%2Fname.json?next=/a/../b&v=%2f%3F%23",source,"https://example.invalid/pkg%2Fname.json?next=/a/../b&v=%2f%3F%23"),
            ("../../%2E%2E/package.json",source,"https://example.invalid/%2E%2E/package.json"),
            ("../../a//b.json?x=1&x=2",source,"https://example.invalid/a//b.json?x=1&x=2"),
            ("../../package.json?",source,"https://example.invalid/package.json?"),
            ("?next=/a/../b&v=%2F",source,"https://example.invalid/list.json?next=/a/../b&v=%2F")
        ]
        for (index,fixture) in references.enumerated() {
            let (raw,base,expected)=fixture
            let data=try JSONSerialization.data(withJSONObject:["servers":[],"oda":raw] as [String:Any])
            let list=try ValidatedODAMetadata.servers(data,source:base)
            guard case .path(let reference) = list.oda else { fatalError("Lost reference model") }
            // Only fixed, public .invalid fixtures are interpolated on failure.
            guard reference == expected else { fatalError("Synthetic reference \(index): \(reference)") }
            let selected=try ValidatedODAMetadata.select(data,source:base,fallback:fallback)
            guard case .reference(let url) = selected else { fatalError("Reference became package") }
            guard url.absoluteString == expected else { fatalError("Synthetic selection \(index): \(url.absoluteString)") }
        }
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
