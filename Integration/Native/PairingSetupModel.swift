// SPDX-License-Identifier: AGPL-3.0-only
#if TETHERLESS_BOUNDED_PAIRING_HOST && TETHERLESS_STAGED_PAIRING_VALIDATION && os(iOS) && canImport(IDevice) && canImport(IdeviceGateway)
import Foundation
import Combine
@preconcurrency import UIKit
import Minimuxer
import MinimuxerCommon
import IdeviceGateway

/// One user-initiated setup or replacement. Its task owns the process mutation
/// lease through every native/platform join and challenge-file cleanup.
@MainActor final class PairingSetupModel: ObservableObject {
    enum Phase: Equatable { case ready, preparing, waiting, pairing, validating, stopping, finished }
    enum Outcome: Equatable { case saved, cancelled, unavailable, failed, recoveryRequired }
    @Published private(set) var phase: Phase = .ready
    @Published private(set) var outcome: Outcome?
    @Published private(set) var pin: String?
    let cancellation = PairingCancellationController()
    private let promotion = PairingPromotion()
    private var task: Task<Void, Never>?
    private var backgroundTask = UIBackgroundTaskIdentifier.invalid
    private var deadline: TimeInterval = 0

    var isRunning: Bool { phase != .ready && phase != .finished }
    private static var platformSupported: Bool {
        #if targetEnvironment(simulator) || targetEnvironment(macCatalyst)
        return false
        #else
        guard #available(iOS 27.0, *) else { return false }
        guard !ProcessInfo.processInfo.isiOSAppOnMac else { return false }
        return UIDevice.current.userInterfaceIdiom == .phone
        #endif
    }
    static var supported: Bool {
        platformSupported && Minimuxer.shared.gateway is IdeviceGateway
    }

    func start() {
        guard phase == .ready else { return }
        guard Self.supported else { phase = .finished; outcome = .unavailable; return }
        phase = .preparing
        deadline = ProcessInfo.processInfo.systemUptime + 120
        let cancellation = self.cancellation
        // The OS callback signals the thread-safe decision immediately. It
        // never waits for the UI actor before requesting native cancellation.
        backgroundTask = UIApplication.shared.beginBackgroundTask(withName: "Pairing setup") { [weak self] in
            _ = cancellation.cancel()
            Task { @MainActor [weak self] in self?.reconcileCancellation() }
        }
        guard backgroundTask != .invalid else { phase = .finished; outcome = .unavailable; return }
        task = Task { @MainActor [self] in
            defer {
                pin = nil
                cancellation.finish()
                UIApplication.shared.endBackgroundTask(backgroundTask)
                backgroundTask = .invalid
                phase = .finished
                task = nil
            }
            do {
                outcome = try await NativeMutationGate.withLease { await runLeased() }
            } catch {
                outcome = cancellation.isCancelled ? .cancelled : .unavailable
            }
        }
    }

    func cancel() {
        guard isRunning, cancellation.cancel() else { return }
        reconcileCancellation()
    }

    func reconcileCancellation() {
        guard isRunning, cancellation.isCancelled else { return }
        _ = promotion.cancel()
        pin = nil
        phase = .stopping
    }

    private func checkCancellation() throws {
        guard !cancellation.isCancelled, !Task.isCancelled else { throw CancellationError() }
    }
    private func remaining(until end: TimeInterval, maximum: UInt32) throws -> UInt32 {
        try checkCancellation()
        let milliseconds = (end - ProcessInfo.processInfo.systemUptime) * 1000
        guard milliseconds >= 1 else { throw NativeHostBridgeError.timedOut }
        return UInt32(min(Double(maximum), milliseconds.rounded(.down)))
    }

    private func makeHost(nativeBackend: Bool) async throws -> BoundedPairingHostBridge {
        let generation = promotion.generation
        let callback: @MainActor @Sendable (UUID, String) -> Void = { [weak self] generation, value in
            guard let self, !self.cancellation.isCancelled,
                  self.promotion.acceptsPIN(for: generation) else { return }
            self.phase = .pairing
            self.pin = value
        }
        // This bounded native preparation has no socket or callback work. Keep
        // the lease while the queued entry runs, including cancellation here.
        return try await withCheckedThrowingContinuation { continuation in
            DispatchQueue(label: "Tetherless.pairing.prepare.native").async {
                do {
                    // Protocol host-role model accepted by the pinned responder;
                    // this metadata is never used as current-phone identity proof.
                    continuation.resume(returning: try BoundedPairingHostBridge(name: "Tetherless", model: "Mac17,7",
                        generation: generation, nativeBackend: nativeBackend, onPIN: callback))
                } catch { continuation.resume(throwing: error) }
            }
        }
    }

