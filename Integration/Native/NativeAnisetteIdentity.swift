// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// One device-local identity shared by ODA and the explicitly selected remote
/// provider. No separate setters or fallback through inaccessible Keychain data.
enum NativeAnisetteIdentity {
    private static let admission = AnisettePackageAdmission()

    private static func store() throws -> VerifiedAnisetteIdentityStore {
        VerifiedAnisetteIdentityStore(storage: try KeychainAuthenticationStorage(
            service: "org.tetherless.anisette." + Bundle.Info.appbundleIdentifier,
            account: "identity-v1"))
    }
    private static func legacy() throws -> LegacyAnisetteIdentity {
        try Keychain.shared.readLegacyAnisetteVerified()
    }
    private static func cleanup() throws { try Keychain.shared.removeLegacyAnisetteVerified() }

    static func withIdentity<Value: Sendable>(
        _ fetch: (AnisetteIdentityRecord) async throws -> (Value, Data?)
    ) async throws -> Value {
        try await NativeMutationGate.withLease {
            // An actor can reenter while awaiting a provider; nested lease
            // ownership alone does not exclude another child of the same task.
            let token = try admission.acquire()
            defer { token.release() }
            return try await store().use(readLegacy: legacy, removeLegacy: cleanup, fetch: fetch)
        }
    }

    /// Called only by explicit account/reset commands, never by fetch failure.
    static func reset(keepingIdentifier: Bool) throws {
        try NativeMutationGate.withSynchronousLease {
            let token = try admission.acquire()
            defer { token.release() }
            let vault = try store()
            if keepingIdentifier, try vault.read() == nil {
                _ = try vault.prepare(readLegacy: legacy, removeLegacy: cleanup)
            }
            try vault.reset(keepingIdentifier: keepingIdentifier, removeLegacy: cleanup)
        }
    }
}
