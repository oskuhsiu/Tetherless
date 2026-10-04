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
        self.assertIn('tapDocumentItem("Tetherless", in: app, documentCell: true)',text)
        self.assertIn('tapDocumentItem("Tetherless-Invalid-Pairing.plist", in: app, documentCell: true)',text)
        self.assertIn('documentCell ? app.cells : app.descendants(matching: .any)',text)
        self.assertIn('01-invalid-pairing-rejected',text)
        self.assertIn('XCTAssertFalse(app.buttons["onboarding.next"].isEnabled)',text)
        self.assertIn('The operation did not complete.',text)
        self.assertNotIn('launchEnvironment',text)
        workflow=(ROOT.parent/'.github/workflows/native-simulator.yml').read_text()
        self.assertLess(workflow.index('simulator_smoke.py launch'),workflow.index('ui_document_fixture.py seed'))
        self.assertLess(workflow.index('xcodebuild test'),workflow.index('ui_document_fixture.py verify'))
        self.assertIn('native-ui-document-fixture.json',workflow)
        self.assertNotIn('continue-on-error',workflow)
        environment=(ROOT/'simulator_environment.py').read_text()
        self.assertIn('payload = listing(timeout=90)',environment)
        self.assertIn('def listing(timeout: int = 30)',environment)


if __name__ == '__main__': unittest.main()
