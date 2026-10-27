// SPDX-License-Identifier: AGPL-3.0-only
import AppIntents

/// Replaces the inherited RefreshAllAppsIntent, retaining its migration identity
/// and widget initializer but removing foreground continuation entirely.
@available(iOS 17.0, tvOS 17.0, *)
struct RefreshAllAppsIntent: AppIntent, CustomIntentMigratedAppIntent {
    static let intentClassName = "RefreshAllIntent"
    static var title: LocalizedStringResource = "Renew Managed Apps"
    static var description = IntentDescription("Renews managed app profiles on this device without opening Tetherless.")
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed
    static var parameterSummary: some ParameterSummary { Summary("Renew Managed Apps") }
    init() {}
    init(presentsNotifications: Bool) {}
    func perform() async throws -> some IntentResult & ProvidesDialog {
        do {
            let report = try await NativeRenewalRuntime.shared.run(trigger: .shortcut)
            return .result(dialog: "\(report.message)")
        } catch {
            // No raw NSError userInfo, server body, Apple ID, profile or token.
            throw NSError(domain: "Tetherless.Renewal", code: 1,
                userInfo: [NSLocalizedDescriptionKey: "Renewal requires attention: \(NativeRenewalRuntime.classify(error).rawValue)"])
        }
    }
}
