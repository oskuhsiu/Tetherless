// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
@preconcurrency import UIKit

/// Independent from the inherited certificate/Anisette Keychain service. Its
/// signed-out tombstone survives legacy cleanup and is never bypassed by it.
enum NativeAuthenticationStore {
    static func make() throws -> VerifiedAuthenticationStore {
        try VerifiedAuthenticationStore(storage: KeychainAuthenticationStorage(
            service: "org.tetherless.session." + Bundle.Info.appbundleIdentifier))
    }
    static func ready() throws -> AuthenticationRecord { try make().requireReady() }
    static func prefillingCredentials() -> AuthenticationCredentials? {
        (try? make().read())?.credentials
    }
    static func assertCurrent(_ record: AuthenticationRecord) throws {
        guard try ready().generation == record.generation else {
            throw AuthenticationStorageFailure.staleAttempt
        }
    }
    @MainActor static func showFailure(_ error: Error) {
        guard let top = UIApplication.shared.topViewController() else { return }
        let detail: String
        if let failure = error as? AuthenticationStorageFailure {
            detail = failure.localizedDescription
        } else {
            detail = "The account operation did not complete. Another operation may be running, or local storage may be unavailable. Retry after it finishes."
        }
        let alert = UIAlertController(title: "Account needs attention", message: detail, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default))
        top.present(alert, animated: true)
    }
}
