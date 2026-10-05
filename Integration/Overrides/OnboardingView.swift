// Derived from SideStore OnboardingView.swift, Copyright © 2026 SideStore.
// Tetherless: explicit setup, honest readiness and accessible navigation.
// SPDX-License-Identifier: AGPL-3.0-only
#if os(iOS)
import SwiftUI
@preconcurrency import UIKit
import UniformTypeIdentifiers

@available(iOS 17.0, *)
struct OnboardingView: View {
    var onFinish: (() -> Void)? = nil
    @AppStorage(SetupStep.storageKey) private var savedStep = SetupStep.welcome.rawValue
    private var step: SetupStep { .resuming(savedStep) }
    @State private var working = false
    @State private var pairingRequest: PairingImportRequest?
    // Physical cover ownership outlives logical abandonment. Do not bind an
    // old cover's onDismiss to whichever request the flow later happens to own.
    @State private var pairingPresentation: PairingImportRequest?
    @State private var pairingImport = PairingImportFlow()
    // A closed, value-free category from the actual import catch. It never
    // contains an error description, document URL, pairing data or identifier.
    private enum PairingImportFailure: String {
        case invalidContent = "pairing/invalidContent"
        case otherFailure = "pairing/otherFailure"
        init(_ error: Error) {
            self = (error as? PrivateFileError) == .invalidContent ? .invalidContent : .otherFailure
        }
    }
    @State private var pairingImportFailure: PairingImportFailure?
    @State private var status: String?
    @State private var readiness = SetupReadiness()
    @State private var observationGeneration = UUID()
    @AppStorage("tetherless.autorenew.enabled") private var renewalPermitted = false

    #if TETHERLESS_BOUNDED_PAIRING_HOST && TETHERLESS_STAGED_PAIRING_VALIDATION && canImport(IDevice) && canImport(IdeviceGateway)
    @State private var hostPairingRequest: PairingSetupRequest?
    @State private var hostPairingPresentation: PairingSetupRequest?
    #endif
    private var pairingBusy: Bool {
        #if TETHERLESS_BOUNDED_PAIRING_HOST && TETHERLESS_STAGED_PAIRING_VALIDATION && canImport(IDevice) && canImport(IdeviceGateway)
        if hostPairingPresentation != nil { return true }
        #endif
        return pairingImport.isBusy || pairingPresentation != nil
    }

    var body: some View {
        #if TETHERLESS_BOUNDED_PAIRING_HOST && TETHERLESS_STAGED_PAIRING_VALIDATION && canImport(IDevice) && canImport(IdeviceGateway)
        let hostDismissalRequest = hostPairingPresentation
        return existingBody.fullScreenCover(item: $hostPairingRequest, onDismiss: {
            guard let hostDismissalRequest, hostPairingPresentation == hostDismissalRequest else { return }
            hostPairingPresentation = nil
            Task { @MainActor in await reload() }
        }) { request in
            PairingSetupView { outcome in
                guard hostPairingRequest == request, hostPairingPresentation == request else { return }
                hostPairingRequest = nil
                switch outcome {
                case .saved: status = "Pairing record saved after checking this app's protected container. Saving does not establish that the running connection is using this record. Connection and renewal remain unverified."
                case .cancelled: status = "Pairing cancelled. Existing pairing was retained."
                case .recoveryRequired: status = "Saving may have completed. Recheck stored pairing before trying again."
                default: status = "Pairing could not be completed. Existing pairing was retained."
                }
                Task { @MainActor in await reload() }
            }
        }
        #else
        return existingBody
        #endif
    }

