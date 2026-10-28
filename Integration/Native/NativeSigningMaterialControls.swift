// SPDX-License-Identifier: AGPL-3.0-only
#if os(iOS)
import SwiftUI
import UniformTypeIdentifiers
import SideSign

@available(iOS 17.0, *)
struct NativeSigningMaterialControls: View {
    var body: some View {
        SwiftUI.Section {
            SwiftUI.NavigationLink("Import or back up signing material") { NativeSigningMaterialScreen() }
                .accessibilityIdentifier("signingMaterial.open")
            Text("Have an existing P12? Import it instead of creating another certificate. Newly issued keys remain in this device's Keychain even if later profile preparation fails; back them up here.")
        } header: { Text("Signing material") }
    }
}

@available(iOS 17.0, *)
private struct SigningBackupDocument: FileDocument {
    static var readableContentTypes: [UTType] { [.folder] }
    var wrapper: FileWrapper
    init(wrapper: FileWrapper) { self.wrapper = wrapper }
    init(configuration: ReadConfiguration) throws { wrapper = configuration.file }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper { wrapper }
}

@available(iOS 17.0, *)
private struct NativeSigningMaterialScreen: View {
    @State private var certificates: [ALTCertificate] = []
    @State private var selected = ""
    @State private var importPassword = ""
    @State private var exportPassword = ""
    @State private var confirmationPassword = ""
    @State private var showImport = false
    @State private var showExport = false
    @State private var document: SigningBackupDocument?
    @State private var status = ""
    @State private var working = false
    @State private var generation = UUID()
    @State private var operation: Task<Void, Never>?

