from pathlib import Path
import importlib.util
import tempfile
import unittest
ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('network', ROOT/'network_safety.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class NetworkIntegrationTests(unittest.TestCase):
    def test_no_legacy_download_or_dependency_fallback(self):
        source = '''    private let session = URLSession(configuration: .default)
    private var activeDownloadTask: URLSessionDownloadTask?
        self.activeDownloadTask?.cancel()
        guard let sourceURL = self.sourceURL else {
    func downloadFile(from downloadURL: URL) async throws -> URL {
UNSAFE DELEGATE AND POST-EXTRACTION MUTATIONS
'''
        result = m.patch_download(source)
        self.assertNotIn('UNSAFE',result)
        self.assertNotIn('URLSession(configuration:',result)
        self.assertNotIn('self.sourceURL',result)
        self.assertIn('BoundedHTTPDownload()',result)
        self.assertIn('boundedDownload.cancel()',result)
        self.assertIn('app.url',result)
        self.assertIn('DependencyManifestPolicy.validate(data)',result)
        self.assertIn('maximum: 262_144',result)
        self.assertIn('if self.isCancelled',result)
    def test_pinned_input_is_not_modified_on_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); file=root/m.DOWNLOAD; file.parent.mkdir(parents=True); file.write_text('unknown')
            with self.assertRaises(ValueError): m.apply(root)
            self.assertEqual(file.read_text(),'unknown')
    def test_network_patch_runs_after_archive_boundary(self):
        source=(ROOT/'archive_safety.py').read_text()
        self.assertLess(source.index('shutil.copyfile(path'),source.index('with_name("network_safety.py")'))
        self.assertEqual(len(m.BLOBS[m.DOWNLOAD]),40)

if __name__ == '__main__': unittest.main()
