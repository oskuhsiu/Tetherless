// SPDX-License-Identifier: AGPL-3.0-only
#if os(iOS)
import Foundation
@preconcurrency import BackgroundTasks

@available(iOS 17.0, *)
enum NativeRenewalBackground {
    static let identifier = "org.tetherless.profile-renewal"
    private static let registration = NSLock()
    private nonisolated(unsafe) static var registered = false

    static func register() {
        registration.lock()
        defer { registration.unlock() }
        guard !registered else { return }
        registered = BGTaskScheduler.shared.register(forTaskWithIdentifier: identifier, using: nil) { bgTask in
            schedule()
            let lifetime = Lifetime(bgTask)
            bgTask.expirationHandler = { lifetime.expire() }
            let task = Task {
                do {
                    let report = try await NativeRenewalRuntime.shared.run(trigger: .background)
                    lifetime.finish(success: report.failures.isEmpty && report.unverified == 0)
                } catch { lifetime.finish(success: false) }
            }
            lifetime.attach(task)
        }
        UserDefaults.standard.set(!registered, forKey: "tetherless.background.registrationFailed")
        if registered { schedule() }
    }

    static func schedule() {
        guard UserDefaults.standard.bool(forKey: NativeRenewalRuntime.enabledKey) else { return }
        let request = BGProcessingTaskRequest(identifier: identifier)
        request.requiresNetworkConnectivity = true
        request.requiresExternalPower = false
        request.earliestBeginDate = Date().addingTimeInterval(21_600)
        // Earliest eligibility, NOT a timer. Shortcuts remains the main trigger.
        do {
            try BGTaskScheduler.shared.submit(request)
            UserDefaults.standard.removeObject(forKey: "tetherless.background.scheduleFailed")
        } catch {
            UserDefaults.standard.set(true, forKey: "tetherless.background.scheduleFailed")
        }
    }

    static func cancel() { BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: identifier) }

    private final class Lifetime: @unchecked Sendable {
        let bgTask: BGTask
        private let mutex = NSLock()
        private var task: Task<Void, Never>?
        private var completed = false
        init(_ task: BGTask) { bgTask = task }
        func attach(_ work: Task<Void, Never>) {
            mutex.lock()
            let shouldCancel = completed
            if !completed { task = work }
            mutex.unlock()
            if shouldCancel { work.cancel() }
        }
        func expire() { finish(success: false, cancelWork: true) }
        func finish(success: Bool, cancelWork: Bool = false) {
            mutex.lock()
            guard !completed else { mutex.unlock(); return }
            completed = true
            let work = task
            task = nil
            mutex.unlock()
            if cancelWork { work?.cancel() }
            bgTask.expirationHandler = nil
            bgTask.setTaskCompleted(success: success)
        }
    }
}
#endif
