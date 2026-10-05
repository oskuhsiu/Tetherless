// SPDX-License-Identifier: AGPL-3.0-only
#if TETHERLESS_BOUNDED_PAIRING_HOST && TETHERLESS_STAGED_PAIRING_VALIDATION && canImport(Darwin)
import Foundation

enum PairingDiscoveryError: Error, Equatable, Sendable { case unavailable, cancelled, timedOut, exhausted, alreadyUsed }

/// Bonjour only locates bounded numeric routing candidates for the accepted
/// peer's address. It never proves identity or authorizes record promotion.
@MainActor final class PairingEndpointResolver: NSObject, @preconcurrency NetServiceBrowserDelegate, @preconcurrency NetServiceDelegate {
    private struct Resolution {
        let service: NetService
        var completed = false
        var stopping = false
        var stopped = false
    }
    private let browser: NetServiceBrowser
    private var services: [ObjectIdentifier: Resolution] = [:]
    private var peer: PairingPeerAddress?
    private var endpoints: [PairingNumericEndpoint] = []
    private var continuation: CheckedContinuation<[PairingNumericEndpoint], Error>?
    private var deadlineTask: Task<Void, Never>?
    private var final: Result<[PairingNumericEndpoint], PairingDiscoveryError>?
    private var used = false
    private var stopping = false
    private var browserStopped = true
    private var firstBatchEnded = false
    private var resolutionTimeout: TimeInterval = 1

    init(browser: NetServiceBrowser = NetServiceBrowser()) {
        self.browser = browser
        super.init()
        browser.remove(from: .main, forMode: .default)
    }

    func resolve(peer: PairingPeerAddress, timeoutMilliseconds: UInt32) async throws -> [PairingNumericEndpoint] {
        guard !used else { throw PairingDiscoveryError.alreadyUsed }
        guard !stopping, !Task.isCancelled else { throw PairingDiscoveryError.cancelled }
        guard (1...10_000).contains(timeoutMilliseconds) else { throw PairingDiscoveryError.unavailable }
        used = true; self.peer = peer
        resolutionTimeout = Double(timeoutMilliseconds) / 1000
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                self.continuation = continuation
                browser.delegate = self
                browser.schedule(in: .main, forMode: .common)
                browserStopped = false
                browser.searchForServices(ofType: "_remotepairing._tcp.", inDomain: "local.")
                if !stopping {
                    deadlineTask = Task { @MainActor [weak self] in
                        do { try await Task.sleep(nanoseconds: UInt64(timeoutMilliseconds) * 1_000_000) }
                        catch { return }
                        guard let self else { return }
                        self.stop(self.endpoints.isEmpty ? .failure(.timedOut) : .success(self.endpoints))
                    }
                }
            }
        } onCancel: {
            Task { @MainActor [weak self] in self?.cancel() }
        }
    }

    func cancel() {
        if stopping, continuation != nil { final = .failure(.cancelled); finishIfJoined() }
        else { stop(.failure(.cancelled)) }
    }

    private func stop(_ result: Result<[PairingNumericEndpoint], PairingDiscoveryError>) {
        guard !stopping else { return }
        stopping = true; final = result
        deadlineTask?.cancel(); deadlineTask = nil
        // Set every state before calls that may synchronously deliver delegates.
        let active = services.values.filter { !$0.stopped && !$0.stopping }.map(\.service)
        for service in active { services[ObjectIdentifier(service)]?.stopping = true }
        if !browserStopped { browser.stop() }
        for service in active { service.stop() }
        finishIfJoined()
    }

    private func stopResolution(_ service: NetService) {
        let id = ObjectIdentifier(service)
        guard let value = services[id], !value.stopping, !value.stopped else { return }
        services[id]?.stopping = true
        service.stop()
    }

    private func considerCompletion() {
        guard !stopping, firstBatchEnded, !endpoints.isEmpty,
              services.values.allSatisfy({ $0.completed }) else { return }
        stop(.success(endpoints))
    }

    private func finishIfJoined() {
        guard stopping, browserStopped, services.values.allSatisfy({ $0.stopped }),
              let final, let continuation else { return }
        self.continuation = nil; self.final = nil
        deadlineTask?.cancel(); deadlineTask = nil
        browser.delegate = nil
        browser.remove(from: .main, forMode: .common)
        for value in services.values {
            value.service.delegate = nil
            value.service.remove(from: .main, forMode: .common)
        }
        services.removeAll()
        continuation.resume(with: final.mapError { $0 as Error })
    }

    func netServiceBrowser(_ browser: NetServiceBrowser, didFind service: NetService, moreComing: Bool) {
        guard browser === self.browser, !stopping else { return }
        firstBatchEnded = !moreComing
        let id = ObjectIdentifier(service)
        guard services[id] == nil else { considerCompletion(); return }
        guard services.count < 8, service.name.utf8.count <= 63,
              service.domain.lowercased() == "local.", service.type == "_remotepairing._tcp." else {
            stop(.failure(.exhausted)); return
        }
        services[id] = Resolution(service: service)
        service.delegate = self
        service.remove(from: .main, forMode: .default)
        service.schedule(in: .main, forMode: .common)
        service.resolve(withTimeout: resolutionTimeout)
    }

    func netServiceBrowser(_ browser: NetServiceBrowser, didRemove service: NetService, moreComing: Bool) {
        guard browser === self.browser, !stopping, services[ObjectIdentifier(service)] != nil else { return }
        services[ObjectIdentifier(service)]?.completed = true
        stopResolution(service)
        firstBatchEnded = !moreComing
        considerCompletion()
    }

    func netServiceBrowserDidStopSearch(_ browser: NetServiceBrowser) {
        guard browser === self.browser else { return }
        browserStopped = true
        if !stopping { stop(.failure(.unavailable)) }
        finishIfJoined()
    }
    func netServiceBrowser(_ browser: NetServiceBrowser, didNotSearch errorDict: [String: NSNumber]) {
        guard browser === self.browser else { return }
        stop(.failure(.unavailable))
    }
    func netServiceDidResolveAddress(_ sender: NetService) {
        let id = ObjectIdentifier(sender)
        guard !stopping, let value = services[id], !value.completed, let peer else { return }
        services[id]?.completed = true
        guard let addresses = sender.addresses, addresses.count <= 8,
              let port = UInt16(exactly: sender.port), port > 0 else { stopResolution(sender); considerCompletion(); return }
        for bytes in addresses {
            guard let endpoint = try? PairingNumericEndpoint(sockaddrBytes: bytes),
                  endpoint.peer == peer, endpoint.port == port, !endpoints.contains(endpoint) else { continue }
            guard endpoints.count < 4 else { stop(.failure(.exhausted)); return }
            endpoints.append(endpoint)
        }
        stopResolution(sender)
        considerCompletion()
    }
    func netService(_ sender: NetService, didNotResolve errorDict: [String: NSNumber]) {
        let id = ObjectIdentifier(sender)
        guard !stopping, services[id] != nil else { return }
        services[id]?.completed = true
        stopResolution(sender)
        considerCompletion()
    }
    func netServiceDidStop(_ sender: NetService) {
        let id = ObjectIdentifier(sender)
        guard services[id] != nil else { return }
        services[id]?.stopped = true
        services[id]?.completed = true
        considerCompletion()
        finishIfJoined()
    }
}
#endif
