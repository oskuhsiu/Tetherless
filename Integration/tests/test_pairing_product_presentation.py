"""Portable source/registration contracts, not Swift execution or device proof.

The exact Swift budget policy has XCTest coverage in PairingValidationBudgetTests.
UIKit coordinator/presentation compilation and runtime evidence remain separate.
"""
import ast
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / 'Integration/pairing_safety.py'
REVIEW = os.environ.get('TETHERLESS_PAIRING_PRESENTATION_REVIEW_ROOT')
FLAGS = 'TETHERLESS_BOUNDED_PAIRING_HOST && TETHERLESS_STAGED_PAIRING_VALIDATION'
SAVED = ("Pairing record saved after checking this app's protected container. "
         'Saving does not establish that the running connection is using this record. '
         'Connection and renewal remain unverified.')
FROZEN_FUNCTIONS = {
    'once': 'bce85397d3d09d78e1de94ff11fa79182b3eb913bcdfad4762e4dd84d6bf3ba7',
    'body': '5fc407b8f2ef73142d1ba60f039f4de695021897ac9777a4caef1c01e2abeef5',
    'patch_service': 'd3fd2ec6099293f573110a064c4bdf016e7a194f0eca298bf214c950d4b8d60b',
    'patch_gateway': '3f530181c12c2d9d8a7fa9153418fca086e042fb310e9abb5ae1111a48222296',
    'patch_wrapper': '6462fb26cbc0766654c66bb6c4b5d200513d543ac3cc8dc4cc93e8cb5f0a5c17',
    'patch_model': 'cf8f1e1e775860ac0d425d52a2a317b56d9723783a327272514fb02b3b95e7b0',
    'apply': '633e10838bd4d831bedfb87b3f5b593dc7a89d6f7d461cbda44cd2ed51987794',
}


def source(relative):
    return (ROOT / relative).read_text()


