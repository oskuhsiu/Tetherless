// SPDX-License-Identifier: AGPL-3.0-only
#if os(iOS)
import SwiftUI
@preconcurrency import UIKit
import UniformTypeIdentifiers

/// A real UIKit picker, owned by one stable request. The additional presenter
/// keeps UIKit's automatic picker dismissal from removing SwiftUI's coordinator
/// before UIKit delivers its selection. No imported copy or original-file edit.
@available(iOS 17.0, *)
@MainActor
struct PairingDocumentPicker: UIViewControllerRepresentable {
    let request: PairingImportRequest
    let contentTypes: [UTType]
    let onResolve: @MainActor (PairingImportRequest, PairingImportFlow.Outcome) -> Void
    let onAbandon: @MainActor (PairingImportRequest) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(request: request, onResolve: onResolve, onAbandon: onAbandon)
    }
    func makeUIViewController(context: Context) -> PickerHostController {
        PairingImportDiagnostic.pickerCreated.record()
        let plistAllowed = UTType(filenameExtension: "plist").map { type in
            contentTypes.contains { type.conforms(to: $0) }
        } ?? false
        (plistAllowed ? PairingImportDiagnostic.plistTypeAllowed : .plistTypeNotAllowed).record()
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: contentTypes, asCopy: false)
        picker.allowsMultipleSelection = false
        picker.shouldShowFileExtensions = true
        picker.modalPresentationStyle = .fullScreen
        picker.delegate = context.coordinator
        context.coordinator.bind(picker)
        return PickerHostController(picker: picker, coordinator: context.coordinator)
    }
    func updateUIViewController(_ host: PickerHostController, context: Context) {
        // Never present again or replace the delegate on a readiness/UI update.
    }
    static func dismantleUIViewController(_ host: PickerHostController, coordinator: Coordinator) {
        // Anticipated removal is not evidence of completed dismissal. This can
        // release an unresolved request, but must never start a selected import.
        coordinator.invalidate()
    }

    @MainActor final class PickerHostController: UIViewController {
        private let picker: UIDocumentPickerViewController
        private let coordinator: Coordinator
        private var presentedPicker = false
        private let recovery = UIStackView()
        init(picker: UIDocumentPickerViewController, coordinator: Coordinator) {
            self.picker = picker; self.coordinator = coordinator
            super.init(nibName: nil, bundle: nil)
        }
        required init?(coder: NSCoder) { fatalError("Programmatic picker presenter only") }
        override func viewDidLoad() {
            super.viewDidLoad()
            view.backgroundColor = .systemBackground
            let message = UILabel()
            message.text = "No document result has arrived. You can return to setup without importing."
            message.numberOfLines = 0
            message.textAlignment = .center
            let close = UIButton(type: .system)
            close.setTitle("Return to setup", for: .normal)
            close.accessibilityIdentifier = "pairing.returnToSetup"
            close.addTarget(self, action: #selector(returnToSetup), for: .touchUpInside)
            recovery.axis = .vertical; recovery.spacing = 16
            recovery.addArrangedSubview(message); recovery.addArrangedSubview(close)
            recovery.translatesAutoresizingMaskIntoConstraints = false
            recovery.isHidden = true
            view.addSubview(recovery)
            NSLayoutConstraint.activate([
                recovery.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 24),
                recovery.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -24),
                recovery.centerYAnchor.constraint(equalTo: view.safeAreaLayoutGuide.centerYAnchor)
            ])
        }
        override func viewDidAppear(_ animated: Bool) {
            super.viewDidAppear(animated)
            guard !presentedPicker else {
                // Disappearance is not cancellation. A user can explicitly
                // abandon an unresolved result if the real picker has closed.
                recovery.isHidden = presentedViewController != nil || !coordinator.hasPendingResult
                return
            }
            presentedPicker = true
            present(picker, animated: true)
            picker.presentationController?.delegate = coordinator
        }
        @objc private func returnToSetup() {
            guard presentedPicker, presentedViewController == nil, coordinator.hasPendingResult else { return }
            recovery.isHidden = true
            coordinator.invalidate()
        }
    }

    @MainActor final class Coordinator: NSObject, UIDocumentPickerDelegate, UIAdaptivePresentationControllerDelegate {
        private weak var picker: UIDocumentPickerViewController?
        private let relay: PairingImportResultRelay
        init(request: PairingImportRequest,
             onResolve: @escaping @MainActor (PairingImportRequest, PairingImportFlow.Outcome) -> Void,
             onAbandon: @escaping @MainActor (PairingImportRequest) -> Void) {
            relay = PairingImportResultRelay(request: request, onResolve: { request, outcome in
                PairingImportDiagnostic.resultDelivered.record()
                onResolve(request, outcome)
            }, onAbandon: onAbandon)
        }
        var hasPendingResult: Bool { relay.isPending }
        func bind(_ picker: UIDocumentPickerViewController) { self.picker = picker }
        func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
            guard controller === picker else { return }
            PairingImportDiagnostic.selectionReceived.record()
            let outcome = PairingImportFlow.Outcome.pickedDocuments(urls)
            if outcome == .invalidSelection { PairingImportDiagnostic.invalidSelection.record() }
            finish(outcome)
        }
        func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
            guard controller === picker else { return }
            PairingImportDiagnostic.cancellationReceived.record()
            finish(.cancelled)
        }
        func presentationControllerDidDismiss(_ presentationController: UIPresentationController) {
            guard presentationController.presentedViewController === picker else { return }
            // UIKit documents this as the completed interactive-dismissal hook;
            // programmatic dismissal does not call it. It is explicit cancellation,
            // unlike SwiftUI's cover onDismiss which also follows selection.
            PairingImportDiagnostic.cancellationReceived.record()
            finish(.cancelled)
        }
        func invalidate() {
            PairingImportDiagnostic.coordinatorInvalidated.record()
            picker?.delegate = nil
            picker?.presentationController?.delegate = nil
            picker = nil
            relay.invalidate()
        }
        private func finish(_ outcome: PairingImportFlow.Outcome) {
            if !relay.resolve(outcome) { PairingImportDiagnostic.lateCallbackIgnored.record() }
        }
    }
}
#endif
