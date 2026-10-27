// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

public enum PairingEndpointError: Error, Sendable { case invalidAddress, unavailable }

/// A routing hint from the accepted TCP peer. It is never identity proof.
public struct PairingPeerAddress: Equatable, Sendable, CustomDebugStringConvertible {
    fileprivate let octets: [UInt8]
    fileprivate let scope: UInt32
    public var debugDescription: String { "PairingPeerAddress(<private>)" }

    public static func connectedPeer(descriptor: Int32) throws -> Self {
        var storage = sockaddr_storage()
        var size = socklen_t(MemoryLayout<sockaddr_storage>.size)
        let result = withUnsafeMutablePointer(to: &storage) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { getpeername(descriptor, $0, &size) }
        }
        guard result == 0, Int(size) <= MemoryLayout<sockaddr_storage>.size else { throw PairingEndpointError.unavailable }
        let bytes = withUnsafeBytes(of: &storage) { Data($0.prefix(Int(size))) }
        return try PairingNumericEndpoint(sockaddrBytes: bytes).peer
    }
}

/// Numeric-only address/port for the existing staged validator. Bonjour is an
/// untrusted routing hint; authenticated container validation remains required.
public struct PairingNumericEndpoint: Equatable, Sendable, CustomDebugStringConvertible {
    public let peer: PairingPeerAddress
    public let port: UInt16
    public var debugDescription: String { "PairingNumericEndpoint(<private>)" }

    public init(sockaddrBytes: Data) throws {
        guard !sockaddrBytes.isEmpty, sockaddrBytes.count <= MemoryLayout<sockaddr_storage>.size else {
            throw PairingEndpointError.invalidAddress
        }
        var storage = sockaddr_storage()
        _ = withUnsafeMutableBytes(of: &storage) { sockaddrBytes.copyBytes(to: $0) }
        let family = Int32(storage.ss_family)
        let bytes: [UInt8]
        let scope: UInt32
        if family == AF_INET {
            guard sockaddrBytes.count == MemoryLayout<sockaddr_in>.size else { throw PairingEndpointError.invalidAddress }
            var address = withUnsafePointer(to: &storage) { $0.withMemoryRebound(to: sockaddr_in.self, capacity: 1) { $0.pointee } }
            bytes = withUnsafeBytes(of: &address.sin_addr) { Array($0) }
            port = UInt16(bigEndian: address.sin_port)
            scope = 0
        } else if family == AF_INET6 {
            guard sockaddrBytes.count == MemoryLayout<sockaddr_in6>.size else { throw PairingEndpointError.invalidAddress }
            var address = withUnsafePointer(to: &storage) { $0.withMemoryRebound(to: sockaddr_in6.self, capacity: 1) { $0.pointee } }
            let full = withUnsafeBytes(of: &address.sin6_addr) { Array($0) }
            port = UInt16(bigEndian: address.sin6_port)
            if full.prefix(10).allSatisfy({ $0 == 0 }), full[10] == 255, full[11] == 255 {
                bytes = Array(full.suffix(4)); scope = 0
            } else {
                bytes = full
                scope = full[0] == 0xfe && (full[1] & 0xc0) == 0x80 ? address.sin6_scope_id : 0
            }
        } else { throw PairingEndpointError.invalidAddress }
        guard port != 0, !bytes.allSatisfy({ $0 == 0 }),
              !(bytes.count == 4 && ((224...239).contains(bytes[0]) || bytes.allSatisfy({ $0 == 255 }))),
              !(bytes.count == 16 && bytes[0] == 255) else { throw PairingEndpointError.invalidAddress }
        peer = PairingPeerAddress(octets: bytes, scope: scope)
    }

    /// Pass directly to native FFI; do not put this value in UI or diagnostics.
    public func nativeAddress() throws -> String {
        let family = peer.octets.count == 4 ? AF_INET : AF_INET6
        let capacity = Int(INET6_ADDRSTRLEN)
        var output = [CChar](repeating: 0, count: capacity)
        let converted = peer.octets.withUnsafeBytes {
            inet_ntop(family, $0.baseAddress, &output, socklen_t(capacity))
        }
        guard converted != nil else { throw PairingEndpointError.invalidAddress }
        let address = String(cString: output)
        let value: String
        if peer.octets.count == 4 { value = "\(address):\(port)" }
        else {
            let scoped = peer.scope == 0 ? address : address + "%" + String(peer.scope)
            value = "[\(scoped)]:\(port)"
        }
        guard value.utf8.count <= 128 else { throw PairingEndpointError.invalidAddress }
        return value
    }
}
