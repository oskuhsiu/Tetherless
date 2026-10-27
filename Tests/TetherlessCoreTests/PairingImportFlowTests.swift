// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore

@Suite("Pairing picker request lifetime: no persistence or device claims")
struct PairingImportFlowTests {
    private let file = URL(fileURLWithPath: "/synthetic/pairing.plist")
    @Test func repeatedTapCannotCreateSecondPresentation() throws {
        var flow = PairingImportFlow()
        #expect(!flow.isBusy && flow.request == nil)
        let created = flow.begin(); let request = try #require(created)
        let observed1 = flow.isBusy && flow.request == request && flow.begin() == nil
        #expect(observed1)
    }
    @Test func selectionWaitsForDismissalAndIsConsumedOnce() throws {
        var flow = PairingImportFlow()
        let created = flow.begin(); let request = try #require(created)
        let observed2 = flow.resolve(.selected(file), request: request)
        #expect(observed2)
        let observed3 = !flow.finished(request)
        #expect(observed3)
        let observed4 = flow.begin() == nil
        #expect(observed4)
        let observed5 = flow.dismissed(request) == .selected(file)
        #expect(observed5)
        let observed6 = flow.dismissed(request) == nil
        #expect(observed6)
        let observed7 = flow.isBusy && flow.begin() == nil
        #expect(observed7)
        let observed8 = flow.finished(request)
        #expect(observed8)
        #expect(!flow.isBusy && flow.request == nil)
    }
    @Test func explicitCancellationNeverProducesAnImport() throws {
        var flow = PairingImportFlow()
        let created = flow.begin(); let request = try #require(created)
        let observed9 = flow.resolve(.cancelled, request: request)
        #expect(observed9)
        let observed10 = !flow.resolve(.selected(file), request: request)
        #expect(observed10)
        let observed11 = flow.dismissed(request) == .cancelled
        #expect(observed11)
        let observed12 = !flow.finished(request)
        #expect(observed12)
        let observed13 = flow.begin() != nil
        #expect(observed13)
    }
    @Test func dismissalAloneWaitsForExplicitOutcomeWithoutInventingCancellation() throws {
        var flow = PairingImportFlow()
        let created = flow.begin(); let request = try #require(created)
        let observed14 = flow.dismissed(request) == nil && flow.isBusy
        #expect(observed14)
        let observed15 = flow.resolve(.cancelled, request: request)
        #expect(observed15)
        let cancelled = flow.consume(request)
        #expect(cancelled == .cancelled)
        #expect(!flow.isBusy)
    }
    @Test func lateDelegateAndDismissalCannotCancelNewPresentation() throws {
        var flow = PairingImportFlow()
        let first = flow.begin(); let old = try #require(first)
        _ = flow.resolve(.cancelled, request: old)
        _ = flow.dismissed(old)
        let second = flow.begin(); let current = try #require(second)
        #expect(current != old)
        let observed16 = !flow.resolve(.cancelled, request: old)
        #expect(observed16)
        let observed17 = !flow.resolve(.selected(file), request: old)
        #expect(observed17)
        let observed18 = flow.dismissed(old) == nil && !flow.finished(old)
        #expect(observed18)
        #expect(flow.request == current && flow.isBusy)
        let observed19 = flow.resolve(.selected(file), request: current)
        #expect(observed19)
        let observed20 = flow.dismissed(current) == .selected(file)
        #expect(observed20)
    }
    @Test func wrongRequestCannotConsumeOrFinishSelection() throws {
        var flow = PairingImportFlow()
        let created = flow.begin(); let request = try #require(created)
        let other = PairingImportRequest()
        let observed21 = flow.dismissed(other) == nil
        #expect(observed21)
        let observed22 = flow.resolve(.selected(file), request: request)
        #expect(observed22)
        let observed23 = flow.dismissed(other) == nil
        #expect(observed23)
        let observed24 = flow.dismissed(request) == .selected(file)
        #expect(observed24)
        let observed25 = !flow.finished(other) && flow.isBusy
        #expect(observed25)
        let observed26 = flow.finished(request)
        #expect(observed26)
        let observed27 = !flow.finished(request)
        #expect(observed27)
    }
    @Test func repeatedSelectionAndCancellationDoNotReplaceFirstResult() throws {
        var flow = PairingImportFlow()
        let created = flow.begin(); let request = try #require(created)
        let observed28 = flow.resolve(.selected(file), request: request)
        #expect(observed28)
        let observed29 = !flow.resolve(.selected(URL(fileURLWithPath: "/different")), request: request)
        #expect(observed29)
        let observed30 = !flow.resolve(.cancelled, request: request)
        #expect(observed30)
        let observed31 = flow.dismissed(request) == .selected(file)
        #expect(observed31)
    }
    @Test func nonFileURLIsNotAnImport() throws {
        var flow = PairingImportFlow()
        let created = flow.begin(); let request = try #require(created)
        let observed32 = flow.resolve(.selected(URL(string: "https://example.invalid/pairing")!), request: request)
        #expect(observed32)
        let observed33 = flow.dismissed(request) == .invalidSelection
        #expect(observed33)
        let observed34 = !flow.isBusy && !flow.finished(request)
        #expect(observed34)
    }
    @Test func importFailureCanFinishAndUserCanRetryWithFreshRequest() throws {
        var flow = PairingImportFlow()
        let created = flow.begin(); let request = try #require(created)
        _ = flow.resolve(.selected(file), request: request)
        _ = flow.dismissed(request)
        // Both success and failure close the ephemeral UI work, not stored state.
        let observed35 = flow.finished(request)
        #expect(observed35)
        let second = flow.begin(); let retry = try #require(second)
        #expect(retry != request)
        let observed36 = flow.dismissed(request) == nil && flow.isBusy
        #expect(observed36)
    }
    @Test func bothEventOrdersConsumeEveryOutcomeExactlyOnce() throws {
        for outcome in [PairingImportFlow.Outcome.selected(file), .cancelled, .invalidSelection] {
            for dismissalFirst in [false, true] {
                var flow = PairingImportFlow()
                let created = flow.begin(); let request = try #require(created)
                if dismissalFirst {
                    let first = flow.dismissed(request)
                    #expect(first == nil)
                    let repeated = flow.dismissed(request)
                    #expect(repeated == nil)
                    #expect(flow.isBusy)
                }
                let accepted = flow.resolve(outcome, request: request)
                #expect(accepted)
                let duplicate = flow.resolve(.cancelled, request: request)
                #expect(!duplicate)
                let result: PairingImportFlow.Outcome?
                if dismissalFirst { result = flow.consume(request) }
                else {
                    let early = flow.consume(request)
                    #expect(early == nil)
                    result = flow.dismissed(request)
                }
                #expect(result == outcome)
                let repeated = flow.consume(request)
                let repeatedDismissal = flow.dismissed(request)
                #expect(repeated == nil && repeatedDismissal == nil)
                if case .selected = outcome {
                    #expect(flow.isBusy)
                    let finished = flow.finished(request)
                    #expect(finished)
                }
                #expect(!flow.isBusy)
            }
        }
    }
    @Test func explicitTeardownAbandonsOnlyAnUnresolvedMatchingGeneration() throws {
        var flow = PairingImportFlow()
        let created = flow.begin(); let first = try #require(created)
        _ = flow.dismissed(first)
        let wrong = flow.abandon(PairingImportRequest())
        #expect(!wrong && flow.isBusy)
        let abandoned = flow.abandon(first)
        #expect(abandoned && !flow.isBusy)
        let repeated = flow.abandon(first)
        #expect(!repeated)
        let second = flow.begin(); let current = try #require(second)
        let late = flow.resolve(.selected(file), request: first)
        let oldDismissal = flow.dismissed(first)
        let oldTeardown = flow.abandon(first)
        #expect(!late && oldDismissal == nil && !oldTeardown)
        #expect(flow.request == current)
        _ = flow.resolve(.selected(file), request: current)
        let resolvedTeardown = flow.abandon(current)
        #expect(!resolvedTeardown && flow.isBusy)
        let result = flow.dismissed(current)
        #expect(result == .selected(file))
        let importingTeardown = flow.abandon(current)
        #expect(!importingTeardown && flow.isBusy)
        let finished = flow.finished(current)
        #expect(finished && !flow.isBusy)
    }
    @Test func actualPickerSelectionPolicyRejectsEmptyMultipleAndNonFileURLs() {
        for urls in [[], [file, file], [URL(string: "https://example.invalid/document")!]] {
            #expect(PairingImportFlow.Outcome.pickedDocuments(urls) == .invalidSelection)
        }
        #expect(PairingImportFlow.Outcome.pickedDocuments([file]) == .selected(file))
    }

}


