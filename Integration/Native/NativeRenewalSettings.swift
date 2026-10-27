// SPDX-License-Identifier: AGPL-3.0-only
#if os(iOS)
import SwiftUI

@available(iOS 17.0, *)
struct NativeRenewalSettings: View {
    var openAccountAndPairing: () -> Void = {}
    var openAppLibrary: () -> Void = {}
    @AppStorage("tetherless.autorenew.enabled") private var enabled = false
    @State private var working = false
    @State private var showSetupWizard = false
    @State private var message = "Automatic renewal has not been observed on this device."
    @State private var timeline = RenewalTimeline()
    @State private var diagnosticText: String?
    @State private var confirmReenrollment = false
    @State private var permissionMessage = "Expiry alerts require notification permission."

    var body: some View {
        SwiftUI.NavigationStack {
            SwiftUI.Form {
                introduction
                setup
                verification
                NativeCertificateRecoveryControls()
                NativeManagerUpdateControls()
                currentApps
                recentRuns
                #if DEBUG
                development
                #endif
                limits
            }
            .navigationTitle("Auto Renewal")
            .task { reload() }
            .sheet(isPresented: $showSetupWizard) {
                OnboardingView {
                    showSetupWizard = false
                    reload()
                }
            }
            .confirmationDialog("Acknowledge a completed reinstall?", isPresented: $confirmReenrollment) {
                SwiftUI.Button("Re-enroll repaired signing identities") {
                    perform(successMessage: "Repaired identities re-enrolled. Automatic renewal may resume.") {
                        try await NativeRenewalRuntime.shared.reEnrollRepairedApps()
                    }
                }
                SwiftUI.Button("Cancel", role: .cancel) {}
            } message: {
                Text("This validates the replacement's current profiles before retiring old recovery metadata. It does not reinstall an app or revoke a certificate.")
            }
        }
    }

    private var introduction: some View {
        SwiftUI.Section {
            Text("Independent SideStore-based development build. Not an official SideStore release.")
            if let observed = timeline.lastObservedBackgroundRenewal {
                Text("Non-foreground profile renewal observed")
                Text(observed, style: .date)
                Text(observed, style: .time)
            } else {
                Text("Awaiting an observed non-foreground renewal")
            }
            Text("This is not proof of a locked screen, a scheduled trigger or an app launch after its original expiry.")
        } header: { Text("Tetherless") }
    }

    private var setup: some View {
        SwiftUI.Section {
            Text("1. Sign in and finish pairing. Enable your local VPN helper and On-Device Anisette. Background renewal never uses a remote fallback or toggles cellular data.")
            SwiftUI.Button("Continue setup") { showSetupWizard = true }
                .disabled(working).accessibilityIdentifier("renewal.resumeSetup")
            SwiftUI.Button("Account and pairing settings", action: openAccountAndPairing)
                .accessibilityIdentifier("renewal.openSetup")
            SwiftUI.Button("Install or manage an IPA", action: openAppLibrary)
            Text("2. In Shortcuts, create a daily Time of Day automation. Add Renew Managed Apps and choose Run Immediately. Do not add Open App.")
            Text("3. Permit unattended renewal, lock the phone, and let the automation run. Tetherless cannot silently create or verify your personal automation settings.")
            SwiftUI.Toggle("Allow unattended profile renewal", isOn: $enabled)
                .accessibilityIdentifier("renewal.allowUnattended")
                .onChange(of: enabled) { _, active in
                    if active {
                        NativeRenewalBackground.schedule()
                        Task { await NativeRenewalNotifications.update(timeline: timeline) }
                    } else {
                        NativeRenewalBackground.cancel()
                        Task { await NativeRenewalNotifications.cancel() }
                    }
                }
            Text("This permits stored credentials to be used after the first unlock, including while locked. It does not bypass Apple's verification prompts.")
            SwiftUI.Button("Allow expiry warnings") {
                Task { @MainActor in
                    let allowed = await NativeRenewalNotifications.requestPermission()
                    permissionMessage = allowed ? "Expiry warnings are permitted." : "Permission was not granted. Enable notifications in iOS Settings."
                    if allowed { await NativeRenewalNotifications.update(timeline: timeline) }
                }
            }
            Text(permissionMessage)
            if UserDefaults.standard.bool(forKey: "tetherless.background.registrationFailed") ||
               UserDefaults.standard.bool(forKey: "tetherless.background.scheduleFailed") {
                Text("iOS background scheduling is unavailable. Check system settings; the authorized Shortcut remains a separate trigger.")
            }
            if UserDefaults.standard.bool(forKey: "tetherless.notifications.scheduleFailed") {
                Text("Expiry notifications could not be scheduled. Their delivery is not currently assured.")
            }
        } header: { Text("First-time setup") }
    }

