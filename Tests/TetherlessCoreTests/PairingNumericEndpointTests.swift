import Foundation
import XCTest
@testable import TetherlessCore
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

final class PairingNumericEndpointTests: XCTestCase {
    private func address(_ text: String, port: UInt16 = 1234, scope: UInt32 = 0) -> Data {
        if text.contains(":") {
            var value = sockaddr_in6()
            value.sin6_family = sa_family_t(AF_INET6); value.sin6_port = port.bigEndian; value.sin6_scope_id = scope
            #if canImport(Darwin)
            value.sin6_len = UInt8(MemoryLayout<sockaddr_in6>.size)
            #endif
            _ = text.withCString { inet_pton(AF_INET6, $0, &value.sin6_addr) }
            return withUnsafeBytes(of: &value) { Data($0) }
        }
        var value = sockaddr_in()
        value.sin_family = sa_family_t(AF_INET); value.sin_port = port.bigEndian
        #if canImport(Darwin)
        value.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        #endif
        _ = text.withCString { inet_pton(AF_INET, $0, &value.sin_addr) }
        return withUnsafeBytes(of: &value) { Data($0) }
    }
    func testNumericAddressesAndMappedPeerComparison() throws {
        let v4 = try PairingNumericEndpoint(sockaddrBytes: address("127.0.0.1"))
        let mapped = try PairingNumericEndpoint(sockaddrBytes: address("::ffff:127.0.0.1", port: 4321))
        XCTAssertEqual(v4.peer, mapped.peer)
        XCTAssertEqual(try v4.nativeAddress(), "127.0.0.1:1234")
        let v6 = try PairingNumericEndpoint(sockaddrBytes: address("fe80::1", scope: 7))
        XCTAssertEqual(try v6.nativeAddress(), "[fe80::1%7]:1234")
        XCTAssertNotEqual(v6.peer, try PairingNumericEndpoint(sockaddrBytes: address("fe80::1", scope: 8)).peer)
    }
    func testMalformedUnspecifiedMulticastAndZeroPortAreRejected() {
        for bytes in [Data(), Data([1]), address("0.0.0.0"), address("::"), address("224.0.0.1"),
                      address("ff02::1"), address("127.0.0.1", port: 0), address("255.255.255.255")] {
            XCTAssertThrowsError(try PairingNumericEndpoint(sockaddrBytes: bytes))
        }
    }
}
