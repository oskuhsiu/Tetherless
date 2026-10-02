from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]

class ResumeSetupIntegrationTests(unittest.TestCase):
    def test_resume_keeps_navigation_separate_from_consent(self):
        text=(ROOT/'Overrides/OnboardingView.swift').read_text()
        self.assertIn('@AppStorage(SetupStep.storageKey)',text)
        self.assertIn('savedStep = next.rawValue',text)
        self.assertIn('.task(id: step) { await reload() }',text)
        self.assertIn('.interactiveDismissDisabled(working)',text)
        body=text.split('private func move(')[1].split('private func finish()')[0]
        for forbidden in ['renewalPermitted =', 'hasCompletedOnboarding =', 'activate(']:
            self.assertNotIn(forbidden,body)
        settings=(ROOT/'Native/NativeRenewalSettings.swift').read_text()
        self.assertIn('renewal.resumeSetup',settings)
        self.assertIn('.sheet(isPresented: $showSetupWizard)',settings)
        self.assertIn('OnboardingView {',settings)
