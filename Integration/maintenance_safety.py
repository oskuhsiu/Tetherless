#!/usr/bin/env python3
"""Keep native cache maintenance inside the existing device-mutation lease."""
from pathlib import Path
import hashlib
import sys

APP = 'AltStore/Managing Apps/AppManager.swift'
CLEAR = 'SideStore/Core/Operations/StandaloneOperations/ClearAppCacheOperation.swift'


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Cache-maintenance boundary changed: ' + old[:80])
    return source.replace(old, new, 1)


def patch_app(source):
    # The old progress flag is process-local and is checked before suspension.
    # Own the lease BEFORE the DB snapshot, and retain it through cache pruning.
    # Locking only pruneUnusedCaches would still admit a stale snapshot.
    signature = '    func reconcileInstalledApps() async {'
    source = once(source, signature, '''    func reconcileInstalledApps() async {
        do {
            try Task.checkCancellation()
            try await NativeMutationGate.withLease {
                try Task.checkCancellation()
                // Preserve both old and replacement payloads until the manager
                // receipt has completed durable reconciliation and readback.
                if let update = try NativeManagerUpdate.journal().read(), update.phase.isPending {
                    throw ManagerUpdateFailure.pendingUpdate
                }
                await self.reconcileInstalledAppsWithNativeLease()
            }
        } catch {
            // A busy/expired maintenance attempt changes no cached payloads.
            // The next reconciliation takes a fresh database snapshot.
        }
    }

    private func reconcileInstalledAppsWithNativeLease() async {''')
    source = once(source,
        '            await scheduleExpirationWarning(for: altStoreApp, in: dbBackgroundContext)',
        '''            try Task.checkCancellation()
            await scheduleExpirationWarning(for: altStoreApp, in: dbBackgroundContext)
            try Task.checkCancellation()''')
    return source


def patch_clear(source):
    # Guard the operation, not only AppManager's current caller: future direct
    # invocations must not bypass the lock. The await retains the lease through
    # coordinator callbacks, deletes, backup enumeration and error completion.
    source = once(source, '    private let coordinatorQueue = OperationQueue()',
        '''    private let coordinatorQueue = OperationQueue()
    private let maintenanceCancellation = TetherlessMaintenanceCancellation()

    override func cancel() {
        maintenanceCancellation.cancel()
        super.cancel()
    }''')
    source = once(source, '        self.coordinatorQueue.name = "AltStore - ClearAppCacheOperation Queue"',
        '''        self.coordinatorQueue.name = "AltStore - ClearAppCacheOperation Queue"
        self.coordinatorQueue.maxConcurrentOperationCount = 1''')
    signature = '    override func execute(parentProgress: Progress?) async throws -> Bool {'
    source = once(source, signature, '''    override func execute(parentProgress: Progress?) async throws -> Bool {
        try await withTaskCancellationHandler {
            try Task.checkCancellation()
            return try await NativeMutationGate.withLease {
                try Task.checkCancellation()
                try maintenanceCancellation.check()
                return try await self.executeWithNativeLease(parentProgress: parentProgress)
            }
        } onCancel: {
            self.maintenanceCancellation.cancel()
        }
    }

    private func executeWithNativeLease(parentProgress: Progress?) async throws -> Bool {''')
    source = once(source,
        '        try await super.executePreconditionCheck(parentProgress: parentProgress)',
        '''        try await super.executePreconditionCheck(parentProgress: parentProgress)
        try maintenanceCancellation.check()''')
    source = once(source, '        self.setProgress(60)\n',
        '        try maintenanceCancellation.check()\n        self.setProgress(60)\n')
    source = once(source, '        self.setProgress(90)\n        if !allErrors.isEmpty {',
        '        try maintenanceCancellation.check()\n        self.setProgress(90)\n        if !allErrors.isEmpty {')
    source = once(source, '''        try await self.coordinator.coordinate(with: [intent], queue: self.coordinatorQueue)
        try self.clearTempDirItems(at: intent.url, coordinatorError: nil)''',
        '''        try await self.coordinator.coordinateMaintenanceMutation(
            with: intent, queue: self.coordinatorQueue, cancellation: maintenanceCancellation
        ) { [self] authorized in
            try self.clearTempDirItems(at: authorized, coordinatorError: nil,
                                       check: maintenanceCancellation.check)
        }''')
    source = once(source, '''        try await self.coordinator.coordinate(with: [intent], queue: self.coordinatorQueue)
        try self.removeBackupDirItems(at: intent.url, installedBundleIDs: installedAppBundleIDs, coordinatorError: nil)''',
        '''        try await self.coordinator.coordinateMaintenanceMutation(
            with: intent, queue: self.coordinatorQueue, cancellation: maintenanceCancellation
        ) { [self] authorized in
            try self.removeBackupDirItems(at: authorized, installedBundleIDs: installedAppBundleIDs,
                                         coordinatorError: nil, check: maintenanceCancellation.check)
        }''')
    source = once(source,
        '    private func clearTempDirItems(at url: URL, coordinatorError: Error?) throws {',
        '''    private func clearTempDirItems(at url: URL, coordinatorError: Error?, check: () throws -> Void) throws {
        try check()''')
    source = once(source, '''        let fileURLs = try FileManager.default.contentsOfDirectory(at: url,
                                                                   includingPropertiesForKeys: [],
                                                                   options: [.skipsSubdirectoryDescendants, .skipsHiddenFiles])''',
        '''        let fileURLs = try FileManager.default.contentsOfDirectory(at: url,
                                                                   includingPropertiesForKeys: [],
                                                                   options: [.skipsSubdirectoryDescendants, .skipsHiddenFiles])
            // TransferWorkspace owns this pool and its stable usage.lock.
            // The device-mutation lease does not replace that separate lock.
            // Normal transfer admission alone reclaims its abandoned stages.
            .filter { $0.lastPathComponent != "tetherless-oda-transfers-v1" }''')
    source = once(source,
        '    private func removeBackupDirItems(at url: URL, installedBundleIDs: Set<String>, coordinatorError: Error?) throws {',
        '''    private func removeBackupDirItems(at url: URL, installedBundleIDs: Set<String>, coordinatorError: Error?, check: () throws -> Void) throws {
        try check()''')
    for loop in (
        '        for (index, fileURL) in fileURLs.enumerated() {',
        '        for (index, backupDirectory) in fileURLs.enumerated() {',
    ):
        source = once(source, loop, loop + '\n            try check()')
    for removal in (
        '                try FileManager.default.removeItem(at: fileURL)',
        '                    try FileManager.default.removeItem(at: backupDirectory)',
    ):
        indent = removal[:len(removal) - len(removal.lstrip())]
        source = once(source, removal, indent + 'try check()\n' + removal)
    return source + COORDINATED_MUTATION


