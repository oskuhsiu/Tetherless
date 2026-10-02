import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
ROOT = Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('ui', ROOT/'prepare_ui_tests.py')
ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)

class OnboardingIntegrationTests(unittest.TestCase):
    def test_unknown_project_cannot_be_patched(self):
        with self.assertRaises(ValueError): ui.patch_project('unreviewed')
    def test_scheme_only_uses_real_app_and_ui_target(self):
        root=ET.fromstring(ui.scheme())
        targets=root.findall('./BuildAction/BuildActionEntries/BuildActionEntry/BuildableReference')
        self.assertEqual({node.attrib['BlueprintIdentifier'] for node in targets},{ui.APP,ui.TARGET})
        self.assertEqual(len(root.findall('./TestAction/Testables/TestableReference')),1)
    def test_product_has_no_ui_fixture_flags(self):
        text=(ROOT/'Overrides/OnboardingView.swift').read_text()
        self.assertNotIn('ProcessInfo.processInfo.arguments',text)
        self.assertNotIn("You're All Set",text)
        self.assertIn('skipResign: false',text)
        self.assertIn('account?.phase == .ready',text)
        self.assertIn('A manual check does not count as an unattended run.',text)
    def test_wizard_completion_does_not_grant_permission(self):
        text=(ROOT/'Overrides/OnboardingView.swift').read_text().split('private func finish()')[1]
        self.assertIn('hasCompletedOnboarding = true',text)
        self.assertNotIn('renewalPermitted = true',text)
        self.assertNotIn('activate(',text)
    def test_buttons_have_accessible_identifiers(self):
        text=(ROOT/'Overrides/OnboardingView.swift').read_text()
        for identifier in ['title','next','back','later','signIn','importPairing','allowUnattended','finish','readiness']:
            self.assertIn('"onboarding.'+identifier+'"',text)
    def test_onboarding_runs_after_issuance(self):
        text=(ROOT/'network_safety.py').read_text()
        self.assertLess(text.index('"certificate_issuance.py"'),text.index('"onboarding.py"'))
    def test_ui_tests_never_log_in_or_fake_backend_success(self):
        text=(ROOT/'UITests/TetherlessUITests.swift').read_text()
        self.assertNotIn('typeText(',text)
        self.assertNotIn('method_exchangeImplementations',text)
        self.assertNotIn('launchEnvironment',text)
        self.assertIn('XCTAttachment(screenshot: app.screenshot())',text)
    def test_replay_entry_is_guarded_without_raising_entire_deployment_target(self):
        spec=importlib.util.spec_from_file_location('onboarding',ROOT/'onboarding.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        original='''                            OnboardingView(onFinish: {
                                showOnboardingSheet = false
                            })'''
        result=module.patch_replay(original)
        self.assertLess(result.index('if #available(iOS 17.0, *)'),result.index('OnboardingView('))
        self.assertIn('requires iOS 17 or later',result)
        with self.assertRaises(ValueError): module.patch_replay('drift')
