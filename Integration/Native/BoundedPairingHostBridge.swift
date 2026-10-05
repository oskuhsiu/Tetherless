// SPDX-License-Identifier: AGPL-3.0-only
// Enable only after the exact packaged host ABI has compiled and linked.
#if TETHERLESS_BOUNDED_PAIRING_HOST && canImport(IDevice)
import Foundation
import IDevice

struct NativeHostAdvertisement: Sendable {
    let identifier: String
    let txt: [String: Data]
    // Sensitive session metadata; never render or log this value.
    let hostIRK: Data
}

enum NativeHostBridgeError: Error, Sendable {
    case unsupported, invalidInput, unavailable, cancelled, timedOut, protocolFailure, alreadyUsed
}

/// Owns one native token. Each accepted/cancel call reserves a lifetime claim
/// before entry is queued, so retirement cannot free a pending entry's context.
final class BoundedPairingHostBridge: @unchecked Sendable {
    let advertisement: NativeHostAdvertisement
    private let handle: OpaquePointer
    private let lifetime = NativeCallLifetime()
    private let lock = NSLock()
    private let worker = DispatchQueue(label: "Tetherless.pairing.host.native")
    private let generation: UUID
    private let onPIN: @MainActor @Sendable (UUID, String) -> Void
    private var started = false
    private var cancelled = false
    private var returned = false
    private var freed = false
    private var waiters: [@Sendable () -> Void] = []

    init(name: String, model: String, generation: UUID, nativeBackend: Bool,
         onPIN: @escaping @MainActor @Sendable (UUID, String) -> Void) throws {
        #if targetEnvironment(simulator) || !os(iOS)
        throw NativeHostBridgeError.unsupported
        #else
        guard #available(iOS 27.0, *), nativeBackend else { throw NativeHostBridgeError.unsupported }
        var token: OpaquePointer?
        var metadata = TetherlessPairingHostAdvertisement()
        let nameBytes = Array(name.utf8), modelBytes = Array(model.utf8)
        let result = nameBytes.withUnsafeBufferPointer { nameBuffer in
            modelBytes.withUnsafeBufferPointer { modelBuffer in
                tetherless_pairing_host_prepare(nameBuffer.baseAddress, UInt(nameBuffer.count),
                    modelBuffer.baseAddress, UInt(modelBuffer.count), &token, &metadata)
            }
        }
        guard result == TetherlessPairingHostOk, let token else { throw NativeHostBridgeError.unavailable }
        do {
            guard metadata.identifier_len > 0, metadata.identifier_len <= 64,
                  metadata.txt_plist_len > 0, metadata.txt_plist_len <= 2048 else {
                throw NativeHostBridgeError.protocolFailure
            }
            let identifierLength = Int(metadata.identifier_len), txtLength = Int(metadata.txt_plist_len)
            let identifierData = withUnsafeBytes(of: &metadata.identifier) { Data($0.prefix(identifierLength)) }
            let txtData = withUnsafeBytes(of: &metadata.txt_plist) { Data($0.prefix(txtLength)) }
            guard let identifier = String(data: identifierData, encoding: .utf8), UUID(uuidString: identifier) != nil,
                  let values = try PropertyListSerialization.propertyList(from: txtData, format: nil) as? [String: String],
                  values.count == 7, values["identifier"] == identifier else {
                throw NativeHostBridgeError.protocolFailure
            }
            let txt = values.mapValues { Data($0.utf8) }
            guard txt.allSatisfy({ !$0.key.isEmpty && $0.key.utf8.count + 1 + $0.value.count <= 255 }) else {
                throw NativeHostBridgeError.protocolFailure
            }
            advertisement = NativeHostAdvertisement(identifier: identifier, txt: txt,
                hostIRK: withUnsafeBytes(of: &metadata.host_alt_irk) { Data($0) })
        } catch {
            tetherless_pairing_host_free(token)
            throw NativeHostBridgeError.protocolFailure
        }
        handle = token
        self.generation = generation
        self.onPIN = onPIN
        #endif
    }