COORDINATED_MUTATION = '''
// The accessor is delivered on an OperationQueue, not the suspended Swift task.
// Carry cancellation explicitly, including Progress/operation.cancel(), and
// never resume the caller until all accessor-owned filesystem work has stopped.
private final class TetherlessMaintenanceCancellation: @unchecked Sendable {
    private let lock = NSLock()
    private var cancelled = false
    func cancel() {
        lock.lock(); defer { lock.unlock() }
        cancelled = true
    }
    func check() throws {
        lock.lock(); defer { lock.unlock() }
        if cancelled { throw CancellationError() }
    }
}

// NSFileCoordinator owns the intent's coordinated URL while invoking accessor.
// Sharing this immutable holder does not expose it to a concurrent mutation.
private final class TetherlessMaintenanceAccess: @unchecked Sendable {
    let intent: NSFileAccessIntent
    init(_ intent: NSFileAccessIntent) { self.intent = intent }
}

private extension NSFileCoordinator {
    func coordinateMaintenanceMutation(with intent: NSFileAccessIntent,
            queue: OperationQueue, cancellation: TetherlessMaintenanceCancellation,
            body: @escaping @Sendable (URL) throws -> Void) async throws {
        let access = TetherlessMaintenanceAccess(intent)
        try cancellation.check()
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            self.coordinate(with: [access.intent], queue: queue) { error in
                let result: Result<Void, Error>
                do {
                    if let error { throw error }
                    try cancellation.check()
                    try body(access.intent.url)
                    try cancellation.check()
                    result = .success(())
                } catch {
                    result = .failure(error)
                }
                // This queue is serial. Its next operation cannot resume the
                // awaiting lease owner until the accessor operation returns.
                queue.addOperation { continuation.resume(with: result) }
            }
        }
    }
}
'''


PATCHES = {APP: patch_app, CLEAR: patch_clear}
# Exact SideStore 0dd743f inputs after catalog_safety changes AppManager.
BLOBS = {APP: 'ae9ed3e39d77aebda142b1dae716769967ac2259',
         CLEAR: '5f92f47c3c6815e15cb189783a5ed1bc012b2488'}


def apply(root):
    outputs = {}
    for relative, patch in PATCHES.items():
        raw = (root / relative).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != BLOBS[relative]:
            raise ValueError('Unreviewed cache-maintenance source: ' + relative)
        outputs[root / relative] = patch(raw.decode())
    for path, content in outputs.items():
        path.write_text(content)


if __name__ == '__main__':
    apply(Path(sys.argv[1]))
