// SPDX-License-Identifier: AGPL-3.0-only
import Testing
@testable import TetherlessCore

@Suite("Onboarding readiness is not unattended execution proof")
struct SetupReadinessTests {
    @Test func pairingAloneNeverCompletesSetup() {
        var state = SetupReadiness(); state.pairingStored = true
        #expect(!state.canAttemptVerification)
        #expect(state.title == "Setup is not finished")
    }
    @Test func everyPrerequisiteIsRequired() {
        for missing in 0..<5 {
            var state = SetupReadiness()
            state.pairingStored = missing != 0
            state.accountStored = missing != 1
            state.signingKeyStored = missing != 2
            state.localAnisetteSelected = missing != 3
            state.renewalPermitted = missing != 4
            #expect(!state.canAttemptVerification)
        }
    }
    @Test func localCompleteIsStillOnlyReadyForVerification() {
        var state = SetupReadiness()
        state.pairingStored = true; state.accountStored = true; state.signingKeyStored = true
        state.localAnisetteSelected = true; state.renewalPermitted = true
        #expect(state.canAttemptVerification)
        #expect(state.title == "Ready for a renewal check")
        #expect(state.detail.contains("still need verification"))
        state.localObservationFailed = true
        #expect(!state.canAttemptVerification)
        #expect(state.title == "Setup status could not be read")
    }
}

@Suite("Resumable navigation grants no setup authority")
struct SetupStepTests {
    @Test func stableStepNamesRoundTrip() {
        #expect(SetupStep.allCases.map(\.rawValue) ==
                ["welcome", "pairing", "connection", "account", "automation", "review"])
        for step in SetupStep.allCases { #expect(SetupStep.resuming(step.rawValue) == step) }
    }
    @Test func unknownCheckpointsStartAtWelcome() {
        for value in ["", "2", "finished", "futureStep", "PAIRING"] {
            #expect(SetupStep.resuming(value) == .welcome)
        }
    }
    @Test func navigationIsAdjacentAndBounded() {
        let steps = SetupStep.allCases
        for (index, step) in steps.enumerated() {
            #expect(step.ordinal == index + 1)
            #expect(step.moved(by: 1) == (index + 1 < steps.count ? steps[index + 1] : nil))
            #expect(step.moved(by: -1) == (index > 0 ? steps[index - 1] : nil))
            for invalid in [0, -2, 2, Int.min, Int.max] { #expect(step.moved(by: invalid) == nil) }
        }
    }
    @Test func restoringReviewDoesNotMakePrerequisitesReady() {
        #expect(SetupStep.resuming("review") == .review)
        let state = SetupReadiness()
        #expect(!state.canAttemptVerification)
        #expect(!state.renewalPermitted)
        #expect(state.title == "Setup is not finished")
    }
}
