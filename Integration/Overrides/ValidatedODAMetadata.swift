// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// Adapter for the existing SideSign public models. Only these validated
/// results reach the native metadata fetch routes; decoding failures propagate.
enum ValidatedODAMetadata {
    enum Selection {
        case package(ODAInfo)
        case reference(URL)
    }
    static func package(_ data: Data) throws -> ODAInfo {
        convert(try ODAMetadata.decodePackage(data))
    }
    static func servers(_ data: Data, source: URL) throws -> AnisetteServerData {
        let document = try ODAMetadata.decode(data)
        let oda: ODAValue?
        switch document.entry {
        case .package(let p): oda = .direct(convert(p))
        case .reference(let raw): oda = .path(try ODAMetadata.resolveURL(raw, relativeTo: source).absoluteString)
        case nil: oda = nil
        }
        return AnisetteServerData(servers: document.servers.map {
            AnisetteServerItem(name: $0.name, address: $0.address, isHidden: $0.isHidden)
        }, oda: oda)
    }
    static func select(_ data: Data, source: URL, fallback: URL?) throws -> Selection {
        // Deliberately not try?: malformed metadata cannot turn into "no oda".
        let document = try ODAMetadata.decode(data)
        switch document.entry {
        case .package(let p): return .package(convert(p))
        case .reference(let raw): return .reference(try ODAMetadata.resolveURL(raw, relativeTo: source))
        case nil:
            guard let fallback else { throw AnisetteError.missingODAEntry }
            return .reference(try ODAMetadata.resolveURL(fallback.absoluteString))
        }
    }
    private static func convert(_ p: ODAMetadata.Package) -> ODAInfo {
        ODAInfo(url: p.url, base64Payload: p.base64Payload, sha256: p.sha256)
    }
}
