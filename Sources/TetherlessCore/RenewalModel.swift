// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

public enum RenewalFailure: String, Error, Codable, Sendable {
    case busy, invalidInput, invalidEvidence, corruptJournal, unsupportedJournal
    case storageUnavailable, lockUnavailable, needsAuthentication, needsPairing
    case needsForeground, unavailable, cancelled, noExtension, identityChanged, budgetExhausted
}

/// Public metadata only. Never put account names, UDIDs, passwords, tokens, keys,
/// raw profiles or pairing records into this model or a renewal journal.
public struct AppLease: Codable, Equatable, Sendable {
    public let bundleID: String
    public let isManager: Bool
    public let effectiveExpiry: Date
    public let identityDigest: String?

    public init(bundleID: String, isManager: Bool, effectiveExpiry: Date, identityDigest: String? = nil) throws {
        guard !bundleID.isEmpty, bundleID.utf8.count <= 255,
              bundleID.unicodeScalars.allSatisfy({
                  CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_").contains($0)
              }), effectiveExpiry.timeIntervalSince1970.isFinite else {
            throw RenewalFailure.invalidInput
        }
        if let identityDigest {
            guard identityDigest.count == 64,
                  identityDigest.allSatisfy({ "0123456789abcdef".contains($0) }) else {
                throw RenewalFailure.invalidInput
            }
        }
        self.identityDigest = identityDigest
        self.bundleID = bundleID
        self.isManager = isManager
        self.effectiveExpiry = effectiveExpiry
    }
}

public enum EvidenceLevel: String, Codable, Sendable {
    case applied, deviceReadback
}

public struct RenewalEvidence: Codable, Equatable, Sendable {
    public let bundleID: String
    public let previousExpiry: Date
    public let newExpiry: Date
    public let level: EvidenceLevel
    /// False for a Team/certificate change. Such changes require a distinct
    /// foreground signing transaction, not a silent profile-only refresh.
    public let sameSigningIdentity: Bool

    public init(bundleID: String, previousExpiry: Date, newExpiry: Date,
                level: EvidenceLevel, sameSigningIdentity: Bool) {
        self.bundleID = bundleID
        self.previousExpiry = previousExpiry
        self.newExpiry = newExpiry
        self.level = level
        self.sameSigningIdentity = sameSigningIdentity
    }

    public func validate(for app: AppLease, now: Date) throws {
        guard bundleID == app.bundleID, previousExpiry == app.effectiveExpiry,
              previousExpiry.timeIntervalSince1970.isFinite,
              newExpiry.timeIntervalSince1970.isFinite,
              now.timeIntervalSince1970.isFinite else {
            throw RenewalFailure.invalidEvidence
        }
        guard sameSigningIdentity else { throw RenewalFailure.identityChanged }
        guard newExpiry > previousExpiry, newExpiry > now else {
            throw RenewalFailure.noExtension
        }
    }
}

public enum AttemptOutcome: String, Codable, Sendable {
    case verified, appliedUnverified, checkedNotExtended, failed, interrupted
}

public struct PendingRenewal: Codable, Equatable, Sendable {
    public let id: UUID
    public let app: AppLease
    public let startedAt: Date
}

public struct RenewalRecord: Codable, Equatable, Sendable {
    public var lastAttemptAt: Date?
    public var lastAppliedAt: Date?
    public var lastVerifiedAt: Date?
    public var lastKnownExpiry: Date?
    public var retryAfter: Date?
    public var consecutiveFailures: Int = 0
    public var outcome: AttemptOutcome?
    public var failure: RenewalFailure?
    public var requiresInteraction: Bool = false
    public var pending: PendingRenewal?
    public init() {}
}

public struct RenewalState: Codable, Equatable, Sendable {
    public var schemaVersion: Int = 1
    public var records: [String: RenewalRecord] = [:]
    public var gate: RenewalGate?
    public init() {}

