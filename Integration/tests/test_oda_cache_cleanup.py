"""Native tmp-cleaner/ODA ownership composition, without a new test workflow."""
from pathlib import Path
import hashlib
import importlib.util
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).with_name('fixtures')
spec = importlib.util.spec_from_file_location('oda_cleanup_maintenance', ROOT / 'maintenance_safety.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SWIFTC = shutil.which('swiftc')
EXCLUSION = '            .filter { $0.lastPathComponent != "tetherless-oda-transfers-v1" }'
CORE = ['PrivateFileStore.swift', 'LibraryCacheMaintenance.swift', 'TransferWorkspace.swift']


def original():
    raw = (FIXTURES / 'ClearAppCacheOperation.swift').read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if actual != m.BLOBS[m.CLEAR]:
        raise AssertionError('Unreviewed native cache-cleaner preimage')
    return raw.decode('utf-8')


def cleanup_method(negative=False):
    text = m.patch_clear(original())
    start = '    private func clearTempDirItems('
    end = '    private func removeUninstalledAppBackupDirectories()'
    if text.count(start) != 1 or text.count(end) != 1:
        raise AssertionError('Native cleanup method boundaries changed')
    result = start + text.split(start, 1)[1].split(end, 1)[0]
    if result.count(EXCLUSION) != 1:
        raise AssertionError('Managed pool exclusion missing or ambiguous')
    if negative:
        # The negative control removes only the fix, leaving the native method
        # and production ODA ownership unchanged. It must reproduce the race.
        result = result.replace(EXCLUSION, '', 1)
    return result


def harness(negative=False):
    template = (FIXTURES / 'oda_cache_cleanup_harness.swift').read_text()
    if template.count('CLEANUP_METHOD_HERE') != 1:
        raise AssertionError('Composition harness boundary changed')
    return template.replace('CLEANUP_METHOD_HERE', cleanup_method(negative))


class ODACacheCleanupTests(unittest.TestCase):
    def test_exact_native_preimage_and_single_target_exclusion(self):
        text = m.patch_clear(original())
        self.assertEqual(text.count(EXCLUSION), 1)
        method = cleanup_method()
        self.assertLess(method.index(EXCLUSION), method.index('let count = fileURLs.count'))
        self.assertIn('FileManager.default.removeItem(at: fileURL)', method)
        self.assertIn('options: [.skipsSubdirectoryDescendants, .skipsHiddenFiles]', method)
        self.assertNotIn('TransferWorkspace(', method)
        self.assertNotIn('usage.lock', method.split(EXCLUSION, 1)[1])
        backup_body = text.split('    private func removeUninstalledAppBackupDirectories()', 1)[1]
        self.assertNotIn(EXCLUSION, backup_body)

    def test_reserved_name_matches_production_oda_pool(self):
        source = (ROOT / 'Overrides/AnisettePackageTransfer.swift').read_text()
        pool = re.findall(r'temporaryDirectory\.appendingPathComponent\("([^"]+)", isDirectory: true\)', source)
        self.assertEqual(pool, ['tetherless-oda-transfers-v1'])
        self.assertIn('"' + pool[0] + '"', EXCLUSION)

    def test_full_method_is_executed_with_real_production_transfer_sources(self):
        text = harness()
        self.assertNotIn('CLEANUP_METHOD_HERE', text)
        self.assertEqual(text.count('private func clearTempDirItems('), 1)
        self.assertIn('try clearTempDirItems(at: directory, coordinatorError: nil, check: check)', text)
        self.assertIn('let workspace = try TransferWorkspace(pool:', text)
        self.assertIn('catch LibraryCacheMaintenanceFailure.busy', text)
        self.assertIn('lstat(url.path, &info)', text)
        self.assertIn('try workspace.readOutput(file)', text)
        self.assertIn('try CacheClearProbe().clear(root)', text)
        self.assertIn('try workspace.finish()', text)
        self.assertIn('let next = try TransferWorkspace(pool:', text)
        self.assertTrue(all((ROOT.parent / 'Sources/TetherlessCore' / name).is_file() for name in CORE))

    def test_negative_control_changes_only_the_production_exclusion(self):
        self.assertEqual(cleanup_method().replace(EXCLUSION, '', 1), cleanup_method(negative=True))
        self.assertNotIn(EXCLUSION, cleanup_method(negative=True))
        self.assertIn('negative control reproduced active-pool deletion and replacement lock', harness(True))

    @unittest.skipUnless(SWIFTC, 'Swift compiler unavailable; actual ODA cleanup composition remains pending')
    def test_real_transfer_survives_native_cleanup_and_negative_control_reproduces(self):
        for negative in (False, True):
            with self.subTest(negative_control=negative), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / 'main.swift'
                source.write_text(harness(negative))
                executable = root / 'oda-cleanup-check'
                inputs = [str(ROOT.parent / 'Sources/TetherlessCore' / name) for name in CORE]
                build = subprocess.run([SWIFTC, '-swift-version', '6', '-parse-as-library',
                    *inputs, str(source), '-o', str(executable)], capture_output=True, text=True, timeout=60)
                self.assertEqual(build.returncode, 0, build.stderr)
                data = root / 'tmp'
                data.mkdir()
                run = subprocess.run([str(executable), str(data), 'negative' if negative else 'protected'],
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(run.returncode, 0, run.stderr)
                expected = ('negative control reproduced active-pool deletion and replacement lock' if negative else
                            'ODA pool survives generic cleanup; active ownership and stable inode preserved')
                self.assertIn(expected, run.stdout)


if __name__ == '__main__':
    unittest.main()
