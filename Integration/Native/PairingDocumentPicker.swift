// SPDX-License-Identifier: AGPL-3.0-only
#if os(iOS)
import SwiftUI
@preconcurrency import UIKit
import UniformTypeIdentifiers

/// A concrete UIKit picker, owned by a stable request rather than a Form's
/// fileImporter Boolean. It grants read access only; never copies into a public Inbox or edits the original.
@available(iOS 17.0, *)
@MainActor
struct PairingDocumentPicker: UIViewControllerRepresentable {
    let request: PairingImportRequest
    let contentTypes: [UTType]
    let onResolve: @MainActor (PairingImportRequest, PairingImportFlow.Outcome) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(request: request, onResolve: onResolve) }
    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        PairingImportDiagnostic.pickerCreated.record()
        let plistAllowed = UTType(filenameExtension: "plist").map { type in
            contentTypes.contains { type.conforms(to: $0) }
        } ?? false
        (plistAllowed ? PairingImportDiagnostic.plistTypeAllowed : .plistTypeNotAllowed).record()
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: contentTypes, asCopy: false)
        picker.allowsMultipleSelection = false
        picker.shouldShowFileExtensions = true
        picker.delegate = context.coordinator
        return picker
    }
    func updateUIViewController(_ picker: UIDocumentPickerViewController, context: Context) {
        // Never present again or replace the delegate on a readiness/UI update.
    }
    static func dismantleUIViewController(_ picker: UIDocumentPickerViewController, coordinator: Coordinator) {
        coordinator.invalidate()
        picker.delegate = nil
    }

    @MainActor final class Coordinator: NSObject, UIDocumentPickerDelegate {
        private let request: PairingImportRequest
        private var onResolve: (@MainActor (PairingImportRequest, PairingImportFlow.Outcome) -> Void)?
        init(request: PairingImportRequest,
             onResolve: @escaping @MainActor (PairingImportRequest, PairingImportFlow.Outcome) -> Void) {
            self.request = request; self.onResolve = onResolve
        }
        func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
            PairingImportDiagnostic.selectionReceived.record()
            guard urls.count == 1, let url = urls.first, url.isFileURL else {
                PairingImportDiagnostic.invalidSelection.record()
                finish(.invalidSelection); return
            }
            finish(.selected(url))
        }
        func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
            PairingImportDiagnostic.cancellationReceived.record()
            finish(.cancelled)
        }
        func invalidate() {
            PairingImportDiagnostic.coordinatorInvalidated.record()
            onResolve = nil
        }
        private func finish(_ outcome: PairingImportFlow.Outcome) {
            // Clear BEFORE calling into SwiftUI. A reentrant/late delegate event
            // cannot dispatch a second import or cancel a newer request.
            let callback = onResolve
            onResolve = nil
            (callback == nil ? PairingImportDiagnostic.lateCallbackIgnored : .resultDelivered).record()
            callback?(request, outcome)
        }
    }
}
#endif
