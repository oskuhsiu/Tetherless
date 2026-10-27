#if canImport(Darwin)
import Foundation
import Darwin
import XCTest
@testable import TetherlessCore

@MainActor final class PairingBonjourListenerTests: XCTestCase {
    private final class Acceptor: PairingTCPAcceptor, @unchecked Sendable {
        let port: Int32 = 49152
        private let lock = NSLock()
        private var cancelled = 0
        var cancellations: Int { lock.lock(); defer { lock.unlock() }; return cancelled }
        func cancel() { lock.lock(); cancelled += 1; lock.unlock() }
    }
    private final class Publisher: NetService, @unchecked Sendable {
        let published = AsyncStream<Void>.makeStream()
        let stopped = AsyncStream<Void>.makeStream()
        let configured = AsyncStream<Void>.makeStream()
        var acceptsTXT = true
        private let eventLock = NSLock()
        private var events: [String] = []
        var eventLog: [String] { eventLock.lock(); defer { eventLock.unlock() }; return events }
        private func record(_ value: String) { eventLock.lock(); events.append(value); eventLock.unlock() }
        override func publish(options: NetService.Options = []) { record("publish"); published.continuation.yield(()) }
        override func stop() { record("stop"); stopped.continuation.yield(()) }
        override func setTXTRecord(_ recordData: Data?) -> Bool {
            record("txt"); configured.continuation.yield(()); return acceptsTXT
        }
        override func schedule(in aRunLoop: RunLoop, forMode mode: RunLoop.Mode) {
            record("schedule:" + mode.rawValue); super.schedule(in: aRunLoop, forMode: mode)
        }
        override func remove(from aRunLoop: RunLoop, forMode mode: RunLoop.Mode) {
            record("remove:" + mode.rawValue); super.remove(from: aRunLoop, forMode: mode)
        }
    }
    private func metadata(_ id: String) -> [String: Data] {
        ["identifier": Data(id.utf8), "name": Data("synthetic".utf8), "model": Data("Mac17,7".utf8),
         "authTag": Data("synthetic".utf8), "flags": Data("1".utf8), "ver": Data("26".utf8), "minVer": Data("17".utf8)]
    }
    private func signal(_ stream: AsyncStream<Void>) async {
        var iterator = stream.makeAsyncIterator()
        _ = await iterator.next()
    }
    private func connection() throws -> (PairingAcceptedSocket, Int32) {
        var descriptors: [Int32] = [-1, -1]
        guard socketpair(AF_UNIX, SOCK_STREAM, 0, &descriptors) == 0 else { throw PairingListenerFailure.unavailable }
        return (PairingAcceptedSocket(descriptors[0]), descriptors[1])
    }

    func testAcceptedDescriptorWaitsForBothStopAcknowledgementsInEitherOrder() async throws {
        for publisherFirst in [false, true] {
            let id = UUID().uuidString, acceptor = Acceptor()
            let publisher = Publisher(domain: "local.", type: "_synthetic._tcp.", name: id, port: acceptor.port)
            var event: (@Sendable (Result<PairingAcceptedSocket, PairingListenerFailure>) -> Void)?
            var stopped: (@Sendable () -> Void)?
            let listener = PairingBonjourListener(makeListener: { event = $0; stopped = $1; return acceptor },
                                                   makePublisher: { _, _ in publisher })
            var delivered = false
            let operation = Task { @MainActor in
                let result = try await listener.acceptOne(identifier: id, txt: metadata(id), timeoutMilliseconds: 1000)
                delivered = true
                return result
            }
            await signal(publisher.published.stream)
            let (accepted, peer) = try connection()
            defer { _ = Darwin.close(peer) }
            event?(.success(accepted))
            await signal(publisher.stopped.stream)
            XCTAssertFalse(delivered)
            if publisherFirst { listener.netServiceDidStop(publisher) }
            else { stopped?(); await Task.yield() }
            XCTAssertFalse(delivered)
            if publisherFirst { stopped?() }
            else { listener.netServiceDidStop(publisher) }
            let result = try await operation.value
            XCTAssertTrue(delivered)
            XCTAssertTrue(result === accepted)
            XCTAssertGreaterThanOrEqual(fcntl(result.descriptor, F_GETFL), 0)
            result.discardIfUnclaimed()
            XCTAssertEqual(acceptor.cancellations, 1)
        }
    }

    func testCancellationWhileStoppingClosesAcceptedSocketAndStillJoins() async throws {
        let id = UUID().uuidString, acceptor = Acceptor()
        let publisher = Publisher(domain: "local.", type: "_synthetic._tcp.", name: id, port: acceptor.port)
        var event: (@Sendable (Result<PairingAcceptedSocket, PairingListenerFailure>) -> Void)?
        var stopped: (@Sendable () -> Void)?
        let listener = PairingBonjourListener(makeListener: { event = $0; stopped = $1; return acceptor },
                                               makePublisher: { _, _ in publisher })
        var delivered = false
        let operation = Task { @MainActor in
            defer { delivered = true }
            return try await listener.acceptOne(identifier: id, txt: metadata(id), timeoutMilliseconds: 1000)
        }
        await signal(publisher.published.stream)
        let (accepted, peer) = try connection()
        defer { _ = Darwin.close(peer) }
        event?(.success(accepted))
        await signal(publisher.stopped.stream)
        listener.cancel()
        XCTAssertFalse(delivered)
        XCTAssertEqual(fcntl(accepted.descriptor, F_GETFL), -1)
        stopped?()
        listener.netServiceDidStop(publisher)
        do { _ = try await operation.value; XCTFail("cancel returned a connection") }
        catch { XCTAssertEqual(error as? PairingListenerFailure, .cancelled) }
        XCTAssertTrue(delivered)
    }

