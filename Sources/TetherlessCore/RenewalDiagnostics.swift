// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// Structured metadata only. Raw errors, profile bytes and credential material
/// have no field here. Optional additions preserve old last-run.json decoding.
public struct RenewalSummary: Codable, Equatable, Sendable {
    public let startedAt: Date
    public let finishedAt: Date
    public let trigger: RenewalTrigger
    public let managerWasForeground: Bool
    public let attempted: Int
    public let verified: Int
    public let unverified: Int
    public let deferred: Int
    public let failures: [String]
    public var observedLeases: [AppLease]?
    public var managedIDs: [String]?
    public var verifiedIDs: [String]?

    public init(startedAt: Date, finishedAt: Date, trigger: RenewalTrigger,
                managerWasForeground: Bool, result: RenewalRunResult) {
        self.startedAt = startedAt
        self.finishedAt = finishedAt
        self.trigger = trigger
        self.managerWasForeground = managerWasForeground
        attempted = result.attempted.count
        verified = result.verified.count
        unverified = result.appliedUnverified.count
        deferred = result.deferred.count
        failures = Array(Set((Array(result.failures.values) + [result.globalFailure].compactMap { $0 })
            .map(\.rawValue))).sorted()
        observedLeases = result.managedIDs == nil ? nil : result.observed
        managedIDs = result.managedIDs
        verifiedIDs = result.verified
    }

    public var managerRenewedOutsideForeground: Bool {
        guard !managerWasForeground, [.shortcut, .background].contains(trigger),
              failures.isEmpty, unverified == 0,
              let manager = observedLeases?.first(where: \.isManager) else { return false }
        return verifiedIDs?.contains(manager.bundleID) == true
    }
    public var message: String {
        if let first = failures.first.flatMap(RenewalFailure.init(rawValue:)) {
            return (verified > 0 ? "Renewed \(verified) app(s). " : "") + first.recoveryHint
        }
        if !failures.isEmpty { return "Unknown evidence format. Recheck status before continuing." }
        if unverified > 0 { return "Applied, but device readback has not verified the renewal." }
        if verified > 0 { return "Verified profile renewal for \(verified) app(s)." }
        return "No renewal completed: apps were deferred or are not due."
    }
    public func validate() throws {
        guard startedAt.timeIntervalSince1970.isFinite, finishedAt.timeIntervalSince1970.isFinite,
              [attempted, verified, unverified, deferred].allSatisfy({ (0...256).contains($0) }),
              failures.count <= 32, failures.allSatisfy({ RenewalFailure(rawValue: $0) != nil }) else {
            throw RenewalFailure.corruptJournal
        }
        if let leases = observedLeases {
            try RenewalSnapshot(apps: leases).validate()
            guard leases.filter(\.isManager).count <= 1,
                  let managedIDs, Set(leases.map(\.bundleID)).isSubset(of: Set(managedIDs)) else {
                throw RenewalFailure.corruptJournal
            }
        }
        if let managedIDs {
            guard managedIDs.count <= 256, Set(managedIDs).count == managedIDs.count,
                  managedIDs.allSatisfy(ManagedBundleIdentifier.isSafe) else { throw RenewalFailure.corruptJournal }
        }
        if let verifiedIDs {
            guard verifiedIDs.count == verified, Set(verifiedIDs).count == verifiedIDs.count,
                  verifiedIDs.allSatisfy(ManagedBundleIdentifier.isSafe) else { throw RenewalFailure.corruptJournal }
        }
    }
}

public struct RenewalTimeline: Codable, Equatable, Sendable {
    public var schemaVersion = 1
    public private(set) var runs: [RenewalSummary] = []
    public private(set) var lastObservedLeases: [AppLease] = []
    public init() {}
    public mutating func record(_ summary: RenewalSummary) throws {
        try validate()
        try summary.validate()
        if let managedIDs = summary.managedIDs {
            let active = Set(managedIDs)
            var leases = Dictionary(uniqueKeysWithValues: lastObservedLeases
                .filter { active.contains($0.bundleID) }.map { ($0.bundleID, $0) })
            for app in summary.observedLeases ?? [] { leases[app.bundleID] = app }
            lastObservedLeases = try RenewalPolicy().ordered(Array(leases.values))
        }
        runs.append(summary)
        if runs.count > 64 { runs.removeFirst(runs.count - 64) }
    }
    public var latest: RenewalSummary? { runs.last }
    /// Evidence of a non-foreground run, NOT attestation of a locked screen or
    /// proof that Shortcuts was triggered on a schedule rather than by a tap.
    public var lastObservedBackgroundRenewal: Date? {
        runs.last(where: \.managerRenewedOutsideForeground)?.finishedAt
    }
    public func validate() throws {
        guard schemaVersion == 1 else { throw RenewalFailure.unsupportedJournal }
        guard runs.count <= 64 else { throw RenewalFailure.corruptJournal }
        for run in runs { try run.validate() }
        try RenewalSnapshot(apps: lastObservedLeases).validate()
        guard lastObservedLeases.filter(\.isManager).count <= 1 else { throw RenewalFailure.corruptJournal }
    }

