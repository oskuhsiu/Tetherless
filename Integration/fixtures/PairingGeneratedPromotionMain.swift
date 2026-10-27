// SPDX-License-Identifier: AGPL-3.0-only
// Actual-manager/store/reset/synchronous-wrapper execution with explicit app,
// parser and acquisition seams. No native ABI, real parser or device proof.
import Foundation
import MinimuxerCommon

@main struct PairingGeneratedPromotionMain {
    @MainActor static let manager = PairingFileManager.shared
    static let remote = AppConstants.Pairing.remotePairingFileName
    static let lockdown = AppConstants.Pairing.lockdownPairingFileName
    static let legacy = AppConstants.Pairing.legacyPairingFileName

    static func remoteRecord(_ identifier: String, keyBytes: Int = 32) throws -> PairingRecord {
        let bytes = try PropertyListSerialization.data(fromPropertyList: [
            "identifier": identifier, "private_key": Data(repeating: 1, count: keyBytes),
            "public_key": Data(repeating: 2, count: 32), "alt_irk": Data(repeating: 3, count: 16)
        ], format: .binary, options: 0)
        return try PairingRecord(data: bytes, expected: .remote)
    }
    static func lockdownRecord() throws -> PairingRecord {
        var value: [String: Any] = [:]
        for key in ["WiFiMACAddress", "SystemBUID", "HostID", "UDID"] { value[key] = "synthetic-only" }
        for key in ["RootPrivateKey", "HostPrivateKey", "RootCertificate", "EscrowBag", "HostCertificate", "DeviceCertificate"] {
            value[key] = Data([1])
        }
        return try PairingRecord(data: PropertyListSerialization.data(fromPropertyList: value, format: .xml, options: 0))
    }
    @MainActor static func fresh() throws -> PrivateFileStore {
        precondition(!PairingGeneratedFixture.lease.counts.held)
        let root = PairingGeneratedFixture.root
        if FileManager.default.fileExists(atPath: root.path) { try FileManager.default.removeItem(at: root) }
        for part in ["support", "documents", "lease"] {
            try FileManager.default.createDirectory(at: root.appendingPathComponent(part), withIntermediateDirectories: true)
        }
        manager.persistedActiveProtocol = .lockdown
        manager.preferredProtocol = .lockdown
        UserDefaults.standard.isPairingReset = false
        PairingFileParser.calls = 0; PairingFileParser.onParse = nil
        let store = try PrivateFileStore(root: PairingFileManager.protectedRoot)
        try store.prepare()
        return store
    }
    @MainActor static func seed(_ store: PrivateFileStore) throws -> (Data, Data) {
        let old = try remoteRecord("old").xml, fallback = try lockdownRecord().xml
        try store.write(old, named: remote); try store.write(fallback, named: lockdown)
        try Data("synthetic legacy".utf8).write(to: FileManager.default.documentsDirectory.appendingPathComponent(legacy))
        return (old, fallback)
    }
    @MainActor static func assertOldSelection() {
        precondition(manager.persistedActiveProtocol == .lockdown)
        precondition(manager.preferredProtocol == .lockdown)
    }
    static func check(_ condition: Bool) { precondition(condition) }
    static func expectFailure(_ body: () throws -> Void) {
        do { try body(); preconditionFailure("expected fixture failure") } catch {}
    }
    @MainActor static func report(_ name: String) { print("pairing_generated_fixture passed=" + name) }