    public func validate() throws {
        guard schemaVersion == 1 else { throw RenewalFailure.unsupportedJournal }
        try gate?.validate()
        guard records.count <= 256 else { throw RenewalFailure.corruptJournal }
        for (id, record) in records {
            guard (0...1000).contains(record.consecutiveFailures) else { throw RenewalFailure.corruptJournal }
            let dates = [record.lastAttemptAt, record.lastAppliedAt, record.lastVerifiedAt,
                         record.lastKnownExpiry, record.retryAfter, record.pending?.startedAt]
            guard dates.compactMap({ $0 }).allSatisfy({ $0.timeIntervalSince1970.isFinite }) else {
                throw RenewalFailure.corruptJournal
            }
            do {
                _ = try AppLease(bundleID: id, isManager: false,
                                 effectiveExpiry: record.lastKnownExpiry ?? Date(timeIntervalSince1970: 0))
                if let pending = record.pending {
                    guard pending.app.bundleID == id else { throw RenewalFailure.corruptJournal }
                    _ = try AppLease(bundleID: pending.app.bundleID, isManager: pending.app.isManager,
                                     effectiveExpiry: pending.app.effectiveExpiry, identityDigest: pending.app.identityDigest)
                }
            } catch { throw RenewalFailure.corruptJournal }
        }
    }
}

public enum RenewalTrigger: String, Codable, Sendable {
    case shortcut, background, manual, acceleratedTest
}

public struct RenewalRunResult: Sendable {
    public var observed: [AppLease] = []
    /// nil means discovery never completed; do not interpret it as no apps.
    public var managedIDs: [String]?
    public var globalFailure: RenewalFailure?
    public var attempted: [String] = []
    public var verified: [String] = []
    public var appliedUnverified: [String] = []
    public var deferred: [String] = []
    public var failures: [String: RenewalFailure] = [:]
    public init() {}
}

/// A live snapshot can report an invalid target without inventing an expiry for
/// it or preventing unrelated targets (especially the manager) from renewing.
public struct RenewalSnapshot: Sendable {
    public let apps: [AppLease]
    public let failures: [String: RenewalFailure]
    public init(apps: [AppLease], failures: [String: RenewalFailure] = [:]) {
        self.apps = apps
        self.failures = failures
    }
    public func validate() throws {
        guard apps.count + failures.count <= 256,
              Set(apps.map(\.bundleID)).count == apps.count,
              Set(apps.map(\.bundleID)).isDisjoint(with: failures.keys),
              failures.keys.allSatisfy(ManagedBundleIdentifier.isSafe),
              failures.values.allSatisfy({ !$0.isRunWide && !$0.isStorageFailure && $0 != .cancelled }) else {
            throw RenewalFailure.invalidEvidence
        }
        for app in apps {
            _ = try AppLease(bundleID: app.bundleID, isManager: app.isManager,
                             effectiveExpiry: app.effectiveExpiry, identityDigest: app.identityDigest)
        }
    }
}

/// Preflight failure has no app to attach to. Retain a separate run-wide gate
/// so an expired session cannot cause another login attempt on every trigger.
/// Optional in schema 1 for backwards-compatible decoding of existing journals.
public struct RenewalGate: Codable, Equatable, Sendable {
    public let failure: RenewalFailure
    public let retryAfter: Date?
    public let consecutiveFailures: Int
    public init(failure: RenewalFailure, retryAfter: Date?, consecutiveFailures: Int) {
        self.failure = failure
        self.retryAfter = retryAfter
        self.consecutiveFailures = consecutiveFailures
    }
    public var requiresInteraction: Bool { failure.requiresInteraction }
    public func validate() throws {
        guard (1...1000).contains(consecutiveFailures),
              retryAfter.map({ $0.timeIntervalSince1970.isFinite }) ?? true else {
            throw RenewalFailure.corruptJournal
        }
    }
}

public extension RenewalFailure {
    var isStorageFailure: Bool {
        [.storageUnavailable, .corruptJournal, .unsupportedJournal, .lockUnavailable].contains(self)
    }
    var requiresInteraction: Bool {
        [.needsAuthentication, .needsPairing, .needsForeground, .identityChanged].contains(self)
    }
    /// An app's signing identity can differ from the manager's. A change in one
    /// app must not block every other app; authentication/pairing really is shared.
    var isRunWide: Bool { [.needsAuthentication, .needsPairing, .budgetExhausted].contains(self) }
}
