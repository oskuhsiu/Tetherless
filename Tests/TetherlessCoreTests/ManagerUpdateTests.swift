// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore

@Suite("Manager update journal: exact identities and real durable files, not device installation")
struct ManagerUpdateTests {
    let main = "org.tetherless.Tetherless"
    func identity(_ digest: String = "a", team: String = "TESTTEAM01", extensionDigest: String = "c") -> ManagerUpdateIdentity {
        ManagerUpdateIdentity(bundleID: main, teamID: team, version: "0.1.0", build: "0100", components: [
            .init(bundleID: main, profileSHA256: String(repeating: digest, count: 64), executableSHA256: String(repeating: digest, count: 64)),
            .init(bundleID: main + ".widget", profileSHA256: String(repeating: extensionDigest, count: 64), executableSHA256: String(repeating: extensionDigest, count: 64))])
    }
    func plan() -> ManagerUpdateRecord {
        .init(before: identity(), after: identity("b"), metadata: .init(originalBundleID: main,
              cacheFingerprint: String(repeating: "d", count: 64), certificateSerial: "abcdef0123", storeBuild: nil,
              extensionOriginalIDs: [main + ".widget": main + ".widget"]))
    }
    func withJournal(_ body: (ManagerUpdateJournal, URL) throws -> Void) throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        try body(ManagerUpdateJournal(storage: FileManagerUpdateStorage(root: root)), root)
    }
    @Test func writeAheadAndRestartReconciliation() throws {
        try withJournal { journal, root in
            let record = plan()
            try journal.stage(record, running: identity()); try journal.beginApplying(id: record.id)
            let restarted = ManagerUpdateJournal(storage: try FileManagerUpdateStorage(root: root))
            var saves = 0
            let reconciled = try restarted.reconcile(running: identity("b")) { received in
                #expect(received.metadata == record.metadata); saves += 1
            }
            #expect(reconciled)
            #expect(saves == 1); #expect(try restarted.read()?.phase == .completed)
            #expect(try !restarted.reconcile(running: identity("b")) { _ in Issue.record("Repeated completed recovery") })
        }
    }
    @Test func unchangedRunningBundleDoesNotRestoreOrErase() throws {
        try withJournal { journal, _ in
            let record = plan(); try journal.stage(record, running: identity()); try journal.beginApplying(id: record.id)
            #expect(throws: ManagerUpdateFailure.notInstalled) {
                try journal.reconcile(running: identity()) { _ in Issue.record("Wrong restore") }
            }
            #expect(try journal.read()?.phase == .applying)
        }
    }
    @Test func changedExtensionOrUnrelatedBuildIsNotSuccess() throws {
        try withJournal { journal, _ in
            let record = plan(); try journal.stage(record, running: identity()); try journal.beginApplying(id: record.id)
            for running in [identity("e"), identity("b", extensionDigest: "e")] {
                #expect(throws: ManagerUpdateFailure.identityMismatch) {
                    try journal.reconcile(running: running) { _ in Issue.record("Wrong restore") }
                }
            }
            #expect(try journal.read()?.phase == .applying)
        }
    }
    @Test func failedDatabaseSaveRetainsPendingForRetry() throws {
        try withJournal { journal, _ in
            let record = plan(); try journal.stage(record, running: identity()); try journal.beginApplying(id: record.id)
            #expect(throws: RenewalFailure.storageUnavailable) {
                try journal.reconcile(running: identity("b")) { _ in throw RenewalFailure.storageUnavailable }
            }
            #expect(try journal.read()?.phase == .applying)
            #expect(try journal.reconcile(running: identity("b")) { _ in })
        }
    }
    @Test func pendingCannotBeOverwrittenOrMarkedByAnotherGeneration() throws {
        try withJournal { journal, _ in
            let record = plan(); try journal.stage(record, running: identity())
            #expect(throws: ManagerUpdateFailure.pendingUpdate) { try journal.stage(plan(), running: identity()) }
            #expect(throws: ManagerUpdateFailure.wrongGeneration) { try journal.beginApplying(id: UUID()) }
            #expect(try journal.read() == record)
        }
    }
    @Test func preparedButUndispatchedCannotRestore() throws {
        try withJournal { journal, _ in
            try journal.stage(plan(), running: identity())
            #expect(throws: ManagerUpdateFailure.identityMismatch) {
                try journal.reconcile(running: identity("b")) { _ in Issue.record("Undispatched restore") }
            }
        }
    }
    @Test func explicitAbandonRequiresOriginalRunningIdentity() throws {
        try withJournal { journal, _ in
            try journal.stage(plan(), running: identity())
            #expect(throws: ManagerUpdateFailure.identityMismatch) { try journal.abandonUnapplied(running: identity("b")) }
            try journal.abandonUnapplied(running: identity())
            #expect(try journal.read()?.phase == .abandoned)
            try journal.stage(plan(), running: identity())
        }
    }
    @Test func malformedAndFutureRecordsAreNotReset() throws {
        try withJournal { journal, root in
            var record = plan(); record.schemaVersion = 99
            let bytes = try JSONEncoder().encode(record)
            let url = root.appendingPathComponent("manager-update.json")
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
            try bytes.write(to: url)
            #expect(throws: ManagerUpdateFailure.unsupportedSchema) { try journal.read() }
            #expect(try Data(contentsOf: url) == bytes)
        }
    }
    @Test func teamChangesAndMissingMainAreRejected() throws {
        let original = plan()
        let changed = ManagerUpdateRecord(before: identity(), after: identity("b", team: "DIFFTEAM01"), metadata: original.metadata)
        #expect(throws: ManagerUpdateFailure.invalidRecord) { try changed.validate() }
        let missing = ManagerUpdateIdentity(bundleID: main, teamID: "TESTTEAM01", version: "1", build: "1", components: [])
        #expect(throws: ManagerUpdateFailure.invalidRecord) { try missing.validate() }
    }
    @Test func failedCompletionReadbackRetainsRecoverableApplyingRecord() throws {
        struct DropCompletion: ManagerUpdateRecordStorage {
            let files: FileManagerUpdateStorage
            func read() throws -> Data? { try files.read() }
            func write(_ bytes: Data) throws {
                if try JSONDecoder().decode(ManagerUpdateRecord.self, from: bytes).phase == .completed { return }
                try files.write(bytes)
            }
        }
        try withJournal { journal, root in
            let record = plan(); try journal.stage(record, running: identity()); try journal.beginApplying(id: record.id)
            let failing = ManagerUpdateJournal(storage: DropCompletion(files: try FileManagerUpdateStorage(root: root)))
            var writes = 0
            #expect(throws: ManagerUpdateFailure.storageMismatch) {
                try failing.reconcile(running: identity("b")) { _ in writes += 1 }
            }
            #expect(writes == 1)
            #expect(try journal.read()?.phase == .applying)
            #expect(try journal.reconcile(running: identity("b")) { _ in writes += 1 })
            #expect(writes == 2) // Database write callback must be idempotent.
        }
    }
    @Test func versionAndBuildArePartOfTheExpectedRunningIdentity() throws {
        try withJournal { journal, _ in
            let record = plan(); try journal.stage(record, running: identity()); try journal.beginApplying(id: record.id)
            let expected = identity("b")
            let changed = ManagerUpdateIdentity(bundleID: main, teamID: expected.teamID,
                version: "9.0", build: expected.build, components: expected.components)
            #expect(throws: ManagerUpdateFailure.identityMismatch) {
                try journal.reconcile(running: changed) { _ in Issue.record("Wrong version restored") }
            }
            #expect(try journal.read()?.phase == .applying)
        }
    }
    @Test func corruptedRecordDoesNotGetReplacedByAStage() throws {
        try withJournal { journal, root in
            let bytes = Data("not a valid receipt".utf8)
            let files = try FileManagerUpdateStorage(root: root)
            try files.write(bytes)
            #expect(throws: ManagerUpdateFailure.invalidRecord) { try journal.stage(plan(), running: identity()) }
            #expect(try files.read() == bytes)
        }
    }
    @Test func ignoredWriteCannotDispatch() throws {
        struct DiscardWrites: ManagerUpdateRecordStorage {
            func read() throws -> Data? { nil }
            func write(_ data: Data) throws {}
        }
        let journal = ManagerUpdateJournal(storage: DiscardWrites())
        #expect(throws: ManagerUpdateFailure.storageMismatch) { try journal.stage(plan(), running: identity()) }
    }
}