    var body: some View {
        SwiftUI.Form {
            SwiftUI.Section {
                SecureField("P12 password", text: $importPassword).textContentType(.password)
                    .accessibilityIdentifier("signingMaterial.importPassword")
                SwiftUI.Button("Import existing P12") { showImport = true }
                    .disabled(working).accessibilityIdentifier("signingMaterial.import")
                Text("The file and password stay on this device. Import saves the matching private key in Keychain; it does not contact Apple, revoke anything, select an active signer or enable automatic renewal. Continue setup afterwards to verify the selected Team and reuse it.")
            } header: { Text("Already have a certificate?") }
            SwiftUI.Section {
                SwiftUI.Picker("Certificate", selection: $selected) {
                    Text("Select a certificate").tag("")
                    ForEach(certificates, id: \.serialNumber) { certificate in
                        Text("Serial \(certificate.serialNumber)").tag(certificate.serialNumber)
                    }
                }.disabled(working)
                if let certificate = certificates.first(where: { $0.serialNumber == selected }) {
                    Text("Expires \(certificate.x509.expiryDate.formatted())")
                }
                SecureField("New backup password (12+ characters)", text: $exportPassword)
                    .accessibilityIdentifier("signingMaterial.exportPassword")
                SecureField("Repeat backup password", text: $confirmationPassword)
                SwiftUI.Button("Save encrypted P12 and available profiles") { exportBackup() }
                    .disabled(working || selected.isEmpty).accessibilityIdentifier("signingMaterial.export")
                Text("The backup includes an encrypted private key and matching profiles from this running app only. Profiles may contain device identifiers and may be expired. Choose the destination yourself and keep the password separately. Cancelling Save creates no user backup; the original Keychain entry is retained.")
            } header: { Text("Back up before leaving setup") }
            SwiftUI.Section {
                Text(status).accessibilityIdentifier("signingMaterial.status")
                SwiftUI.Button("Reload saved certificates") { reload() }.disabled(working)
                Text("Local signing is not installation: the app's existing signing pipeline can re-sign an IPA with a matching key and valid profiles. Replacing the running manager additionally uses the configured device installation channel and reconciliation. A P12 alone cannot bootstrap an unsigned first install or extend Apple's profile expiry; real-device acceptance is still required.")
            }
        }
        .navigationTitle("Signing material")
        .task { reload() }
        .fileImporter(isPresented: $showImport, allowedContentTypes: [.data], allowsMultipleSelection: false) { result in
            importFile(result)
        }
        .fileExporter(isPresented: $showExport, document: document, contentType: .folder,
                      defaultFilename: "Tetherless-signing-backup") { result in
            document = nil; working = false
            switch result {
            case .success: status = "Encrypted backup saved. Keep its password separately; the original signing key was not changed."
            case .failure: status = "Backup was not saved. The original signing key remains in Keychain."
            }
        }
        .onChange(of: showExport) { _, presented in
            // The system exporter owns its document value while presented.
            // Cancellation may dismiss it without a completion callback.
            if !presented { document = nil; working = false }
        }
        .onDisappear {
            operation?.cancel(); operation = nil; generation = UUID()
            importPassword = ""; exportPassword = ""; confirmationPassword = ""
            document = nil; certificates = []; working = false
        }
    }
    private func reload() {
        guard !working else { return }
        // Existing registry is metadata only; each private entry is checked.
        let values: [ALTCertificate]
        do { values = try CertificateManager.shared.getAllLocalCertificatesVerified() }
        catch { certificates = []; selected = ""; status = "Keychain could not be read. This is not evidence that your signing keys are missing."; return }
        certificates = values
        if !values.contains(where: { $0.serialNumber == selected }) { selected = "" }
        status = values.isEmpty ? "No readable saved signing key. A public .cer or IPA cannot restore a lost private key." : "Choose a saved certificate to back up. No Apple request was made."
    }
    private func importFile(_ result: Result<[URL], Error>) {
        guard !working, case .success(let urls) = result, urls.count == 1, let url = urls.first else {
            importPassword = ""; status = "Import cancelled; existing signing material was unchanged."; return
        }
        let password = importPassword; importPassword = ""; working = true
        let current = UUID(); generation = current
        operation = Task { @MainActor in
            let task = Task.detached {
                let scoped = url.startAccessingSecurityScopedResource()
                defer { if scoped { url.stopAccessingSecurityScopedResource() } }
                guard let bytes = try PrivateFileStore.readExternal(url, maximum: 32_768) else { throw CertificateExportFailure.unavailable }
                try Task.checkCancellation()
                return try NativeSigningMaterial.importP12(bytes, password: password)
            }
            do {
                let serial = try await withTaskCancellationHandler { try await task.value } onCancel: { task.cancel() }
                guard !Task.isCancelled, generation == current else { return }
                working = false; reload(); selected = serial
                status = "P12 saved and verified locally. Continue setup to verify current-Team membership and reuse it. No certificate was created or revoked."
            } catch {
                guard generation == current else { return }; working = false; status = safeMessage(error)
            }
            operation = nil
        }
    }
    private func exportBackup() {
        guard !working, !selected.isEmpty else { return }
        let serial = selected, password = exportPassword, confirmation = confirmationPassword
        exportPassword = ""; confirmationPassword = ""; working = true
        let current = UUID(); generation = current
        status = "Encrypting locally. No signing material is uploaded."
        operation = Task { @MainActor in
            let task = Task.detached { try NativeSigningMaterial.backup(serial: serial, password: password, confirmation: confirmation) }
            do {
                let files = try await withTaskCancellationHandler { try await task.value } onCancel: { task.cancel() }
                guard !Task.isCancelled, generation == current else { return }
                document = SigningBackupDocument(wrapper: FileWrapper(directoryWithFileWrappers: files.mapValues { FileWrapper(regularFileWithContents: $0) }))
                status = "Choose a destination for the encrypted backup. Cancelling keeps the original Keychain identity."
                showExport = true
            } catch {
                guard generation == current else { return }; working = false; status = safeMessage(error)
            }
            operation = nil
        }
    }
    private func safeMessage(_ error: Error) -> String {
        (error as? CertificateExportFailure)?.localizedDescription ?? "Signing material could not be read or saved. No certificate was created or revoked; existing keys were not reported as changed."
    }
}
#endif
