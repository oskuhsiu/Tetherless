from pathlib import Path
import importlib.util
import json
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('fixture_app', ROOT/'document_fixture_app.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
import ui_document_fixture as fixture


class DocumentFixtureAppTests(unittest.TestCase):
    def test_bundle_exposes_only_invalid_public_document_with_separate_identity(self):
        with tempfile.TemporaryDirectory() as d:
            app = Path(d)/'fixture.app'
            entitlements = m.build_inputs(app, 'XYZ0123456.org.tetherless.Tetherless.XYZ0123456')
            info = plistlib.loads((app/'Info.plist').read_bytes())
            self.assertEqual(info['CFBundleIdentifier'], 'org.tetherless.testdocuments')
            self.assertTrue(info['LSSupportsOpeningDocumentsInPlace'])
            self.assertTrue(info['UIFileSharingEnabled'])
            self.assertNotIn('NSAppTransportSecurity', info)
            self.assertEqual(plistlib.loads((app/'InvalidPairingFixture.plist').read_bytes()),
                             {'TetherlessInvalidPairingFixture': True})
            self.assertEqual(set(p.name for p in app.iterdir()), {'Info.plist', 'InvalidPairingFixture.plist'})
            ent = plistlib.loads(entitlements.read_bytes())
            self.assertEqual(ent, {'application-identifier': 'XYZ0123456.org.tetherless.testdocuments',
                                  'get-task-allow': True})
            self.assertNotIn('keychain-access-groups', ent)
            self.assertNotIn('com.apple.security.application-groups', ent)

    def test_build_refuses_unknown_identity_and_never_overwrites_existing_bundle(self):
        with tempfile.TemporaryDirectory() as d:
            app = Path(d)/'fixture.app'
            with self.assertRaises(ValueError): m.build_inputs(app, 'arbitrary')
            self.assertFalse(app.exists())
            m.build_inputs(app, 'XYZ0123456.org.example')
            before = {p.name:p.read_bytes() for p in app.iterdir()}
            with self.assertRaises(FileExistsError): m.build_inputs(app, 'XYZ0123456.org.example')
            self.assertEqual(before, {p.name:p.read_bytes() for p in app.iterdir()})

    def test_architecture_is_explicit_and_unknown_host_is_refused(self):
        self.assertEqual(m.target('arm64'), 'arm64-apple-ios17.0-simulator')
        self.assertEqual(m.target('x86_64'), 'x86_64-apple-ios17.0-simulator')
        with self.assertRaises(ValueError): m.target('unknown')

    def test_command_failure_is_retained_and_not_retried(self):
        with tempfile.TemporaryDirectory() as d, patch.object(m,'LOG',Path(d)/'log'):
            with self.assertRaises(subprocess.CalledProcessError):
                m.command([sys.executable, '-c', 'print("fixture-build-failure");raise SystemExit(3)'], 5)
            text = m.LOG.read_text()
            self.assertEqual(text.count('$ '), 1)
            self.assertIn('fixture-build-failure', text)

    def test_native_writer_is_coordinated_and_not_linked_into_product_or_test_bundle(self):
        text = (ROOT/'UITestSupport/DocumentFixtureApp.swift').read_text()
        self.assertIn('coordinator.coordinate(writingItemAt: output',text)
        self.assertIn('options: .forReplacing',text)
        self.assertIn('options: .withoutOverwriting',text)
        self.assertIn('object == ["TetherlessInvalidPairingFixture": true]',text)
        self.assertNotIn('URLSession',text)
        self.assertNotIn('PairingFileManager',text)
        self.assertNotIn('TetherlessCore',text)
        for p in [ROOT/'prepare.py', ROOT/'prepare_ui_tests.py']:
            self.assertNotIn('DocumentFixtureApp', p.read_text())
        self.assertFalse((ROOT/'UITests/DocumentFixtureApp.swift').exists())
        result = subprocess.run(['swiftc','-frontend','-parse',str(ROOT/'UITestSupport/DocumentFixtureApp.swift')],
                                capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_real_source_ready_precedes_product_picker_without_changing_outcome(self):
        text = (ROOT/'UITests/TetherlessUITests.swift').read_text()
        self.assertLess(text.index('documents.launch()'),text.index('fixture.documentReady'))
        self.assertLess(text.index('fixture.documentReady'),text.index('app.launch()'))
        self.assertIn('documents.terminate()',text)
        self.assertIn('tapDocumentItem("Tetherless Test Documents", in: app, documentCell: true)',text)
        self.assertIn('for attempt in 1...2',text)
        self.assertIn('rejected.waitForExistence(timeout: 10)',text)
        self.assertIn('XCTAssertFalse(pickerStillVisible',text)
        self.assertIn('The operation did not complete.',text)
        self.assertNotIn('launchEnvironment',text)
        self.assertNotIn('documentPicker(',text)

    def test_preservation_runs_after_failed_ui_but_cannot_assert_ui_success(self):
        text = (ROOT.parent/'.github/workflows/native-simulator.yml').read_text()
        self.assertIn("if: ${{ always() && steps.document_fixture.outcome == 'success' }}",text)
        self.assertNotIn('ui_document_fixture.py seed',text)
        self.assertNotIn('continue-on-error',text)
        self.assertLess(text.index('document_fixture_app.py'),text.index('xcodebuild test'))
        self.assertIn('native-document-fixture-build.log',text)
        verification = (ROOT/'ui_document_fixture.py').read_text()
        self.assertIn("choices=['verify']",verification)
        self.assertIn("bundle != 'org.tetherless.testdocuments'",verification)
        self.assertNotIn("evidence['bundleID']",verification)
        self.assertNotIn("'uiResult': 'passed'",verification)

    def test_preservation_refuses_symlinked_parent_and_oversized_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'outside').mkdir(); (root/'Documents').symlink_to(root/'outside')
            with self.assertRaises(ValueError):fixture.verify(root)
            (root/'Documents').unlink(); fixture.seed(root)
            p=root/'Documents'/fixture.NAME;p.write_bytes(b'x'*1000000)
            with self.assertRaises(RuntimeError):fixture.verify(root)

if __name__ == '__main__':unittest.main()