    func testStopAcknowledgementCannotOvertakeQueuedAcceptedDescriptorCleanup() async throws {
        let id = UUID().uuidString, acceptor = Acceptor()
        let publisher = Publisher(domain: "local.", type: "_synthetic._tcp.", name: id, port: acceptor.port)
        var event: (@Sendable (Result<PairingAcceptedSocket, PairingListenerFailure>) -> Void)?
        var stopped: (@Sendable () -> Void)?
        let listener = PairingBonjourListener(makeListener: { event = $0; stopped = $1; return acceptor },
                                               makePublisher: { _, _ in publisher })
        let operation = Task { @MainActor in
            try await listener.acceptOne(identifier: id, txt: metadata(id), timeoutMilliseconds: 1000)
        }
        await signal(publisher.published.stream)
        let (accepted, peer) = try connection()
        defer { _ = Darwin.close(peer) }
        // Event is queued for the actor; acknowledge the source and publisher
        // before allowing that queued delivery to execute.
        event?(.success(accepted))
        listener.cancel()
        stopped?()
        listener.netServiceDidStop(publisher)
        do { _ = try await operation.value; XCTFail("cancel returned a connection") }
        catch { XCTAssertEqual(error as? PairingListenerFailure, .cancelled) }
        XCTAssertEqual(fcntl(accepted.descriptor, F_GETFL), -1)
    }

    func testFailedPublicationStillCallsStopAndWaitsForItsAcknowledgement() async throws {
        let id = UUID().uuidString, acceptor = Acceptor()
        let publisher = Publisher(domain: "local.", type: "_synthetic._tcp.", name: id, port: acceptor.port)
        var stopped: (@Sendable () -> Void)?
        let listener = PairingBonjourListener(makeListener: { _, callback in stopped = callback; return acceptor },
                                               makePublisher: { _, _ in publisher })
        var delivered = false
        let operation = Task { @MainActor in
            defer { delivered = true }
            return try await listener.acceptOne(identifier: id, txt: metadata(id), timeoutMilliseconds: 1000)
        }
        await signal(publisher.published.stream)
        listener.netService(publisher, didNotPublish: [:])
        await signal(publisher.stopped.stream)
        stopped?()
        await Task.yield()
        XCTAssertFalse(delivered)
        listener.netServiceDidStop(publisher)
        do { _ = try await operation.value; XCTFail("failed publication succeeded") }
        catch { XCTAssertEqual(error as? PairingListenerFailure, .unavailable) }
    }

    func testSocketCanTransferOnlyOnceAndDuplicateDisposalCannotCloseActiveCall() throws {
        let (accepted, peer) = try connection()
        defer { _ = Darwin.close(peer) }
        let claim = try XCTUnwrap(accepted.claimForNative())
        XCTAssertNil(accepted.claimForNative())
        accepted.discardIfUnclaimed()
        XCTAssertGreaterThanOrEqual(fcntl(accepted.descriptor, F_GETFL), 0)
        claim.returned()
        XCTAssertEqual(fcntl(accepted.descriptor, F_GETFL), -1)
        claim.returned()
        XCTAssertNil(accepted.claimForNative())
        XCTAssertGreaterThanOrEqual(fcntl(peer, F_GETFL), 0)
    }

    func testTXTFailureRemovesBothDefaultAndExplicitScheduleWithoutPublishing() async throws {
        let id = UUID().uuidString, acceptor = Acceptor()
        let publisher = Publisher(domain: "local.", type: "_synthetic._tcp.", name: id, port: acceptor.port)
        publisher.acceptsTXT = false
        var stopped: (@Sendable () -> Void)?
        let listener = PairingBonjourListener(makeListener: { _, callback in stopped = callback; return acceptor },
                                               makePublisher: { _, _ in publisher })
        let operation = Task { @MainActor in
            try await listener.acceptOne(identifier: id, txt: metadata(id), timeoutMilliseconds: 1000)
        }
        await signal(publisher.configured.stream)
        stopped?()
        do { _ = try await operation.value; XCTFail("invalid TXT published") }
        catch { XCTAssertEqual(error as? PairingListenerFailure, .unavailable) }
        let log = publisher.eventLog
        XCTAssertFalse(log.contains("publish"))
        XCTAssertFalse(log.contains("stop"))
        let removeDefault = try XCTUnwrap(log.firstIndex(of: "remove:" + RunLoop.Mode.default.rawValue))
        let scheduleCommon = try XCTUnwrap(log.firstIndex(of: "schedule:" + RunLoop.Mode.common.rawValue))
        let removeCommon = try XCTUnwrap(log.lastIndex(of: "remove:" + RunLoop.Mode.common.rawValue))
        XCTAssertLessThan(removeDefault, scheduleCommon)
        XCTAssertLessThan(scheduleCommon, removeCommon)
        XCTAssertEqual(acceptor.cancellations, 1)
    }

    func testCancellationBeforeStartNeverCreatesPublisherOrListener() async throws {
        let listener = PairingBonjourListener(makeListener: { _, _ in
            XCTFail("created cancelled listener"); return Acceptor()
        }, makePublisher: { _, _ in XCTFail("created cancelled publisher"); return NetService(domain: "local.", type: "_synthetic._tcp.", name: "unused", port: 1) })
        listener.cancel()
        let id = UUID().uuidString
        do { _ = try await listener.acceptOne(identifier: id, txt: metadata(id), timeoutMilliseconds: 1000); XCTFail("cancel ignored") }
        catch { XCTAssertEqual(error as? PairingListenerFailure, .cancelled) }
    }
}
#endif
