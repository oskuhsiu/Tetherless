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
    @State private var showImporter = false
    @State private var status: String?
    @State private var readiness = SetupReadiness()
    @AppStorage("tetherless.autorenew.enabled") private var renewalPermitted = false

    var body: some View {
        SwiftUI.NavigationStack {
            SwiftUI.Form {
                SwiftUI.Section {
                    Text(step.title).font(.title2.bold())
                        .accessibilityIdentifier("onboarding.title")
                    Text("Step \(step.ordinal) of \(SetupStep.allCases.count)")
                        .foregroundStyle(.secondary)
                }
                content
                if let status {
                    SwiftUI.Section { Text(status).accessibilityIdentifier("onboarding.status") }
                }
            }
            .navigationTitle("Tetherless")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    if step != .welcome {
                        SwiftUI.Button("Back") { move(-1) }
                            .disabled(working).accessibilityIdentifier("onboarding.back")
                    }
                }
            }
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 10) {
                    if step == .review {
                        SwiftUI.Button("Open Tetherless") { finish() }
                            .buttonStyle(.borderedProminent).disabled(working)
                            .accessibilityIdentifier("onboarding.finish")
                    } else {
                        SwiftUI.Button(step == .welcome ? "Get started" : "Continue") { move(1) }
                            .buttonStyle(.borderedProminent)
                            .disabled(working || (step == .pairing && !readiness.pairingStored) ||
                                      (step == .account && !readiness.accountStored))
                            .accessibilityIdentifier("onboarding.next")
                        if step == .pairing || step == .connection || step == .account {
                            SwiftUI.Button("Set up later") { move(1) }
                                .disabled(working).accessibilityIdentifier("onboarding.later")
                        }
                    }
                }
                .frame(maxWidth: .infinity).padding().background(.regularMaterial)
            }
            .interactiveDismissDisabled(working)
            .task(id: step) { await reload() }
            .onReceive(NotificationCenter.default.publisher(for: UIApplication.didBecomeActiveNotification)) { _ in
                Task { @MainActor in await reload() }
            }
            .fileImporter(isPresented: $showImporter,
                          allowedContentTypes: PairingFileManager.supportedContentTypes,
                          allowsMultipleSelection: false) { result in
                switch result {
                case .success(let urls):
                    guard let url = urls.first else { return }
                    perform {
                        try PairingFileManager.shared.importPairingFile(from: url)
                        status = "Pairing record saved. A live device connection still needs checking."
                    }
                case .failure: status = "The pairing file was not imported. Existing pairing was retained."
                }
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
                observedRow("Protected pairing record", present: readiness.pairingStored)
                SwiftUI.Button("Choose pairing file") { showImporter = true }
                    .disabled(working).accessibilityIdentifier("onboarding.importPairing")
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
                }.disabled(working).accessibilityIdentifier("onboarding.localAnisette")
            }
        case .account:
            SwiftUI.Section {
                Text("Sign in with a dedicated Apple Account and complete Apple's verification. No password or verification code belongs in GitHub issues, chat, or diagnostics.")
                observedRow("Locally saved account", present: readiness.accountStored)
                observedRow("Local signing key", present: readiness.signingKeyStored)
                SwiftUI.Button(readiness.accountStored ? "Check or repair sign-in" : "Sign in") {
                    perform {
                        try await DatabaseManager.shared.start()
                        _ = try await AuthManager.shared.signIn(
                            presentingViewController: UIApplication.shared.topViewController(),
                            skipResign: false, skipHowTos: true)
                        status = "Sign-in flow finished. Review the actual local prerequisites below."
                    }
                }.disabled(working).accessibilityIdentifier("onboarding.signIn")
                Text("The first setup may ask to replace the bootstrap-signed manager once. Daily profile renewal does not reinstall Tetherless. New logins retain the session token, not your Apple password.")
            }
        case .automation:
            SwiftUI.Section {
                SwiftUI.Toggle("Allow unattended profile renewal", isOn: $renewalPermitted)
                    .disabled(working).accessibilityIdentifier("onboarding.allowUnattended")
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
                Text(readiness.detail)
                observedRow("Protected pairing record", present: readiness.pairingStored)
                observedRow("Locally saved account", present: readiness.accountStored)
                observedRow("Local signing key", present: readiness.signingKeyStored)
                observedRow("On-device Anisette selected", present: readiness.localAnisetteSelected)
                observedRow("Unattended renewal permitted", present: renewalPermitted)
                Text("Next: use Auto Renewal to run an explicit check, then verify your authorized Shortcut while the screen is locked. A manual check does not count as an unattended run.")
                SwiftUI.Button("Recheck local setup") { Task { @MainActor in await reload() } }
                    .disabled(working).accessibilityIdentifier("onboarding.recheck")
            }
        }
    }
    private func observedRow(_ title: String, present: Bool) -> some View {
        SwiftUI.Label(present ? "\(title): present" : "\(title): missing",
                      systemImage: present ? "checkmark.circle" : "exclamationmark.circle")
    }
    @MainActor private func reload() async {
        var facts = SetupReadiness()
        facts.renewalPermitted = renewalPermitted
        facts.localAnisetteSelected = UserDefaults.standard.useOnDeviceAnisette
        do {
            let stored = try await NativeMutationGate.withLease { () -> (Bool, Bool, Bool) in
                let account = try NativeAuthenticationStore.make().read()
                let signer = try CertificateManager.shared.loadActiveCertificate()
                return (PairingFileManager.shared.hasPairingFile(), account?.phase == .ready,
                        signer.map { !$0.certificate.privateKey.isEmpty && $0.certificate.expiryDate > Date() } ?? false)
            }
            facts.pairingStored = stored.0; facts.accountStored = stored.1; facts.signingKeyStored = stored.2
        } catch { facts.localObservationFailed = true }
        readiness = facts
    }
    @MainActor private func perform(_ operation: @escaping @MainActor () async throws -> Void) {
        guard !working else { return }
        working = true; status = nil
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
        guard !working, let next = step.moved(by: delta) else { return }
        status = nil; savedStep = next.rawValue
    }
    private func finish() {
        // This flag only dismisses onboarding; it grants no permission and is
        // deliberately absent from SetupReadiness and renewal eligibility.
        UserDefaults.standard.hasCompletedOnboarding = true
        onFinish?()
    }
}
#endif
