// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
#if canImport(CoreData)
import CoreData
#endif

/// Only fixed messages leave the catalog boundary. A remote catalog must not
/// cause a process trap or choose an arbitrary winner for conflicting payloads.
public enum CatalogImportError: Int, Error, LocalizedError, CustomNSError, Sendable {
    case duplicateApp = 1
    case duplicateVersion
    case unresolvedConstraint
    case invalidVersionRecord
    case tooManyVersions

    public static var errorDomain: String { "org.tetherless.CatalogImport" }
    public var errorCode: Int { rawValue }
    public var errorDescription: String? {
        switch self {
        case .duplicateApp: return "The source contains duplicate app entries."
        case .duplicateVersion: return "The source contains conflicting version entries, including across release channels."
        case .unresolvedConstraint: return "The source could not be merged without an ambiguous database conflict."
        case .invalidVersionRecord: return "The source contains an incomplete version identity."
        case .tooManyVersions: return "The source contains too many versions."
        }
    }
    public var recoverySuggestion: String? {
        "The previous catalog is kept. Correct or remove this source and try again. Installed apps are not removed."
    }
    public var errorUserInfo: [String: Any] {
        [NSLocalizedDescriptionKey: errorDescription ?? "Invalid source catalog.",
         NSLocalizedRecoverySuggestionErrorKey: recoverySuggestion ?? ""]
    }
}

/// Matches the database's composite key, NOT the display channel or a delimited
/// version string. nil and an empty build both map to the stored empty build.
public struct CatalogVersionIdentity: Hashable, Sendable {
    public let source: String?
    public let app: String
    public let version: String
    public let build: String
    public init(source: String?, app: String, version: String, build: String?) {
        self.source = source; self.app = app; self.version = version
        self.build = build ?? ""
    }
}

public enum CatalogImportSafety {
    public static func requireUniqueVersions<S: Sequence>(_ identities: S) throws
        where S.Element == CatalogVersionIdentity {
        var seen = Set<CatalogVersionIdentity>()
        for identity in identities {
            guard seen.count < 50_000 else { throw CatalogImportError.tooManyVersions }
            guard !identity.app.isEmpty, !identity.version.isEmpty else {
                throw CatalogImportError.invalidVersionRecord
            }
            guard seen.insert(identity).inserted else { throw CatalogImportError.duplicateVersion }
        }
    }

    #if canImport(CoreData)
    /// Call on the context's queue after decoding, before saving to its parent.
    /// Inspect the entire inserted graph: app.versions covers only one channel.
    public static func validateNewVersions(in context: NSManagedObjectContext) throws {
        let versions = context.insertedObjects.lazy.filter {
            !$0.isDeleted && $0.entity.name == "AppVersion"
        }
        let identities = try versions.map { object -> CatalogVersionIdentity in
            guard let app = object.value(forKey: "appBundleID") as? String,
                  let version = object.value(forKey: "version") as? String,
                  let build = object.value(forKey: "buildVersion") as? String else {
                throw CatalogImportError.invalidVersionRecord
            }
            return CatalogVersionIdentity(source: object.value(forKey: "sourceID") as? String,
                                          app: app, version: version, build: build)
        }
        try requireUniqueVersions(identities)
    }
    #endif
}
