// SPDX-License-Identifier: AGPL-3.0-only
#if os(iOS)
import SwiftUI

@available(iOS 17.0, *)
struct NativeRenewalSettings: View {
    @AppStorage("tetherless.autorenew.enabled") private var enabled = false
    @State private var working = false
    @State private var message = "Automatic renewal has not been verified on this device."
    @State private var summary: NativeRenewalSummary?
    var body: some View {
        NavigationStack {
            Form {
                Section("Tetherless") {
                    Text("Independent SideStore-based development build. Not an official SideStore release.")
                    Text("Daily renewal is attempted before expiry. Successful build and manual checks do not prove locked-device automation.")
                }
                Section("First-time setup") {
                    Text("1. Sign in and finish installation/pairing in the existing setup screens. Enable the local VPN helper.")
                    Text("2. Select On-Device Anisette in Settings. Background renewal will not use a remote fallback or toggle cellular data.")
                    Text("3. In Shortcuts, create a daily Time of Day automation. Add Tetherless’s Renew Managed Apps action and choose Run Immediately. Do not add Open App.")
                    Text("4. Lock the phone and let that automation run. A manual test is not the same evidence.")
                    Toggle("Allow unattended profile renewal", isOn: $enabled)
                        .accessibilityIdentifier("renewal.allowUnattended")
                        .onChange(of: enabled) { _, active in
                            if active { NativeRenewalBackground.schedule() }
                            else { NativeRenewalBackground.cancel() }
                        }
                    Text("Enabling this allows the intent to use stored credentials after the first unlock, including while locked. It does not create a personal automation for you.")
                }
                Section("Verification and recovery") {
                    Button("Run an explicit renewal check") { perform { _ = try await NativeRenewalRuntime.shared.run(trigger: .manual, force: true) } }
                        .disabled(working).accessibilityIdentifier("renewal.manualCheck")
                    Button("Recheck after repairing login or pairing") { perform { try await NativeRenewalRuntime.shared.confirmRepair() } }
                        .disabled(working).accessibilityIdentifier("renewal.recheckRepair")
                    Text(message).accessibilityIdentifier("renewal.status")
                    if let summary {
                        Text("Last trigger: \(summary.trigger.rawValue)")
                        Text(summary.managerWasForeground ? "Manager was in the foreground." : "Manager was not in the foreground at start.")
                        Text("Profile-store readback: \(summary.verified); unverified: \(summary.unverified); deferred: \(summary.deferred).")
                        Text("This does not attest that the phone was locked or prove an app launch beyond the original expiry.")
                    }
                    Button("Reload evidence") { reload() }.disabled(working)
                }
                #if DEBUG
                Section("Development") { TestCadenceToggle() }
                #endif
                Section("Limits") {
                    Text("Expired/revoked certificates, changed signing identities, missing install metadata, wildcard profiles and new login challenges require explicit repair. No background action revokes a certificate or reinstalls the manager.")
                }
            }
            .navigationTitle("Auto Renewal")
            .task { reload() }
        }
    }
    private func perform(_ operation: @escaping () async throws -> Void) {
        working = true
        Task { @MainActor in
            defer { working = false }
            do { try await operation(); reload() }
            catch { message = "Needs attention: \(NativeRenewalRuntime.classify(error).rawValue)" }
        }
    }
    private func reload() {
        do {
            guard let bytes = try NativeRenewalStorage.read(NativeRenewalStorage.root().appendingPathComponent("last-run.json")) else { return }
            let value = try JSONDecoder().decode(NativeRenewalSummary.self, from: bytes)
            summary = value
            message = value.message
        } catch { message = "Stored evidence cannot be read. It has not been reset." }
    }
}
#if DEBUG
@available(iOS 17.0, *)
private struct TestCadenceToggle: View {
    @AppStorage("tetherless.test.twoHourCadence") private var accelerated = false
    var body: some View {
        Toggle("Use two-hour eligibility (not a timer)", isOn: $accelerated)
        Text("This changes when a trigger is eligible to renew, not Apple's signed expiry or iOS scheduling.")
    }
}
#endif
#endif
