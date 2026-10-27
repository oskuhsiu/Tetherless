// SPDX-License-Identifier: AGPL-3.0-only
#if TETHERLESS_BOUNDED_PAIRING_HOST && TETHERLESS_STAGED_PAIRING_VALIDATION && canImport(IDevice)
import Foundation
import IDevice

enum NativeStagedValidationError: Error, Sendable {
    case unavailable, invalidInput, alreadyUsed, cancelled, timedOut, mismatch, rejected
}

/// A distinct one-shot token for authenticated staged-record acquisition and
/// challenge read. No active gateway, pairing store or shared protocol is changed.
final class NativeStagedPairingValidator: @unchecked Sendable {
    private let token: OpaquePointer
    private let lifetime = NativeCallLifetime()
    private let lock = NSLock()
    private let worker = DispatchQueue(label: "Tetherless.pairing.validate.native")
    private var started = false
    private var freed = false
    private var waiters: [@Sendable () -> Void] = []

    init() throws {
        guard let token = tetherless_pairing_validation_new() else { throw NativeStagedValidationError.unavailable }
        self.token = token
    }

    func validate(record: Data, endpoint: PairingNumericEndpoint,
                  bundleIdentifier: String, challenge: PairingValidationChallenge,
                  timeoutMilliseconds: UInt32) async throws {
        guard !record.isEmpty, record.count <= 4096, (1...10_000).contains(timeoutMilliseconds),
              Self.validBundle(bundleIdentifier) else { throw NativeStagedValidationError.invalidInput }
        let address = Array(try endpoint.nativeAddress().utf8)
        let bundle = Array(bundleIdentifier.utf8)
        guard reserveStart(), let claim = lifetime.admit() else { throw NativeStagedValidationError.alreadyUsed }
        let borrow: PairingValidationChallenge.Borrow
        do { borrow = try challenge.borrowForNative() }
        catch { claim.returned(); throw error }
        let path = Array(borrow.relativePath.utf8)
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                worker.async { [self, claim, borrow] in
                    let status = record.withUnsafeBytes { recordBytes in
                        address.withUnsafeBufferPointer { endpointBytes in
                            bundle.withUnsafeBufferPointer { bundleBytes in
                                path.withUnsafeBufferPointer { pathBytes in
                                    borrow.withExpectedBytes { expectedBytes in
                                        tetherless_pairing_validate_staged(
                                            recordBytes.bindMemory(to: UInt8.self).baseAddress, UInt(recordBytes.count),
                                            endpointBytes.baseAddress, UInt(endpointBytes.count), token,
                                            bundleBytes.baseAddress, UInt(bundleBytes.count),
                                            pathBytes.baseAddress, UInt(pathBytes.count),
                                            expectedBytes.bindMemory(to: UInt8.self).baseAddress, UInt(expectedBytes.count),
                                            timeoutMilliseconds)
                                    }
                                }
                            }
                        }
                    }
                    let result: Result<Void, Error>
                    switch status {
                    case TetherlessPairingValidationOk: result = .success(())
                    case TetherlessPairingValidationCancelled: result = .failure(NativeStagedValidationError.cancelled)
                    case TetherlessPairingValidationTimedOut: result = .failure(NativeStagedValidationError.timedOut)
                    case TetherlessPairingValidationMismatch: result = .failure(NativeStagedValidationError.mismatch)
                    default: result = .failure(NativeStagedValidationError.rejected)
                    }
                    // The Rust return joins owned streams and its future. Only
                    // now may the document borrow and native entry claim retire.
                    borrow.returned()
                    claim.returned()
                    retire { continuation.resume(with: result) }
                }
            }
        } onCancel: { self.cancel() }
    }

    private static func validBundle(_ value: String) -> Bool {
        !value.isEmpty && value.utf8.count <= 255 &&
        value.split(separator: ".", omittingEmptySubsequences: false).allSatisfy { !$0.isEmpty } &&
        value.utf8.allSatisfy { (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) || $0 == 46 || $0 == 45 }
    }
    private func reserveStart() -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard !started, !freed else { return false }
        started = true; return true
    }
    func cancel() {
        guard let claim = lifetime.admit() else { return }
        _ = tetherless_pairing_validation_cancel(token)
        claim.returned()
    }
    func close() async {
        cancel()
        await withCheckedContinuation { continuation in retire { continuation.resume() } }
    }
    private func retire(_ completion: @escaping @Sendable () -> Void) {
        lock.lock()
        if freed { lock.unlock(); completion(); return }
        waiters.append(completion)
        lock.unlock()
        lifetime.retire { [self] in
            tetherless_pairing_validation_free(token)
            lock.lock(); freed = true; let ready = waiters; waiters.removeAll(); lock.unlock()
            ready.forEach { $0() }
        }
    }
    deinit { if !freed { tetherless_pairing_validation_free(token) } }
}
#endif