    private func runLeased() async -> Outcome {
        do {
            try checkCancellation()
            // Selection may have changed while awaiting the existing lease.
            // Recheck immediately before native preparation; never substitute
            // a cached eligibility value or mutate the running gateway here.
            let nativeBackend = Minimuxer.shared.gateway is IdeviceGateway
            guard Self.platformSupported, nativeBackend else { return .unavailable }
            _ = try remaining(until: deadline, maximum: 120_000)
            let host = try await makeHost(nativeBackend: nativeBackend)
            let hostCancellation = cancellation.register { host.cancel() }
            let candidate: Data
            let peer: PairingPeerAddress
            do {
                try checkCancellation()
                let listener = PairingBonjourListener()
                let listenerCancellation = cancellation.register { Task { @MainActor in listener.cancel() } }
                let socket: PairingAcceptedSocket
                do {
                    phase = .waiting
                    socket = try await listener.acceptOne(identifier: host.advertisement.identifier,
                        txt: host.advertisement.txt, timeoutMilliseconds: remaining(until: deadline, maximum: 120_000))
                } catch {
                    listenerCancellation?.remove()
                    throw error // acceptOne has joined publication, listener and delivery callbacks.
                }
                listenerCancellation?.remove()
                do {
                    try checkCancellation()
                    peer = try PairingPeerAddress.connectedPeer(descriptor: socket.descriptor)
                    candidate = try await host.accept(socket, timeoutMilliseconds: remaining(until: deadline, maximum: 120_000))
                } catch { socket.discardIfUnclaimed(); throw error }
            } catch {
                await host.close()
                hostCancellation?.remove()
                throw error
            }
            await host.close()
            hostCancellation?.remove()
            try checkCancellation()
            pin = nil
            phase = .validating
            let store = try PrivateFileStore(root: PairingFileManager.protectedRoot)
            try store.prepare()
            let result = await promotion.validateAndPromote(candidate: candidate, validate: { [self] normalized in
                try await validate(normalized, peer: peer)
            }, readTarget: {
                try store.read(AppConstants.Pairing.remotePairingFileName)
            }, commit: { [self] record in
                // No await can intervene between the thread-safe winner and
                // the existing reentrant protected-store commit and readback.
                guard cancellation.beginPromotion() else { throw CancellationError() }
                _ = try PairingFileManager.shared.saveValidatedRemotePairingRecord(record)
                PairingFileManager.shared.preferredProtocol = .rppairing
            })
            switch result {
            case .committed: return .saved
            case .cancelled: return .cancelled
            case .recoveryRequired: return .recoveryRequired
            default: return cancellation.isCancelled ? .cancelled : .failed
            }
        } catch { return cancellation.isCancelled || error is CancellationError ? .cancelled : .failed }
    }

    private func validate(_ record: Data, peer: PairingPeerAddress) async throws {
        try checkCancellation()
        guard let bundle = Bundle.main.bundleIdentifier else { throw NativeStagedValidationError.invalidInput }
        let end = min(deadline, ProcessInfo.processInfo.systemUptime + 10)
        let resolver = PairingEndpointResolver()
        let resolverCancellation = cancellation.register { Task { @MainActor in resolver.cancel() } }
        let endpoints: [PairingNumericEndpoint]
        do { endpoints = try await resolver.resolve(peer: peer, timeoutMilliseconds: remaining(until: end, maximum: 10_000)) }
        catch { resolverCancellation?.remove(); throw error }
        resolverCancellation?.remove() // resolve returns only after every stop acknowledgement.
        try checkCancellation()
        let library = try FileManager.default.url(for: .libraryDirectory, in: .userDomainMask, appropriateFor: nil, create: false)
        let challenge = try PairingValidationChallenge(libraryDirectory: library)
        do {
            var verified = false
            for (index, endpoint) in endpoints.enumerated() {
                // All attempts share the original end. Reserve a proportional
                // share for each remaining endpoint, including this one. Native
                // close must still join even if cleanup consumes the remainder.
                let available = try remaining(until: end, maximum: 10_000)
                guard let timeout = PairingValidationBudget.timeoutMilliseconds(
                    remainingMilliseconds: available, endpointsRemaining: endpoints.count - index) else {
                    throw NativeHostBridgeError.timedOut
                }
                let validator = try NativeStagedPairingValidator()
                let registration = cancellation.register { validator.cancel() }
                do {
                    try await validator.validate(record: record, endpoint: endpoint, bundleIdentifier: bundle,
                        challenge: challenge, timeoutMilliseconds: timeout)
                    verified = true
                } catch {
                    await validator.close()
                    registration?.remove()
                    try checkCancellation()
                    continue
                }
                await validator.close()
                registration?.remove()
                break
            }
            guard verified else { throw NativeStagedValidationError.rejected }
            try checkCancellation()
        } catch {
            // A failed validation never promotes. A cleanup error also leaves
            // active storage untouched; no timer substitutes for native join.
            try await challenge.closeAfterValidation()
            throw error
        }
        try await challenge.closeAfterValidation()
        try checkCancellation()
    }
}
#endif