    func accept(_ socket: PairingAcceptedSocket, timeoutMilliseconds: UInt32) async throws -> Data {
        // Claim before any rejection cleanup. A duplicate call sharing the same
        // socket cannot close the first call's original descriptor.
        guard let connection = socket.claimForNative() else { throw NativeHostBridgeError.alreadyUsed }
        guard (1...120_000).contains(timeoutMilliseconds) else {
            connection.returned(); throw NativeHostBridgeError.invalidInput
        }
        guard reserveStart(), let claim = lifetime.admit() else {
            connection.returned(); throw NativeHostBridgeError.alreadyUsed
        }
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                worker.async { [self, connection, claim] in
                    var output = [UInt8](repeating: 0, count: 4096)
                    var count: UInt = 0
                    let status = output.withUnsafeMutableBufferPointer { bytes in
                        tetherless_pairing_host_accept_fd(handle, connection.descriptor, timeoutMilliseconds,
                            { bytes, count, context in
                                guard let context, let bytes, count == 6 else { return }
                                let owner = Unmanaged<BoundedPairingHostBridge>.fromOpaque(context).takeUnretainedValue()
                                owner.receivedPIN(bytes, count: Int(count))
                            }, Unmanaged.passUnretained(self).toOpaque(), bytes.baseAddress, 4096, &count)
                    }
                    let result: Result<Data, Error>
                    if status == TetherlessPairingHostOk, count > 0, count <= 4096 {
                        result = .success(Data(output.prefix(Int(count))))
                    } else if status == TetherlessPairingHostCancelled { result = .failure(NativeHostBridgeError.cancelled) }
                    else if status == TetherlessPairingHostTimedOut { result = .failure(NativeHostBridgeError.timedOut) }
                    else { result = .failure(NativeHostBridgeError.protocolFailure) }
                    markReturned()
                    // Native has dropped its duplicate before the original closes.
                    connection.returned()
                    claim.returned()
                    retire { continuation.resume(with: result) }
                }
            }
        } onCancel: { self.cancel() }
    }

    private func reserveStart() -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard !started, !freed else { return false }
        started = true
        return true
    }

    func cancel() {
        lock.lock(); cancelled = true; lock.unlock()
        guard let claim = lifetime.admit() else { return }
        _ = tetherless_pairing_host_cancel(handle)
        claim.returned()
    }

    /// Also handles a prepared token that never received a connection. This is
    /// a real join; the await is not shortened when the Swift task is cancelled.
    func close() async {
        cancel()
        await withCheckedContinuation { continuation in retire { continuation.resume() } }
    }

    private func markReturned() { lock.lock(); returned = true; lock.unlock() }
    private func mayDeliverPIN() -> Bool {
        lock.lock(); defer { lock.unlock() }
        return started && !cancelled && !returned && !freed
    }
    private func receivedPIN(_ bytes: UnsafePointer<UInt8>, count: Int) {
        guard mayDeliverPIN(), count == 6 else { return }
        let copy = Array(UnsafeBufferPointer(start: bytes, count: count))
        guard copy.allSatisfy({ (48...57).contains($0) }), let value = String(bytes: copy, encoding: .utf8) else { return }
        Task { @MainActor [self] in
            guard mayDeliverPIN() else { return }
            onPIN(generation, value)
        }
    }

    private func retire(_ completion: @escaping @Sendable () -> Void) {
        lock.lock()
        if freed { lock.unlock(); completion(); return }
        waiters.append(completion)
        lock.unlock()
        lifetime.retire { [self] in
            tetherless_pairing_host_free(handle)
            lock.lock()
            freed = true
            let ready = waiters
            waiters.removeAll()
            lock.unlock()
            ready.forEach { $0() }
        }
    }

    deinit {
        // Queued/active calls and queued UI delivery retain self. With no entry
        // left, an abandoned prepared token can be safely reclaimed here.
        if !freed { tetherless_pairing_host_free(handle) }
    }
}
#endif