    private var verification: some View {
        SwiftUI.Section {
            SwiftUI.Button("Run an explicit renewal check") {
                perform { _ = try await NativeRenewalRuntime.shared.run(trigger: .manual, force: true) }
            }
            .disabled(working).accessibilityIdentifier("renewal.manualCheck")
            SwiftUI.Button("Recheck after repairing login or pairing") {
                perform(successMessage: "Available app state rechecked. Pending work still requires reconciliation.") {
                    try await NativeRenewalRuntime.shared.confirmRepair()
                }
            }
            .disabled(working).accessibilityIdentifier("renewal.recheckRepair")
            SwiftUI.Button("Re-enroll after an explicit reinstall") { confirmReenrollment = true }
                .disabled(working)
            Text(message).accessibilityIdentifier("renewal.status")
            SwiftUI.Button("Reload saved evidence") { reload() }.disabled(working)
            Text("Reload only reads saved evidence; it does not trigger a renewal or contact Apple.")
            if let diagnosticText {
                SwiftUI.ShareLink("Share sanitized diagnostics", item: diagnosticText)
                Text("The export contains timestamps, trigger types, counts and known error codes only. No account, Team ID, bundle ID, device ID, token, profile, key or pairing file is exported.")
            }
        } header: { Text("Verification and recovery") }
    }

    private var currentApps: some View {
        SwiftUI.Section {
            if timeline.lastObservedLeases.isEmpty { Text("No live app expiry has been recorded yet.") }
            ForEach(timeline.lastObservedLeases, id: \.bundleID) { app in
                VStack(alignment: .leading) {
                    Text(app.isManager ? "Tetherless (manager)" : app.bundleID)
                    Text("Last observed effective expiry:")
                    Text(app.effectiveExpiry, style: .date)
                    Text(app.effectiveExpiry, style: .time)
                }
            }
        } header: { Text("Last observed authorization") }
    }

    private var recentRuns: some View {
        SwiftUI.Section {
            ForEach(Array(timeline.runs.suffix(5).reversed().enumerated()), id: \.offset) { _, run in
                VStack(alignment: .leading) {
                    Text("\(run.trigger.rawValue) · \(run.verified) verified · \(run.deferred) deferred")
                    Text(run.finishedAt, style: .date)
                    Text(run.finishedAt, style: .time)
                    Text(run.message)
                }
            }
        } header: { Text("Recent runs") }
    }

    private var limits: some View {
        SwiftUI.Section {
            Text("Ordinary renewal attempts occur daily, not on day seven. iOS controls execution opportunities; expiry warnings are not a substitute for renewal.")
            Text("Expired/revoked certificates, changed identities, missing install metadata, wildcard profiles and new login challenges require explicit repair. Background renewal never revokes a certificate or reinstalls the manager.")
        } header: { Text("Limits") }
    }

    #if DEBUG
    private var development: some View {
        SwiftUI.Section { TestCadenceToggle() } header: { Text("Development") }
    }
    #endif

    private func perform(successMessage: String? = nil, _ operation: @escaping () async throws -> Void) {
        working = true
        Task { @MainActor in
            defer { working = false }
            do { try await operation(); reload(); if let successMessage { message = successMessage } }
            catch { message = NativeRenewalRuntime.classify(error).recoveryHint }
        }
    }
    private func reload() {
        do {
            let value = try NativeRenewalStorage.timeline()
            timeline = value
            diagnosticText = String(data: try value.diagnosticData(), encoding: .utf8)
            message = value.latest?.message ?? "No renewal attempt has been recorded yet."
        } catch {
            diagnosticText = nil
            message = "Stored evidence cannot be read. It has not been reset."
        }
    }
}
#if DEBUG
@available(iOS 17.0, *)
private struct TestCadenceToggle: View {
    @AppStorage("tetherless.test.twoHourCadence") private var accelerated = false
    var body: some View {
        SwiftUI.Toggle("Use two-hour eligibility (not a timer)", isOn: $accelerated)
        Text("This changes eligibility, not Apple's signed expiry or iOS scheduling.")
    }
}
#endif
#endif
