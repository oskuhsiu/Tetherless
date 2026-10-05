// SPDX-License-Identifier: AGPL-3.0-only
#if TETHERLESS_BOUNDED_PAIRING_HOST && TETHERLESS_STAGED_PAIRING_VALIDATION && os(iOS) && canImport(IDevice) && canImport(IdeviceGateway)
import SwiftUI
@preconcurrency import UIKit

struct PairingSetupRequest: Identifiable, Equatable { let id = UUID() }

/// Remains presented while cancellation joins native/platform work. Owner
/// teardown also signals cancellation; the model task retains the lease.
@available(iOS 17.0, *)
struct PairingSetupView: View {
    @StateObject private var model = PairingSetupModel()
    @State private var concealPIN = false
    let finished: (PairingSetupModel.Outcome) -> Void

    var body: some View {
        SwiftUI.NavigationStack {
            SwiftUI.Form {
                SwiftUI.Section {
                    Text("Pair this iPhone").font(.title2.bold())
                    Text(detail)
                        .accessibilityIdentifier("pairing.setupStatus")
                    if model.isRunning { ProgressView().accessibilityLabel("Pairing in progress") }
                }
                if model.phase == .waiting || model.phase == .pairing {
                    SwiftUI.Section("Pairing code") {
                        if let pin = model.pin, !concealPIN, !model.cancellation.isCancelled {
                            Text(pin).font(.system(.largeTitle, design: .monospaced)).textSelection(.disabled)
                                .privacySensitive().accessibilityIdentifier("pairing.setupPIN")
                                .accessibilityLabel("Pairing code")
                                .accessibilityValue(pin.map { String($0) }.joined(separator: " "))
                        } else {
                            Text("The code appears after this iPhone starts pairing.")
                        }
                        Text("Open the pairing screen in iOS Settings and select Tetherless. If Settings asks for a code, return here to read it, then enter it in Settings.")
                        Text("Only approve pairing you started on this iPhone. Keep the code private.")
                    }
                }
                if model.phase == .ready {
                    SwiftUI.Section {
                        Text("Start when you are ready to switch to Settings. Tetherless will check access to this app's protected container before saving the new record.")
                        if PairingSetupModel.supported {
                            SwiftUI.Button("Start pairing") { model.start() }
                                .buttonStyle(.borderedProminent).accessibilityIdentifier("pairing.setupStart")
                        } else {
                            Text("Pairing is unavailable in this configuration. You can still import an authorized pairing file.")
                        }
                    }
                }
                if let outcome = model.outcome, model.phase == .finished {
                    SwiftUI.Section {
                        SwiftUI.Button("Done") { finished(outcome) }
                            .buttonStyle(.borderedProminent).accessibilityIdentifier("pairing.setupDone")
                    }
                }
            }
            .navigationTitle("Pairing")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    if model.phase == .ready {
                        SwiftUI.Button("Cancel") { finished(.cancelled) }
                    } else if model.isRunning {
                        SwiftUI.Button("Cancel") { model.cancel() }
                            .disabled(model.phase == .stopping).accessibilityIdentifier("pairing.setupCancel")
                    }
                }
            }
        }
        .interactiveDismissDisabled(model.isRunning)
        .onDisappear { model.cancel() }
        .onReceive(NotificationCenter.default.publisher(for: UIApplication.willResignActiveNotification)) { _ in concealPIN = true }
        .onReceive(NotificationCenter.default.publisher(for: UIApplication.didBecomeActiveNotification)) { _ in
            model.reconcileCancellation()
            concealPIN = false
        }
    }

    private var detail: String {
        switch model.phase {
        case .ready: return "Pairing requires your approval in Settings. An existing saved record stays in place while the new record is checked."
        case .preparing: return "Preparing a private pairing session."
        case .waiting: return "Ready for the pairing request from this iPhone."
        case .pairing: return "Complete the pairing prompt in Settings."
        case .validating: return "Checking access to this app's protected container."
        case .stopping: return "Stopping pairing and closing the connection."
        case .finished:
            switch model.outcome {
            case .saved: return "Pairing record saved after checking this app's protected container. Saving does not establish that the running connection is using this record. Connection and renewal remain unverified."
            case .cancelled: return "Pairing cancelled. Existing pairing was retained."
            case .unavailable: return "Pairing is unavailable in this configuration. You can still import an authorized pairing file."
            case .recoveryRequired: return "Saving may have completed. Recheck the stored pairing before trying again."
            default: return "Pairing could not be completed. Existing pairing was retained."
            }
        }
    }
}
#endif
