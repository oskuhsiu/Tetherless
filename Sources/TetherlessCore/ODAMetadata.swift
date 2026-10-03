// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

public enum ODAMetadataFailure: String, Error, LocalizedError, Sendable {
    case malformed, invalidSchema, duplicateKey, ambiguous, tooLarge, tooDeep
    case tooManyValues, tooManyServers, stringTooLarge, invalidURL, busy
    public var errorDescription: String? { "ODA metadata rejected: \(rawValue)." }
}

/// Public metadata only. No remote mutation, binary execution or publisher trust.
/// Preflight bounds the JSON graph BEFORE Foundation constructs its object map.
public enum ODAMetadata {
    public struct Package: Decodable, Equatable, Sendable {
        public let url: String?
        public let base64Payload: String?
        public let sha256: String
        enum CodingKeys: String, CodingKey, CaseIterable {
            case url, l, libraries, payload, data, sha256, sha, s
        }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            func one(_ keys: [CodingKeys]) throws -> (CodingKeys, String)? {
                var selected: (CodingKeys, String)?
                for key in keys {
                    if let value = try c.decodeIfPresent(String.self, forKey: key) {
                        guard selected == nil else { throw ODAMetadataFailure.ambiguous }
                        selected = (key, value)
                    }
                }
                return selected
            }
            sha256 = try AnisettePackageInput.digest(one([.sha256, .sha, .s])?.1)
            guard let (key, value) = try one([.url, .l, .libraries, .payload, .data]), !value.isEmpty else {
                throw ODAMetadataFailure.invalidSchema
            }
            let prefix = value.prefix(8).lowercased()
            if key == .url || prefix.hasPrefix("http://") || prefix.hasPrefix("https://") {
                url = try ODAMetadata.resolveURL(value).absoluteString
                base64Payload = nil
            } else {
                guard value.utf8.count <= AnisettePackageInput.maximumEncodedBytes else {
                    throw ODAMetadataFailure.tooLarge
                }
                url = nil; base64Payload = value
            }
        }
    }
    public struct Server: Decodable, Equatable, Sendable {
        public let name: String
        public let address: String
        public let isHidden: Bool
        enum CodingKeys: String, CodingKey { case name, address, url, isHidden }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            name = try c.decodeIfPresent(String.self, forKey: .name) ?? ""
            guard name.utf8.count <= 256 else { throw ODAMetadataFailure.stringTooLarge }
            let address = try c.decodeIfPresent(String.self, forKey: .address)
            let url = try c.decodeIfPresent(String.self, forKey: .url)
            guard address == nil || url == nil else { throw ODAMetadataFailure.ambiguous }
            guard let raw = address ?? url else { throw ODAMetadataFailure.invalidSchema }
            self.address = try ODAMetadata.resolveURL(raw).absoluteString
            isHidden = try c.decodeIfPresent(Bool.self, forKey: .isHidden) ?? false
        }
    }
    public enum Entry: Decodable, Equatable, Sendable {
        case reference(String), package(Package)
        public init(from decoder: Decoder) throws {
            let c = try decoder.singleValueContainer()
            if let raw = try? c.decode(String.self) {
                guard !raw.isEmpty, raw.utf8.count <= 16_384 else { throw ODAMetadataFailure.invalidURL }
                self = .reference(raw)
            } else { self = .package(try c.decode(Package.self)) }
        }
    }
    public struct Document: Decodable, Equatable, Sendable {
        public let servers: [Server]
        public let entry: Entry?
        public let isDirectPackage: Bool
        enum CodingKeys: String, CodingKey { case servers, oda, url, l, libraries, payload, data, sha256, sha, s }
        public init(from decoder: Decoder) throws {
            if var array = try? decoder.unkeyedContainer() {
                var items = [Server]()
                while !array.isAtEnd {
                    guard items.count < 128 else { throw ODAMetadataFailure.tooManyServers }
                    items.append(try array.decode(Server.self))
                }
                servers = items; entry = nil; isDirectPackage = false
                return
            }
            let c = try decoder.container(keyedBy: CodingKeys.self)
            let directKeys: [CodingKeys] = [.url, .l, .libraries, .payload, .data, .sha256, .sha, .s]
            if directKeys.contains(where: c.contains) {
                guard !c.contains(.servers), !c.contains(.oda) else { throw ODAMetadataFailure.ambiguous }
                entry = .package(try Package(from: decoder)); servers = []; isDirectPackage = true
            } else {
                guard c.contains(.servers) || c.contains(.oda) else { throw ODAMetadataFailure.invalidSchema }
                servers = try c.decodeIfPresent([Server].self, forKey: .servers) ?? []
                guard servers.count <= 128 else { throw ODAMetadataFailure.tooManyServers }
                entry = try c.decodeIfPresent(Entry.self, forKey: .oda)
                isDirectPackage = false
            }
        }
    }

    private static let decodeLock = NSLock()
    public static func decode(_ data: Data) throws -> Document {
        // Synchronous and nonwaiting: a large parse cannot queue more retained
        // Foundation graphs in this process. Transfer memory is a separate budget.
        guard decodeLock.try() else { throw ODAMetadataFailure.busy }
        defer { decodeLock.unlock() }
        try Task.checkCancellation()
        do {
            try validateStructure(data)
            let result = try JSONDecoder().decode(Document.self, from: data)
            try Task.checkCancellation()
            return result
        } catch is CancellationError { throw CancellationError() }
        catch let error as ODAMetadataFailure { throw error }
        catch let error as AnisettePackageFailure { throw error }
        catch { throw ODAMetadataFailure.invalidSchema }
    }
    public static func decodePackage(_ data: Data) throws -> Package {
        let doc = try decode(data)
        guard doc.isDirectPackage, case .package(let package) = doc.entry else {
            throw ODAMetadataFailure.invalidSchema
        }
        return package
    }
    public static func resolveURL(_ raw: String, relativeTo base: URL? = nil) throws -> URL {
        guard !raw.isEmpty, raw.utf8.count <= 16_384,
              !raw.unicodeScalars.contains(where: { $0.value <= 32 || $0.value == 127 }),
              let url = URL(string: raw, relativeTo: base)?.absoluteURL,
              let c = URLComponents(url: url, resolvingAgainstBaseURL: true),
              c.scheme?.lowercased() == "https", let host = c.host, !host.isEmpty,
              c.user == nil, c.password == nil, c.fragment == nil,
              url.absoluteString.utf8.count <= 16_384 else { throw ODAMetadataFailure.invalidURL }
        return url
    }

    // Internal test injection exercises small exact limits without huge fixtures.
    struct Limits {
        var bytes = AnisettePackageInput.maximumMetadataBytes
        var depth = 8
        var values = 4096
        var arrayItems = 256
        var keyBytes = 128
        var ordinaryStringBytes = 16_384
        var payloadStringBytes = AnisettePackageInput.maximumEncodedBytes
        var allStringBytes = AnisettePackageInput.maximumEncodedBytes + 65_536
    }
    static func validateStructure(_ data: Data, limits: Limits = Limits()) throws {
        guard !data.isEmpty, data.count <= limits.bytes else { throw ODAMetadataFailure.tooLarge }
        try data.withUnsafeBytes { raw in
            var parser = Scanner(bytes: raw.bindMemory(to: UInt8.self), limits: limits)
            try parser.value(path: [], depth: 0)
            try parser.whitespace()
            guard parser.index == parser.bytes.count else { throw ODAMetadataFailure.malformed }
        }
    }
    private struct Scanner {
        let bytes: UnsafeBufferPointer<UInt8>
        let limits: Limits
        var index = 0
        var values = 0
        var strings = 0
        var nextCancellationCheck = 0
        mutating func checkpoint() throws {
            if index >= nextCancellationCheck {
                try Task.checkCancellation()
                nextCancellationCheck = index + 16_384
            }
        }
        mutating func whitespace() throws {
            while index < bytes.count && [9, 10, 13, 32].contains(bytes[index]) {
                try checkpoint(); index += 1
            }
        }
        mutating func take(_ byte: UInt8) throws {
            try whitespace()
            guard index < bytes.count, bytes[index] == byte else { throw ODAMetadataFailure.malformed }
            index += 1
        }
        mutating func value(path: [String], depth: Int) throws {
            try checkpoint(); try whitespace()
            guard index < bytes.count else { throw ODAMetadataFailure.malformed }
            values += 1
            guard values <= limits.values else { throw ODAMetadataFailure.tooManyValues }
            switch bytes[index] {
            case 123:
                guard depth < limits.depth else { throw ODAMetadataFailure.tooDeep }
                index += 1; try whitespace()
                if index < bytes.count && bytes[index] == 125 { index += 1; return }
                var keys = Set<String>()
                while true {
                    try whitespace()
                    let range = try string(maximum: limits.keyBytes)
                    let key: String
                    do { key = try JSONDecoder().decode(String.self, from: Data(bytes[range])) }
                    catch { throw ODAMetadataFailure.malformed }
                    guard keys.insert(key).inserted else { throw ODAMetadataFailure.duplicateKey }
                    try take(58); try value(path: path + [key], depth: depth + 1); try whitespace()
                    guard index < bytes.count else { throw ODAMetadataFailure.malformed }
                    if bytes[index] == 125 { index += 1; return }
                    try take(44)
                }
            case 91:
                guard depth < limits.depth else { throw ODAMetadataFailure.tooDeep }
                index += 1; try whitespace()
                if index < bytes.count && bytes[index] == 93 { index += 1; return }
                var count = 0
                while true {
                    count += 1
                    guard count <= limits.arrayItems else { throw ODAMetadataFailure.tooManyValues }
                    try value(path: path + ["[]"], depth: depth + 1); try whitespace()
                    guard index < bytes.count else { throw ODAMetadataFailure.malformed }
                    if bytes[index] == 93 { index += 1; return }
                    try take(44)
                }
            case 34:
                // Only direct package payload fields, not arbitrary unknown
                // strings or nested lookalikes, may use the archive-sized budget.
                let key = path.last ?? ""
                let payload = ["l", "libraries", "payload", "data"].contains(key) &&
                    (path.count == 1 || (path.count == 2 && path[0] == "oda"))
                _ = try string(maximum: payload ? limits.payloadStringBytes : limits.ordinaryStringBytes)
            case 116: try literal([116, 114, 117, 101])
            case 102: try literal([102, 97, 108, 115, 101])
            case 110: try literal([110, 117, 108, 108])
            case 45, 48...57: try number()
            default: throw ODAMetadataFailure.malformed
            }
        }
        mutating func string(maximum: Int) throws -> Range<Int> {
            guard index < bytes.count, bytes[index] == 34 else { throw ODAMetadataFailure.malformed }
            let start = index; index += 1
            while index < bytes.count {
                try checkpoint()
                let count = index - start - 1
                guard count <= maximum, strings <= limits.allStringBytes - count else { throw ODAMetadataFailure.stringTooLarge }
                let byte = bytes[index]; index += 1
                if byte == 34 { strings += count; return start..<index }
                guard byte >= 32 else { throw ODAMetadataFailure.malformed }
                if byte == 92 {
                    guard index < bytes.count else { throw ODAMetadataFailure.malformed }
                    let escaped = bytes[index]; index += 1
                    if escaped == 117 {
                        let unit = try hexUnit()
                        if (0xD800...0xDBFF).contains(unit) {
                            guard index + 2 <= bytes.count, bytes[index] == 92, bytes[index + 1] == 117 else {
                                throw ODAMetadataFailure.malformed
                            }
                            index += 2
                            guard (0xDC00...0xDFFF).contains(try hexUnit()) else { throw ODAMetadataFailure.malformed }
                        } else if (0xDC00...0xDFFF).contains(unit) { throw ODAMetadataFailure.malformed }
                    } else if ![34, 47, 92, 98, 102, 110, 114, 116].contains(escaped) {
                        throw ODAMetadataFailure.malformed
                    }
                } else if byte >= 128 { try utf8Continuation(after: byte) }
            }
            throw ODAMetadataFailure.malformed
        }
        mutating func hexUnit() throws -> Int {
            var value = 0
            for _ in 0..<4 {
                guard index < bytes.count else { throw ODAMetadataFailure.malformed }
                let byte = bytes[index]; index += 1
                switch byte {
                case 48...57: value = value * 16 + Int(byte - 48)
                case 65...70: value = value * 16 + Int(byte - 55)
                case 97...102: value = value * 16 + Int(byte - 87)
                default: throw ODAMetadataFailure.malformed
                }
            }
            return value
        }
        mutating func utf8Continuation(after first: UInt8) throws {
            let count: Int
            let second: ClosedRange<UInt8>
            switch first {
            case 0xC2...0xDF: count = 1; second = 0x80...0xBF
            case 0xE0: count = 2; second = 0xA0...0xBF
            case 0xE1...0xEC, 0xEE...0xEF: count = 2; second = 0x80...0xBF
            case 0xED: count = 2; second = 0x80...0x9F
            case 0xF0: count = 3; second = 0x90...0xBF
            case 0xF1...0xF3: count = 3; second = 0x80...0xBF
            case 0xF4: count = 3; second = 0x80...0x8F
            default: throw ODAMetadataFailure.malformed
            }
            guard index + count <= bytes.count, second.contains(bytes[index]) else { throw ODAMetadataFailure.malformed }
            index += 1
            for _ in 1..<count {
                guard (0x80...0xBF).contains(bytes[index]) else { throw ODAMetadataFailure.malformed }
                index += 1
            }
        }
        mutating func literal(_ word: [UInt8]) throws {
            for byte in word {
                guard index < bytes.count, bytes[index] == byte else { throw ODAMetadataFailure.malformed }
                index += 1
            }
        }
        mutating func number() throws {
            let start = index
            if bytes[index] == 45 { index += 1 }
            guard index < bytes.count else { throw ODAMetadataFailure.malformed }
            if bytes[index] == 48 { index += 1 }
            else { try digits() }
            if index < bytes.count, bytes[index] == 46 { index += 1; try digits() }
            if index < bytes.count, bytes[index] == 69 || bytes[index] == 101 {
                index += 1
                if index < bytes.count, bytes[index] == 43 || bytes[index] == 45 { index += 1 }
                try digits()
            }
            guard index - start <= 64 else { throw ODAMetadataFailure.malformed }
        }
        mutating func digits() throws {
            let start = index
            while index < bytes.count, (48...57).contains(bytes[index]) {
                guard index - start < 64 else { throw ODAMetadataFailure.malformed }
                index += 1
            }
            guard index > start else { throw ODAMetadataFailure.malformed }
        }
    }
}