@Suite("Actual picker result relay: explicit teardown and generation isolation")
@MainActor
struct PairingImportRelayTests {
    @Test func lateSelectionAfterDismissalSurvivesUntilExplicitDelegateDelivery() throws {
        var flow = PairingImportFlow()
        let created = flow.begin(); let request = try #require(created)
        let file = URL(fileURLWithPath: "/synthetic/selected.plist")
        var results: [PairingImportFlow.Outcome] = []
        var abandoned = false
        let relay = PairingImportResultRelay(request: request, onResolve: { bound, outcome in
            if flow.resolve(outcome, request: bound), let result = flow.consume(bound) { results.append(result) }
        }, onAbandon: { bound in abandoned = flow.abandon(bound) })
        let early = flow.dismissed(request)
        #expect(early == nil && relay.isPending)
        let delivered = relay.resolve(.selected(file))
        #expect(delivered && results == [.selected(file)])
        let teardown = relay.invalidate()
        let duplicate = relay.resolve(.cancelled)
        #expect(!teardown && !duplicate && !abandoned)
        #expect(flow.isBusy)
        let finished = flow.finished(request)
        #expect(finished)
    }
    @Test func explicitRecoveryBeforeResultIgnoresLateCallbacksAndCannotCancelNewRequest() throws {
        var flow = PairingImportFlow()
        let created = flow.begin(); let request = try #require(created)
        var callbacks = 0
        var abandonments = 0
        let relay = PairingImportResultRelay(request: request, onResolve: { bound, outcome in
            callbacks += 1
            _ = flow.resolve(outcome, request: bound)
        }, onAbandon: { bound in
            if flow.abandon(bound) { abandonments += 1 }
        })
        let first = relay.invalidate()
        let second = relay.invalidate()
        #expect(first && !second && !flow.isBusy && !relay.isPending)
        let next = flow.begin(); let current = try #require(next)
        let late = relay.resolve(.selected(URL(fileURLWithPath: "/synthetic/late.plist")))
        #expect(!late && callbacks == 0 && abandonments == 1)
        #expect(flow.request == current)
    }
    @Test func recoveryAfterResultCannotErasePendingOrConsumedSelection() throws {
        var flow = PairingImportFlow()
        let created = flow.begin(); let request = try #require(created)
        let file = URL(fileURLWithPath: "/synthetic/selected.plist")
        var abandonments = 0
        let relay = PairingImportResultRelay(request: request, onResolve: { bound, outcome in
            _ = flow.resolve(outcome, request: bound)
        }, onAbandon: { _ in abandonments += 1 })
        let selected = relay.resolve(.selected(file))
        let teardown = relay.invalidate()
        #expect(selected && !teardown && !relay.isPending && abandonments == 0)
        let result = flow.dismissed(request)
        #expect(result == .selected(file))
        let repeated = relay.invalidate()
        #expect(!repeated && flow.isBusy)
        let finished = flow.finished(request)
        #expect(finished)
    }
    @Test func relayClearsCallbacksBeforeReentrantTeardown() {
        let request = PairingImportRequest()
        var relay: PairingImportResultRelay?
        var callbacks = 0
        var abandonments = 0
        var reentrantDelivery = true
        relay = PairingImportResultRelay(request: request, onResolve: { bound, outcome in
            #expect(bound == request && outcome == .cancelled)
            callbacks += 1
            relay?.invalidate()
            reentrantDelivery = relay?.resolve(.invalidSelection) ?? false
        }, onAbandon: { _ in abandonments += 1 })
        let delivered = relay?.resolve(.cancelled)
        #expect(delivered == true && callbacks == 1 && abandonments == 0 && !reentrantDelivery)
        relay = nil
    }
}
