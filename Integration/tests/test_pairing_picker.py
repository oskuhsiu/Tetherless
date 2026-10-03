from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).parents[1]

class PairingPickerIntegrationTests(unittest.TestCase):
    def test_native_picker_is_owned_and_never_recreated_on_ui_update(self):
        text = (ROOT / 'Native/PairingDocumentPicker.swift').read_text()
        self.assertIn('UIDocumentPickerViewController(forOpeningContentTypes: contentTypes, asCopy: false)', text)
        self.assertIn('picker.delegate = context.coordinator', text)
        self.assertIn('coordinator.invalidate()', text)
        self.assertIn('picker.delegate = nil', text)
        update = text.split('func updateUIViewController(')[1].split('static func dismantleUIViewController')[0]
        self.assertNotIn('present(', update)
        self.assertNotIn('UIDocumentPickerViewController(', update)
        finish = text.split('private func finish(')[1]
        self.assertLess(finish.index('onResolve = nil'), finish.index('callback?('))
        self.assertIn('urls.count == 1', text)
        self.assertIn('url.isFileURL', text)
        self.assertNotIn('print(', text)

    def test_import_occurs_only_after_matching_dismissal(self):
        text = (ROOT / 'Overrides/OnboardingView.swift').read_text()
        self.assertNotIn('.fileImporter(', text)
        self.assertIn('.fullScreenCover(item: $pairingRequest', text)
        self.assertIn('let dismissalRequest = pairingImport.request', text)
        self.assertIn('pairingImport.resolve(outcome, request: resolved)', text)
        selection = text.split('private func finishPairingSelection(')[1].split('@ViewBuilder')[0]
        self.assertLess(selection.index('pairingImport.dismissed(request)'), selection.index('importPairingFile(from: url)'))
        self.assertIn('defer { pairingImport.finished(request) }', selection)
        self.assertNotIn('renewalPermitted =', selection)
        self.assertNotIn('hasCompletedOnboarding =', selection)
        self.assertNotIn('deletePairing', selection)

    def test_ui_requires_two_real_system_cancellations_without_extra_wait(self):
        text = (ROOT / 'UITests/TetherlessUITests.swift').read_text()
        self.assertIn('for attempt in 1...2', text)
        self.assertIn('app.buttons["Cancel"].firstMatch', text)
        self.assertIn('cancelImport.waitForExistence(timeout: 10)', text)
        self.assertIn('cancelImport.isHittable', text)
        self.assertIn('Import cancelled. Existing pairing was retained.', text)
        self.assertIn('app.terminate(); app.launch()', text)
        self.assertNotIn('typeText(', text)
        self.assertNotIn('launchEnvironment', text)

    def test_external_pairing_read_is_scoped_coordinated_and_bounded(self):
        text = (ROOT / 'Overrides/PairingFileManager.swift').read_text()
        read = text.split('func inspectPairingFile(from url: URL)')[1].split('func importPairingFile(')[0]
        self.assertLess(read.index('startAccessingSecurityScopedResource()'), read.index('coordinator.coordinate('))
        self.assertIn('defer { if scoped { url.stopAccessingSecurityScopedResource() } }', read)
        self.assertIn('options: .withoutChanges', read)
        self.assertIn('PrivateFileStore.readExternal(coordinatedURL)', read)
        self.assertLess(read.index('coordinationError == nil'), read.index('captured.get()'))
        self.assertNotIn('removeItem(', read)
        self.assertNotIn('write(', read)
        self.assertNotIn('print(', read)

    def test_real_swift_sources_parse(self):
        # Parsing is a local syntax check only; UIKit typechecking needs Xcode CI.
        result = subprocess.run(['swiftc', '-frontend', '-parse',
             str(ROOT / 'Native/PairingDocumentPicker.swift'),
             str(ROOT / 'Overrides/OnboardingView.swift')], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
