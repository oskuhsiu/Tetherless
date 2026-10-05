#if canImport(Darwin)
import Foundation
import Darwin
import XCTest
@testable import TetherlessCore

@MainActor final class PairingEndpointResolverTests: XCTestCase {
    private final class Browser: NetServiceBrowser, @unchecked Sendable {
        let searched = AsyncStream<Void>.makeStream()
        let stopped = AsyncStream<Void>.makeStream()
        override func searchForServices(ofType type: String, inDomain domain: String) { searched.continuation.yield(()) }
        override func stop() { stopped.continuation.yield(()) }
    }
    private final class Service: NetService, @unchecked Sendable {
        let resolved = AsyncStream<Void>.makeStream()
        let stopped = AsyncStream<Void>.makeStream()
        var payload: [Data] = []
        override var addresses: [Data]? { payload }
        override func resolve(withTimeout timeout: TimeInterval) { resolved.continuation.yield(()) }
        override func stop() { stopped.continuation.yield(()) }
    }
    private func signal(_ stream: AsyncStream<Void>) async {
        var iterator = stream.makeAsyncIterator(); _ = await iterator.next()
    }
    private func address(_ text: String, port: UInt16 = 49152) -> Data {
        var value = sockaddr_in()
        value.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        value.sin_family = sa_family_t(AF_INET); value.sin_port = port.bigEndian
        _ = text.withCString { inet_pton(AF_INET, $0, &value.sin_addr) }
        return withUnsafeBytes(of: &value) { Data($0) }
    }
    private func peer() throws -> PairingPeerAddress { try PairingNumericEndpoint(sockaddrBytes: address("127.0.0.1")).peer }
    private func service(_ name: String = "synthetic") -> Service {
        Service(domain: "local.", type: "_remotepairing._tcp.", name: name, port: 49152)
    }

    func testRoutingCandidateFiltersWrongPeerAndWaitsForBothStops() async throws {
        for browserFirst in [true, false] {
            let browser = Browser(), service = service()
            let subject = PairingEndpointResolver(browser: browser)
            var returned = false
            let operation = Task { @MainActor in
                let value = try await subject.resolve(peer: peer(), timeoutMilliseconds: 1000)
                returned = true; return value
            }
            await signal(browser.searched.stream)
            subject.netServiceBrowser(browser, didFind: service, moreComing: false)
            await signal(service.resolved.stream)
            service.payload = [address("127.0.0.2"), address("127.0.0.1", port: 49153), address("127.0.0.1")]
            subject.netServiceDidResolveAddress(service)
            await signal(service.stopped.stream); await signal(browser.stopped.stream)
            XCTAssertFalse(returned)
            if browserFirst { subject.netServiceBrowserDidStopSearch(browser) }
            else { subject.netServiceDidStop(service) }
            XCTAssertFalse(returned)
            if browserFirst { subject.netServiceDidStop(service) }
            else { subject.netServiceBrowserDidStopSearch(browser) }
            let values = try await operation.value
            XCTAssertEqual(values.count, 1)
            XCTAssertEqual(try values[0].nativeAddress(), "127.0.0.1:49152")
            XCTAssertTrue(returned)
        }
    }

    func testCancellationDiscardsLateResolutionAndStillWaitsForAcknowledgements() async throws {
        let browser = Browser(), service = service()
        let resolver = PairingEndpointResolver(browser: browser)
        var returned = false
        let operation = Task { @MainActor in
            defer { returned = true }
            return try await resolver.resolve(peer: peer(), timeoutMilliseconds: 1000)
        }
        await signal(browser.searched.stream)
        resolver.netServiceBrowser(browser, didFind: service, moreComing: false)
        await signal(service.resolved.stream)
        resolver.cancel()
        await signal(browser.stopped.stream); await signal(service.stopped.stream)
        service.payload = [address("127.0.0.1")]
        resolver.netServiceDidResolveAddress(service)
        resolver.netServiceBrowserDidStopSearch(browser)
        XCTAssertFalse(returned)
        resolver.netServiceDidStop(service)
        do { _ = try await operation.value; XCTFail("cancel returned endpoints") }
        catch { XCTAssertEqual(error as? PairingDiscoveryError, .cancelled) }
    }

    func testServiceBudgetStopsEveryAdmittedResolutionBeforeReturning() async throws {
        let browser = Browser()
        let resolver = PairingEndpointResolver(browser: browser)
        let operation = Task { @MainActor in try await resolver.resolve(peer: peer(), timeoutMilliseconds: 1000) }
        await signal(browser.searched.stream)
        var admitted: [Service] = []
        for index in 0..<8 {
            let value = service("synthetic-\(index)"); admitted.append(value)
            resolver.netServiceBrowser(browser, didFind: value, moreComing: true)
            await signal(value.resolved.stream)
        }
        resolver.netServiceBrowser(browser, didFind: service("ninth"), moreComing: false)
        await signal(browser.stopped.stream)
        for value in admitted { await signal(value.stopped.stream) }
        resolver.netServiceBrowserDidStopSearch(browser)
        for value in admitted { resolver.netServiceDidStop(value) }
        do { _ = try await operation.value; XCTFail("service budget was bypassed") }
        catch { XCTAssertEqual(error as? PairingDiscoveryError, .exhausted) }
    }

    func testFailedSearchRequestsStopAndWaitsForAcknowledgement() async throws {
        let browser = Browser()
        let subject = PairingEndpointResolver(browser: browser)
        var returned = false
        let operation = Task { @MainActor in
            defer { returned = true }
            return try await subject.resolve(peer: peer(), timeoutMilliseconds: 1000)
        }
        await signal(browser.searched.stream)
        subject.netServiceBrowser(browser, didNotSearch: [:])
        await signal(browser.stopped.stream)
        XCTAssertFalse(returned)
        subject.netServiceBrowserDidStopSearch(browser)
        do { _ = try await operation.value; XCTFail("failed search returned endpoints") }
        catch { XCTAssertEqual(error as? PairingDiscoveryError, .unavailable) }
    }
}
#endif
