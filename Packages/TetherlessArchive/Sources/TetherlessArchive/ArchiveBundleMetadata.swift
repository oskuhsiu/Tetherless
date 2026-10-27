// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// Bound Info.plist parsing and filesystem-derived identifiers before handing
/// a bundle to the signing library. This is not entitlement/signature approval.
enum ArchiveBundleMetadata {
    static func validateTree(at app: URL) throws {
        try validate(info: app.appendingPathComponent("Info.plist"), executableRequired: true)
        guard let files = FileManager.default.enumerator(at: app, includingPropertiesForKeys: [.isRegularFileKey]) else {
            throw SafeArchiveError.invalidApp
        }
        var count = 0
        for case let path as URL in files {
            count += 1
            guard count <= 60_000 else { throw SafeArchiveError.limitExceeded }
            try Task.checkCancellation()
            guard path.lastPathComponent == "Info.plist", path.deletingLastPathComponent() != app else { continue }
            let kind = path.deletingLastPathComponent().pathExtension
            if ["app", "appex", "framework", "bundle"].contains(kind) {
                try validate(info: path, executableRequired: kind != "bundle")
            }
        }
    }
    private static func validate(info: URL, executableRequired: Bool) throws {
        let attrs = try FileManager.default.attributesOfItem(atPath: info.path)
        guard attrs[.type] as? FileAttributeType == .typeRegular,
              let size = attrs[.size] as? NSNumber, size.uint64Value <= 1_048_576 else { throw SafeArchiveError.invalidApp }
        let bytes = try Data(contentsOf: info)
        if !bytes.starts(with: Data("bplist00".utf8)) {
            guard let text = String(data: bytes, encoding: .utf8), !text.contains("<!ENTITY"),
                  text.range(of: #"<!DOCTYPE[^>]*\["#, options: .regularExpression) == nil else { throw SafeArchiveError.invalidApp }
        }
        guard let dict = try PropertyListSerialization.propertyList(from: bytes, format: nil) as? [String: Any] else {
            throw SafeArchiveError.invalidApp
        }
        var nodes = 0
        try bound(dict, depth: 0, nodes: &nodes)
        if let identifier = dict["CFBundleIdentifier"] {
            guard let value = identifier as? String, !value.isEmpty, value.utf8.count <= 255,
                  !value.split(separator: ".", omittingEmptySubsequences: false).contains(where: { $0.isEmpty }),
                  value.utf8.allSatisfy({ (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) || $0 == 45 || $0 == 46 }) else {
                throw SafeArchiveError.invalidApp
            }
        } else if executableRequired { throw SafeArchiveError.invalidApp }
        guard let rawExecutable = dict["CFBundleExecutable"] else {
            if executableRequired { throw SafeArchiveError.invalidApp }
            return
        }
        guard let executable = rawExecutable as? String else { throw SafeArchiveError.invalidApp }
        var paths = ArchivePaths()
        guard try paths.accept(executable, directory: false) == executable, !executable.contains("/") else { throw SafeArchiveError.invalidApp }
        let file = info.deletingLastPathComponent().appendingPathComponent(executable)
        guard try file.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true else { throw SafeArchiveError.invalidApp }
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: file.path)
    }
    private static func bound(_ value: Any, depth: Int, nodes: inout Int) throws {
        nodes += 1
        guard nodes <= 20_000, depth <= 32 else { throw SafeArchiveError.invalidApp }
        if let values = value as? [String: Any] {
            for item in values.values { try bound(item, depth: depth+1, nodes: &nodes) }
        } else if let values = value as? [Any] {
            for item in values { try bound(item, depth: depth+1, nodes: &nodes) }
        }
    }
}
