// SPDX-License-Identifier: AGPL-3.0-only
#if TETHERLESS_BOUNDED_PAIRING_HOST && canImport(Darwin)
import Foundation
import Darwin

/// Single-owner connection. The native bridge retains this object for queued
/// entry and closes it only after native return. No caller performs parallel I/O.
final class PairingAcceptedSocket: @unchecked Sendable {
    let descriptor: Int32
    private enum Ownership: Equatable { case available, native, closed }
    private let lock = NSLock()
    private var ownership: Ownership = .available
    init(_ descriptor: Int32) { self.descriptor = descriptor }

    func claimForNative() -> NativeOwnership? {
        lock.lock(); defer { lock.unlock() }
        guard ownership == .available else { return nil }
        ownership = .native
        return NativeOwnership(owner: self)
    }

    /// A stale/repeated delivery may dispose only an untransferred connection.
    /// It must never close a descriptor already owned by a queued native call.
    func discardIfUnclaimed() {
        lock.lock(); defer { lock.unlock() }
        guard ownership == .available else { return }
        ownership = .closed
        _ = Darwin.close(descriptor)
    }
    private func nativeReturned() {
        lock.lock(); defer { lock.unlock() }
        guard ownership == .native else { return }
        ownership = .closed
        _ = Darwin.close(descriptor)
    }
    deinit { discardIfUnclaimed() }

    final class NativeOwnership: @unchecked Sendable {
        let descriptor: Int32
        private let lock = NSLock()
        private var owner: PairingAcceptedSocket?
        fileprivate init(owner: PairingAcceptedSocket) { self.owner = owner; descriptor = owner.descriptor }
        func returned() {
            lock.lock()
            let owner = self.owner
            self.owner = nil
            lock.unlock()
            owner?.nativeReturned()
        }
        deinit { returned() }
    }
}

enum PairingListenerFailure: Error, Equatable, Sendable { case unavailable, cancelled, timedOut, alreadyUsed }

protocol PairingTCPAcceptor: AnyObject, Sendable {
    var port: Int32 { get }
    func cancel()
}

/// BSD listener uses a serial dispatch source. Cancellation completion is the
/// source's cancellation handler, after its last event handler has returned.
private final class PairingSocketListener: PairingTCPAcceptor, @unchecked Sendable {
    let port: Int32
    private let source: DispatchSourceRead
    private let lock = NSLock()
    private var ending = false

    init(result: @escaping @Sendable (Result<PairingAcceptedSocket, PairingListenerFailure>) -> Void,
         stopped: @escaping @Sendable () -> Void) throws {
        let fd = Darwin.socket(AF_INET6, SOCK_STREAM, IPPROTO_TCP)
        guard fd >= 0 else { throw PairingListenerFailure.unavailable }
        var transferred = false
        defer { if !transferred { _ = Darwin.close(fd) } }
        var dualStack: Int32 = 0
        guard setsockopt(fd, IPPROTO_IPV6, IPV6_V6ONLY, &dualStack, socklen_t(MemoryLayout<Int32>.size)) == 0,
              Self.configure(fd) else { throw PairingListenerFailure.unavailable }
        var address = sockaddr_in6()
        address.sin6_len = UInt8(MemoryLayout<sockaddr_in6>.size)
        address.sin6_family = sa_family_t(AF_INET6)
        address.sin6_addr = in6addr_any
        let bound = withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in6>.size))
            }
        }
        guard bound == 0, Darwin.listen(fd, 1) == 0 else { throw PairingListenerFailure.unavailable }
        var length = socklen_t(MemoryLayout<sockaddr_in6>.size)
        let inspected = withUnsafeMutablePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(fd, $0, &length) }
        }
        guard inspected == 0 else { throw PairingListenerFailure.unavailable }
        port = Int32(UInt16(bigEndian: address.sin6_port))
        source = DispatchSource.makeReadSource(fileDescriptor: fd,
            queue: DispatchQueue(label: "Tetherless.pairing.listener"))
        source.setCancelHandler { _ = Darwin.close(fd); stopped() }
        source.setEventHandler { [weak self] in
            guard let self, !self.isEnding() else { return }
            let accepted = Darwin.accept(fd, nil, nil)
            if accepted < 0 {
                if errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR { return }
                guard self.end() else { return }
                result(.failure(.unavailable)); return
            }
            guard Self.configure(accepted) else {
                _ = Darwin.close(accepted)
                guard self.end() else { return }
                result(.failure(.unavailable)); return
            }
            guard self.end() else { _ = Darwin.close(accepted); return }
            result(.success(PairingAcceptedSocket(accepted)))
        }
        transferred = true
        source.resume()
    }
    private static func configure(_ fd: Int32) -> Bool {
        let flags = fcntl(fd, F_GETFL), descriptorFlags = fcntl(fd, F_GETFD)
        var noSignal: Int32 = 1
        return flags >= 0 && descriptorFlags >= 0 &&
            fcntl(fd, F_SETFL, flags | O_NONBLOCK) == 0 &&
            fcntl(fd, F_SETFD, descriptorFlags | FD_CLOEXEC) == 0 &&
            setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &noSignal, socklen_t(MemoryLayout<Int32>.size)) == 0
    }
    private func isEnding() -> Bool { lock.lock(); defer { lock.unlock() }; return ending }
    @discardableResult private func end() -> Bool {
        lock.lock()
        guard !ending else { lock.unlock(); return false }
        ending = true
        lock.unlock()
        source.cancel()
        return true
    }
    func cancel() { _ = end() }
    deinit { source.cancel() }
}

