import importlib.util
from pathlib import Path
import unittest
ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('a', ROOT / 'archive_safety.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)

class ArchiveTransformTests(unittest.TestCase):
    def test_shared_unzip_uses_same_tested_implementation(self):
        fixture = 'PRE\n    public func unzipArchive(UNSAFE\n    public struct CompressionLevel: REST'
        value = a.patch_zip(fixture)
        self.assertNotIn('UNSAFE', value)
        self.assertEqual(value.count('SafeArchive.extractIPA'), 2)
        self.assertEqual(value.count('SafeArchive.extract('), 1)
    def test_package_declares_streaming_dependency(self):
        source = '\n    dependencies: [\n                .product(name: "libdeflate", package: "libdeflate"),'
        value = a.patch_package(source)
        self.assertIn('exact: "0.9.20"', value)
        self.assertIn('.product(name: "ZIPFoundation", package: "ZIPFoundation")', value)
    def test_directory_import_cannot_bypass_validator(self):
        value = a.patch_download('BEFORE\n        if resourceValues.isDirectory == true {\nUNSAFE COPY\n            // File, so assuming this is a .ipa file.\nAFTER')
        self.assertNotIn('UNSAFE COPY', value)
        self.assertIn('throw OperationError.invalidParameters', value)
        self.assertIn('AFTER', value)
    def test_pins_and_preparation(self):
        self.assertEqual(set(a.BLOBS), set(a.PATCHES))
        self.assertTrue(all(len(v) == 40 for v in a.BLOBS.values()))
        self.assertIn('archive_safety.py', (ROOT/'prepare.py').read_text())
    def test_production_source_is_the_test_package_not_a_second_copy(self):
        self.assertIn('Packages/TetherlessArchive/Sources/TetherlessArchive', (ROOT/'archive_safety.py').read_text())

if __name__ == '__main__': unittest.main()
