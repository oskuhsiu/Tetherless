// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// Syntactic/type validation only: a well-formed pairing record is not proof that
/// Apple/device services accept it. No real keys or device identifiers in tests.
public struct PairingRecord: Sendable {
    public enum Kind: String, Sendable { case lockdown, remote }
    public static let maximumBytes = 1_048_576
    public let kind: Kind
    public let xml: Data
    public var content: String { String(decoding: xml, as: UTF8.self) }

    public init(data: Data, expected: Kind? = nil) throws {
        guard !data.isEmpty, data.count <= Self.maximumBytes else { throw PrivateFileError.tooLarge }
        // Allow Apple's usual external plist DTD, not custom entity declarations
        // or internal subsets. Binary plists are accepted and normalized to XML.
        if !data.starts(with: Data("bplist00".utf8)) {
            guard let text = String(data: data, encoding: .utf8) else { throw PrivateFileError.invalidContent }
            if text.contains("<!ENTITY") || text.range(of: #"<!DOCTYPE[^>]*\["#, options: .regularExpression) != nil {
                throw PrivateFileError.invalidContent
            }
        }
        guard let value = try? PropertyListSerialization.propertyList(from: data, options: [], format: nil),
              let dictionary = value as? [String: Any] else { throw PrivateFileError.invalidContent }
        var nodes = 0
        try Self.bound(value, depth: 0, nodes: &nodes)
        let remote = dictionary["private_key"] != nil || dictionary["public_key"] != nil || dictionary["identifier"] != nil
        let lockdown = dictionary["HostPrivateKey"] != nil || dictionary["RootPrivateKey"] != nil || dictionary["UDID"] != nil
        guard remote != lockdown else { throw PrivateFileError.invalidContent }
        kind = remote ? .remote : .lockdown
        guard expected == nil || expected == kind else { throw PrivateFileError.invalidContent }
        let strings: [String]
        let blobs: [String]
        switch kind {
        case .remote:
            strings = ["identifier"]
            blobs = ["private_key", "public_key"]
        case .lockdown:
            strings = ["WiFiMACAddress", "SystemBUID", "HostID", "UDID"]
            blobs = ["RootPrivateKey", "HostPrivateKey", "RootCertificate", "EscrowBag", "HostCertificate", "DeviceCertificate"]
        }
        for key in strings {
            guard let string = dictionary[key] as? String,
                  !string.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  string.utf8.count <= 4096, !string.unicodeScalars.contains(where: { $0.value < 32 }) else {
                throw PrivateFileError.invalidContent
            }
        }
        for key in blobs {
            guard let bytes = dictionary[key] as? Data, !bytes.isEmpty, bytes.count <= 262_144 else {
                throw PrivateFileError.invalidContent
            }
        }
        xml = try PropertyListSerialization.data(fromPropertyList: dictionary, format: .xml, options: 0)
        guard xml.count <= Self.maximumBytes else { throw PrivateFileError.tooLarge }
    }
    private static func bound(_ value: Any, depth: Int, nodes: inout Int) throws {
        nodes += 1
        guard depth <= 16, nodes <= 4096 else { throw PrivateFileError.invalidContent }
        if let dictionary = value as? [String: Any] {
            guard dictionary.count <= 256, dictionary.keys.allSatisfy({ $0.utf8.count <= 256 }) else { throw PrivateFileError.invalidContent }
            for item in dictionary.values { try bound(item, depth: depth + 1, nodes: &nodes) }
        } else if let array = value as? [Any] {
            guard array.count <= 1024 else { throw PrivateFileError.invalidContent }
            for item in array { try bound(item, depth: depth + 1, nodes: &nodes) }
        }
    }
}