    private var existingBody: some View {
        let dismissalRequest = pairingPresentation
        return SwiftUI.NavigationStack {
            SwiftUI.Form {
                SwiftUI.Section {
                    Text(step.title).font(.title2.bold())
                        .accessibilityIdentifier("onboarding.title")
                    Text("Step \(step.ordinal) of \(SetupStep.allCases.count)")
                        .foregroundStyle(.secondary)
                }
                content
                if let status {
                    SwiftUI.Section {
                        Text(status).accessibilityIdentifier("onboarding.status")
                            .accessibilityValue(pairingImportFailure?.rawValue ?? "")
                    }
                }
            }
            .navigationTitle("Tetherless")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    if step != .welcome {
                        SwiftUI.Button("Back") { move(-1) }
                            .disabled(working || pairingBusy).accessibilityIdentifier("onboarding.back")
                    }
                }
            }
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 10) {
                    if step == .review {
                        SwiftUI.Button("Open Tetherless") { finish() }
                            .buttonStyle(.borderedProminent).disabled(working || pairingBusy)
                            .accessibilityIdentifier("onboarding.finish")
                    } else {
                        SwiftUI.Button(step == .welcome ? "Get started" : "Continue") { move(1) }
                            .buttonStyle(.borderedProminent)
                            .disabled(working || pairingBusy || (step == .pairing && !readiness.pairingStored) ||
                                      (step == .account && !readiness.accountStored))
                            .accessibilityIdentifier("onboarding.next")
                        if step == .pairing || step == .connection || step == .account {
                            SwiftUI.Button("Set up later") { move(1) }
                                .disabled(working || pairingBusy).accessibilityIdentifier("onboarding.later")
                        }
                    }
                }
                .frame(maxWidth: .infinity).padding().background(.regularMaterial)
            }
            .interactiveDismissDisabled(working || pairingBusy)
            .task(id: step) { await reload() }
            .onReceive(NotificationCenter.default.publisher(for: UIApplication.didBecomeActiveNotification)) { _ in
                Task { @MainActor in await reload() }
            }
        }
        .fullScreenCover(item: $pairingRequest, onDismiss: {
            PairingImportDiagnostic.coverDismissed.record()
            guard let dismissalRequest, pairingPresentation == dismissalRequest else {
                PairingImportDiagnostic.dismissalUnbound.record(); return
            }
            pairingPresentation = nil
            finishPairingSelection(dismissalRequest)
        }) { request in
            PairingDocumentPicker(request: request, contentTypes: PairingFileManager.supportedContentTypes) { resolved, outcome in
                guard pairingImport.resolve(outcome, request: resolved) else {
                    PairingImportDiagnostic.resolutionIgnored.record(); return
                }
                PairingImportDiagnostic.resolutionAccepted.record()
                pairingRequest = nil
                // UIKit may report selection after the cover already dismissed.
                finishPairingSelection(resolved, afterDismissal: false)
            } onAbandon: { abandoned in
                // Owner teardown is explicit abandonment, never a selection or
                // an inference from onDismiss. A delivered result is retained.
                guard pairingImport.abandon(abandoned) else { return }
                pairingRequest = nil
                status = "Import cancelled. Existing pairing was retained."
            }
        }
    }

    @MainActor private func choosePairingFile() {
        guard !working, pairingPresentation == nil, let request = pairingImport.begin() else { return }
        pairingPresentation = request
        PairingImportDiagnostic.requestBegan.record()
        status = nil; pairingImportFailure = nil
        pairingRequest = request
    }

    @MainActor private func finishPairingSelection(_ request: PairingImportRequest,
                                                  afterDismissal: Bool = true) {
        let ready: PairingImportFlow.Outcome?
        if afterDismissal {
            PairingImportDiagnostic.dismissalObserved.record()
            ready = pairingImport.dismissed(request)
        } else {
            ready = pairingImport.consume(request)
        }
        guard let outcome = ready else {
            if afterDismissal { PairingImportDiagnostic.dismissalIgnored.record() }
            return
        }
        switch outcome {
        case .cancelled:
            PairingImportDiagnostic.cancelFinished.record()
            status = "Import cancelled. Existing pairing was retained."
        case .invalidSelection:
            status = "Select one local pairing file. Existing pairing was retained."
        case .selected(let url):
            // The picker has closed before coordinated, bounded reading and protected
            // mutation begin. No mutation lease is held while browsing.
            perform {
                defer { pairingImport.finished(request) }
                PairingImportDiagnostic.importStarted.record()
                do {
                    try PairingFileManager.shared.importPairingFile(from: url)
                    PairingImportDiagnostic.importSucceeded.record()
                } catch {
                    pairingImportFailure = PairingImportFailure(error)
                    PairingImportDiagnostic.importFailed.record()
                    throw error
                }
                status = "Pairing record saved. A live device connection still needs checking."
            }
        }
    }

    @ViewBuilder private var content: some View {
        switch step {
        case .welcome:
            SwiftUI.Section {
                SwiftUI.Label("Your apps, without the cable", systemImage: "arrow.triangle.2.circlepath")
                    .font(.headline)
                Text("Install trusted IPA files using your own Apple Account. Tetherless attempts profile renewal daily, before the seven-day deadline.")
                Text("After this one-time setup, ordinary renewal does not need a computer or an open Tetherless window. iOS execution opportunities and Apple account checks still apply.")
                Text("Independent open-source derivative of SideStore. Not an official SideStore or Apple product.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        case .pairing:
            SwiftUI.Section {
                Text("Import the device's pairing record from your authorized first-install process. A saved record is not proof of a live connection.")
                observedRow("Protected pairing record", present: readiness.pairingStored, component: .pairing)
                SwiftUI.Button("Choose pairing file") { choosePairingFile() }
                    .disabled(working || pairingBusy).accessibilityIdentifier("onboarding.importPairing")
                #if TETHERLESS_BOUNDED_PAIRING_HOST && TETHERLESS_STAGED_PAIRING_VALIDATION && canImport(IDevice) && canImport(IdeviceGateway)
                if PairingSetupModel.supported {
                    SwiftUI.Button(readiness.pairingStored ? "Replace pairing on this iPhone" : "Pair this iPhone") {
                        guard !working, !pairingBusy else { return }
                        status = nil; pairingImportFailure = nil
                        let request = PairingSetupRequest()
                        hostPairingPresentation = request
                        hostPairingRequest = request
                    }
                    .disabled(working || pairingBusy).accessibilityIdentifier("onboarding.wirelessPairing")
                }
                #endif
                Text("Keep pairing files private. Tetherless stores its copy locally and does not upload it. A computer may be needed once for bootstrap on your supported setup.")
            }
        case .connection:
            SwiftUI.Section {
                Text("Use LocalDevVPN for the on-device connection. Opening the helper is an explicit action; Tetherless never silently disables another VPN.")
                SwiftUI.Button("Open LocalDevVPN") {
                    open(URL(string: "localdevvpn://enable?scheme=tetherless")!)
                }.accessibilityIdentifier("onboarding.openVPN")
                SwiftUI.Button("Get LocalDevVPN") {
                    open(URL(string: "https://apps.apple.com/app/localdevvpn/id6755608044")!)
                }
                Text("A successful Open action does not prove the tunnel is working. The later renewal check tests the real connection.")
                observedRow("On-device Anisette selected", present: readiness.localAnisetteSelected)
                SwiftUI.Button("Use on-device Anisette") {
                    perform {
                        try await NativeMutationGate.withLease { UserDefaults.standard.useOnDeviceAnisette = true }
                    }
                }.disabled(working || pairingBusy).accessibilityIdentifier("onboarding.localAnisette")
            }
        case .account:
            SwiftUI.Section {
                Text("Sign in with a dedicated Apple Account and complete Apple's verification. No password or verification code belongs in GitHub issues, chat, or diagnostics.")
                observedRow("Locally saved account", present: readiness.accountStored, component: .account)
                observedRow("Local signing key", present: readiness.signingKeyStored, component: .signingKey)
                SwiftUI.Button(readiness.accountStored ? "Check or repair sign-in" : "Sign in") {
                    perform {
                        try await DatabaseManager.shared.start()
                        _ = try await AuthManager.shared.signIn(
                            presentingViewController: UIApplication.shared.topViewController(),
                            skipResign: false, skipHowTos: true)
                        status = "Sign-in flow finished. Review the actual local prerequisites below."
                    }
                }.disabled(working || pairingBusy).accessibilityIdentifier("onboarding.signIn")
                Text("The first setup may ask to replace the bootstrap-signed manager once. Daily profile renewal does not reinstall Tetherless. New logins retain the session token, not your Apple password.")
            }
        case .automation:
            SwiftUI.Section {
                SwiftUI.Toggle("Allow unattended profile renewal", isOn: $renewalPermitted)
                    .disabled(working || pairingBusy).accessibilityIdentifier("onboarding.allowUnattended")
                    .onChange(of: renewalPermitted) { _, active in
                        if active { NativeRenewalBackground.schedule() }
                        else {
                            NativeRenewalBackground.cancel()
                            Task { await NativeRenewalNotifications.cancel() }
                        }
                    }
                Text("This lets Tetherless use its stored session after the first unlock, including while the screen is locked. It cannot bypass a new Apple sign-in or 2FA request.")
                Text("In Shortcuts: create a daily Time of Day automation, add Renew Managed Apps, and select Run Immediately. Do not add Open App.")
                SwiftUI.Button("Open Shortcuts") { open(URL(string: "shortcuts://")!) }
                    .accessibilityIdentifier("onboarding.openShortcuts")
                Text("Tetherless cannot silently create or inspect your personal automation. The switch alone is not evidence that automatic renewal works.")
                SwiftUI.Button("Allow expiry warnings") {
                    perform {
                        let allowed = await NativeRenewalNotifications.requestPermission()
                        status = allowed ? "Warnings permitted; they are not a renewal scheduler." : "Warnings were not permitted. You can change this in iOS Settings."
                    }
                }
            }
        case .review:
            SwiftUI.Section {
                Text(readiness.title).font(.headline).accessibilityIdentifier("onboarding.readiness")
                Text(readiness.detail).accessibilityIdentifier("onboarding.readinessDetail")
                observedRow("Protected pairing record", present: readiness.pairingStored, component: .pairing)
                observedRow("Locally saved account", present: readiness.accountStored, component: .account)
                observedRow("Local signing key", present: readiness.signingKeyStored, component: .signingKey)
                observedRow("On-device Anisette selected", present: readiness.localAnisetteSelected)
                observedRow("Unattended renewal permitted", present: renewalPermitted)
                Text("Next: use Auto Renewal to run an explicit check, then verify your authorized Shortcut while the screen is locked. A manual check does not count as an unattended run.")
                SwiftUI.Button("Recheck local setup") { Task { @MainActor in await reload() } }
                    .disabled(working || pairingBusy).accessibilityIdentifier("onboarding.recheck")
            }
        }
    }
    private func observedRow(_ title: String, present: Bool,
                             component: SetupObservationIssue.Stage? = nil) -> some View {
        let label = component.map { readiness.observationLabel(for: $0) } ?? (present ? "present" : "missing")
        return SwiftUI.Label("\(title): \(label)",
                             systemImage: label == "present" ? "checkmark.circle" : "exclamationmark.circle")
    }
    @MainActor private func reload() async {
        let generation = UUID()
        observationGeneration = generation
        var facts = SetupReadiness()
        let allowed = renewalPermitted
        let localAnisette = UserDefaults.standard.useOnDeviceAnisette
        do {
            facts = try await NativeMutationGate.withLease {
                SetupReadiness.observing(renewalPermitted: allowed, localAnisetteSelected: localAnisette,
                    account: { try NativeAuthenticationStore.make().read()?.phase == .ready },
                    signer: {
                        let signer = try CertificateManager.shared.loadActiveCertificate()
                        return signer.map { !$0.certificate.privateKey.isEmpty && $0.certificate.expiryDate > Date() } ?? false
                    },
                    pairing: { try PairingFileManager.shared.fetchPairingFileVerified() != nil })
            }
        } catch { facts.recordFailure(error, at: .access) }
        // SwiftUI cancels prior step tasks; a stale result must not replace the
        // current observation or an explicitly changed consent value.
        guard !Task.isCancelled, observationGeneration == generation else { return }
        facts.renewalPermitted = renewalPermitted
        facts.localAnisetteSelected = UserDefaults.standard.useOnDeviceAnisette
        readiness = facts
    }
    @MainActor private func perform(_ operation: @escaping @MainActor () async throws -> Void) {
        guard !working else { return }
        working = true; status = nil; pairingImportFailure = nil
        Task { @MainActor in
            defer { working = false }
            do { try await operation() }
            catch is CancellationError { status = "Cancelled. Existing setup was not marked complete." }
            catch {
                status = (error as? CertificateIssuanceFailure)?.localizedDescription ??
                    "The operation did not complete. Check account, connection, and local storage, then retry."
            }
            await reload()
        }
    }
    @MainActor private func open(_ url: URL) {
        UIApplication.shared.open(url, options: [:]) { success in
            Task { @MainActor in
                if !success { status = "The requested app could not be opened. Install it or continue setup later." }
            }
        }
    }
    private func move(_ delta: Int) {
        guard !working, !pairingBusy, let next = step.moved(by: delta) else { return }
        status = nil; pairingImportFailure = nil; savedStep = next.rawValue
    }
    private func finish() {
        // This flag only dismisses onboarding; it grants no permission and is
        // deliberately absent from SetupReadiness and renewal eligibility.
        UserDefaults.standard.hasCompletedOnboarding = true
        onFinish?()
    }
}
#endif
