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
        PickerTiming.emit(.dismantle, hostWindowAttached: host.viewIfLoaded?.window != nil)
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
            PickerTiming.emit(.hostDidAppear, hostWindowAttached: viewIfLoaded?.window != nil,
                              pickerWindowAttached: picker.viewIfLoaded?.window != nil,
                              presentedControllerMatches: presentedViewController === picker,
                              alreadyPresented: presentedPicker)
            guard !presentedPicker else {
                // Disappearance is not cancellation. A user can explicitly
                // abandon an unresolved result if the real picker has closed.
                recovery.isHidden = presentedViewController != nil || !coordinator.hasPendingResult
                return
            }
            presentedPicker = true
            PickerTiming.emit(.presentationAttempt, hostWindowAttached: viewIfLoaded?.window != nil,
                              pickerWindowAttached: picker.viewIfLoaded?.window != nil,
                              presentedControllerMatches: presentedViewController === picker,
                              alreadyPresented: presentedPicker)
            present(picker, animated: true) { [weak self, weak picker] in
                guard let self, let picker else { return }
                PickerTiming.emit(.presentationCompleted, hostWindowAttached: self.viewIfLoaded?.window != nil,
                                  pickerWindowAttached: picker.viewIfLoaded?.window != nil,
                                  presentedControllerMatches: self.presentedViewController === picker,
                                  alreadyPresented: self.presentedPicker)
            }
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
            PickerTiming.emit(.delegateSelection, pickerWindowAttached: controller.viewIfLoaded?.window != nil)
            PairingImportDiagnostic.selectionReceived.record()
            let outcome = PairingImportFlow.Outcome.pickedDocuments(urls)
            if outcome == .invalidSelection { PairingImportDiagnostic.invalidSelection.record() }
            finish(outcome)
        }
        func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
            guard controller === picker else { return }
            PickerTiming.emit(.delegateCancellation, pickerWindowAttached: controller.viewIfLoaded?.window != nil)
            PairingImportDiagnostic.cancellationReceived.record()
            finish(.cancelled)
        }
        func presentationControllerDidDismiss(_ presentationController: UIPresentationController) {
            guard presentationController.presentedViewController === picker else { return }
            PickerTiming.emit(.interactiveDismissal, pickerWindowAttached: picker?.viewIfLoaded?.window != nil)
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

/// A second, strictly allowlisted diagnostic channel. It changes no result or
/// lifetime and never accepts document data, request identifiers or error text.
@MainActor private enum PickerTiming {
    enum Event: String {
        case hostDidAppear, presentationAttempt, presentationCompleted
        case delegateSelection, delegateCancellation, interactiveDismissal, dismantle
    }
    static func emit(_ event: Event, hostWindowAttached: Bool? = nil,
                     pickerWindowAttached: Bool? = nil, presentedControllerMatches: Bool? = nil,
                     alreadyPresented: Bool? = nil) {
        let before = ProcessInfo.processInfo.systemUptime * 1_000_000
        let wall = Date().timeIntervalSince1970 * 1_000_000
        let after = ProcessInfo.processInfo.systemUptime * 1_000_000
        guard [before, wall, after].allSatisfy({ $0.isFinite && $0 >= 0 && $0 < 9_007_199_254_740_992 }) else { return }
        var fields: [String: Any] = ["schemaVersion": 1, "source": "app", "event": event.rawValue,
            "processID": Int(ProcessInfo.processInfo.processIdentifier),
            "monotonicBeforeUS": UInt64(before), "unixTimeUS": UInt64(wall), "monotonicAfterUS": UInt64(after)]
        if let hostWindowAttached { fields["hostWindowAttached"] = hostWindowAttached }
        if let pickerWindowAttached { fields["pickerWindowAttached"] = pickerWindowAttached }
        if let presentedControllerMatches { fields["presentedControllerMatches"] = presentedControllerMatches }
        if let alreadyPresented { fields["alreadyPresented"] = alreadyPresented }
        guard let data = try? JSONSerialization.data(withJSONObject: fields, options: [.sortedKeys]),
              data.count <= 1024 else { return }
        // One small write, bounded independently of arbitrary UIKit logging.
        // Leading newline prevents a partial unrelated line swallowing the marker.
        var line = Data("\n[Tetherless.PickerTiming] ".utf8)
        line.append(data); line.append(0x0A)
        try? FileHandle.standardOutput.write(contentsOf: line)
    }
}

#endif
