// Test doubles exercise the generated operation's ownership contract; they do
// not establish Apple's NSFileCoordinator, Core Data, or physical-device behavior.
import Foundation
import CoreFoundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

public enum RenewalFailure: Error { case lockUnavailable, busy }
enum ProbeFailure: Error { case coordinator, deletion }
enum OperationError: Error { case cancelled, invalidParameters(String), missingAppGroup(name: String), unknownResult }
LEASE_HERE
enum NativeRenewalStorage {
    static func root() throws -> URL { URL(fileURLWithPath: CommandLine.arguments[1]) }
}
GATE_HERE

final class Control: @unchecked Sendable {
    let scheduled = DispatchSemaphore(value: 0)
    let begin = DispatchSemaphore(value: 0)
    let deleteEntered = DispatchSemaphore(value: 0)
    let deleteFinished = DispatchSemaphore(value: 0)
    let continueDeletion = DispatchSemaphore(value: 0)
    let accessorFinished = DispatchSemaphore(value: 0)
    let allowAccessorReturn = DispatchSemaphore(value: 0)
    let cancelled = DispatchSemaphore(value: 0)
    let failCoordinator: Bool
    let failDeletion: Bool
    let missingDuringDeletion: Bool
    let omitAccessor: Bool
    let redirect: URL?
    let onSynchronousReturn: (@Sendable () -> Void)?
    private let lock = NSLock()
    private var active = false
    private var deletes = 0
    init(parkBeforeAccessor: Bool = false, parkDuringDeletion: Bool = false,
         parkAfterAccessor: Bool = false, failCoordinator: Bool = false,
         failDeletion: Bool = false, missingDuringDeletion: Bool = false,
         omitAccessor: Bool = false, redirect: URL? = nil,
         onSynchronousReturn: (@Sendable () -> Void)? = nil) {
        self.failCoordinator = failCoordinator
        self.failDeletion = failDeletion
        self.missingDuringDeletion = missingDuringDeletion
        self.omitAccessor = omitAccessor
        self.redirect = redirect
        self.onSynchronousReturn = onSynchronousReturn
        if !parkBeforeAccessor { begin.signal() }
        if !parkDuringDeletion { continueDeletion.signal() }
        if !parkAfterAccessor { allowAccessorReturn.signal() }
    }
    func setActive(_ value: Bool) { lock.lock(); active = value; lock.unlock() }
    func assertActive(_ expected: Bool) {
        lock.lock(); defer { lock.unlock() }
        precondition(active == expected, "coordinated accessor lifetime mismatch")
    }
    func recordDeletion() { lock.lock(); deletes += 1; lock.unlock() }
    func deletionCount() -> Int { lock.lock(); defer { lock.unlock() }; return deletes }
}
final class ProbeState: @unchecked Sendable {
    static let shared = ProbeState()
    private let lock = NSLock()
    private var value = Control()
    func set(_ control: Control) { lock.lock(); value = control; lock.unlock() }
    func get() -> Control { lock.lock(); defer { lock.unlock() }; return value }
}
final class TestFileAccessIntent: @unchecked Sendable {
    struct WritingOptions: OptionSet, Sendable {
        let rawValue: Int
        static let forDeleting = WritingOptions(rawValue: 1)
    }
    let url: URL
    init(_ url: URL) { self.url = url }
    static func writingIntent(with url: URL, options: WritingOptions) -> TestFileAccessIntent {
        precondition(options == .forDeleting)
        return TestFileAccessIntent(ProbeState.shared.get().redirect ?? url)
    }
}
final class TestFileCoordinator: @unchecked Sendable {
    private let control = ProbeState.shared.get()
    init(filePresenter: AnyObject? = nil) {}
    func coordinate(with intents: [TestFileAccessIntent], queue: OperationQueue,
                    byAccessor accessor: @escaping @Sendable (Error?) -> Void) {
        precondition(queue.maxConcurrentOperationCount == 1)
        precondition(intents.count == 1)
        queue.addOperation { [control] in
            control.scheduled.signal()
            control.begin.wait()
            control.setActive(true)
            accessor(control.failCoordinator ? ProbeFailure.coordinator : nil)
            control.accessorFinished.signal()
            // Park after the callback's body has queued its continuation but
            // before this accessor operation returns. Early resume loses here.
            control.allowAccessorReturn.wait()
            control.setActive(false)
        }
    }
    func coordinate(writingItemAt url: URL, options: TestFileAccessIntent.WritingOptions,
                    error: inout NSError?, byAccessor accessor: (URL) -> Void) {
        precondition(options == .forDeleting)
        control.scheduled.signal()
        control.begin.wait()
        if control.failCoordinator {
            error = NSError(domain: "BackupCoordinationProbe", code: 1)
        } else if !control.omitAccessor {
            control.setActive(true)
            accessor(control.redirect ?? url)
        }
        control.accessorFinished.signal()
        control.allowAccessorReturn.wait()
        control.onSynchronousReturn?()
        control.setActive(false)
    }
}
final class TestFileManager: @unchecked Sendable {
    static let shared = TestFileManager()
    func fileExists(atPath path: String) -> Bool { FileManager.default.fileExists(atPath: path) }
    func backupDirectoryURL(forBundleIdentifier identifier: String) -> URL? {
        identifier.isEmpty ? nil : URL(fileURLWithPath: identifier)
    }
    func removeItem(at url: URL) throws {
        let control = ProbeState.shared.get()
        control.assertActive(true)
        control.recordDeletion()
        control.deleteEntered.signal()
        control.continueDeletion.wait()
        if control.failDeletion { throw ProbeFailure.deletion }
        if control.missingDuringDeletion { throw CocoaError(.fileNoSuchFile) }
        try FileManager.default.removeItem(at: url)
        control.assertActive(true)
        control.deleteFinished.signal()
    }
}
final class TestManagedObjectContext: @unchecked Sendable {
    func perform<T: Sendable>(_ body: @escaping @Sendable () -> T) async -> T { body() }
}
final class InstalledApp: @unchecked Sendable {
    let managedObjectContext: TestManagedObjectContext? = TestManagedObjectContext()
    let bundleIdentifier = "example.backup"
    var resignedBundleIdentifier: String { backupURL?.path ?? "" }
    let backupURL: URL?
    init(_ url: URL?) { backupURL = url }
}
final class InstallAppOperationContext: @unchecked Sendable {
    let installedApp: InstalledApp?
    init(_ app: InstalledApp?) { installedApp = app }
}
class BasePipelineOperation<Context, Value>: @unchecked Sendable {
    let context: Context
    let progress = Progress.discreteProgress(totalUnitCount: 100)
    private let lock = NSLock()
    private var cancelled = false
    init(context: Context) {
        self.context = context
        self.progress.cancellationHandler = { [weak self] in self?.cancel() }
    }
    func cancel() {
        lock.lock(); cancelled = true; lock.unlock()
        ProbeState.shared.get().cancelled.signal()
    }
    func check() throws {
        lock.lock(); defer { lock.unlock() }
        if cancelled { throw OperationError.cancelled }
    }
    func executePreconditionCheck(parentProgress: Progress?) async throws { try check() }
    func execute(parentProgress: Progress?) async throws -> Value { fatalError("abstract") }
    func setProgress(_ count: Int64) { progress.completedUnitCount = count }
}
func debugLog(_ message: @autoclosure () -> String) {}
OPERATION_HERE
HELPER_HERE

