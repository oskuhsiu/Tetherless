// SPDX-License-Identifier: AGPL-3.0-only
#if os(iOS)
import SwiftUI
import SideSign

@available(iOS 17.0, *)
struct NativeCertificateRecoveryControls: View {
    var body: some View {
        SwiftUI.Section {
            SwiftUI.NavigationLink {
                NativeCertificateRecoveryScreen()
            } label: { Text("Certificate request recovery") }
            .accessibilityIdentifier("recovery.open")
            Text("Inspect an interrupted request without creating another certificate. Recovery never changes the active signer automatically.")
        } header: { Text("Signing request recovery") }
    }
}

@available(iOS 17.0, *)
private struct NativeCertificateRecoveryScreen: View {
    private struct Confirmation {
        let id: UUID
        let type: CertificateType
        let action: CertificateRecoveryAction
        let title: String
    }
    @State private var typeID = CertificateType.development.rawValue
    @State private var observation: CertificateRecoveryObservation?
    @State private var status = "Reading local request..."
    @State private var result = ""
    @State private var operation: Task<Void, Never>?
    @State private var generation = UUID()
    @State private var working = false
    @State private var confirmation: Confirmation?
    @State private var showConfirmation = false

    var body: some View {
        SwiftUI.Form {
            SwiftUI.Section {
                SwiftUI.Picker("Certificate type", selection: $typeID) {
                    ForEach(CertificateType.allCases, id: \.rawValue) { type in
                        Text(type.displayName).tag(type.rawValue)
                    }
                }.disabled(working)
                Text(status).accessibilityIdentifier("recovery.status")
                SwiftUI.Button("Reload local request") { reload() }
                    .disabled(working).accessibilityIdentifier("recovery.reload")
                Text("Reload only reads the current account's local request. It does not contact Apple.")
            } header: { Text("Saved request") }
            SwiftUI.Section {
                SwiftUI.Button("Check saved request") { check() }
                    .disabled(working || observation?.requestID == nil)
                    .accessibilityIdentifier("recovery.check")
                Text("Only queries an already-submitted request or validates an existing saved response. It never submits an application, saves a key or changes signing selection.")
            } header: { Text("Read-only check") }
            SwiftUI.Section {
                SwiftUI.Button("Save recovered certificate") { confirm(.saveExisting, title: "Save recovered certificate?") }
                    .disabled(working || observation?.canSave != true).accessibilityIdentifier("recovery.save")
                SwiftUI.Button("Submit prepared request") { confirm(.submitPrepared, title: "Submit this prepared request to Apple?") }
                    .disabled(working || observation?.canSubmit != true).accessibilityIdentifier("recovery.submit")
                SwiftUI.Button("Discard never-submitted request", role: .destructive) {
                    confirm(.discardPrepared, title: "Discard this never-submitted request?")
                }.disabled(working || observation?.canDiscard != true).accessibilityIdentifier("recovery.discard")
                Text("A possibly submitted request cannot be resent or discarded. A missing result may need another check later; its key is retained. No existing certificate is revoked.")
                if !result.isEmpty { Text(result).accessibilityIdentifier("recovery.result") }
            } header: { Text("Explicit actions") }
        }
        .navigationTitle("Certificate recovery")
        .task(id: typeID) { reload() }
        .onDisappear {
            operation?.cancel(); operation = nil; generation = UUID()
            working = false; observation = nil; confirmation = nil; showConfirmation = false
        }
        .confirmationDialog("Confirm certificate recovery", isPresented: $showConfirmation, presenting: confirmation) { value in
            SwiftUI.Button(value.title, role: value.action == .discardPrepared ? .destructive : nil) { resolve(value) }
            SwiftUI.Button("Cancel", role: .cancel) {}
        } message: { value in
            Text(value.action == .discardPrepared
                 ? "Only the exact never-dispatched request and its private key will be removed. A submitted request is never eligible. This does not delete installed apps or other certificates."
                 : "This is an explicit foreground action for the saved request. It preserves the existing active signer and automatic-renewal consent. Continue setup separately after material is saved.")
        }
    }

    private func selectedType() throws -> CertificateType {
        guard let type = CertificateType.allCases.first(where: { $0.rawValue == typeID }) else {
            throw CertificateIssuanceFailure.invalidRecord
        }
        return type
    }
    private func reload() {
        guard !working else { return }
        generation = UUID(); observation = nil; result = ""
        do { display(try NativeCertificateRecovery.local(type: selectedType())) }
        catch { status = message(error) }
    }
    private func display(_ value: CertificateRecoveryObservation) {
        observation = value
        switch value.state {
        case .none: status = "No pending request for this account and certificate type."
        case .prepared: status = "Prepared locally; never submitted. Submit or discard only after confirmation."
        case .submitted: status = "Submission may have reached Apple. Check before saving; do not create again."
        case .awaitingPortal: status = "No matching certificate is visible yet. The original request and private key are retained."
        case .available: status = "One matching certificate was found. Nothing was saved or activated by this check."
        case .issued: status = "An issued response is saved locally. Its key can be recovered; this is not a fresh Apple-status check."
        }
    }
    private func confirm(_ action: CertificateRecoveryAction, title: String) {
        guard !working, let id = observation?.requestID, let type = try? selectedType() else { return }
        // Freeze the exact request and type at the button press, not at dialog dismissal.
        confirmation = Confirmation(id: id, type: type, action: action, title: title)
        showConfirmation = true
    }
    private func check() {
        guard let id = observation?.requestID, let type = try? selectedType() else { return }
        run {
            let value = try await DeveloperPortalProxy.shared.checkCertificateRequest(type: type, expectedID: id)
            return (value, "Check finished. No request, signing key or active signer was changed.")
        }
    }
    private func resolve(_ value: Confirmation) {
        run {
            if value.action == .discardPrepared {
                try NativeCertificateRecovery.discardPrepared(type: value.type, expectedID: value.id)
            } else {
                try await DeveloperPortalProxy.shared.resolveCertificateRequest(type: value.type, expectedID: value.id, action: value.action)
            }
            let current = try NativeCertificateRecovery.local(type: value.type)
            return (current, value.action == .discardPrepared
                    ? "The never-submitted request was discarded. Other certificates and installed apps were not changed."
                    : "Signing material was saved and read back. The active signer and renewal consent were not changed; continue setup separately.")
        }
    }
    private func run(_ body: @escaping @MainActor () async throws -> (CertificateRecoveryObservation, String)) {
        guard !working else { return }
        working = true; let current = UUID(); generation = current; result = ""
        operation = Task { @MainActor in
            defer { if generation == current { working = false; operation = nil } }
            do {
                let (value, text) = try await body()
                guard !Task.isCancelled, generation == current else { return }
                display(value); result = text
            } catch {
                guard generation == current else { return }
                observation = nil; status = message(error)
            }
        }
    }
    private func message(_ error: Error) -> String {
        if let error = error as? AuthenticationStorageFailure, error == .notReady {
            return "Sign in to inspect requests for this account."
        }
        if let error = error as? CertificateIssuanceFailure { return error.localizedDescription }
        if let error = error as? AuthenticationStorageFailure { return error.localizedDescription }
        if error is CancellationError { return "Operation cancelled. Reload the saved request before deciding what to do next." }
        return "Recovery could not finish. Reload or repair your session and check again; no automatic replacement was requested."
    }
}
#endif
