// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

public struct RenewalPolicy: Equatable, Sendable {
    public let interval: TimeInterval
    public let urgentWindow: TimeInterval
    public let retryDelays: [TimeInterval]

    public init(interval: TimeInterval = 86_400, urgentWindow: TimeInterval = 259_200,
                retryDelays: [TimeInterval] = [900, 3_600, 21_600, 43_200]) throws {
        guard interval.isFinite, interval >= 60,
              urgentWindow.isFinite, urgentWindow >= 0,
              !retryDelays.isEmpty,
              retryDelays.allSatisfy({ $0.isFinite && $0 >= 60 }),
              retryDelays == retryDelays.sorted() else {
            throw RenewalFailure.invalidInput
        }
        self.interval = interval
        self.urgentWindow = urgentWindow
        self.retryDelays = retryDelays
    }

    public func isDue(app: AppLease, record: RenewalRecord?, now: Date) -> Bool {
        guard let record else { return true }
        // A pending transaction is reconciled before this policy is consulted.
        guard !record.requiresInteraction else { return false }
        // Urgency must NEVER override rate limiting or a Retry-After deadline.
        if let retryAfter = record.retryAfter, retryAfter > now { return false }
        let last = record.lastAppliedAt ?? record.lastVerifiedAt
        if let last, last > now { return true } // Re-evaluate after a clock rollback.
        if app.effectiveExpiry.timeIntervalSince(now) <= urgentWindow {
            // Avoid looping on every trigger when the signing certificate itself
            // limits the expiry. At most one ordinary attempt per hour.
            return record.lastAttemptAt.map { now.timeIntervalSince($0) >= 3_600 } ?? true
        }
        return last.map { now.timeIntervalSince($0) >= interval } ?? true
    }

    public func retryDate(failures: Int, now: Date) -> Date {
        let index = min(max(failures, 1) - 1, retryDelays.count - 1)
        return now.addingTimeInterval(retryDelays[index])
    }

    public func ordered(_ apps: [AppLease]) throws -> [AppLease] {
        guard Set(apps.map(\.bundleID)).count == apps.count,
              apps.filter(\.isManager).count <= 1 else {
            throw RenewalFailure.invalidInput
        }
        return apps.sorted {
            if $0.isManager != $1.isManager { return $0.isManager }
            if $0.effectiveExpiry != $1.effectiveExpiry {
                return $0.effectiveExpiry < $1.effectiveExpiry
            }
            return $0.bundleID < $1.bundleID
        }
    }
}

/// Metadata selection only, NOT CMS/certificate-chain validation. The adapter
/// must validate Apple's signed bytes, entitlements, device and revocation state
/// before setting `validatedForInstalledBinary` to true.
public struct ProfileCandidate: Sendable {
    public let id: String
    public let componentID: String
    public let teamID: String
    public let certificateID: String
    public let notBefore: Date
    public let expiry: Date
    public let validatedForInstalledBinary: Bool

    public init(id: String, componentID: String, teamID: String, certificateID: String,
                notBefore: Date, expiry: Date, validatedForInstalledBinary: Bool) {
        self.id = id
        self.componentID = componentID
        self.teamID = teamID
        self.certificateID = certificateID
        self.notBefore = notBefore
        self.expiry = expiry
        self.validatedForInstalledBinary = validatedForInstalledBinary
    }
}

public enum ProfileSelection {
    public static func effectiveExpiry(requiredComponents: Set<String>, teamID: String,
                                       certificateID: String, certificateExpiry: Date,
                                       candidates: [ProfileCandidate], now: Date) throws -> Date {
        guard !requiredComponents.isEmpty, !teamID.isEmpty, !certificateID.isEmpty,
              certificateExpiry.timeIntervalSince1970.isFinite, certificateExpiry > now,
              now.timeIntervalSince1970.isFinite else { throw RenewalFailure.invalidEvidence }
        // Repeated UUIDs with conflicting metadata are not silently accepted.
        guard Set(candidates.map(\.id)).count == candidates.count else {
            throw RenewalFailure.invalidEvidence
        }
        var expiry = certificateExpiry
        for component in requiredComponents {
            let eligible = candidates.filter {
                !$0.id.isEmpty && $0.componentID == component && $0.teamID == teamID &&
                $0.certificateID == certificateID && $0.validatedForInstalledBinary &&
                $0.notBefore.timeIntervalSince1970.isFinite &&
                $0.expiry.timeIntervalSince1970.isFinite &&
                $0.notBefore <= now && $0.expiry > now && $0.expiry > $0.notBefore
            }
            guard let best = eligible.map(\.expiry).max() else {
                throw RenewalFailure.invalidEvidence
            }
            expiry = min(expiry, best)
        }
        return expiry
    }

    public static func requireMainProfile<T>(in profiles: [String: T], bundleID: String) throws -> T {
        guard let profile = profiles[bundleID] else { throw RenewalFailure.invalidEvidence }
        return profile
    }
}