final class CancellationTarget: @unchecked Sendable {
    private let ready = DispatchSemaphore(value: 0)
    private let lock = NSLock()
    private var action: (@Sendable () -> Void)?
    func set(_ action: @escaping @Sendable () -> Void) {
        lock.lock(); self.action = action; lock.unlock()
        ready.signal()
    }
    func cancel() {
        ready.wait()
        lock.lock(); let action = self.action; lock.unlock()
        action?()
    }
}

@main struct Main {
    static func wait(_ semaphore: DispatchSemaphore) async {
        await withCheckedContinuation { continuation in
            DispatchQueue.global().async {
                semaphore.wait()
                continuation.resume()
            }
        }
    }
    static func busy(_ path: URL) {
        do { let lease = try ProcessLease.acquire(at: path); lease.release(); fatalError("lease released early") }
        catch RenewalFailure.busy {} catch { fatalError("unexpected lease error") }
    }
    static func runSynchronous(_ body: @escaping @Sendable () throws -> Void) async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            DispatchQueue.global().async {
                continuation.resume(with: Result(catching: body))
            }
        }
    }
    static func free(_ path: URL) throws {
        try ProcessLease.acquire(at: path).release()
        precondition(FileManager.default.fileExists(atPath: path.path), "lock inode was unlinked")
    }
    static func makeBackup(_ root: URL, _ name: String) throws -> URL {
        let url = root.appendingPathComponent(name)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        try Data("backup content".utf8).write(to: url.appendingPathComponent("payload"))
        return url
    }
    static func operation(_ control: Control, _ url: URL?) -> RemoveBackupDataOperation {
        ProbeState.shared.set(control)
        return RemoveBackupDataOperation(context: InstallAppOperationContext(InstalledApp(url)))
    }
    static func exists(_ url: URL) -> Bool { FileManager.default.fileExists(atPath: url.path) }
    static func main() async throws {
        try await runChecks()
    }

    // Async @main is implicitly MainActor-isolated. These scenarios exercise
    // nonisolated operations and lease bodies, with no UIKit/actor-owned state.
    // Keep their closures in that same isolation domain under Swift 6 checking.
    nonisolated static func runChecks() async throws {
        let root = try NativeRenewalStorage.root()
        let path = root.appendingPathComponent("device-mutation.lock")
        let unrelated = try makeBackup(root, "unrelated-app")

        // A direct caller cannot bypass an unrelated lease owner.
        let busyURL = try makeBackup(root, "busy-app")
        let busyControl = Control()
        let busyOperation = operation(busyControl, busyURL)
        let owner = try ProcessLease.acquire(at: path)
        do { _ = try await busyOperation.execute(parentProgress: nil); fatalError("busy admitted") }
        catch RenewalFailure.busy {}
        precondition(exists(busyURL) && busyControl.deletionCount() == 0)
        owner.release()

        // Cancellation before entry is rejected without starting file work.
        let preCancelledURL = try makeBackup(root, "pre-cancelled")
        let preCancelledControl = Control()
        let preCancelled = operation(preCancelledControl, preCancelledURL)
        preCancelled.cancel()
        do { _ = try await preCancelled.execute(parentProgress: nil); fatalError("pre-cancel admitted") }
        catch is CancellationError {}
        precondition(exists(preCancelledURL) && preCancelledControl.deletionCount() == 0)
        try free(path)

        // Task and Progress cancellation while queued must not release early.
        for cancelTask in [true, false] {
            let victim = try makeBackup(root, cancelTask ? "task-cancel" : "progress-cancel")
            let control = Control(parkBeforeAccessor: true, parkAfterAccessor: true)
            let step = operation(control, victim)
            let task = Task { try await step.execute(parentProgress: nil) }
            await wait(control.scheduled)
            busy(path)
            if cancelTask {
                task.cancel()
            } else {
                step.progress.cancel()
                await wait(control.cancelled)
            }
            busy(path)
            control.begin.signal()
            await wait(control.accessorFinished)
            busy(path)
            precondition(exists(victim) && control.deletionCount() == 0)
            control.allowAccessorReturn.signal()
            do { _ = try await task.value; fatalError("cancellation succeeded") }
            catch is CancellationError {}
            control.assertActive(false)
            try free(path)
        }

        // Cancellation during synchronous deletion does not claim the mutation
        // was rolled back, and ownership lasts until that work actually stops.
        for cancelTask in [true, false] {
            let victim = try makeBackup(root, cancelTask ? "running-task" : "running-operation")
            let control = Control(parkDuringDeletion: true, parkAfterAccessor: true)
            let step = operation(control, victim)
            let task = Task { try await step.execute(parentProgress: nil) }
            await wait(control.deleteEntered)
            if cancelTask { task.cancel() } else { step.cancel() }
            busy(path)
            precondition(exists(victim))
            control.continueDeletion.signal()
            await wait(control.accessorFinished)
            busy(path)
            precondition(!exists(victim))
            control.allowAccessorReturn.signal()
            do { _ = try await task.value; fatalError("running cancellation succeeded") }
            catch is CancellationError {}
            control.assertActive(false)
            try free(path)
        }

        // Both coordinator and filesystem errors propagate without a deletion.
        for coordinationError in [true, false] {
            let victim = try makeBackup(root, coordinationError ? "coordination-error" : "delete-error")
            let control = Control(parkAfterAccessor: true, failCoordinator: coordinationError,
                                  failDeletion: !coordinationError)
            let step = operation(control, victim)
            let task = Task { try await step.execute(parentProgress: nil) }
            await wait(control.accessorFinished)
            busy(path)
            precondition(exists(victim))
            control.allowAccessorReturn.signal()
            do { _ = try await task.value; fatalError("error succeeded") }
            catch ProbeFailure.coordinator { precondition(coordinationError) }
            catch ProbeFailure.deletion { precondition(!coordinationError) }
            control.assertActive(false)
            try free(path)
        }

        // Never substitute the original request URL for the coordinated URL.
        let requested = try makeBackup(root, "requested-backup")
        let authorized = try makeBackup(root, "coordinated-backup")
        let redirect = Control(parkAfterAccessor: true, redirect: authorized)
        let redirectedStep = operation(redirect, requested)
        let redirectedTask = Task { try await redirectedStep.execute(parentProgress: nil) }
        await wait(redirect.accessorFinished)
        busy(path)
        precondition(exists(requested) && !exists(authorized) && exists(unrelated))
        redirect.allowAccessorReturn.signal()
        let redirectedResult = try await redirectedTask.value
        precondition(redirectedResult)
        redirect.assertActive(false)
        try free(path)

        // Nested pipeline-style calls borrow the same lease rather than flock
        // again; completing a child cannot release its still-running parent.
        let nestedURL = try makeBackup(root, "nested-backup")
        let nestedControl = Control()
        let nestedStep = operation(nestedControl, nestedURL)
        try await NativeMutationGate.withLease {
            let result = try await nestedStep.execute(parentProgress: nil)
            precondition(result && !exists(nestedURL))
            busy(path)
        }
        try free(path)

        // An admitted inherited child keeps ownership if its parent returns.
        let childURL = try makeBackup(root, "inherited-child")
        let childControl = Control(parkBeforeAccessor: true)
        let childStep = operation(childControl, childURL)
        let child: Task<Bool, Error> = try await NativeMutationGate.withLease {
            let task = Task { try await childStep.execute(parentProgress: nil) }
            await wait(childControl.scheduled)
            return task
        }
        busy(path)
        childControl.begin.signal()
        let childResult = try await child.value
        precondition(childResult && !exists(childURL))
        childControl.assertActive(false)
        try free(path)

        // Existing absent-backup and raced-ENOENT behavior remains idempotent.
        let absent = root.appendingPathComponent("already-absent")
        let absentControl = Control()
        let absentResult = try await operation(absentControl, absent).execute(parentProgress: nil)
        precondition(absentResult && absentControl.deletionCount() == 0)
        let raced = try makeBackup(root, "raced-missing")
        let racedControl = Control(missingDuringDeletion: true)
        let racedResult = try await operation(racedControl, raced).execute(parentProgress: nil)
        precondition(racedResult && racedControl.deletionCount() == 1)
        try free(path)

        // Exercise the exact main-app FileManager wrapper with a synchronous
        // coordinator double and the production synchronous lease extension.
        let uiBusyURL = try makeBackup(root, "ui-busy")
        ProbeState.shared.set(Control())
        let uiOwner = try ProcessLease.acquire(at: path)
        do { try TestFileManager.shared.deleteBackup(for: InstalledApp(uiBusyURL)); fatalError("UI busy admitted") }
        catch RenewalFailure.busy {}
        uiOwner.release()
        precondition(exists(uiBusyURL))

        let uiRequested = try makeBackup(root, "ui-requested")
        let uiAuthorized = try makeBackup(root, "ui-coordinated")
        let uiControl = Control(parkAfterAccessor: true, redirect: uiAuthorized)
        ProbeState.shared.set(uiControl)
        let uiTask = Task {
            try await runSynchronous { try TestFileManager.shared.deleteBackup(for: InstalledApp(uiRequested)) }
        }
        await wait(uiControl.accessorFinished)
        busy(path)
        precondition(exists(uiRequested) && !exists(uiAuthorized) && exists(unrelated))
        uiControl.allowAccessorReturn.signal()
        try await uiTask.value
        uiControl.assertActive(false)
        try free(path)

        for failure in 0..<3 {
            let victim = try makeBackup(root, "ui-failure-\(failure)")
            let control = Control(parkAfterAccessor: true, failCoordinator: failure == 0,
                                  failDeletion: failure == 1, omitAccessor: failure == 2)
            ProbeState.shared.set(control)
            let task = Task {
                try await runSynchronous { try TestFileManager.shared.deleteBackup(for: InstalledApp(victim)) }
            }
            await wait(control.accessorFinished)
            busy(path)
            precondition(exists(victim))
            control.allowAccessorReturn.signal()
            do { try await task.value; fatalError("UI failure succeeded") }
            catch ProbeFailure.deletion { precondition(failure == 1) }
            catch OperationError.unknownResult { precondition(failure == 2) }
            catch { precondition(failure == 0 && (error as NSError).domain == "BackupCoordinationProbe") }
            try free(path)
        }

        let uiNested = try makeBackup(root, "ui-nested")
        ProbeState.shared.set(Control())
        try await NativeMutationGate.withLease {
            try TestFileManager.shared.deleteBackup(for: InstalledApp(uiNested))
            precondition(!exists(uiNested))
            busy(path)
        }
        try free(path)

        // A synchronous caller's cancellation is reported after coordination
        // returns. It does not pretend a completed deletion was rolled back.
        let uiCancelled = try makeBackup(root, "ui-cancelled")
        let target = CancellationTarget()
        let cancellation = Control(onSynchronousReturn: { target.cancel() })
        ProbeState.shared.set(cancellation)
        let cancelledTask = Task {
            try TestFileManager.shared.deleteBackup(for: InstalledApp(uiCancelled))
        }
        target.set { cancelledTask.cancel() }
        do { try await cancelledTask.value; fatalError("UI cancellation succeeded") }
        catch is CancellationError {}
        precondition(!exists(uiCancelled))
        cancellation.assertActive(false)
        try free(path)

        let missingUI = Control()
        ProbeState.shared.set(missingUI)
        try TestFileManager.shared.deleteBackup(for: InstalledApp(nil))
        try TestFileManager.shared.deleteBackup(for: InstalledApp(absent))
        precondition(missingUI.deletionCount() == 0)
        try free(path)
        precondition(exists(unrelated))
        print("backup lifetime checks passed")
    }
}
