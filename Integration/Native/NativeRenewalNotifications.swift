// SPDX-License-Identifier: AGPL-3.0-only
#if os(iOS)
import Foundation
import UserNotifications

@available(iOS 17.0, *)
enum NativeRenewalNotifications {
    static func requestPermission() async -> Bool {
        // Only called from the explicit foreground setup button.
        do { return try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) }
        catch { return false }
    }
    static func update(timeline: RenewalTimeline) async {
        guard UserDefaults.standard.bool(forKey: NativeRenewalRuntime.enabledKey) else { return }
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        guard [.authorized, .provisional, .ephemeral].contains(settings.authorizationStatus) else { return }
        do {
            let plan = try RenewalAlertPolicy.plan(leases: timeline.lastObservedLeases, now: Date())
            let desired = Set(plan.map(\.id))
            let pending = await center.pendingNotificationRequests()
            let delivered = await center.deliveredNotifications()
            let existing = Set(pending.map(\.identifier) + delivered.map { $0.request.identifier })
            // Never remove another feature's notifications.
            let obsolete = pending.map(\.identifier).filter {
                $0.hasPrefix(RenewalAlertPolicy.identifierPrefix) && !desired.contains($0)
            }
            center.removePendingNotificationRequests(withIdentifiers: obsolete)
            for alert in plan where !existing.contains(alert.id) {
                let content = UNMutableNotificationContent()
                content.title = "Tetherless renewal needs attention"
                switch alert.severity {
                case .warning48h: content.body = "A managed app has less than two days of observed authorization remaining. Check automatic renewal."
                case .urgent24h: content.body = "A managed app has less than one day remaining. Open Tetherless to check recovery instructions."
                case .expired: content.body = "The last observed authorization has expired. An external reinstall may be needed if Tetherless cannot open."
                }
                content.sound = .default
                let interval = max(1, alert.deliverAt.timeIntervalSinceNow)
                let trigger = UNTimeIntervalNotificationTrigger(timeInterval: interval, repeats: false)
                try await center.add(UNNotificationRequest(identifier: alert.id, content: content, trigger: trigger))
            }
            UserDefaults.standard.removeObject(forKey: "tetherless.notifications.scheduleFailed")
        } catch {
            UserDefaults.standard.set(true, forKey: "tetherless.notifications.scheduleFailed")
        }
    }
    static func cancel() async {
        let center = UNUserNotificationCenter.current()
        let pending = await center.pendingNotificationRequests()
        center.removePendingNotificationRequests(withIdentifiers: pending.map(\.identifier).filter {
            $0.hasPrefix(RenewalAlertPolicy.identifierPrefix)
        })
    }
}
#endif
