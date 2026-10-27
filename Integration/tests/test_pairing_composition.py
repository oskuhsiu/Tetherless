"""Source contract checks only; not native execution or current-phone proof."""
from pathlib import Path
import hashlib
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT if (ROOT / 'Package.swift').exists() else ROOT.parent / 'tetherless-closure-next'

class PairingCompositionContractTests(unittest.TestCase):
    def test_preparation_uses_the_pinned_host_role_model_contract(self):
        source = (ROOT / 'Integration/Native/PairingSetupModel.swift').read_text()
        model = re.search(r'BoundedPairingHostBridge\(name: "Tetherless", model: "([^"]+)"', source).group(1)
        # Exact frozen bounded_pairing_host.rs public prepare guard, not a
        # statement that the current phone is a Mac or a native runtime test.
        self.assertTrue(model.startswith('Mac'))
        self.assertLessEqual(len(model.encode()), 64)
        self.assertTrue(all(c.isascii() and (c.isalnum() or c == ',') for c in model))
        self.assertEqual(model, 'Mac17,7')

    def test_existing_protected_import_store_is_unchanged(self):
        source = BASE / 'Integration/Overrides/PairingFileManager.swift'
        text = source.read_text()
        start = '    /// Generated remote records reach this entry only after joined staged\n'
        end = '    /// Internal capability: a wireless session owns the same process lease until\n'
        self.assertEqual(text.count(start), 1)
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        # Only the typed entry is new. The generic import/reset/commit bytes stay pinned.
        self.assertEqual(hashlib.sha256((before + end + after).encode()).hexdigest(),
                         '6ef6d342f3fd2f291b3e935a190cd4dd00b40c74bdf5cceb4a779d6c9f9cf84a')
        new = (ROOT / 'Integration/Overrides/OnboardingView.swift').read_text()
        self.assertIn('hostPairingPresentation == hostDismissalRequest', new)
        self.assertIn('pairingPresentation == dismissalRequest', new)
        self.assertIn('PairingFileManager.shared.importPairingFile(from: url)', new)
        self.assertIn('#if TETHERLESS_BOUNDED_PAIRING_HOST && TETHERLESS_STAGED_PAIRING_VALIDATION', new)

    def test_cancelled_pin_is_never_revealed_on_foreground(self):
        view = (ROOT / 'Integration/Native/PairingSetupView.swift').read_text()
        self.assertIn('if let pin = model.pin, !concealPIN, !model.cancellation.isCancelled', view)
        foreground = view.split('UIApplication.didBecomeActiveNotification', 1)[1]
        self.assertLess(foreground.index('model.reconcileCancellation()'), foreground.index('concealPIN = false'))
        model = (ROOT / 'Integration/Native/PairingSetupModel.swift').read_text()
        expired = model.split('beginBackgroundTask(withName:', 1)[1].split('guard backgroundTask', 1)[0]
        self.assertLess(expired.index('cancellation.cancel()'), expired.index('Task { @MainActor'))

    def test_generation_is_not_identity_and_commit_uses_existing_store(self):
        source = (ROOT / 'Integration/Native/PairingSetupModel.swift').read_text()
        commit = source.split('}, commit: { [self] record in', 1)[1].split('})', 1)[0]
        self.assertLess(commit.index('cancellation.beginPromotion()'), commit.index('saveValidatedRemotePairingRecord'))
        self.assertIn('saveValidatedRemotePairingRecord(record)', commit)
        self.assertNotIn('record.content', commit)
        self.assertIn('PairingPeerAddress.connectedPeer(descriptor: socket.descriptor)', source)
        self.assertIn('Bundle.main.bundleIdentifier', source)
        self.assertIn('try await challenge.closeAfterValidation()', source)
        self.assertIn('NativeMutationGate.withLease', source)
        for forbidden in ['Task.detached', 'UserDefaults.standard.lastDiscoveredRemotePairingPort',
                          'reinitializePairingData', 'print(', 'debugLog(']:
            self.assertNotIn(forbidden, source)

if __name__ == '__main__': unittest.main()
