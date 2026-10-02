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