def load_gate():
    spec = importlib.util.spec_from_file_location('pairing_presentation_gate', GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


class PairingProductPresentationTests(unittest.TestCase):
    def test_only_intended_iphone_platform_can_be_eligible(self):
        model = source('Integration/Native/PairingSetupModel.swift')
        platform = model.split('private static var platformSupported: Bool {', 1)[1].split('static var supported:', 1)[0]
        self.assertIn('#if targetEnvironment(simulator) || targetEnvironment(macCatalyst)', platform)
        self.assertIn('guard #available(iOS 27.0, *) else { return false }', platform)
        self.assertIn('guard !ProcessInfo.processInfo.isiOSAppOnMac else { return false }', platform)
        self.assertLess(platform.index('guard #available(iOS 27.0, *)'), platform.index('isiOSAppOnMac'))
        self.assertLess(platform.index('isiOSAppOnMac'), platform.index('UIDevice.current.userInterfaceIdiom'))
        self.assertIn('UIDevice.current.userInterfaceIdiom == .phone', platform)
        self.assertIn('platformSupported && Minimuxer.shared.gateway is IdeviceGateway', model)

    def test_backend_is_rechecked_under_existing_lease_before_native_prepare(self):
        model = source('Integration/Native/PairingSetupModel.swift')
        self.assertIn('NativeMutationGate.withLease { await runLeased() }', model)
        leased = model.split('private func runLeased()', 1)[1]
        before_host = leased.split('let host = try await makeHost(nativeBackend: nativeBackend)', 1)[0]
        self.assertLess(before_host.index('try checkCancellation()'), before_host.index('let nativeBackend ='))
        self.assertIn('let nativeBackend = Minimuxer.shared.gateway is IdeviceGateway', before_host)
        self.assertIn('guard Self.platformSupported, nativeBackend else { return .unavailable }', before_host)
        self.assertIn('remaining(until: deadline, maximum: 120_000)', before_host)
        self.assertNotIn('await ', before_host)
        self.assertIn('generation: generation, nativeBackend: nativeBackend, onPIN: callback', model)
        self.assertNotIn('nativeBackend: true', model)

    def test_session_and_validation_total_deadlines_are_not_extended(self):
        model = source('Integration/Native/PairingSetupModel.swift')
        self.assertEqual(model.count('deadline = ProcessInfo.processInfo.systemUptime + 120'), 1)
        validation = model.split('private func validate(', 1)[1]
        end = 'let end = min(deadline, ProcessInfo.processInfo.systemUptime + 10)'
        self.assertEqual(validation.count(end), 1)
        self.assertLess(validation.index(end), validation.index('resolver.resolve'))
        self.assertLess(validation.index(end), validation.index('for (index, endpoint)'))
        self.assertEqual(validation.count('remaining(until: end, maximum: 10_000)'), 2)
        loop = validation.split('for (index, endpoint)', 1)[1]
        self.assertNotIn('systemUptime +', loop)
        self.assertIn('endpointsRemaining: endpoints.count - index', loop)
        policy = source('Sources/TetherlessCore/PairingValidationBudget.swift')
        self.assertIn('maximumMilliseconds: UInt32 = 10_000', policy)
        self.assertIn('maximumEndpoints = 4', policy)
        self.assertIn('let available = min(remainingMilliseconds, maximumMilliseconds)', policy)
        self.assertIn('let share = available / UInt32(endpointsRemaining)', policy)
        self.assertIn('return share > 0 ? share : nil', policy)

    def test_each_attempt_uses_actual_remainder_and_a_fresh_joined_token(self):
        model = source('Integration/Native/PairingSetupModel.swift')
        remaining = model.split('private func remaining(', 1)[1].split('private func makeHost', 1)[0]
        self.assertLess(remaining.index('try checkCancellation()'), remaining.index('systemUptime'))
        loop = model.split('for (index, endpoint) in endpoints.enumerated()', 1)[1]
        self.assertLess(loop.index('remaining(until: end'), loop.index('PairingValidationBudget.timeoutMilliseconds'))
        self.assertLess(loop.index('PairingValidationBudget.timeoutMilliseconds'), loop.index('NativeStagedPairingValidator()'))
        self.assertIn('record: record, endpoint: endpoint, bundleIdentifier: bundle', loop)
        failure = loop.split('} catch {', 1)[1].split('continue', 1)[0]
        self.assertLess(failure.index('await validator.close()'), failure.index('registration?.remove()'))
        self.assertLess(failure.index('registration?.remove()'), failure.index('try checkCancellation()'))
        success = loop.split('continue', 1)[1].split('break', 1)[0]
        self.assertLess(success.index('await validator.close()'), success.index('registration?.remove()'))

    def test_background_expiry_pin_and_commit_winners_are_preserved(self):
        model = source('Integration/Native/PairingSetupModel.swift')
        expiry = model.split('beginBackgroundTask(withName:', 1)[1].split('guard backgroundTask', 1)[0]
        self.assertLess(expiry.index('cancellation.cancel()'), expiry.index('Task { @MainActor'))
        callback = model.split('let callback:', 1)[1].split('// This bounded', 1)[0]
        self.assertIn('!self.cancellation.isCancelled', callback)
        self.assertIn('self.promotion.acceptsPIN(for: generation)', callback)
        commit = model.split('}, commit: { [self] record in', 1)[1].split('})', 1)[0]
        self.assertIn('guard cancellation.beginPromotion() else { throw CancellationError() }', commit)
        self.assertIn('saveValidatedRemotePairingRecord(record)', commit)
        self.assertNotIn('await ', '\n'.join(line for line in commit.splitlines() if not line.lstrip().startswith('//')))
        view = source('Integration/Native/PairingSetupView.swift')
        self.assertIn('if let pin = model.pin, !concealPIN, !model.cancellation.isCancelled', view)
        self.assertIn('.interactiveDismissDisabled(model.isRunning)', view)
        self.assertIn('.onDisappear { model.cancel() }', view)
        foreground = view.split('UIApplication.didBecomeActiveNotification', 1)[1]
        self.assertLess(foreground.index('model.reconcileCancellation()'), foreground.index('concealPIN = false'))

    def test_all_success_wording_distinguishes_saved_record_from_running_backend(self):
        for relative in ['Integration/Native/PairingSetupView.swift',
                         'Integration/Overrides/OnboardingView.swift',
                         'Integration/Overrides/WirelessPairView.swift']:
            with self.subTest(relative=relative):
                text = source(relative)
                self.assertIn(SAVED, text)
                self.assertNotIn('belongs to this iPhone', text)
                self.assertNotIn('Run the normal connection check next.', text)

    def test_setup_start_stays_explicit_and_requires_current_eligibility(self):
        view = source('Integration/Native/PairingSetupView.swift')
        ready = view.split('if model.phase == .ready {', 1)[1].split('if let outcome', 1)[0]
        self.assertIn('if PairingSetupModel.supported {', ready)
        self.assertIn('SwiftUI.Button("Start pairing") { model.start() }', ready)
        self.assertEqual(view.count('model.start()'), 1)
        self.assertIn('Checking access to this app\'s protected container.', view)

    def test_advanced_replacement_shares_closed_capability_and_safe_setup(self):
        text = source('Integration/Overrides/WirelessPairView.swift')
        self.assertEqual(text.count('#if ' + FLAGS), 2)
        self.assertEqual(text.count('canImport(IDevice) && canImport(IdeviceGateway)'), 2)
        self.assertIn('if #available(iOS 17.0, *)', text)
        self.assertIn('if PairingSetupModel.supported {', text)
        self.assertIn('PairingSetupView { outcome in', text)
        self.assertNotIn('model.start()', text)
        for forbidden in ['WirelessPairViewModel', 'WirelessPairWrapper', 'openClientDialog',
                          'togglePairing', 'ShareLink', 'UIActivityViewController',
                          'targetIp', 'targetPort', 'pinCode']:
            self.assertNotIn(forbidden, text)
        self.assertIn('You can still import an authorized pairing file', text)

    def test_advanced_and_onboarding_keep_separate_logical_and_physical_generations(self):
        text = source('Integration/Overrides/WirelessPairView.swift')
        self.assertIn('@State private var request: PairingSetupRequest?', text)
        self.assertIn('@State private var presentation: PairingSetupRequest?', text)
        self.assertIn('guard request == nil, presentation == nil else { return }', text)
        self.assertIn('let dismissalRequest = presentation', text)
        self.assertIn('guard let dismissalRequest, presentation == dismissalRequest else { return }', text)
        self.assertIn('guard request == current, presentation == current else { return }', text)
        self.assertEqual(text.count('presentation = nil'), 1)
        onboarding = source('Integration/Overrides/OnboardingView.swift')
        self.assertIn('hostPairingPresentation == hostDismissalRequest', onboarding)
        self.assertIn('pairingPresentation == dismissalRequest', onboarding)
        self.assertIn('PairingFileManager.shared.importPairingFile(from: url)', onboarding)

    def test_no_gateway_restart_cache_port_or_new_store_is_introduced(self):
        for relative in ['Integration/Native/PairingSetupModel.swift',
                         'Integration/Native/PairingSetupView.swift',
                         'Integration/Overrides/WirelessPairView.swift']:
            text = source(relative)
            for forbidden in ['reinitialize', '.restart(', 'lastDiscoveredRemotePairingPort',
                              'UserDefaults', 'Task.detached', 'print(', 'debugLog(']:
                self.assertNotIn(forbidden, text)

    def test_existing_gate_privacy_and_legacy_denial_functions_are_byte_identical(self):
        text = GATE.read_text()
        functions = {node.name: ast.get_source_segment(text, node) for node in ast.parse(text).body
                     if isinstance(node, ast.FunctionDef)}
        self.assertEqual(set(functions), set(FROZEN_FUNCTIONS) | {'patch_view'})
        for name, expected in FROZEN_FUNCTIONS.items():
            self.assertEqual(hashlib.sha256(functions[name].encode()).hexdigest(), expected, name)
        gate = load_gate()
        self.assertEqual(gate.BLOBS[gate.VIEW], 'ceed7ac68c1f802e45127d209fa22a2041069039')
        self.assertEqual(set(gate.BLOBS), set(gate.PATCHES))
        self.assertEqual(gate.PATCHES[gate.VIEW](''), source('Integration/Overrides/WirelessPairView.swift'))

    def test_advanced_preimage_drift_does_not_write_any_output(self):
        gate = load_gate()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            # Synthetic prior inputs isolate the unchanged all-input validation
            # transaction; they are not claimed to be pinned upstream sources.
            inputs = {name: b'synthetic preimage' for name in gate.BLOBS}
            hashes = {name: blob(raw) for name, raw in inputs.items()}
            transforms = {name: lambda value: 'synthetic output' for name in inputs}
            transforms[gate.VIEW] = gate.patch_view
            for name, raw in inputs.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            (root / gate.VIEW).write_bytes(b'drift')
            before = {name: (root / name).read_bytes() for name in inputs}
            with patch.object(gate, 'BLOBS', hashes), patch.object(gate, 'PATCHES', transforms):
                with self.assertRaisesRegex(ValueError, 'Unreviewed pairing safety source:'):
                    gate.apply(root)
            self.assertEqual(before, {name: (root / name).read_bytes() for name in inputs})

    def test_registration_replaces_view_and_reapplication_fails_before_writing(self):
        gate = load_gate()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = {name: b'synthetic preimage' for name in gate.BLOBS}
            hashes = {name: blob(raw) for name, raw in inputs.items()}
            transforms = {name: lambda value: 'synthetic output' for name in inputs}
            transforms[gate.VIEW] = gate.patch_view
            for name, raw in inputs.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            with patch.object(gate, 'BLOBS', hashes), patch.object(gate, 'PATCHES', transforms):
                gate.apply(root)
                self.assertEqual((root / gate.VIEW).read_text(), source('Integration/Overrides/WirelessPairView.swift'))
                before = {name: (root / name).read_bytes() for name in inputs}
                with self.assertRaises(ValueError):
                    gate.apply(root)
                self.assertEqual(before, {name: (root / name).read_bytes() for name in inputs})

    @unittest.skipUnless(REVIEW, 'Exact pre-registration sources not mounted; source transform not executed')
    def test_exact_reviewed_sources_admit_the_advanced_replacement(self):
        gate = load_gate()
        review = Path(REVIEW)
        inputs = {name: (review / name).read_bytes() for name in gate.BLOBS}
        for name, raw in inputs.items():
            self.assertEqual(blob(raw), gate.BLOBS[name], name)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, raw in inputs.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            gate.apply(root)
            self.assertEqual((root / gate.VIEW).read_text(), source('Integration/Overrides/WirelessPairView.swift'))
            for name in set(inputs) - {gate.VIEW}:
                self.assertEqual((root / name).read_text(), gate.PATCHES[name](inputs[name].decode()))
            before = {name: (root / name).read_bytes() for name in inputs}
            with self.assertRaises(ValueError):
                gate.apply(root)
            self.assertEqual(before, {name: (root / name).read_bytes() for name in inputs})


if __name__ == '__main__':
    unittest.main()
