// SPDX-License-Identifier: AGPL-3.0-only
import Testing
@testable import TetherlessCore

@Suite("Main interface requires actual database startup, not wizard dismissal")
struct LaunchReadinessTests {
    @Test func wizardFinishesBeforeDatabase() {
        var state = LaunchReadiness(onboardingDismissed: false)
        state.dismissOnboarding()
        let allowed1 = state.claimTransition()
        #expect(!allowed1)
        #expect(!state.hasTransitioned)
        state.databaseDidStart()
        let allowed2 = state.claimTransition()
        #expect(allowed2)
        let allowed3 = state.claimTransition()
        #expect(!allowed3)
    }
    @Test func databaseFinishesBeforeWizard() {
        var state = LaunchReadiness(onboardingDismissed: false)
        state.databaseDidStart()
        let allowed4 = state.claimTransition()
        #expect(!allowed4)
        state.dismissOnboarding()
        let allowed5 = state.claimTransition()
        #expect(allowed5)
        let allowed6 = state.claimTransition()
        #expect(!allowed6)
    }
    @Test func priorWizardDismissalDoesNotBypassDatabase() {
        var state = LaunchReadiness(onboardingDismissed: true)
        let allowed7 = state.claimTransition()
        #expect(!allowed7)
        state.databaseDidStart()
        let allowed8 = state.claimTransition()
        #expect(allowed8)
    }
    @Test func repeatedFailureCannotPresentMainButSuccessfulRetryCan() {
        var state = LaunchReadiness(onboardingDismissed: true)
        for _ in 0..<4 { let allowed = state.claimTransition(); #expect(!allowed) }
        #expect(!state.databaseReady)
        state.databaseDidStart()
        let allowed9 = state.claimTransition()
        #expect(allowed9)
        state.dismissOnboarding(); state.databaseDidStart()
        let allowed10 = state.claimTransition()
        #expect(!allowed10)
    }
}
