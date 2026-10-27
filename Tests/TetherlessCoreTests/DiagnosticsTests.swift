import Foundation
import Testing
@testable import TetherlessCore

private let date = Date(timeIntervalSince1970: 1_800_000_000)
private func exampleSummary(trigger: RenewalTrigger = .shortcut, foreground: Bool = false,
                            manager: Bool = true, failure: RenewalFailure? = nil) throws -> RenewalSummary {
    let app = try AppLease(bundleID: "private.TeamID.App", isManager: manager,
                           effectiveExpiry: date.addingTimeInterval(7 * 86_400), identityDigest: String(repeating: "c", count: 64))
    var result = RenewalRunResult()
    result.observed = [app]; result.managedIDs = [app.bundleID]
    result.attempted = [app.bundleID]; result.verified = [app.bundleID]; result.globalFailure = failure
    return RenewalSummary(startedAt: date, finishedAt: date.addingTimeInterval(5), trigger: trigger,
                          managerWasForeground: foreground, result: result)
}
@Suite("Evidence timeline and privacy-whitelisted diagnostics")
struct DiagnosticsTests {
    @Test func manualOrForegroundRunCannotConfirmBackgroundRenewal() throws {
        #expect(try !exampleSummary(trigger: .manual).managerRenewedOutsideForeground)
        #expect(try !exampleSummary(foreground: true).managerRenewedOutsideForeground)
        #expect(try !exampleSummary(trigger: .acceleratedTest).managerRenewedOutsideForeground)
        #expect(try !exampleSummary(manager: false).managerRenewedOutsideForeground)
        #expect(try exampleSummary().managerRenewedOutsideForeground)
    }
    @Test func partialSuccessDoesNotClaimACompleteBackgroundRun() throws {
        #expect(try !exampleSummary(failure: .needsForeground).managerRenewedOutsideForeground)
    }
    @Test func timelineIsBoundedAndExportContainsNoIdentifiersOrIdentityDigests() throws {
        var timeline = RenewalTimeline()
        for _ in 0..<100 { try timeline.record(exampleSummary()) }
        #expect(timeline.runs.count == 64)
        #expect(timeline.lastObservedBackgroundRenewal != nil)
        let text = String(decoding: try timeline.diagnosticData(), as: UTF8.self)
        #expect(!text.contains("private.TeamID.App"))
        #expect(!text.contains(String(repeating: "c", count: 64)))
        #expect(!text.contains("observedLeases"))
        #expect(text.contains("deviceLaunchValidated"))
    }
    @Test func incompleteDiscoveryDoesNotDeleteLastObservedExpiries() throws {
        var timeline = RenewalTimeline()
        try timeline.record(exampleSummary())
        var result = RenewalRunResult(); result.globalFailure = .needsAuthentication
        try timeline.record(RenewalSummary(startedAt: date, finishedAt: date, trigger: .background,
                                           managerWasForeground: false, result: result))
        #expect(timeline.lastObservedLeases.count == 1)
    }
    @Test func completeEmptySnapshotRemovesStaleUninstalledApps() throws {
        var timeline = RenewalTimeline()
        try timeline.record(exampleSummary())
        var result = RenewalRunResult(); result.managedIDs = []
        try timeline.record(RenewalSummary(startedAt: date, finishedAt: date, trigger: .background,
                                           managerWasForeground: false, result: result))
        #expect(timeline.lastObservedLeases.isEmpty)
    }
    @Test func priorSingleRunEvidenceIsCompatibleButNotBackgroundProof() throws {
        let json = #"{"startedAt":0,"finishedAt":1,"trigger":"shortcut","managerWasForeground":false,"attempted":1,"verified":1,"unverified":0,"deferred":0,"failures":[]}"#
        let summary = try JSONDecoder().decode(RenewalSummary.self, from: Data(json.utf8))
        try summary.validate()
        #expect(!summary.managerRenewedOutsideForeground)
    }
    @Test func unknownErrorTextCannotEnterDiagnosticExport() throws {
        let json = #"{"startedAt":0,"finishedAt":1,"trigger":"shortcut","managerWasForeground":false,"attempted":0,"verified":0,"unverified":0,"deferred":0,"failures":["password=DO_NOT_EXPORT"]}"#
        let summary = try JSONDecoder().decode(RenewalSummary.self, from: Data(json.utf8))
        var timeline = RenewalTimeline()
        #expect(throws: RenewalFailure.corruptJournal) { try timeline.record(summary) }
    }
    @Test func futureTimelineSchemaIsNotSilentlyReset() throws {
        var timeline = RenewalTimeline(); timeline.schemaVersion = 99
        #expect(throws: RenewalFailure.unsupportedJournal) { try timeline.record(exampleSummary()) }
    }
}
@Suite("Expiry notification planning is not an execution scheduler")
struct AlertTests {
    private func leases(days: Double) throws -> [AppLease] {
        [try AppLease(bundleID: "test.manager", isManager: true, effectiveExpiry: date.addingTimeInterval(days * 86_400))]
    }
    @Test func fullLeasePreSchedulesAllThreeWarnings() throws {
        let plan = try RenewalAlertPolicy.plan(leases: leases(days: 7), now: date)
        #expect(plan.map(\.severity) == [.warning48h, .urgent24h, .expired])
        #expect(plan[0].deliverAt == date.addingTimeInterval(5 * 86_400))
    }
    @Test func doNotSendThreeImmediateAlertsForAnExpiredApp() throws {
        let plan = try RenewalAlertPolicy.plan(leases: leases(days: -1), now: date)
        #expect(plan.count == 1)
        #expect(plan[0].severity == .expired)
        #expect(plan[0].deliverAt == date)
    }
    @Test func urgentStageHasOneImmediateAndOneFutureAlarm() throws {
        let plan = try RenewalAlertPolicy.plan(leases: leases(days: 0.5), now: date)
        #expect(plan.map(\.severity) == [.urgent24h, .expired])
        #expect(plan[0].deliverAt == date)
    }
    @Test func sameExpiryUsesStableIDsAndRenewedExpiryUsesNewIDs() throws {
        let one = try RenewalAlertPolicy.plan(leases: leases(days: 7), now: date)
        let repeatPlan = try RenewalAlertPolicy.plan(leases: leases(days: 7), now: date.addingTimeInterval(60))
        let renewed = try RenewalAlertPolicy.plan(leases: leases(days: 8), now: date)
        #expect(one.map(\.id) == repeatPlan.map(\.id))
        #expect(Set(one.map(\.id)).isDisjoint(with: renewed.map(\.id)))
    }
    @Test func noAppsDoesNotInventAnExpiry() throws {
        #expect(try RenewalAlertPolicy.plan(leases: [], now: date).isEmpty)
    }
}