/// One advertising generation. Platform stop and listener cancellation are
/// both acknowledged before the accepted descriptor or terminal error returns.
@MainActor final class PairingBonjourListener: NSObject, @preconcurrency NetServiceDelegate {
    private let forwardedEvents = NativeCallLifetime()
    private var service: NetService?
    typealias ListenerFactory = (
        @escaping @Sendable (Result<PairingAcceptedSocket, PairingListenerFailure>) -> Void,
        @escaping @Sendable () -> Void
    ) throws -> any PairingTCPAcceptor
    private let makeListener: ListenerFactory
    private let makePublisher: (String, Int32) -> NetService
    private var listener: (any PairingTCPAcceptor)?
    private var continuation: CheckedContinuation<PairingAcceptedSocket, Error>?
    private var timer: Task<Void, Never>?
    private var outcome: Result<PairingAcceptedSocket, PairingListenerFailure>?
    private var used = false
    private var stopRequested = false
    private var listenerStopped = true
    private var publisherStopped = true

    init(makeListener: @escaping ListenerFactory = { try PairingSocketListener(result: $0, stopped: $1) },
         makePublisher: @escaping (String, Int32) -> NetService = {
             NetService(domain: "local.", type: "_remotepairing-pairable-host._tcp.", name: $0, port: $1)
         }) {
        self.makeListener = makeListener
        self.makePublisher = makePublisher
        super.init()
    }

    func acceptOne(identifier: String, txt: [String: Data], timeoutMilliseconds: UInt32) async throws -> PairingAcceptedSocket {
        guard !used else { throw PairingListenerFailure.alreadyUsed }
        guard !stopRequested else { throw PairingListenerFailure.cancelled }
        used = true
        guard UUID(uuidString: identifier) != nil, txt.count == 7,
              txt["identifier"] == Data(identifier.utf8),
              txt.allSatisfy({ !$0.key.isEmpty && $0.key.utf8.count + 1 + $0.value.count <= 255 }),
              (1...120_000).contains(timeoutMilliseconds) else { throw PairingListenerFailure.unavailable }
        guard !Task.isCancelled else { throw PairingListenerFailure.cancelled }
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                self.continuation = continuation
                do {
                    listenerStopped = false
                    let forwardedEvents = self.forwardedEvents
                    listener = try makeListener({ [weak self, forwardedEvents] value in
                        guard let delivery = forwardedEvents.admit() else {
                            if case .success(let socket) = value { socket.discardIfUnclaimed() }
                            return
                        }
                        let owner = self
                        Task { @MainActor in
                            if let owner { owner.received(value) }
                            else if case .success(let socket) = value { socket.discardIfUnclaimed() }
                            delivery.returned()
                        }
                    }, { [weak self, forwardedEvents] in
                        // The source has stopped producing events. Join every
                        // event forwarded before acknowledging that stop.
                        let owner = self
                        forwardedEvents.retire {
                            Task { @MainActor in owner?.listenerDidStop() }
                        }
                    })
                    let publisher = makePublisher(identifier, listener!.port)
                    service = publisher
                    publisher.delegate = self
                    publisher.remove(from: .main, forMode: .default)
                    publisher.schedule(in: .main, forMode: .common)
                    guard publisher.setTXTRecord(NetService.data(fromTXTRecord: txt)) else {
                        throw PairingListenerFailure.unavailable
                    }
                    publisherStopped = false
                    publisher.publish(options: .noAutoRename)
                    if !stopRequested {
                        timer = Task { @MainActor [weak self] in
                            do { try await Task.sleep(nanoseconds: UInt64(timeoutMilliseconds) * 1_000_000) }
                            catch { return }
                            self?.stop(with: .failure(.timedOut))
                        }
                    }
                } catch {
                    if listener == nil {
                        forwardedEvents.retire { [self] in
                            Task { @MainActor in listenerDidStop() }
                        }
                    }
                    stop(with: .failure(.unavailable))
                }
            }
        } onCancel: {
            Task { @MainActor [weak self] in self?.cancel() }
        }
    }

    func cancel() {
        if stopRequested, continuation != nil {
            if case .success(let socket) = outcome { socket.discardIfUnclaimed() }
            outcome = .failure(.cancelled)
            finishIfStopped()
        } else { stop(with: .failure(.cancelled)) }
    }

    private func received(_ value: Result<PairingAcceptedSocket, PairingListenerFailure>) {
        guard !stopRequested else {
            if case .success(let socket) = value { socket.discardIfUnclaimed() }
            return
        }
        stop(with: value)
    }

    private func stop(with value: Result<PairingAcceptedSocket, PairingListenerFailure>) {
        guard !stopRequested else { return }
        stopRequested = true
        outcome = value
        timer?.cancel(); timer = nil
        listener?.cancel()
        if !publisherStopped { service?.stop() }
        finishIfStopped()
    }

    private func listenerDidStop() { listenerStopped = true; finishIfStopped() }

    private func finishIfStopped() {
        guard stopRequested, listenerStopped, publisherStopped, let outcome, let continuation else { return }
        self.continuation = nil
        self.outcome = nil
        timer?.cancel(); timer = nil
        service?.delegate = nil
        service?.remove(from: .main, forMode: .common)
        service = nil
        listener = nil
        continuation.resume(with: outcome.mapError { $0 as Error })
    }

    func netServiceDidStop(_ sender: NetService) {
        guard sender === service else { return }
        publisherStopped = true
        if !stopRequested { stop(with: .failure(.unavailable)) }
        finishIfStopped()
    }
    func netService(_ sender: NetService, didNotPublish errorDict: [String: NSNumber]) {
        guard sender === service else { return }
        // A failed publication still requires explicit stop acknowledgement.
        stop(with: .failure(.unavailable))
        finishIfStopped()
    }
}
#endif
