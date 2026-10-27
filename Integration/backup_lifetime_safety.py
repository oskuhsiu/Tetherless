#!/usr/bin/env python3
"""Hold the native lease and coordinated accessor through backup deletion."""
from pathlib import Path
import hashlib
import importlib.util
import sys

SOURCE = 'SideStore/Core/Operations/PipelineOperations/RemoveBackupDataOperation.swift'
HELPER = 'AltStore/Core/Extensions/FileManager+Backups.swift'
# SideStore 0dd743f75afc358b0ba4a002feb5f19474492371. No earlier transform changes
# this file: the input is still the pinned upstream blob after maintenance_safety.
EXPECTED = '0ee77641720c5c5592a123f727608a2888bbbfce'
HELPER_EXPECTED = 'c65acfdb39a5b17225a5155cdb35d2321153f186'


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Backup-lifetime boundary changed: ' + old[:80])
    return source.replace(old, new, 1)


def coordination_bridge():
    # Reuse the reviewed maintenance ownership contract without widening its
    # file-private declarations or changing another operation's transform.
    spec = importlib.util.spec_from_file_location(
        'backup_maintenance_contract', Path(__file__).with_name('maintenance_safety.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.COORDINATED_MUTATION.replace('Maintenance', 'Backup')


def patch(source):
    source = once(source, '    private let coordinatorQueue = OperationQueue()', '''    private let coordinatorQueue: OperationQueue = {
        let queue = OperationQueue()
        queue.name = "Tetherless - RemoveBackupDataOperation Queue"
        queue.maxConcurrentOperationCount = 1
        return queue
    }()
    private let backupCancellation = TetherlessBackupCancellation()

    override func cancel() {
        backupCancellation.cancel()
        super.cancel()
    }''')
    source = once(source,
        '    override func execute(parentProgress: Progress?) async throws -> Bool {',
        '''    override func execute(parentProgress: Progress?) async throws -> Bool {
        try await withTaskCancellationHandler {
            try Task.checkCancellation()
            return try await NativeMutationGate.withLease {
                try Task.checkCancellation()
                try backupCancellation.check()
                return try await self.executeWithNativeLease(parentProgress: parentProgress)
            }
        } onCancel: {
            self.backupCancellation.cancel()
        }
    }

    private func executeWithNativeLease(parentProgress: Progress?) async throws -> Bool {''')
    source = once(source,
        '        try await super.executePreconditionCheck(parentProgress: parentProgress)',
        '''        try await super.executePreconditionCheck(parentProgress: parentProgress)
        try backupCancellation.check()''')
    source = once(source, '        guard let backupDirectoryURL else {',
        '''        try backupCancellation.check()
        guard let backupDirectoryURL else {''')
    source = once(source,
        '''        try await self.coordinator.coordinate(with: [intent], queue: self.coordinatorQueue)
        
        self.setProgress(80)
        try self.removeBackupItem(at: intent.url, backupDirectoryURL: backupDirectoryURL, coordinatorError: nil)''',
        '''        try await self.coordinator.coordinateBackupMutation(
            with: intent, queue: self.coordinatorQueue, cancellation: backupCancellation
        ) { [self] authorized in
            self.setProgress(80)
            try self.removeBackupItem(at: authorized, backupDirectoryURL: backupDirectoryURL,
                                      coordinatorError: nil, check: backupCancellation.check)
        }
        try backupCancellation.check()''')
    source = once(source,
        '    private func removeBackupItem(at url: URL, backupDirectoryURL: URL, coordinatorError: Error?) throws {',
        '''    private func removeBackupItem(at url: URL, backupDirectoryURL: URL,
                                  coordinatorError: Error?, check: () throws -> Void) throws {
        try check()''')
    source = once(source, '            try FileManager.default.removeItem(at: url)',
        '''            try check()
            try FileManager.default.removeItem(at: url)''')
    return source + coordination_bridge()


def patch_helper(source):
    return once(source,
        '        try self.deleteBackup(forBundleIdentifier: app.resignedBundleIdentifier)',
        '''        try Task.checkCancellation()
        try NativeMutationGate.withSynchronousLease {
            try Task.checkCancellation()
            // Keep the main-app UI route under the same lease as the pipeline.
            // Shared's helper is also built into other targets and stays generic.
            guard let backupDirectoryURL = self.backupDirectoryURL(for: app),
                  self.fileExists(atPath: backupDirectoryURL.path) else { return }
            let coordinator = NSFileCoordinator(filePresenter: nil)
            var coordinationError: NSError?
            var deletion: Result<Void, Error>?
            coordinator.coordinate(writingItemAt: backupDirectoryURL, options: .forDeleting,
                                   error: &coordinationError) { authorized in
                deletion = Result {
                    try Task.checkCancellation()
                    guard self.fileExists(atPath: authorized.path) else { return }
                    try self.removeItem(at: authorized)
                }
            }
            // This synchronous API has returned from its accessor before any
            // result (including cancellation or failure) can leave the lease.
            if let coordinationError { throw coordinationError }
            guard let deletion else { throw OperationError.unknownResult }
            try deletion.get()
            try Task.checkCancellation()
        }''')


PATCHES = {SOURCE: patch, HELPER: patch_helper}
BLOBS = {SOURCE: EXPECTED, HELPER: HELPER_EXPECTED}


def apply(root: Path):
    outputs = {}
    for relative, transform in PATCHES.items():
        target = root / relative
        raw = target.read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != BLOBS[relative]:
            raise ValueError('Unreviewed backup-lifetime source: ' + relative)
        outputs[target] = transform(raw.decode('utf-8'))
    for target, replacement in outputs.items():
        target.write_text(replacement, encoding='utf-8')


if __name__ == '__main__':
    apply(Path(sys.argv[1]))
