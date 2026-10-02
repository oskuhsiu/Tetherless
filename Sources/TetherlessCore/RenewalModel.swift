// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

public enum RenewalFailure: String, Error, Codable, Sendable {
    case busy, invalidInput, invalidEvidence, corruptJournal, unsupportedJournal
    case storageUnavailable, lockUnavailable, needsAuthentication, needsPairing
    case needsForeground, unavailable, cancelled, noExtension, identityChanged
}

/// Public metadata only. Never put account names, UDIDs, passwords, tokens, keys,
/// raw profiles or pairing records into this model or a renewal journal.
public struct AppLease: Codable, Equatable, Sendable {
    public let bundleID: String
    public let isManager: Bool
    public let effectiveExpiry: Date

    public init(bundleID: String, isManager: Bool, effectiveExpiry: Date) throws {
        guard !bundleID.isEmpty, bundleID.utf8.count <= 255,
              bundleID.unicodeScalars.allSatisfy({
                  CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_").contains($0)
              }), effectiveExpiry.timeIntervalSince1970.isFinite else {
            throw RenewalFailure.invalidInput
        }
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
    public init() {}

    public func validate() throws {
        guard schemaVersion == 1 else { throw RenewalFailure.unsupportedJournal }
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
                                     effectiveExpiry: pending.app.effectiveExpiry)
                }
            } catch { throw RenewalFailure.corruptJournal }
        }
    }
}

public enum RenewalTrigger: String, Codable, Sendable {
    case shortcut, background, manual, acceleratedTest
}

public struct RenewalRunResult: Sendable {
    public var attempted: [String] = []
    public var verified: [String] = []
    public var appliedUnverified: [String] = []
    public var deferred: [String] = []
    public var failures: [String: RenewalFailure] = [:]
    public init() {}
}
