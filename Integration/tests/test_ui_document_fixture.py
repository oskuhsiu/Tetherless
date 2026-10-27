from pathlib import Path
import hashlib
import importlib.util
import plistlib
import sys
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('document_fixture', ROOT/'ui_document_fixture.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class UIDocumentFixtureTests(unittest.TestCase):
    def test_only_a_malformed_pairing_document_is_seeded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = m.seed(root)
            self.assertEqual([p.relative_to(root).as_posix() for p in root.rglob('*')],
                             ['Documents', 'Documents/' + m.NAME])
            self.assertEqual(plistlib.loads((root/'Documents'/m.NAME).read_bytes()),
                             {'TetherlessInvalidPairingFixture': True})
            self.assertEqual(result['uiResult'], 'not-observed')
            self.assertEqual(result['sha256'], hashlib.sha256(m.PAYLOAD).hexdigest())
            self.assertTrue(m.verify(root)['originalPreserved'])

    def test_existing_file_is_not_overwritten_and_bad_readback_is_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); m.seed(root)
            with self.assertRaises(FileExistsError): m.seed(root)
            (root/'Documents'/m.NAME).write_text('changed')
            with self.assertRaises(RuntimeError): m.verify(root)

    def test_symlinked_documents_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); outside = root/'outside'; outside.mkdir()
            (root/'Documents').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError): m.seed(root)
            self.assertEqual(list(outside.iterdir()), [])

    def test_actual_ui_path_requires_rejection_and_preserves_existing_checks(self):
        text=(ROOT/'UITests/TetherlessUITests.swift').read_text()
        self.assertIn('for attempt in 1...2',text)
        self.assertIn('tapDocumentItem("Tetherless Test Documents", in: app, documentCell: true)',text)
        self.assertIn('tapDocumentItem("Tetherless-Invalid-Pairing.plist", in: app, documentCell: true)',text)
        self.assertIn('documentCell ? app.cells : app.descendants(matching: .any)',text)
        self.assertIn('01-invalid-pairing-rejected',text)
        self.assertIn('XCTAssertFalse(app.buttons["onboarding.next"].isEnabled)',text)
        self.assertIn('The operation did not complete.',text)
        self.assertNotIn('launchEnvironment',text)
        workflow=(ROOT.parent/'.github/workflows/native-simulator.yml').read_text()
        self.assertLess(workflow.index('simulator_smoke.py launch'),workflow.index('document_fixture_app.py'))
        self.assertLess(workflow.index('xcodebuild test'),workflow.index('ui_document_fixture.py verify'))
        self.assertIn('native-ui-document-fixture.json',workflow)
        self.assertNotIn('continue-on-error',workflow)
        environment=(ROOT/'simulator_environment.py').read_text()
        self.assertIn('payload = listing(timeout=90)',environment)
        self.assertIn('def listing(timeout: int = 30)',environment)


class DocumentActivationContractTests(unittest.TestCase):
    def test_document_cell_is_the_only_activation_target(self):
        text = (ROOT/'UITests/TetherlessUITests.swift').read_text()
        helper = text.split('private func tapDocumentItem(')[1].split('/// SwiftUI Form')[0]
        self.assertIn('XCTAssertTrue(item.isEnabled', helper)
        self.assertIn('XCTAssertTrue(item.isHittable', helper)
        self.assertEqual(helper.count('item.tap()'), 1)
        self.assertNotIn('item.images', helper)
        self.assertNotIn('preview.tap()', helper)
        self.assertNotIn('coordinate(', helper)
        self.assertNotIn('doubleTap(', helper)
        self.assertNotIn('for ', helper)
        self.assertNotIn('while ', helper)
        self.assertIn('document-before-activation', helper)

    def test_outcome_and_real_dismissal_remain_mandatory(self):
        text = (ROOT/'UITests/TetherlessUITests.swift').read_text()
        part = text.split('let rejected =')[1].split('// Kill/relaunch')[0]
        self.assertIn('rejected.waitForExistence(timeout: 10)', part)
        self.assertIn('app.otherElements["Browse View (Picker)"].exists', part)
        self.assertIn('XCTAssertTrue(outcomeAppeared', part)
        self.assertIn('XCTAssertFalse(pickerStillVisible', part)
        self.assertIn('The operation did not complete.', part)
        self.assertIn('XCTAssertTrue(app.buttons["onboarding.importPairing"].isEnabled)', part)
        self.assertIn('XCTAssertFalse(app.buttons["onboarding.next"].isEnabled)', part)
        self.assertIn('01-after-file-activation', part)


if __name__ == '__main__': unittest.main()
