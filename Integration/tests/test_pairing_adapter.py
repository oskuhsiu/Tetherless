"""Real request/relay permutations plus UIKit source wiring; no fake native success."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parents[1]


class PairingAdapterTests(unittest.TestCase):
    def setUp(self):
        self.core = (ROOT.parent/'Sources/TetherlessCore/PairingImportFlow.swift').read_text()
        self.picker = (ROOT/'Native/PairingDocumentPicker.swift').read_text()
        self.view = (ROOT/'Overrides/OnboardingView.swift').read_text()
        self.ui = (ROOT/'UITests/TetherlessUITests.swift').read_text()

    def test_dismissal_is_observed_without_inventing_a_delegate_outcome(self):
        dismissed = self.core.split('public mutating func dismissed(')[1].split('public mutating func consume(')[0]
        self.assertIn('dismissed: true', dismissed)
        self.assertIn('return consume(request)', dismissed)
        self.assertNotIn('.cancelled', dismissed)
        self.assertNotIn('phase = .idle', dismissed)
        consume = self.core.split('public mutating func consume(')[1].split('public mutating func abandon(')[0]
        self.assertIn('active == request, dismissed, let outcome = pending', consume)
        self.assertIn('phase = .importing(active)', consume)
        self.assertIn('phase = .idle', consume)

    def test_onboarding_checks_the_rendezvous_from_both_event_paths(self):
        self.assertIn('finishPairingSelection(dismissalRequest)', self.view)
        self.assertIn('finishPairingSelection(resolved, afterDismissal: false)', self.view)
        consume = self.view.split('private func finishPairingSelection(')[1].split('@ViewBuilder')[0]
        self.assertIn('ready = pairingImport.dismissed(request)', consume)
        self.assertIn('ready = pairingImport.consume(request)', consume)
        self.assertLess(consume.index('guard let outcome = ready'), consume.index('importPairingFile(from: url)'))
        self.assertIn('defer { pairingImport.finished(request) }', consume)
        self.assertIn('pairingImportFailure = PairingImportFailure(error)', consume)
        abandonment = self.view.split('} onAbandon: { abandoned in')[1].split('\n            }')[0]
        self.assertIn('guard pairingImport.abandon(abandoned) else { return }', abandonment)
        self.assertNotIn('importPairingFile', abandonment)
        self.assertNotIn('pairingImport.dismissed', abandonment)

    def test_physical_cover_identity_outlives_abandonment_and_blocks_a_new_presentation(self):
        self.assertIn('@State private var pairingPresentation: PairingImportRequest?', self.view)
        self.assertIn('let dismissalRequest = pairingPresentation', self.view)
        self.assertNotIn('let dismissalRequest = pairingImport.request', self.view)
        self.assertIn('pairingImport.isBusy || pairingPresentation != nil', self.view)
        choose = self.view.split('private func choosePairingFile()')[1].split('private func finishPairingSelection(')[0]
        self.assertIn('guard !working, pairingPresentation == nil, let request = pairingImport.begin()', choose)
        self.assertLess(choose.index('pairingPresentation = request'), choose.index('pairingRequest = request'))
        dismissed = self.view.split('.fullScreenCover(item: $pairingRequest, onDismiss: {')[1].split('}) { request in')[0]
        self.assertIn('guard let dismissalRequest, pairingPresentation == dismissalRequest', dismissed)
        self.assertLess(dismissed.index('pairingPresentation = nil'), dismissed.index('finishPairingSelection(dismissalRequest)'))
        self.assertEqual(self.view.count('pairingPresentation = nil'), 1)
        abandon = self.view.split('} onAbandon: { abandoned in')[1].split('\n            }')[0]
        self.assertNotIn('pairingPresentation = nil', abandon)
        self.assertIn('.disabled(working || pairingBusy)', self.view)

    def test_stable_host_presents_actual_picker_once_and_keeps_coordinator_alive(self):
        self.assertIn('return PickerHostController(picker: picker, coordinator: context.coordinator)', self.picker)
        host = self.picker.split('final class PickerHostController:')[1].split('final class Coordinator:')[0]
        self.assertIn('private let coordinator: Coordinator', host)
        self.assertIn('private let picker: UIDocumentPickerViewController', host)
        self.assertEqual(host.count('present(picker, animated: true)'), 1)
        self.assertLess(host.index('guard !presentedPicker'), host.index('presentedPicker = true'))
        self.assertLess(host.index('presentedPicker = true'), host.index('present(picker, animated: true)'))
        self.assertIn('picker.modalPresentationStyle = .fullScreen', self.picker)
        self.assertIn('forOpeningContentTypes: contentTypes, asCopy: false', self.picker)
        self.assertIn('picker.presentationController?.delegate = coordinator', host)
        update = self.picker.split('func updateUIViewController(')[1].split('static func dismantleUIViewController(')[0]
        self.assertNotIn('present(', update)
        self.assertNotIn('delegate =', update)
        self.assertNotIn('DispatchQueue', self.picker)
        self.assertNotIn('asyncAfter', self.picker)
        self.assertNotIn('sleep(', self.picker + self.view + self.core)

    def test_native_callbacks_are_bound_and_teardown_cannot_import(self):
        self.assertEqual(self.picker.count('guard controller === picker else { return }'), 2)
        interactive = self.picker.split('func presentationControllerDidDismiss(')[1].split('func invalidate()')[0]
        self.assertIn('guard presentationController.presentedViewController === picker else { return }', interactive)
        self.assertIn('finish(.cancelled)', interactive)
        teardown = self.picker.split('func invalidate()')[1].split('private func finish(')[0]
        self.assertIn('picker?.delegate = nil', teardown)
        self.assertIn('picker?.presentationController?.delegate = nil', teardown)
        self.assertIn('relay.invalidate()', teardown)
        self.assertNotIn('finish(', teardown)
        self.assertNotIn('dismissed(', teardown)
        abandon = self.core.split('public mutating func abandon(')[1].split('public mutating func finished(')[0]
        self.assertIn('active == request, outcome == nil', abandon)
        self.assertNotIn('consume(', abandon)
        self.assertNotIn('.selected', abandon)

    def test_recovery_is_explicit_unresolved_only_and_never_an_acceptance_action(self):
        self.assertIn('"Return to setup"', self.picker)
        self.assertIn('close.accessibilityIdentifier = "pairing.returnToSetup"', self.picker)
        self.assertIn('recovery.isHidden = true', self.picker)
        self.assertIn('recovery.isHidden = presentedViewController != nil || !coordinator.hasPendingResult', self.picker)
        recovery = self.picker.split('private func returnToSetup()')[1].split('final class Coordinator:')[0]
        self.assertIn('guard presentedPicker, presentedViewController == nil, coordinator.hasPendingResult', recovery)
        self.assertIn('coordinator.invalidate()', recovery)
        self.assertNotIn('dismissed(', recovery)
        self.assertIn('var hasPendingResult: Bool { relay.isPending }', self.picker)
        self.assertNotIn('Return to setup', self.ui)
        self.assertNotIn('returnToSetup', self.ui)
        self.assertIn('for attempt in 1...2', self.ui)
        self.assertIn('app.buttons["Cancel"].firstMatch', self.ui)
        self.assertIn('rejected.waitForExistence(timeout: 10)', self.ui)
        self.assertIn('XCTAssertEqual(rejected.value as? String, "pairing/invalidContent"', self.ui)
        self.assertEqual(self.ui.count('tapDocumentItem("Tetherless-Invalid-Pairing.plist", in: app, documentCell: true)'), 1)

    def test_actual_production_flow_and_relay_compile_and_run_in_both_modes(self):
        harness = r'''
import Foundation
@main struct Main {
    @MainActor static func main() {
        let file = URL(fileURLWithPath: "/synthetic/selected.plist")
        let outcomes: [PairingImportFlow.Outcome] = [.selected(file), .cancelled, .invalidSelection]
        for outcome in outcomes {
            for dismissalFirst in [false, true] {
                var flow = PairingImportFlow()
                let request = flow.begin()!
                var received: [PairingImportFlow.Outcome] = []
                var abandoned = 0
                let relay = PairingImportResultRelay(request: request, onResolve: { bound, result in
                    precondition(bound == request)
                    precondition(flow.resolve(result, request: bound))
                    if let ready = flow.consume(bound) { received.append(ready) }
                }, onAbandon: { bound in
                    if flow.abandon(bound) { abandoned += 1 }
                })
                if dismissalFirst {
                    precondition(flow.dismissed(request) == nil)
                    precondition(flow.dismissed(request) == nil)
                }
                precondition(relay.isPending)
                precondition(relay.resolve(outcome))
                precondition(!relay.resolve(.cancelled))
                precondition(!relay.invalidate())
                if !dismissalFirst {
                    precondition(received.isEmpty)
                    if let ready = flow.dismissed(request) { received.append(ready) }
                }
                precondition(received == [outcome] && abandoned == 0)
                precondition(flow.consume(request) == nil && flow.dismissed(request) == nil)
                if case .selected = outcome {
                    precondition(!flow.abandon(request))
                    precondition(flow.finished(request))
                }
                precondition(!flow.isBusy)
            }
        }
        // Explicit owner teardown/recovery before result, then a fresh generation.
        for dismissalFirst in [false, true] {
            var flow = PairingImportFlow()
            let request = flow.begin()!
            var callbacks = 0
            var abandoned = 0
            let relay = PairingImportResultRelay(request: request, onResolve: { _, _ in callbacks += 1 },
                onAbandon: { bound in if flow.abandon(bound) { abandoned += 1 } })
            if dismissalFirst { precondition(flow.dismissed(request) == nil) }
            precondition(relay.invalidate())
            precondition(!relay.invalidate() && !relay.isPending && !flow.isBusy)
            let current = flow.begin()!
            precondition(!relay.resolve(.selected(file)))
            precondition(!flow.resolve(.selected(file), request: request))
            precondition(flow.dismissed(request) == nil && !flow.abandon(request))
            precondition(flow.request == current && callbacks == 0 && abandoned == 1)
        }
        // Native selection decision used by the actual coordinator.
        for urls in [[], [file, file], [URL(string: "https://example.invalid/file")!]] {
            precondition(PairingImportFlow.Outcome.pickedDocuments(urls) == .invalidSelection)
        }
        precondition(PairingImportFlow.Outcome.pickedDocuments([file]) == .selected(file))
        // Clear callbacks before reentrant owner cleanup.
        let request = PairingImportRequest()
        var relay: PairingImportResultRelay?
        var callbacks = 0
        var abandoned = 0
        relay = PairingImportResultRelay(request: request, onResolve: { _, _ in
            callbacks += 1
            precondition(relay?.invalidate() == false)
            precondition(relay?.resolve(.invalidSelection) == false)
        }, onAbandon: { _ in abandoned += 1 })
        precondition(relay?.resolve(.cancelled) == true)
        precondition(callbacks == 1 && abandoned == 0)
        print("production-pairing-rendezvous-and-relay-passed")
    }
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root/'Main.swift'; source.write_text(harness)
            for optimization in ['-Onone', '-O']:
                result = subprocess.run(['swiftc', '-swift-version', '6', optimization,
                    str(ROOT.parent/'Sources/TetherlessCore/PairingImportFlow.swift'), str(source),
                    '-o', str(root/'check')], capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                result = subprocess.run([str(root/'check')], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), 'production-pairing-rendezvous-and-relay-passed')


if __name__ == '__main__': unittest.main()
