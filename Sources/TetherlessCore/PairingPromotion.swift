// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// One user-initiated generation. The owner holds the real process mutation
/// lease throughout handshake, validation, transport cleanup and this commit.
@MainActor public final class PairingPromotion {
    public enum Outcome: Equatable, Sendable {
        case committed, cancelled, validationFailed, unchangedFailure, recoveryRequired, alreadyUsed
    }
    private enum Phase: Equatable { case idle, validating, cancelled, committing, finished }
    public let generation = UUID()
    private var phase: Phase = .idle

    public init() {}

    /// Recheck this on the UI actor when a queued PIN callback is delivered.
    public func acceptsPIN(for generation: UUID) -> Bool {
        self.generation == generation && phase == .idle
    }

    /// False means final promotion has already won, or the session is finished.
    /// Cancelling UI state does not join or free any native call.
    @discardableResult
    public func cancel() -> Bool {
        switch phase {
        case .idle, .validating, .cancelled: phase = .cancelled; return true
        case .committing, .finished: return false
        }
    }

    /// `validate` must return only after the staged peer operation and every
    /// owned callback/socket have joined. It authenticates exactly the bytes it
    /// receives without changing active storage. Cancellation never skips this
    /// await. `commit` may use the existing protected atomic-write/import path;
    /// it must not change active metadata or delete old records before writing.
    /// `readTarget` reads the same target that commit writes, under the lease.
    /// Do not retry recoveryRequired automatically: rename may have succeeded.
    public func validateAndPromote(
        candidate: Data,
        validate: @MainActor (Data) async throws -> Void,
        readTarget: @MainActor () throws -> Data?,
        commit: @MainActor (PairingRecord) throws -> Void
    ) async -> Outcome {
        guard phase == .idle else { return phase == .cancelled ? .cancelled : .alreadyUsed }
        guard !Task.isCancelled else { phase = .finished; return .cancelled }
        phase = .validating
        let record: PairingRecord
        let previous: Data?
        do {
            guard candidate.count <= 4096 else { throw PrivateFileError.tooLarge }
            record = try PairingRecord(data: candidate, expected: .remote)
            guard record.xml.count <= 4096 else { throw PrivateFileError.tooLarge }
            previous = try readTarget()
        } catch {
            let result: Outcome = (phase == .cancelled || Task.isCancelled) ? .cancelled : .unchangedFailure
            phase = .finished
            return result
        }
        guard phase != .cancelled, !Task.isCancelled else {
            phase = .finished
            return .cancelled
        }
        do { try await validate(record.xml) }
        catch {
            let result: Outcome = (phase == .cancelled || Task.isCancelled) ? .cancelled : .validationFailed
            phase = .finished
            return result
        }
        guard phase != .cancelled, !Task.isCancelled else {
            phase = .finished
            return .cancelled
        }
        // No await between the final cancellation check, claiming promotion and
        // the synchronous commit. A later cancellation cannot undo a rename.
        phase = .committing
        defer { phase = .finished }
        do {
            // Detect a change observed since validation began. The held lease
            // remains required; this comparison is not an atomic file CAS.
            guard try readTarget() == previous else { return .recoveryRequired }
            try commit(record)
            guard try readTarget() == record.xml else { return .recoveryRequired }
            return .committed
        } catch {
            return reconcileAfterFailure(previous: previous, readTarget: readTarget)
        }
    }

    private func reconcileAfterFailure(previous: Data?,
                                       readTarget: @MainActor () throws -> Data?) -> Outcome {
        do { return try readTarget() == previous ? .unchangedFailure : .recoveryRequired }
        catch { return .recoveryRequired }
    }
}
