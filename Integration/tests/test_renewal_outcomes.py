"""Native wiring checks; executed Swift scenarios carry the behavioral evidence."""
from pathlib import Path
import unittest
ROOT = Path(__file__).parents[1]

class RenewalOutcomeIntegrationTests(unittest.TestCase):
    def test_runtime_keeps_per_invocation_results_on_throw(self):
        text = (ROOT / 'Native/NativeRenewalRuntime.swift').read_text()
        run = text.split('func run(trigger:')[1].split('private func saveEvidence')[0]
        self.assertIn('let capture = RenewalRunCapture()', run)
        self.assertIn('reportOnExit: { capture.record($0) }', run)
        self.assertIn('let result = capture.interrupted(by: failure)', run)
        self.assertNotIn('var result = RenewalRunResult()', run)
        self.assertIn('throw failure', run)

    def test_native_commit_consumes_the_verified_batch_snapshot(self):
        text = (ROOT / 'Native/NativeRenewalBackend.swift').read_text()
        complete = text.split('private func complete(')[1].split('private func validate(')[0]
        self.assertIn('ProfileBatchExecutor.applyMissingAndReadback(', complete)
        self.assertIn('let installed = readback.installedProfiles', complete)
        self.assertIn('effectiveExpiry(of: descriptor, in: installed)', complete)
        self.assertIn('installed: installed)', complete)
        self.assertNotIn('transport.readInstalledProfileBytes()', complete)

    def test_existing_extension_path_uses_one_consistent_snapshot(self):
        text = (ROOT / 'Native/NativeRenewalBackend.swift').read_text()
        refresh = text.split('private func refreshImpl(')[1].split('private func reconcileImpl(')[0]
        self.assertEqual(refresh.count('transport.readInstalledProfileBytes()'), 1)
        self.assertIn('installed: initialProfiles)', refresh)
        # No raw response/profile is copied into the public outcome capture.
        capture = (ROOT.parent / 'Sources/TetherlessCore/RenewalRunCapture.swift').read_text().split('public final class RenewalRunCapture')[1]
        self.assertNotIn('Data', capture)