    /// Export a whitelist, never serialize this whole object for support. Bundle
    /// identifiers may embed Team IDs, so even identifiers/digests are omitted.
    public func diagnosticData() throws -> Data {
        try validate()
        struct Entry: Encodable {
            let startedAt: Date
            let finishedAt: Date
            let trigger: RenewalTrigger
            let managerWasForeground: Bool
            let attempted: Int
            let verified: Int
            let unverified: Int
            let deferred: Int
            let failures: [String]
        }
        struct Report: Encodable {
            let schemaVersion = 1
            let containsCredentials = false
            let deviceLaunchValidated = false
            let entries: [Entry]
        }
        let entries = runs.map {
            Entry(startedAt: $0.startedAt, finishedAt: $0.finishedAt, trigger: $0.trigger,
                  managerWasForeground: $0.managerWasForeground, attempted: $0.attempted,
                  verified: $0.verified, unverified: $0.unverified, deferred: $0.deferred, failures: $0.failures)
        }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .prettyPrinted]
        encoder.dateEncodingStrategy = .iso8601
        return try encoder.encode(Report(entries: entries))
    }
}

public enum RenewalAlertSeverity: String, Codable, Sendable {
    case warning48h, urgent24h, expired
}
public struct RenewalAlert: Equatable, Sendable {
    public let id: String
    public let severity: RenewalAlertSeverity
    public let deliverAt: Date
}

/// Compute alarms once from verified/observed expiry, then let the OS deliver
/// them even if renewal is never awakened again. Notifications are not renewal.
public enum RenewalAlertPolicy {
    public static let identifierPrefix = "org.tetherless.expiry."
    public static func plan(leases: [AppLease], now: Date) throws -> [RenewalAlert] {
        guard now.timeIntervalSince1970.isFinite else { throw RenewalFailure.invalidInput }
        try RenewalSnapshot(apps: leases).validate()
        guard let expiry = leases.map(\.effectiveExpiry).min() else { return [] }
        let stages: [(RenewalAlertSeverity, TimeInterval)] = [(.warning48h, 172_800), (.urgent24h, 86_400), (.expired, 0)]
        var future: [RenewalAlert] = []
        var immediate: RenewalAlert?
        for (severity, lead) in stages {
            let due = expiry.addingTimeInterval(-lead)
            let id = identifierPrefix + severity.rawValue + "." + String(expiry.timeIntervalSince1970)
            let alert = RenewalAlert(id: id, severity: severity, deliverAt: max(due, now))
            if due <= now { immediate = alert } else { future.append(alert) }
        }
        if let immediate { future.insert(immediate, at: 0) }
        return future
    }
}

public extension RenewalFailure {
    var recoveryHint: String {
        switch self {
        case .needsAuthentication: return "Sign in again and complete Apple's verification, then recheck setup."
        case .needsPairing: return "Repair pairing and the local VPN connection, then recheck setup."
        case .identityChanged: return "An app's signing identity changed. Complete an explicit reinstall, then re-enroll it."
        case .needsForeground: return "Finish the one-time setup or explicit repair in Tetherless."
        case .budgetExhausted: return "The execution budget ended. Completed renewals were kept; remaining work will retry."
        case .noExtension: return "Apple did not extend the usable expiry. No successful renewal was recorded."
        case .busy: return "Another device operation is running. Retry after it finishes."
        case .cancelled: return "The operation was cancelled. Interrupted work will be reconciled before retrying."
        case .invalidInput, .invalidEvidence: return "App/profile evidence did not match. Existing apps were not replaced. Check the affected app."
        case .corruptJournal, .unsupportedJournal: return "Saved state could not be trusted. It was preserved, not silently reset."
        case .storageUnavailable, .lockUnavailable: return "Protected storage is unavailable. Unlock the phone or check free storage, then retry."
        case .unavailable: return "Apple or the device connection is temporarily unavailable. Renewal will retry with backoff."
        }
    }
}
