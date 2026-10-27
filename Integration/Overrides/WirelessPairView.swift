// Derived from SideStore WirelessPairView.swift, Copyright © 2026 SideStore.
// Tetherless: the advanced entry uses the bounded host setup presentation.
// SPDX-License-Identifier: AGPL-3.0-only
import SwiftUI

struct WirelessPairView: View {
    var body: some View {
        #if TETHERLESS_BOUNDED_PAIRING_HOST && TETHERLESS_STAGED_PAIRING_VALIDATION && os(iOS) && canImport(IDevice) && canImport(IdeviceGateway)
        if #available(iOS 17.0, *) {
            BoundedWirelessPairPresentation()
        } else {
            unavailable
        }
        #else
        unavailable
        #endif
    }

    private var unavailable: some View {
        SwiftUI.Form {
            SwiftUI.Section {
                Text("Pairing is unavailable in this configuration.")
                Text("You can still import an authorized pairing file from Pairing File settings. A saved record does not establish a usable connection.")
            }
        }
        .navigationTitle("Pairing")
    }
}

#if TETHERLESS_BOUNDED_PAIRING_HOST && TETHERLESS_STAGED_PAIRING_VALIDATION && os(iOS) && canImport(IDevice) && canImport(IdeviceGateway)
@available(iOS 17.0, *)
private struct BoundedWirelessPairPresentation: View {
    @State private var request: PairingSetupRequest?
    // Physical cover ownership survives logical dismissal. An old cover must
    // never clear or complete a newer request.
    @State private var presentation: PairingSetupRequest?
    @State private var status: String?

    var body: some View {
        let dismissalRequest = presentation
        return SwiftUI.Form {
            SwiftUI.Section {
                Text("Create or replace a saved pairing record")
                    .font(.headline)
                Text("The new record must pass a check of this app's protected container before it is saved. An existing saved record stays in place while this check runs.")
                Text("Saving does not establish that the running connection is using the record. Connection and renewal remain unverified.")
                if PairingSetupModel.supported {
                    SwiftUI.Button("Set up pairing on this iPhone") {
                        guard request == nil, presentation == nil else { return }
                        status = nil
                        let next = PairingSetupRequest()
                        presentation = next
                        request = next
                    }
                    .disabled(request != nil || presentation != nil)
                    .accessibilityIdentifier("pairing.advancedSetup")
                } else {
                    Text("This pairing method requires a supported iPhone running iOS 27 or later with the native backend selected. You can still import an authorized pairing file from Pairing File settings.")
                }
            }
            if let status {
                SwiftUI.Section {
                    Text(status).accessibilityIdentifier("pairing.advancedStatus")
                }
            }
        }
        .navigationTitle("Pairing")
        .fullScreenCover(item: $request, onDismiss: {
            guard let dismissalRequest, presentation == dismissalRequest else { return }
            presentation = nil
        }) { current in
            PairingSetupView { outcome in
                guard request == current, presentation == current else { return }
                request = nil
                switch outcome {
                case .saved:
                    status = "Pairing record saved after checking this app's protected container. Saving does not establish that the running connection is using this record. Connection and renewal remain unverified."
                case .cancelled:
                    status = "Pairing cancelled. Existing pairing was retained."
                case .unavailable:
                    status = "Pairing is unavailable in this configuration. You can still import an authorized pairing file."
                case .recoveryRequired:
                    status = "Saving may have completed. Recheck stored pairing before trying again."
                case .failed:
                    status = "Pairing could not be completed. Existing pairing was retained."
                }
            }
        }
    }
}
#endif
