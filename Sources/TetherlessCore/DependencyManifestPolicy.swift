// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

public enum DependencyManifestFailure: String, Error, LocalizedError, Sendable {
    case invalidManifest, remoteDependenciesUnsupported
    public var errorDescription: String? {
        switch self {
        case .invalidManifest: return "The IPA dependency manifest is invalid or exceeds the supported limits."
        case .remoteDependenciesUnsupported: return "This IPA requests additional remote files. Import a self-contained IPA; automatic dependency injection is not supported."
        }
    }
}

/// Refuse post-validation downloads into app resources. Otherwise a manifest
/// could replace Info.plist/executables or escape the bundle after ZIP checks.
/// Empty or absent dependency lists are allowed; nothing is fetched or removed.
public enum DependencyManifestPolicy {
    public static func validate(_ data: Data) throws {
        guard !data.isEmpty, data.count <= 262_144 else { throw DependencyManifestFailure.invalidManifest }
        if !data.starts(with: Data("bplist00".utf8)) {
            guard let text = String(data: data, encoding: .utf8), !text.contains("<!ENTITY"),
                  text.range(of: #"<!DOCTYPE[^>]*\["#, options: .regularExpression) == nil else {
                throw DependencyManifestFailure.invalidManifest
            }
        }
        guard let object = try? PropertyListSerialization.propertyList(from: data, format: nil),
              let dict = object as? [String: Any] else { throw DependencyManifestFailure.invalidManifest }
        var nodes = 0
        try bound(object, depth: 0, nodes: &nodes)
        guard let dependencies = dict["ALTDependencies"] else { return }
        guard let entries = dependencies as? [Any] else { throw DependencyManifestFailure.invalidManifest }
        guard entries.isEmpty else { throw DependencyManifestFailure.remoteDependenciesUnsupported }
    }
    private static func bound(_ object: Any, depth: Int, nodes: inout Int) throws {
        nodes += 1
        guard depth <= 16, nodes <= 4096 else { throw DependencyManifestFailure.invalidManifest }
        if let dict = object as? [String: Any] {
            for value in dict.values { try bound(value, depth: depth+1, nodes: &nodes) }
        } else if let values = object as? [Any] {
            for value in values { try bound(value, depth: depth+1, nodes: &nodes) }
        }
    }
}
