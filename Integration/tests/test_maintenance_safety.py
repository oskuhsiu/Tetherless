"""Exact-source transformation checks; portable lease tests are not native UI proof."""
from pathlib import Path
import hashlib
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


m = module('maintenance_safety')
catalog = module('catalog_safety')
REVIEW = Path(os.environ.get('TETHERLESS_MAINTENANCE_REVIEW_ROOT',
                            ROOT.parent / 'Vendor/SideStore'))
HAS_PREIMAGES = all((REVIEW / path).is_file() for path in m.BLOBS)
SWIFTC = shutil.which('swiftc')


def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def preimages():
    values = {path: (REVIEW / path).read_bytes() for path in m.BLOBS}
    # Native CI has the real pinned vendor. An independently retained prepared
    # source artifact is also useful, but its hash must match the precise stage.
    if blob(values[m.APP]) == catalog.BLOBS[catalog.MANAGER]:
        values[m.APP] = catalog.patch_manager(values[m.APP].decode()).encode()
    for path, raw in values.items():
        if blob(raw) != m.BLOBS[path]:
            raise AssertionError('Native maintenance preimage mismatch: ' + path)
    return values


def patched():
    return {path: m.PATCHES[path](raw.decode()) for path, raw in preimages().items()}


class MaintenanceTransformTests(unittest.TestCase):
    def test_unreviewed_inputs_are_not_partially_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for path in m.BLOBS:
                file = root / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('unreviewed')
            with self.assertRaises(ValueError):
                m.apply(root)
            self.assertTrue(all((root / path).read_text() == 'unreviewed' for path in m.BLOBS))

    def test_all_anchors_reject_absent_or_duplicate_bodies(self):
        for patch in m.PATCHES.values():
            with self.assertRaises(ValueError):
                patch('unknown')
        if HAS_PREIMAGES:
            for path, raw in preimages().items():
                with self.assertRaises(ValueError):
                    m.PATCHES[path](raw.decode() * 2)

    def test_order_preserves_catalog_preimage_guard(self):
        text = (ROOT / 'network_safety.py').read_text()
        self.assertEqual(text.count('with_name("maintenance_safety.py")'), 1)
        self.assertLess(text.index('with_name("catalog_safety.py")'),
                        text.index('with_name("maintenance_safety.py")'))

    @unittest.skipUnless(HAS_PREIMAGES, 'Pinned native maintenance sources unavailable')
    def test_exact_preimages_apply_and_second_file_mismatch_preserves_first(self):
        originals = preimages()
        for bad_second in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for path, raw in originals.items():
                    file = root / path
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_bytes(raw)
                if bad_second:
                    (root / m.CLEAR).write_text('unreviewed second source')
                    with self.assertRaises(ValueError):
                        m.apply(root)
                    self.assertEqual((root / m.APP).read_bytes(), originals[m.APP])
                    self.assertEqual((root / m.CLEAR).read_text(), 'unreviewed second source')
                else:
                    m.apply(root)
                    for path, text in patched().items():
                        self.assertEqual((root / path).read_text(), text)
                    with self.assertRaises(ValueError):
                        m.apply(root)

    @unittest.skipUnless(HAS_PREIMAGES, 'Pinned native maintenance sources unavailable')
    def test_snapshot_and_pruning_share_one_awaited_scope(self):
        text = patched()[m.APP]
        wrapper, body = text.split('    private func reconcileInstalledAppsWithNativeLease() async {', 1)
        wrapper = wrapper.split('    func reconcileInstalledApps() async {', 1)[1]
        self.assertIn('try await NativeMutationGate.withLease {', wrapper)
        self.assertIn('await self.reconcileInstalledAppsWithNativeLease()', wrapper)
        self.assertIn('update.phase.isPending', wrapper)
        self.assertLess(wrapper.index('NativeManagerUpdate.journal().read()'),
                        wrapper.index('await self.reconcileInstalledAppsWithNativeLease()'))
        self.assertIn('throw ManagerUpdateFailure.pendingUpdate', wrapper)
        self.assertNotIn('Task {', wrapper)
        self.assertNotIn('Task.detached', wrapper)
        self.assertNotIn('isActivelyManagingAnyApp', wrapper)
        self.assertLess(body.index('dbBackgroundContext.perform'), body.index('pruneUnusedCaches'))
        self.assertIn('try Task.checkCancellation()\n            await scheduleExpirationWarning', body)
        self.assertIn('try Task.checkCancellation()\n\n            CacheAppOperation.pruneUnusedCaches', body)

    @unittest.skipUnless(HAS_PREIMAGES, 'Pinned native maintenance sources unavailable')
    def test_clear_guard_covers_callbacks_and_checks_cancellation_before_deletion(self):
        text = patched()[m.CLEAR]
        wrapper, body = text.split('    private func executeWithNativeLease(parentProgress: Progress?) async throws -> Bool {', 1)
        wrapper = wrapper.split('    override func execute(parentProgress: Progress?) async throws -> Bool {', 1)[1]
        self.assertIn('return try await NativeMutationGate.withLease {', wrapper)
        self.assertIn('return try await self.executeWithNativeLease(parentProgress: parentProgress)', wrapper)
        self.assertNotIn('Task {', wrapper)
        self.assertNotIn('Task.detached', wrapper)
        self.assertEqual(body.count('try await self.coordinator.coordinateMaintenanceMutation('), 2)
        for target in ('clearTempDirItems(at:', 'removeBackupDirItems(at:'):
            self.assertIn('try self.' + target + ' authorized', body)
        for name in ('fileURL', 'backupDirectory'):
            self.assertIn('for (index, ' + name + ') in fileURLs.enumerated() {\n            try check()', body)
        self.assertIn('try maintenanceCancellation.check()\n        self.setProgress(60)', body)
        self.assertNotIn('Task.checkCancellation()', body)
        self.assertIn('} onCancel: {\n            self.maintenanceCancellation.cancel()', wrapper)
        self.assertIn('override func cancel() {\n        maintenanceCancellation.cancel()\n        super.cancel()', text)
        self.assertIn('self.coordinatorQueue.maxConcurrentOperationCount = 1', text)
        coordinated = body.split('func coordinateMaintenanceMutation(', 1)[1]
        self.assertLess(coordinated.index('try body(access.intent.url)'),
                        coordinated.index('queue.addOperation { continuation.resume(with: result) }'))
        self.assertIn('try cancellation.check()\n                    try body(', coordinated)
        self.assertNotIn('cancel()', coordinated)
        self.assertNotIn('device-mutation.lock', body)

    @unittest.skipUnless(HAS_PREIMAGES and SWIFTC, 'Swift compiler or pinned native sources unavailable')
    def test_patched_native_files_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, text in patched().items():
                path = Path(tmp) / Path(name).name
                path.write_text(text)
                paths.append(str(path))
            result = subprocess.run([SWIFTC, '-frontend', '-parse', *paths],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_harness_bridges_blocking_signal_off_the_swift_executor(self):
        self.assertNotIn('await Task.detached', LEASE_HARNESS)
        self.assertIn('DispatchQueue.global().async { [self] in', LEASE_HARNESS)
        self.assertIn('scheduled.wait(timeout: .now() + 5)', LEASE_HARNESS)
        self.assertIn('continuation.resume(throwing: ProbeFailure.schedulingTimedOut)', LEASE_HARNESS)
        self.assertEqual(LEASE_HARNESS.count('coordinator.waitUntilScheduled()'), 2)

    @unittest.skipUnless(HAS_PREIMAGES and SWIFTC, 'Swift compiler or pinned native sources unavailable')
    def test_real_lease_lifetime_busy_interruption_failure_and_success(self):
        # Execute the generated override with the exact production native gate,
        # ProcessLease and MutationScope, plus the exact coordinator bridge.
        # A coordinator test double delays delivery to an OperationQueue; body
        # work deletes a real local file inside that accessor. This tests our
        # continuation/cancellation contract, not Apple's coordination service
        # or UIKit/Core Data integration.
        text = patched()[m.CLEAR]
        wrapper = '    override func execute(parentProgress: Progress?) async throws -> Bool {' + text.split(
            '    override func execute(parentProgress: Progress?) async throws -> Bool {', 1)[1].split(
            '    private func executeWithNativeLease(', 1)[0]
        persistence = (ROOT.parent / 'Sources/TetherlessCore/Persistence.swift').read_text()
        lease = 'public final class ProcessLease:' + persistence.split('public final class ProcessLease:', 1)[1].split(
            '/// Non-secret state only.', 1)[0]
        storage = (ROOT / 'Native/NativeRenewalStorage.swift').read_text()
        gate = 'enum NativeMutationGate {' + storage.split('enum NativeMutationGate {', 1)[1]
        coordination = m.COORDINATED_MUTATION.replace('NSFileCoordinator', 'TestFileCoordinator').replace(
            'NSFileAccessIntent', 'TestFileAccessIntent')
        source = LEASE_HARNESS.replace('WRAPPER_HERE', wrapper).replace('LEASE_HERE', lease).replace(
            'GATE_HERE', gate).replace('COORDINATION_HERE', coordination)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = root / 'main.swift'
            main.write_text(source)
            executable = root / 'lease-check'
            build = subprocess.run([SWIFTC, '-swift-version', '6', '-parse-as-library',
                str(ROOT.parent / 'Sources/TetherlessCore/MutationScope.swift'), str(main), '-o', str(executable)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(executable), str(root)], capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('maintenance lease checks passed', run.stdout)


LEASE_HARNESS = r'''
import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif
public enum RenewalFailure: Error { case lockUnavailable, busy }
enum ProbeFailure: Error { case deliberate, schedulingTimedOut }
LEASE_HERE
enum NativeRenewalStorage {
    static func root() throws -> URL { URL(fileURLWithPath: CommandLine.arguments[1]) }
}
GATE_HERE
final class TestFileAccessIntent: @unchecked Sendable {
    let url: URL
    init(_ url: URL) { self.url = url }
}
final class TestFileCoordinator: @unchecked Sendable {
    let scheduled = DispatchSemaphore(value: 0), resume = DispatchSemaphore(value: 0)
    // Never block Swift's cooperative executor. The synchronous semaphore
    // belongs to this test double; bridge its signal on a GCD worker instead.
    func waitUntilScheduled() async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            DispatchQueue.global().async { [self] in
                if scheduled.wait(timeout: .now() + 5) == .success {
                    continuation.resume()
                } else {
                    continuation.resume(throwing: ProbeFailure.schedulingTimedOut)
                }
            }
        }
    }
    private let lock = NSLock()
    private var active = false
    let fail: Bool
    init(fail: Bool = false) { self.fail = fail }
    func assertAccessorActive() {
        lock.lock(); defer { lock.unlock() }
        precondition(active, "filesystem mutation escaped coordinated accessor")
    }
    func assertAccessorInactive() {
        lock.lock(); defer { lock.unlock() }
        precondition(!active, "caller resumed before the accessor returned")
    }
    func coordinate(with intents: [TestFileAccessIntent], queue: OperationQueue,
                    byAccessor accessor: @escaping @Sendable (Error?) -> Void) {
        queue.addOperation { [self] in
            scheduled.signal()
            resume.wait()
            lock.lock(); active = true; lock.unlock()
            accessor(fail ? ProbeFailure.deliberate : nil)
            lock.lock(); active = false; lock.unlock()
        }
    }
}
COORDINATION_HERE
class Base: @unchecked Sendable {
    func execute(parentProgress: Progress?) async throws -> Bool { false }
    func cancel() {}
}
final class Probe: Base, @unchecked Sendable {
    let coordinator: TestFileCoordinator
    private let queue = OperationQueue()
    private let maintenanceCancellation = TetherlessMaintenanceCancellation()
    let victim: URL
    let fail: Bool
    init(victim: URL, fail: Bool = false, coordinatorFail: Bool = false) {
        self.victim = victim; self.fail = fail
        coordinator = TestFileCoordinator(fail: coordinatorFail)
        queue.maxConcurrentOperationCount = 1
    }
    override func cancel() {
        maintenanceCancellation.cancel()
        super.cancel()
    }
WRAPPER_HERE
    private func executeWithNativeLease(parentProgress: Progress?) async throws -> Bool {
        try await coordinator.coordinateMaintenanceMutation(with: TestFileAccessIntent(victim),
            queue: queue, cancellation: maintenanceCancellation) { [self] url in
                coordinator.assertAccessorActive()
                try maintenanceCancellation.check()
                if fail { throw ProbeFailure.deliberate }
                try FileManager.default.removeItem(at: url)
            }
        return true
    }
}
@main struct Main {
    static func busy(_ path: URL) {
        do { let lease = try ProcessLease.acquire(at: path); lease.release(); fatalError("lease released early") }
        catch RenewalFailure.busy {} catch { fatalError("unexpected lock error") }
    }
    static func main() async throws {
        let root = try NativeRenewalStorage.root()
        let path = root.appendingPathComponent("device-mutation.lock")
        let victim = root.appendingPathComponent("active-input.ipa")
        try Data("preserve me".utf8).write(to: victim)
        let owner = try ProcessLease.acquire(at: path)
        do { _ = try await Probe(victim: victim).execute(parentProgress: nil); fatalError("busy admitted") }
        catch RenewalFailure.busy {}
        precondition(FileManager.default.fileExists(atPath: victim.path))
        owner.release()
        let cancelled = Probe(victim: victim)
        let task = Task { try await cancelled.execute(parentProgress: nil) }
        try await cancelled.coordinator.waitUntilScheduled()
        busy(path)
        task.cancel()
        busy(path)
        cancelled.coordinator.resume.signal()
        do { _ = try await task.value; fatalError("cancel succeeded") } catch is CancellationError {}
        cancelled.coordinator.assertAccessorInactive()
        precondition(FileManager.default.fileExists(atPath: victim.path))
        try ProcessLease.acquire(at: path).release()
        let operationCancelled = Probe(victim: victim)
        let operationTask = Task { try await operationCancelled.execute(parentProgress: nil) }
        try await operationCancelled.coordinator.waitUntilScheduled()
        operationCancelled.cancel()
        busy(path)
        operationCancelled.coordinator.resume.signal()
        do { _ = try await operationTask.value; fatalError("operation cancel succeeded") } catch is CancellationError {}
        operationCancelled.coordinator.assertAccessorInactive()
        precondition(FileManager.default.fileExists(atPath: victim.path))
        try ProcessLease.acquire(at: path).release()
        let failing = Probe(victim: victim, fail: true)
        failing.coordinator.resume.signal()
        do { _ = try await failing.execute(parentProgress: nil); fatalError("failure succeeded") }
        catch ProbeFailure.deliberate {}
        failing.coordinator.assertAccessorInactive()
        try ProcessLease.acquire(at: path).release()
        precondition(FileManager.default.fileExists(atPath: victim.path))
        let coordinationFailed = Probe(victim: victim, coordinatorFail: true)
        coordinationFailed.coordinator.resume.signal()
        do { _ = try await coordinationFailed.execute(parentProgress: nil); fatalError("coordination failure succeeded") }
        catch ProbeFailure.deliberate {}
        coordinationFailed.coordinator.assertAccessorInactive()
        try ProcessLease.acquire(at: path).release()
        precondition(FileManager.default.fileExists(atPath: victim.path))
        let success = Probe(victim: victim)
        success.coordinator.resume.signal()
        let completed = try await success.execute(parentProgress: nil)
        success.coordinator.assertAccessorInactive()
        precondition(completed && !FileManager.default.fileExists(atPath: victim.path))
        try ProcessLease.acquire(at: path).release()
        precondition(FileManager.default.fileExists(atPath: path.path))
        print("maintenance lease checks passed")
    }
}
'''


if __name__ == '__main__':
    unittest.main()
