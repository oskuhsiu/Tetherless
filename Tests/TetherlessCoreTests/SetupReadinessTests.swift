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

@Suite("Stage-specific setup observations do not turn unreadable items into missing items")
struct SetupObservationTests {
    @Test func emptyReadableInstallationIsIncompleteNotFailed() {
        let value = SetupReadiness.observing(renewalPermitted: false, localAnisetteSelected: true,
            account: { false }, signer: { false }, pairing: { false })
        #expect(!value.localObservationFailed)
        #expect(value.title == "Setup is not finished")
        for stage in [SetupObservationIssue.Stage.account, .signingKey, .pairing] {
            #expect(value.observationLabel(for: stage) == "missing")
        }
    }
    @Test func failedAccountStopsLaterReadsAndNeverBecomesMissing() {
        var reads = 0
        let value = SetupReadiness.observing(renewalPermitted: false, localAnisetteSelected: true,
            account: { throw AuthenticationStorageFailure.unavailable },
            signer: { reads += 1; return true }, pairing: { reads += 1; return true })
        #expect(reads == 0)
        #expect(value.observationIssue?.diagnosticCode == "setup/account/storage")
        #expect(value.observationLabel(for: .account) == "unavailable")
        #expect(value.observationLabel(for: .signingKey) == "not checked")
        #expect(!value.canAttemptVerification)
    }
    @Test func failedSignerRetainsOnlyAlreadyObservedAccount() {
        let value = SetupReadiness.observing(renewalPermitted: true, localAnisetteSelected: true,
            account: { true }, signer: { throw AuthenticationStorageFailure.invalidRecord }, pairing: { true })
        #expect(value.observationIssue?.diagnosticCode == "setup/signingKey/invalidRecord")
        #expect(value.observationLabel(for: .account) == "present")
        #expect(value.observationLabel(for: .signingKey) == "unavailable")
        #expect(value.observationLabel(for: .pairing) == "not checked")
        #expect(!value.canAttemptVerification)
    }
    @Test func malformedPairingIsNotAbsentOrReset() {
        let value = SetupReadiness.observing(renewalPermitted: true, localAnisetteSelected: true,
            account: { true }, signer: { true }, pairing: { throw PrivateFileError.invalidContent })
        #expect(value.observationIssue?.diagnosticCode == "setup/pairing/invalidRecord")
        #expect(!value.canAttemptVerification)
        #expect(value.observationLabel(for: .pairing) == "unavailable")
    }
    @Test func lockContentionHasSpecificRetryAdvice() {
        var value = SetupReadiness()
        value.recordFailure(RenewalFailure.busy, at: .access)
        #expect(value.observationIssue?.diagnosticCode == "setup/access/busy")
        #expect(value.detail.contains("Another operation"))
        #expect(value.observationLabel(for: .account) == "not checked")
    }
    @Test func arbitraryErrorsCannotLeakToDiagnosticText() {
        struct SecretError: Error, CustomStringConvertible {
            var description: String { "token SECRET /private/path account@example.com" }
        }
        let issue = SetupObservationIssue(stage: .signingKey, error: SecretError())
        #expect(issue.diagnosticCode == "setup/signingKey/storage")
        for forbidden in ["SECRET", "/private/path", "account@example.com"] {
            #expect(!issue.detail.contains(forbidden))
        }
    }
    @Test func completeObservationStillNeedsLiveVerification() {
        let value = SetupReadiness.observing(renewalPermitted: true, localAnisetteSelected: true,
            account: { true }, signer: { true }, pairing: { true })
        #expect(value.canAttemptVerification)
        #expect(value.title == "Ready for a renewal check")
        #expect(value.observationIssue == nil)
        #expect(value.detail.contains("still need verification"))
    }
}
