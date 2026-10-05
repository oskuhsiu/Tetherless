"""Pinned backup transform and lease-lifetime tests, not Apple coordination proof."""
from pathlib import Path
import hashlib
import importlib.util
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('backup_lifetime', ROOT / 'backup_lifetime_safety.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
FIXTURE = Path(__file__).with_name('fixtures') / 'RemoveBackupDataOperation.swift'
HELPER_FIXTURE = FIXTURE.with_name('FileManager+Backups.swift')
SWIFTC = shutil.which('swiftc')


def original():
    raw = FIXTURE.read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if actual != m.EXPECTED:
        raise AssertionError('Bundled upstream backup preimage changed')
    return raw.decode('utf-8')


def originals():
    values = {m.SOURCE: original(), m.HELPER: HELPER_FIXTURE.read_text()}
    for relative, text in values.items():
        raw = text.encode()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != m.BLOBS[relative]:
            raise AssertionError('Bundled backup preimage changed: ' + relative)
    return values


def write_preimages(root):
    for relative, text in originals().items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


def harness():
    # Run the entire generated operation, not a rewrite of its execute method.
    # Only its platform services are doubles. The scope and ProcessLease are
    # the production code and deletion actually removes a temporary directory.
    operation = m.patch(original()).replace('NSFileCoordinator', 'TestFileCoordinator').replace(
        'NSFileAccessIntent', 'TestFileAccessIntent').replace('FileManager.default', 'TestFileManager.shared')
    persistence = (ROOT.parent / 'Sources/TetherlessCore/Persistence.swift').read_text()
    lease = 'public final class ProcessLease:' + persistence.split('public final class ProcessLease:', 1)[1].split(
        '/// Non-secret state only.', 1)[0]
    storage = (ROOT / 'Native/NativeRenewalStorage.swift').read_text()
    gate = 'enum NativeMutationGate {' + storage.split('enum NativeMutationGate {', 1)[1]
    gate += (ROOT / 'Native/NativePairingMutation.swift').read_text()
    helper = m.patch_helper(originals()[m.HELPER]).replace(
        'public extension FileManager', 'extension TestFileManager').replace('NSFileCoordinator', 'TestFileCoordinator')
    return (Path(__file__).with_name('fixtures') / 'backup_lifetime_harness.swift').read_text().replace(
        'LEASE_HERE', lease).replace('GATE_HERE', gate).replace('OPERATION_HERE', operation).replace('HELPER_HERE', helper)


class BackupLifetimeTests(unittest.TestCase):
    def test_exact_pinned_source_applies_once(self):
        text = original()
        with tempfile.TemporaryDirectory() as tmp:
            write_preimages(Path(tmp))
            target = Path(tmp) / m.SOURCE
            m.apply(Path(tmp))
            self.assertEqual(target.read_text(), m.patch(text))
            self.assertEqual((Path(tmp) / m.HELPER).read_text(), m.patch_helper(originals()[m.HELPER]))
            with self.assertRaises(ValueError):
                m.apply(Path(tmp))

    def test_mismatch_fails_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / m.SOURCE
            target.parent.mkdir(parents=True)
            target.write_text(original() + '// changed\n')
            before = target.read_bytes()
            with self.assertRaises(ValueError):
                m.apply(Path(tmp))
            self.assertEqual(target.read_bytes(), before)

    def test_missing_and_duplicate_anchors_fail_closed(self):
        for text in ('unknown', original() * 2):
            with self.assertRaises(ValueError):
                m.patch(text)
        for text in ('unknown', originals()[m.HELPER] * 2):
            with self.assertRaises(ValueError):
                m.patch_helper(text)

    def test_helper_preimage_mismatch_never_publishes_first_transform(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_preimages(root)
            target = root / m.HELPER
            target.write_text(target.read_text() + '// drift\n')
            with self.assertRaises(ValueError):
                m.apply(root)
            self.assertEqual((root / m.SOURCE).read_text(), original())
            self.assertEqual(target.read_text(), originals()[m.HELPER] + '// drift\n')

    def test_direct_helper_coordinates_authorized_url_inside_synchronous_lease(self):
        text = m.patch_helper(originals()[m.HELPER])
        self.assertIn('try NativeMutationGate.withSynchronousLease {', text)
        self.assertLess(text.index('withSynchronousLease'), text.index('guard let backupDirectoryURL'))
        self.assertIn('self.backupDirectoryURL(forBundleIdentifier: app.resignedBundleIdentifier)', text)
        self.assertNotIn('self.deleteBackup(forBundleIdentifier:', text)
        self.assertIn('self.fileExists(atPath: backupDirectoryURL.path) else { return }', text)
        self.assertIn('self.fileExists(atPath: authorized.path) else { return }', text)
        self.assertIn('try self.removeItem(at: authorized)', text)
        self.assertIn('if let coordinationError { throw coordinationError }', text)
        self.assertIn('guard let deletion else { throw OperationError.unknownResult }', text)
        self.assertIn('try deletion.get()\n            try Task.checkCancellation()', text)
        self.assertNotIn('try?', text)
        self.assertNotIn('Task {', text)
        self.assertNotIn('ProcessLease.acquire', text)

    def test_direct_execute_and_snapshot_are_inside_existing_lease(self):
        text = m.patch(original())
        wrapper, body = text.split('    private func executeWithNativeLease(', 1)
        self.assertIn('return try await NativeMutationGate.withLease {', wrapper)
        self.assertIn('return try await self.executeWithNativeLease(parentProgress: parentProgress)', wrapper)
        self.assertIn('try Task.checkCancellation()', wrapper)
        self.assertIn('try backupCancellation.check()', wrapper)
        self.assertIn('managedObjectContext?.perform', body)
        self.assertNotIn('Task {', text)
        self.assertNotIn('Task.detached', text)
        self.assertNotIn('ProcessLease.acquire', text)
        self.assertNotIn('device-mutation.lock', text)

    def test_task_operation_and_progress_cancel_reach_same_callback_token(self):
        text = m.patch(original())
        self.assertIn('override func cancel() {\n        backupCancellation.cancel()\n        super.cancel()', text)
        self.assertIn('} onCancel: {\n            self.backupCancellation.cancel()', text)
        self.assertIn('try backupCancellation.check()\n        guard let backupDirectoryURL else', text)
        self.assertIn('try check()\n            try FileManager.default.removeItem(at: url)', text)
        self.assertNotIn('cancelAllOperations', text)
        self.assertNotIn('coordinator.cancel', text)

    def test_delete_is_in_accessor_using_authorized_url(self):
        text = m.patch(original())
        accessor = text.split('try await self.coordinator.coordinateBackupMutation(', 1)[1].split(
            '        try backupCancellation.check()', 1)[0]
        self.assertIn(') { [self] authorized in', accessor)
        self.assertIn('try self.removeBackupItem(at: authorized,', accessor)
        self.assertNotIn('at: intent.url', text)
        self.assertNotIn('try await self.coordinator.coordinate(with:', text)
        self.assertIn('options: [.forDeleting]', text)
        self.assertEqual(text.count('FileManager.default.removeItem(at:'), 1)
        self.assertNotIn('contentsOfDirectory', text)

    def test_deletion_scope_and_existing_idempotence_are_preserved(self):
        text = m.patch(original())
        self.assertIn('FileManager.default.backupDirectoryURL(for: installedApp)', text)
        self.assertIn('catch let error as CocoaError where error.code == .fileNoSuchFile', text)
        self.assertIn('            throw error\n', text)
        self.assertNotIn('try?', text)
        self.assertIn('guard FileManager.default.fileExists(atPath: backupDirectoryURL.path)', text)

    def test_serial_completion_reuses_reviewed_maintenance_contract(self):
        spec = importlib.util.spec_from_file_location('maintenance_reference', ROOT / 'maintenance_safety.py')
        reference = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reference)
        self.assertEqual(m.coordination_bridge(), reference.COORDINATED_MUTATION.replace('Maintenance', 'Backup'))
        text = m.patch(original())
        self.assertIn('queue.maxConcurrentOperationCount = 1', text)
        bridge = m.coordination_bridge()
        self.assertLess(bridge.index('try body(access.intent.url)'),
                        bridge.index('queue.addOperation { continuation.resume(with: result) }'))
        self.assertIn('try body(access.intent.url)\n                    try cancellation.check()', bridge)
        self.assertNotIn('cancel()', bridge.split('private extension NSFileCoordinator', 1)[1])

    def test_harness_waits_in_synchronous_gcd_work_only(self):
        text = harness()
        self.assertNotIn('Task.detached', text)
        self.assertIn('DispatchQueue.global().async {\n                semaphore.wait()', text)
        self.assertIn('await withCheckedContinuation', text)
        self.assertEqual(text.count('final class RemoveBackupDataOperation:'), 1)
        self.assertNotIn('OPERATION_HERE', text)

    def test_harness_scenarios_do_not_inherit_main_actor(self):
        text = harness()
        entry = text.split('    static func main() async throws {', 1)[1].split('    }', 1)[0]
        self.assertEqual(entry.strip(), 'try await runChecks()')
        suite = text.split('    nonisolated static func runChecks() async throws {', 1)[1]
        self.assertEqual(suite.count('NativeMutationGate.withLease {'), 3)
        self.assertIn('let child: Task<Bool, Error>', suite)
        self.assertNotIn('@MainActor', suite)

    @unittest.skipUnless(SWIFTC, 'Swift compiler unavailable; native parse remains unverified')
    def test_generated_native_source_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'RemoveBackupDataOperation.swift'
            source.write_text(m.patch(original()))
            helper = Path(tmp) / 'FileManager+Backups.swift'
            helper.write_text(m.patch_helper(originals()[m.HELPER]))
            result = subprocess.run([SWIFTC, '-frontend', '-parse', str(source), str(helper)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(SWIFTC, 'Swift compiler unavailable; runtime ownership checks remain unverified')
    def test_full_operation_lease_cancellation_errors_nesting_and_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'main.swift'
            source.write_text(harness())
            executable = root / 'backup-check'
            build = subprocess.run([SWIFTC, '-swift-version', '6', '-parse-as-library',
                str(ROOT.parent / 'Sources/TetherlessCore/MutationScope.swift'), str(source), '-o', str(executable)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(executable), str(root)], capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('backup lifetime checks passed', run.stdout)


if __name__ == '__main__':
    unittest.main()
