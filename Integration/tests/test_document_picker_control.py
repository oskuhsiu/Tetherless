from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).parents[1]

class DocumentPickerControlTests(unittest.TestCase):
    def setUp(self):
        self.ui = (ROOT/'UITests/TetherlessUITests.swift').read_text()
        self.source = (ROOT/'UITestSupport/DocumentFixtureApp.swift').read_text()
        self.control = self.ui.split('private func inspectIndependentPickerControl(')[1].split('private func tapDocumentItem(')[0]

    def test_runs_only_after_original_frozen_failure_and_cannot_make_it_pass(self):
        before, after = self.ui.split('inspectIndependentPickerControl(after: app, documents: documents)')
        self.assertIn('if !outcomeAppeared || pickerStillVisible {', before)
        self.assertIn('let outcomeAppeared = rejected.waitForExistence(timeout: 10)', before)
        self.assertIn('let pickerStillVisible = app.otherElements["Browse View (Picker)"].exists', before)
        self.assertIn('XCTAssertTrue(outcomeAppeared', after)
        self.assertIn('XCTAssertFalse(pickerStillVisible', after)
        self.assertIn('productAccepted=false', self.control)
        self.assertNotIn('continueAfterFailure = true', self.ui)
        self.assertEqual(self.ui.count('inspectIndependentPickerControl(after: app'), 1)

    def test_control_cannot_relaunch_or_reselect_in_product(self):
        self.assertEqual(self.control.count('product.'), 1)
        self.assertIn('product.terminate()', self.control)
        self.assertIn('defer { documents.terminate() }', self.control)
        self.assertEqual(self.control.count('documents.launch()'), 1)
        self.assertNotIn('product.launch()', self.control)
        self.assertNotIn('coordinate(', self.control)
        self.assertNotIn('doubleTap(', self.control)
        self.assertNotIn('while ', self.control)
        self.assertNotIn('sleep(', self.control)
        self.assertIn('timeout: 10)', self.control)
        self.assertIn('case', self.source)  # fixed outcomes, not arbitrary diagnostics

    def test_probe_uses_real_independent_uikit_and_open_in_place(self):
        self.assertIn('UIViewController, UIDocumentPickerDelegate', self.source)
        self.assertIn('forOpeningContentTypes: [.propertyList, .xml], asCopy: false', self.source)
        self.assertIn('picker.delegate = self', self.source)
        self.assertIn('present(picker, animated: true)', self.source)
        self.assertIn('guard controller === activePicker', self.source)
        for forbidden in ['SwiftUI', 'PairingFileManager', 'PairingImportFlow', 'TetherlessCore']:
            # Comments can explain independence; executable imports/references must not exist.
            code = '\n'.join(line for line in self.source.splitlines() if not line.lstrip().startswith('//'))
            self.assertNotIn(forbidden, code)
        self.assertEqual(self.source.count('func documentPicker('), 1)
        self.assertNotIn('.documentPicker(', self.source + self.ui)

    def test_original_document_validation_and_product_rejection_stay_required(self):
        self.assertIn('object == ["TetherlessInvalidPairingFixture": true]', self.source)
        self.assertIn('try Data(contentsOf: url) == payload', self.source)
        self.assertIn('for attempt in 1...2', self.ui)
        self.assertIn('The operation did not complete.', self.ui)
        self.assertIn('XCTAssertFalse(app.buttons["onboarding.next"].isEnabled)', self.ui)
        self.assertIn('XCTAssertEqual(enabled.value as? String, "0")', self.ui)
        workflow = (ROOT.parent/'.github/workflows/native-simulator.yml').read_text()
        self.assertIn('ui_document_fixture.py verify', workflow)
        self.assertNotIn('continue-on-error', workflow)

    def test_control_reports_only_fixed_outcomes_and_never_reads_selected_contents(self):
        code = self.source.split('final class DocumentPickerControl:')[1]
        self.assertIn('private enum Outcome: String', code)
        self.assertIn('private func observe(_ outcome: Outcome)', code)
        self.assertIn('urls.count == 1 && urls.first?.isFileURL == true', code)
        self.assertNotIn('Data(contentsOf:', code)
        self.assertNotIn('absoluteString', code)
        self.assertNotIn('.path', code)
        self.assertEqual(code.count('print('), 1)
        self.assertIn('controller.delegate = nil', code)
        self.assertIn('activePicker = nil', code)
        self.assertIn('allowed.contains(status.label)', self.control)
        self.assertIn('independent-picker-control-result', self.control)

    def test_changed_swift_sources_parse(self):
        result = subprocess.run(['swiftc', '-frontend', '-parse',
                                 str(ROOT/'UITestSupport/DocumentFixtureApp.swift'),
                                 str(ROOT/'UITests/TetherlessUITests.swift')],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

if __name__ == '__main__': unittest.main()
