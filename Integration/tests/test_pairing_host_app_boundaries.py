"""Source checks plus actual Swift tests when the official compiler is present.
These do not claim native ABI, Bonjour, container validation or device evidence.
"""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT if (ROOT / 'Package.swift').is_file() else ROOT.parent / 'tetherless-closure-next'


class PairingHostSourceTests(unittest.TestCase):
    def test_existing_import_storage_and_gates_are_not_overlaid(self):
        for relative in ['Integration/Overrides/PairingFileManager.swift', 'Integration/Overrides/OnboardingView.swift',
                         'Integration/pairing_safety.py', 'Sources/TetherlessCore/PrivateFileStore.swift']:
            if BASE != ROOT:
                self.assertFalse((ROOT / relative).exists())
        source = (BASE / 'Integration/Overrides/PairingFileManager.swift').read_text()
        start = '    /// Generated remote records reach this entry only after joined staged\n'
        end = '    /// Internal capability: a wireless session owns the same process lease until\n'
        self.assertEqual(source.count(start), 1)
        before, rest = source.split(start, 1)
        _, after = rest.split(end, 1)
        # The additive typed entry must leave every existing manager byte intact.
        self.assertEqual(hashlib.sha256((before + end + after).encode()).hexdigest(),
                         '6ef6d342f3fd2f291b3e935a190cd4dd00b40c74bdf5cceb4a779d6c9f9cf84a')

    def test_native_bridge_reserves_entry_and_copies_pin_before_dispatch(self):
        source = (ROOT / 'Integration/Native/BoundedPairingHostBridge.swift').read_text()
        self.assertIn('#if TETHERLESS_BOUNDED_PAIRING_HOST && canImport(IDevice)', source)
        accept = source.split('func accept(')[1].split('private func reserveStart')[0]
        self.assertLess(accept.index('lifetime.admit()'), accept.index('worker.async'))
        self.assertLess(accept.index('tetherless_pairing_host_accept_fd'), accept.index('connection.returned()', accept.index('tetherless_pairing_host_accept_fd')))
        self.assertLess(accept.index('claim.returned()'), accept.index('retire { continuation.resume'))
        pin = source.split('private func receivedPIN')[1].split('private func retire')[0]
        self.assertLess(pin.index('Array(UnsafeBufferPointer'), pin.index('Task { @MainActor'))
        self.assertIn('guard mayDeliverPIN()', pin)
        for banned in ['Task.detached', 'print(', 'debugLog(', 'Thread.sleep', 'asyncAfter']:
            self.assertNotIn(banned, source)
        self.assertIn('targetEnvironment(simulator)', source)
        self.assertIn('#available(iOS 27.0, *)', source)
        self.assertIn('nativeBackend else', source)

    def test_bonjour_and_listener_join_before_continuation(self):
        source = (ROOT / 'Integration/Native/PairingBonjourListener.swift').read_text()
        self.assertIn('source.setCancelHandler { _ = Darwin.close(fd); stopped() }', source)
        self.assertIn('stopRequested, listenerStopped, publisherStopped', source)
        self.assertIn('func netServiceDidStop', source)
        self.assertIn('publisher.publish(options: .noAutoRename)', source)
        self.assertIn('guard !stopRequested else { throw PairingListenerFailure.cancelled }', source)
        self.assertIn('if case .success(let socket) = outcome { socket.discardIfUnclaimed() }', source)
        self.assertIn('#if TETHERLESS_BOUNDED_PAIRING_HOST && canImport(Darwin)', source)
        self.assertLess(source.index('publisher.remove(from: .main, forMode: .default)'),
                        source.index('publisher.schedule(in: .main, forMode: .common)'))
        self.assertIn('forwardedEvents.admit()', source)
        self.assertIn('forwardedEvents.retire', source)
        failure = source.split('didNotPublish errorDict')[1]
        self.assertNotIn('publisherStopped = true', failure)
        self.assertNotIn('continuation.resume(throwing: PairingListenerFailure.timedOut)', source)

    def test_promotion_never_commits_before_validation_and_reports_ambiguous_writes(self):
        source = (ROOT / 'Sources/TetherlessCore/PairingPromotion.swift').read_text()
        self.assertLess(source.index('try await validate(record.xml)'), source.index('try commit(record)'))
        self.assertLess(source.index('phase = .committing'), source.index('try commit(record)'))
        self.assertIn('guard try readTarget() == previous', source)
        self.assertIn('guard try readTarget() == record.xml', source)
        self.assertIn('catch { return .recoveryRequired }', source)
        self.assertNotIn('Task.detached', source)


@unittest.skipUnless(shutil.which('swift'), 'Swift compiler unavailable: app boundary Swift tests not executed')
class PairingHostSwiftTests(unittest.TestCase):
    def run_configuration(self, configuration):
        with tempfile.TemporaryDirectory(prefix='pairing-host-app-tests-') as temporary:
            root = Path(temporary).resolve()
            shutil.copyfile(BASE / 'Package.swift', root / 'Package.swift')
            sources = root / 'Sources/TetherlessCore'; sources.mkdir(parents=True)
            tests = root / 'Tests/TetherlessCoreTests'; tests.mkdir(parents=True)
            for name in ['PairingRecord.swift', 'PrivateFileStore.swift']:
                shutil.copyfile(BASE / 'Sources/TetherlessCore' / name, sources / name)
            for name in ['NativeCallLifetime.swift', 'PairingPromotion.swift']:
                source = ROOT / 'Sources/TetherlessCore' / name
                shutil.copyfile(source, sources / name)
            shutil.copyfile(ROOT / 'Integration/Native/PairingBonjourListener.swift', sources / 'PairingBonjourListener.swift')
            for name in ['NativeCallLifetimeTests.swift', 'PairingPromotionTests.swift']:
                source = ROOT / 'Tests/TetherlessCoreTests' / name
                shutil.copyfile(source, tests / name)
            shutil.copyfile(ROOT / 'Integration/fixtures/PairingBonjourListenerTests.swift', tests / 'PairingBonjourListenerTests.swift')
            spec = importlib.util.spec_from_file_location('pairing_app_process_runner', BASE / 'Integration/inspect_pairing_api.py')
            runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(runner)
            # Reuse the reviewed 60-second/16-MiB process-group runner. It reaps
            # compiler/test children before this owned temporary tree is removed.
            result = runner.run_tool([shutil.which('swift'), 'test', '--package-path', str(root), '-c', configuration, '-Xswiftc', '-DTETHERLESS_BOUNDED_PAIRING_HOST'])
            self.assertEqual(result['status'], 'ok', result['status'])
            self.assertEqual(result['returncode'], 0, (result['stdout'] + result['stderr'])[-20000:])

    def test_debug(self): self.run_configuration('debug')
    def test_release(self): self.run_configuration('release')


if __name__ == '__main__': unittest.main()
