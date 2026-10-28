// SPDX-License-Identifier: AGPL-3.0-only
#if os(iOS)
import UIKit
import SideSign

/// No automatic/default selection, including a free Personal Team. Selecting
/// one exact certificate leads to a SECOND destructive confirmation.
@MainActor
enum NativeCertificateQuotaPrompt {
    static func choose(certificates: [ALTX509Certificate], teamID: String, presenter: UIViewController) async throws -> RevokeDecision {
        guard certificates.count <= 128, !teamID.isEmpty, teamID.utf8.count <= 128 else { throw AuthenticationStorageFailure.invalidRecord }
        guard !Task.isCancelled, presenter.viewIfLoaded?.window != nil, presenter.presentedViewController == nil else { return .keepExisting }
        let completion = Completion()
        return await withTaskCancellationHandler {
          await withCheckedContinuation { continuation in
            completion.install(continuation)
            guard !completion.finished else { return }
            let chooser = UIAlertController(title: "Certificate limit — choose how to continue",
                message: "Team: \(teamID)\nAlready have a P12 containing its private key? Keep existing certificates and import it in Auto Renewal → Signing material, then retry setup. A public .cer alone cannot restore a missing private key. Nothing is selected or revoked automatically.", preferredStyle: .alert)
            chooser.addAction(UIAlertAction(title: "Keep certificates / use my P12", style: .cancel) { _ in
                completion.finish(.keepExisting)
            })
            for certificate in certificates {
                let serial = certificate.serialNumber
                let title = "Review serial \(serial)"
                chooser.addAction(UIAlertAction(title: title, style: .default) { _ in
                    chooser.dismiss(animated: true) {
                        guard !completion.finished, presenter.viewIfLoaded?.window != nil, presenter.presentedViewController == nil else { completion.finish(.keepExisting); return }
                        let expiry = ISO8601DateFormatter().string(from: certificate.expiryDate)
                        let confirm = UIAlertController(title: "Revoke exactly this certificate?",
                            message: "Team: \(teamID)\nSerial: \(serial)\nExpires: \(expiry)\n\nRevocation invalidates profiles using this certificate and may stop installed apps signed by it, including Tetherless or apps on other devices. The private key does not undo revocation. If confirmed, setup will attempt ONE replacement request; that may fail. No other certificate is selected.", preferredStyle: .alert)
                        confirm.addAction(UIAlertAction(title: "Keep certificate", style: .cancel) { _ in completion.finish(.keepExisting) })
                        confirm.addAction(UIAlertAction(title: "Revoke this serial and request replacement", style: .destructive) { _ in
                            completion.finish(.revokeSelected([certificate]))
                        })
                        completion.alert = confirm
                        presenter.present(confirm, animated: true)
                        confirm.presentationController?.delegate = completion
                    }
                })
            }
            completion.alert = chooser
            presenter.present(chooser, animated: true)
            chooser.presentationController?.delegate = completion
          }
        } onCancel: {
            Task { @MainActor in completion.finish(.keepExisting, dismiss: true) }
        }
    }
    @MainActor private final class Completion: NSObject, UIAdaptivePresentationControllerDelegate {
        var alert: UIAlertController?
        private var continuation: CheckedContinuation<RevokeDecision, Never>?
        private var observer: NSObjectProtocol?
        private(set) var finished = false
        func install(_ value: CheckedContinuation<RevokeDecision, Never>) {
            if finished { value.resume(returning: .keepExisting); return }
            continuation = value
            observer = NotificationCenter.default.addObserver(forName: UIApplication.didEnterBackgroundNotification,
                object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in self?.finish(.keepExisting, dismiss: true) }
            }
        }
        func finish(_ decision: RevokeDecision, dismiss: Bool = false) {
            guard !finished else { return }; finished = true
            if let observer { NotificationCenter.default.removeObserver(observer); self.observer = nil }
            if dismiss { alert?.dismiss(animated: false) }; alert = nil
            let value = continuation; continuation = nil; value?.resume(returning: decision)
        }
        func presentationControllerDidDismiss(_ presentationController: UIPresentationController) {
            finish(.keepExisting)
        }
    }
}
#endif
