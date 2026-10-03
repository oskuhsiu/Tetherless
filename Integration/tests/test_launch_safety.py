import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('launch_safety', ROOT / 'launch_safety.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LaunchSafetyTests(unittest.TestCase):
    def test_bundle_reader_is_only_for_own_simulator_image(self):
        result = module.patch_bundle('import CodeSignKit\n    var appGroups: [String] {\nexistingDevicePath\n}\n    @objc dynamic var altstoreAppGroup: String? {\n}')
        self.assertIn('#if targetEnvironment(simulator)', result)
        self.assertIn('self.bundleURL == Bundle.main.bundleURL', result)
        self.assertIn('getsectiondata(image, "__TEXT", "__entitlements", &size)', result)
        self.assertIn('size <= 1_048_576', result)
        self.assertIn('existingDevicePath', result)
        self.assertNotIn('temporaryDirectory', result)
        self.assertNotIn('return ["group.', result)
        self.assertNotIn('UserDefaults', result)

    def test_reapplication_and_source_drift_are_rejected(self):
        for source in ['', 'import CodeSignKit\n', '    var appGroups: [String] {\n']:
            with self.assertRaises(ValueError): module.patch_bundle(source)
        source = 'import CodeSignKit\n    var appGroups: [String] {\n}\n    @objc dynamic var altstoreAppGroup: String? {\n}'
        # Hash gate, not an implicit second application, protects generated files.
        self.assertNotEqual(module.patch_bundle(source), source)
        with self.assertRaises(ValueError): module.patch_launch('changed launch')

    def test_all_hashes_checked_before_any_write(self):
        def blob(data):
            return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = {module.BUNDLE: b'import CodeSignKit\n    var appGroups: [String] {\n}\n    @objc dynamic var altstoreAppGroup: String? {\n}',
                    module.LAUNCH: b'unreviewed'}
            for name, raw in data.items():
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            with patch.dict(module.BLOBS, {module.BUNDLE: blob(data[module.BUNDLE])}):
                with self.assertRaisesRegex(ValueError, 'Unreviewed launch input'):
                    module.apply(root)
            for name, raw in data.items(): self.assertEqual((root / name).read_bytes(), raw)

    def test_transition_checks_database_and_onboarding(self):
        source = (ROOT / 'launch_safety.py').read_text()
        self.assertIn('guard launchReadiness.claimTransition() else { return }', source)
        self.assertIn('self?.launchReadiness.dismissOnboarding()', source)
        self.assertIn('launchReadiness.databaseDidStart()', source)
        model = (ROOT.parent / 'Sources/TetherlessCore/LaunchReadiness.swift').read_text()
        self.assertIn('guard databaseReady, onboardingDismissed, !hasTransitioned', model)
        self.assertNotIn('UserDefaults', model)
        self.assertNotIn('renewalPermitted', model)

    def test_production_transform_follows_onboarding(self):
        source = (ROOT / 'network_safety.py').read_text()
        self.assertLess(source.index('"onboarding.py"'), source.index('"launch_safety.py"'))

    def test_actual_ui_relaunch_assertion_is_retained(self):
        source = (ROOT / 'UITests/TetherlessUITests.swift').read_text()
        self.assertIn('app.terminate(); app.launch()', source)
        self.assertIn('XCTAssertFalse(app.alerts["App Group Container Inaccessible"].exists)', source)
        self.assertIn('06-relaunch-database-ready', source)
        self.assertIn('XCTAssertEqual(enabled.value as? String, "0")', source)

    def test_simulator_does_not_assume_image_zero_is_main(self):
        source = (ROOT / 'launch_safety.py').read_text()
        self.assertIn('_dyld_get_image_name(index)', source)
        self.assertIn('actual == expected', source)
        self.assertIn('header.pointee.filetype == MH_EXECUTE', source)
        self.assertNotIn('_dyld_get_image_header(0)', source)
        self.assertIn('count <= 4096', source)

    def test_shared_container_failure_has_a_safe_stage_and_no_fallback(self):
        phrase = 'reason: NSLocalizedString("Unable to access the shared App Group container. Refusing to create or use a private sandbox fallback database.", comment: "")'
        patched = module.patch_container(phrase)
        self.assertIn('Bundle.main.tetherlessAppGroupDiagnostic', patched)
        self.assertNotIn('temporaryDirectory', patched)
        self.assertNotIn('UserDefaults', patched)
        with self.assertRaises(ValueError): module.patch_container('changed')

    def test_ui_rejects_startup_alerts_before_default_handler_can_retry(self):
        source = (ROOT / 'UITests/TetherlessUITests.swift').read_text()
        self.assertEqual(source.count('assertStartupHasNoFailure(app)'), 3)
        self.assertIn('let startup = app.alerts["App Group Container Inaccessible"]', source)
        self.assertIn('XCTAssertFalse(startup.exists, startup.debugDescription)', source)