    @MainActor static func testTypedEntryRejectsBeforeParserLeaseOrWrite() throws {
        let store = try fresh(); let (old, fallback) = try seed(store)
        let counts = PairingGeneratedFixture.lease.counts
        for record in [try lockdownRecord(), try remoteRecord("oversized", keyBytes: 4000)] {
            expectFailure { _ = try manager.saveValidatedRemotePairingRecord(record) }
        }
        precondition(PairingFileParser.calls == 0)
        precondition(PairingGeneratedFixture.lease.counts.acquired == counts.acquired)
        check(try store.read(remote) == old); check(try store.read(lockdown) == fallback)
        assertOldSelection(); precondition(!UserDefaults.standard.isPairingReset)
        report("typed_rejection_before_mutation")
    }
    @MainActor static func testParserFailurePrecedesWriteAndReleasesOwnedLease() throws {
        let store = try fresh(); let (old, fallback) = try seed(store)
        let record = try remoteRecord("new"), counts = PairingGeneratedFixture.lease.counts
        PairingFileParser.onParse = { content, preferred in
            precondition(content == record.content && preferred == .rppairing)
            precondition(PairingGeneratedFixture.lease.counts.held)
            check(try store.read(remote) == old)
            throw PairingFixtureFailure.parser
        }
        expectFailure { _ = try manager.saveValidatedRemotePairingRecord(record) }
        precondition(PairingFileParser.calls == 1)
        check(try store.read(remote) == old); check(try store.read(lockdown) == fallback)
        assertOldSelection()
        precondition(PairingGeneratedFixture.lease.counts.acquired == counts.acquired + 1)
        precondition(PairingGeneratedFixture.lease.counts.released == counts.released + 1)
        report("parser_failure_preserves_old_target")
    }
    @MainActor static func testOrdinaryReplacementKeepsFallbackAndLegacy() throws {
        let store = try fresh(); let (_, fallback) = try seed(store)
        let record = try remoteRecord("new")
        _ = try manager.saveValidatedRemotePairingRecord(record)
        check(try store.read(remote) == record.xml)
        check(try store.read(lockdown) == fallback)
        check(try Data(contentsOf: FileManager.default.documentsDirectory.appendingPathComponent(legacy)) == Data("synthetic legacy".utf8))
        check(try !PairingReset.isMarked(in: store))
        precondition(manager.persistedActiveProtocol == .rppairing)
        // Preferred selection still belongs to the successful app caller.
        precondition(manager.preferredProtocol == .lockdown)
        precondition(!UserDefaults.standard.isPairingReset)
        report("ordinary_replacement_keeps_fallback")
    }
    @MainActor static func testResetRecoveryCleansOnlyAfterReadback() throws {
        let store = try fresh(); let (old, fallback) = try seed(store)
        try store.write(Data([1]), named: PairingReset.marker)
        UserDefaults.standard.isPairingReset = true
        let record = try remoteRecord("after-reset")
        PairingFileParser.onParse = { _, _ in
            check(try store.read(remote) == old); check(try store.read(lockdown) == fallback)
            check(try PairingReset.isMarked(in: store))
        }
        _ = try manager.saveValidatedRemotePairingRecord(record)
        check(try store.read(remote) == record.xml); check(try store.read(lockdown) == nil)
        check(try !PairingReset.isMarked(in: store))
        precondition(!FileManager.default.fileExists(atPath: FileManager.default.documentsDirectory.appendingPathComponent(legacy).path))
        precondition(manager.persistedActiveProtocol == .rppairing && !UserDefaults.standard.isPairingReset)
        report("reset_marked_recovery_cleans_leftovers")
    }
    @MainActor static func testJoinedPromotionBorrowsOuterLeaseAndSavesExactBytes() async throws {
        let store = try fresh(); let (old, _) = try seed(store)
        let candidate = try remoteRecord("generated").xml
        let promotion = PairingPromotion(), cancellation = PairingCancellationController()
        let counts = PairingGeneratedFixture.lease.counts
        let identity = try NativeRenewalStorage.root().appendingPathComponent("device-mutation.lock").path
        var validated: Data?, joined = false
        let outcome = try await MutationScope.withLease(identity: identity, acquire: PairingGeneratedFixture.lease.acquire) {
            let result = await promotion.validateAndPromote(candidate: candidate, validate: { bytes in
                validated = bytes
                check(try store.read(remote) == old)
                await Task.yield(); joined = true
            }, readTarget: { try store.read(remote) }, commit: { record in
                precondition(joined && record.xml == validated)
                guard cancellation.beginPromotion() else { throw CancellationError() }
                PairingFileParser.onParse = { _, _ in
                    precondition(PairingGeneratedFixture.lease.counts.acquired == counts.acquired + 1)
                    precondition(PairingGeneratedFixture.lease.counts.released == counts.released)
                    precondition(PairingGeneratedFixture.lease.counts.held)
                    precondition(!cancellation.cancel())
                }
                _ = try manager.saveValidatedRemotePairingRecord(record)
                manager.preferredProtocol = .rppairing
            })
            precondition(PairingGeneratedFixture.lease.counts.released == counts.released)
            precondition(PairingGeneratedFixture.lease.counts.held)
            return result
        }
        precondition(outcome == .committed && joined)
        check(try store.read(remote) == validated)
        precondition(manager.preferredProtocol == .rppairing)
        precondition(PairingGeneratedFixture.lease.counts.acquired == counts.acquired + 1)
        precondition(PairingGeneratedFixture.lease.counts.released == counts.released + 1)
        cancellation.finish()
        report("exact_bytes_and_inherited_lease")
    }
    @MainActor static func testValidationAndCancellationNeverReachTypedSave() async throws {
        for cancelled in [false, true] {
            let store = try fresh(); let (old, fallback) = try seed(store)
            let promotion = PairingPromotion(), cancellation = PairingCancellationController()
            let outcome = await promotion.validateAndPromote(candidate: try remoteRecord("new").xml, validate: { _ in
                if cancelled { precondition(cancellation.cancel()) }
                else { throw PairingFixtureFailure.parser }
            }, readTarget: { try store.read(remote) }, commit: { record in
                guard cancellation.beginPromotion() else { throw CancellationError() }
                _ = try manager.saveValidatedRemotePairingRecord(record)
                manager.preferredProtocol = .rppairing
            })
            precondition(outcome == (cancelled ? .unchangedFailure : .validationFailed))
            precondition(PairingFileParser.calls == 0)
            check(try store.read(remote) == old); check(try store.read(lockdown) == fallback)
            assertOldSelection(); cancellation.finish()
        }
        report("validation_and_cancellation_preserve_old_target")
    }
    @MainActor static func testPostWriteResetCleanupFailureRequiresRecovery() async throws {
        let store = try fresh(); let (old, _) = try seed(store)
        try store.write(Data([1]), named: PairingReset.marker); UserDefaults.standard.isPairingReset = true
        // Real readExternal rejects this unsafe legacy leftover after the
        // protected lockdown fallback has already been removed. This deliberately
        // demonstrates partial cleanup, rather than pretending all files roll back.
        let unsafe = FileManager.default.documentsDirectory.appendingPathComponent(remote)
        try FileManager.default.createSymbolicLink(at: unsafe, withDestinationURL: PairingFileManager.protectedRoot.appendingPathComponent(remote))
        let promotion = PairingPromotion(), cancellation = PairingCancellationController()
        var validated: Data?
        let outcome = await promotion.validateAndPromote(candidate: try remoteRecord("new").xml,
            validate: { validated = $0 }, readTarget: { try store.read(remote) }, commit: { record in
                guard cancellation.beginPromotion() else { throw CancellationError() }
                _ = try manager.saveValidatedRemotePairingRecord(record)
                manager.preferredProtocol = .rppairing
            })
        precondition(outcome == .recoveryRequired)
        check(try store.read(remote) == validated && validated != old)
        check(try PairingReset.isMarked(in: store)); precondition(UserDefaults.standard.isPairingReset)
        check(try store.read(lockdown) == nil) // Earlier cleanup is not undone.
        precondition(manager.fetchPairingFile() == nil) // The tombstone still fails closed.
        assertOldSelection()
        check(try unsafe.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink == true)
        precondition(FileManager.default.fileExists(atPath: FileManager.default.documentsDirectory.appendingPathComponent(legacy).path))
        // Target readback reports ambiguity; it does not claim global rollback.
        cancellation.finish()
        report("post_write_cleanup_failure_requires_recovery")
    }
    @MainActor static func testUnavailableLeaseCannotEnterParserOrWrite() throws {
        let store = try fresh(); let (old, _) = try seed(store)
        let held = try PairingGeneratedFixture.lease.acquire(); defer { held() }
        expectFailure { _ = try manager.saveValidatedRemotePairingRecord(try remoteRecord("new")) }
        precondition(PairingFileParser.calls == 0); check(try store.read(remote) == old)
        assertOldSelection()
        report("unavailable_lease_blocks_mutation")
    }
    @MainActor static func main() async throws {
        try testTypedEntryRejectsBeforeParserLeaseOrWrite()
        try testParserFailurePrecedesWriteAndReleasesOwnedLease()
        try testOrdinaryReplacementKeepsFallbackAndLegacy()
        try testResetRecoveryCleansOnlyAfterReadback()
        try await testJoinedPromotionBorrowsOuterLeaseAndSavesExactBytes()
        try await testValidationAndCancellationNeverReachTypedSave()
        try await testPostWriteResetCleanupFailureRequiresRecovery()
        try testUnavailableLeaseCannotEnterParserOrWrite()
        precondition(!PairingGeneratedFixture.lease.counts.held)
    }
}
