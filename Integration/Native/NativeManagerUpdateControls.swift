// SPDX-License-Identifier: AGPL-3.0-only
#if os(iOS)
import SwiftUI

@available(iOS 17.0, *)
struct NativeManagerUpdateControls: View {
    @State private var working = false
    @State private var status = "No manager update has been recorded."
    @State private var confirmAbandon = false
    var body: some View {
        SwiftUI.Section {
            Text(status).accessibilityIdentifier("managerUpdate.status")
            Text("Manager version updates are separate from daily profile renewal. They require foreground confirmation and never export your signing key.")
            SwiftUI.Button("Reconcile manager update") { run(abandon: false) }
                .disabled(working).accessibilityIdentifier("managerUpdate.reconcile")
            SwiftUI.Button("Discard an unapplied manager update", role: .destructive) { confirmAbandon = true }
                .disabled(working).accessibilityIdentifier("managerUpdate.abandon")
        } header: { Text("Manager update recovery") }
        .task { reload() }
        .confirmationDialog("Discard only an unapplied update?", isPresented: $confirmAbandon) {
            SwiftUI.Button("Discard recovery attempt", role: .destructive) { run(abandon: true) }
            SwiftUI.Button("Cancel", role: .cancel) {}
        } message: {
            Text("Wait until the previous installation has stopped. This works only if the original manager still matches the saved record. It does not undo an installation, delete app data, or erase accounts or pairing.")
        }
    }
    @MainActor private func run(abandon: Bool) {
        working = true
        Task { @MainActor in
            defer { working = false }
            do {
                try await NativeMutationGate.withLease {
                    try await DatabaseManager.shared.start()
                    if abandon { try await NativeManagerUpdate.abandonUnapplied() }
                    else { _ = try NativeManagerUpdate.reconcile() }
                }
                UserDefaults.standard.removeObject(forKey: "tetherless.managerUpdate.recoveryFailed")
                reload()
            } catch {
                status = (error as? ManagerUpdateFailure)?.localizedDescription ?? "Update recovery is unavailable. The existing record was retained."
            }
        }
    }
    private func reload() {
        do {
            guard let record = try NativeManagerUpdate.journal().read() else { status = "No manager update has been recorded."; return }
            switch record.phase {
            case .prepared: status = "Prepared; installation has not been dispatched."
            case .applying: status = "Installation may have been dispatched. Awaiting an exact running-bundle match and saved-data verification."
            case .completed: status = "Manager replacement reconciled with the running bundle. This is not unattended renewal evidence."
            case .abandoned: status = "The unapplied update attempt was explicitly discarded."
            }
        } catch { status = "The update record could not be read. It has not been reset." }
    }
}
#endif
