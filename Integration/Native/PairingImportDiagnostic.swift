// SPDX-License-Identifier: AGPL-3.0-only
/// Fixed lifecycle markers only. There is deliberately no URL, error, request
/// ID, metadata or arbitrary string parameter. Never use this as acceptance.
enum PairingImportDiagnostic: String, CaseIterable, Sendable {
    case requestBegan, pickerCreated, plistTypeAllowed, plistTypeNotAllowed
    case selectionReceived, invalidSelection, cancellationReceived
    case resultDelivered, lateCallbackIgnored, coordinatorInvalidated
    case resolutionAccepted, resolutionIgnored, coverDismissed, dismissalUnbound
    case dismissalObserved, dismissalIgnored
    case cancelFinished, importStarted, importSucceeded, importFailed

    @MainActor func record() {
        print("[Tetherless.PairingImport] \(rawValue)")
    }
}
