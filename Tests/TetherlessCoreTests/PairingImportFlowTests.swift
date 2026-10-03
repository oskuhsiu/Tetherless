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
    @Test func interactiveDismissalIsCancellation() throws {
        var flow = PairingImportFlow()
        let created = flow.begin(); let request = try #require(created)
        let observed14 = flow.dismissed(request) == .cancelled
        #expect(observed14)
        let observed15 = !flow.isBusy && !flow.resolve(.selected(file), request: request)
        #expect(observed15)
    }
    @Test func lateDelegateAndDismissalCannotCancelNewPresentation() throws {
        var flow = PairingImportFlow()
        let first = flow.begin(); let old = try #require(first)
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
}
