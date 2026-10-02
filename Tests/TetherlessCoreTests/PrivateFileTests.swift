// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

@Suite("Protected files: real IO and crash-before-promote injection")
struct PrivateFileTests {
    private func fixture(_ body: (URL, PrivateFileStore) throws -> Void) throws {
        let parent = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: parent, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: parent) }
        let store = try PrivateFileStore(root: parent.appendingPathComponent("vault"), maximumBytes: 1024)
        try store.prepare()
        try body(parent, store)
    }
    @Test func roundTripPermissionsAndBoundedRead() throws {
        try fixture { _, store in
            try store.write(Data("pair".utf8), named: "pair.plist")
            #expect(try store.read("pair.plist") == Data("pair".utf8))
            let attrs = try FileManager.default.attributesOfItem(atPath: store.root.appendingPathComponent("pair.plist").path)
            #expect((attrs[.posixPermissions] as? NSNumber)?.intValue == 0o600)
            #expect(throws: PrivateFileError.tooLarge) { try store.write(Data(count: 1025), named: "pair.plist") }
            #expect(try store.read("pair.plist") == Data("pair".utf8))
        }
    }
    @Test func failedPromotionPreservesOriginalAndCleansTemporaryFile() throws {
        try fixture { _, store in
            try store.write(Data("old".utf8), named: "pair.plist")
            #expect(throws: PrivateFileError.unavailable) {
                try store.write(Data("new".utf8), named: "pair.plist") { _ in throw PrivateFileError.unavailable }
            }
            #expect(try store.read("pair.plist") == Data("old".utf8))
            #expect(try FileManager.default.contentsOfDirectory(atPath: store.root.path) == ["pair.plist"])
        }
    }
    @Test(arguments: ["", "..", "../pair", "a/b", "a\\b", "a\u{0000}", String(repeating: "x", count: 129)])
    func namesCannotEscape(_ value: String) throws {
        try fixture { _, store in #expect(throws: PrivateFileError.invalidName) { try store.write(Data([1]), named: value) } }
    }
    @Test func symlinkAndHardlinkCannotBeReadOrOverwritten() throws {
        try fixture { parent, store in
            let target = parent.appendingPathComponent("original")
            try Data([4]).write(to: target)
            let linkURL = store.root.appendingPathComponent("pair.plist")
            try FileManager.default.createSymbolicLink(at: linkURL, withDestinationURL: target)
            #expect(throws: PrivateFileError.unsafeFile) { try store.read("pair.plist") }
            #expect(throws: PrivateFileError.unsafeFile) { try store.write(Data([5]), named: "pair.plist") }
            #expect(try Data(contentsOf: target) == Data([4]))
            try FileManager.default.removeItem(at: linkURL)
            try FileManager.default.linkItem(at: target, to: linkURL)
            #expect(throws: PrivateFileError.unsafeFile) { try store.read("pair.plist") }
            #expect(throws: PrivateFileError.unsafeFile) { try store.write(Data([5]), named: "pair.plist") }
        }
    }
    @Test func fifoReadNeverBlocks() throws {
        try fixture { _, store in
            let path = store.root.appendingPathComponent("fifo").path
            #expect(mkfifo(path, 0o600) == 0)
            #expect(throws: PrivateFileError.unsafeFile) { try store.read("fifo") }
        }
    }
    @Test func migrationOnlyRemovesSourceAfterVerifiedSave() throws {
        try fixture { parent, store in
            let source = parent.appendingPathComponent("legacy")
            try Data([1]).write(to: source)
            #expect(try store.migrate(source, to: "pair.plist", normalize: { $0 }))
            #expect(!FileManager.default.fileExists(atPath: source.path))
            #expect(try store.read("pair.plist") == Data([1]))
            #expect(try !store.migrate(source, to: "pair.plist", normalize: { $0 }))
        }
    }
    @Test func conflictAndInvalidMigrationNeverDeleteSource() throws {
        try fixture { parent, store in
            let source = parent.appendingPathComponent("legacy")
            try Data([1]).write(to: source)
            try store.write(Data([2]), named: "pair.plist")
            #expect(throws: PrivateFileError.conflict) { try store.migrate(source, to: "pair.plist", normalize: { $0 }) }
            #expect(try Data(contentsOf: source) == Data([1]))
            #expect(try store.read("pair.plist") == Data([2]))
            #expect(throws: PrivateFileError.invalidContent) {
                try store.migrate(source, to: "new.plist") { _ in throw PrivateFileError.invalidContent }
            }
            #expect(try Data(contentsOf: source) == Data([1]))
        }
    }
    @Test func existingSymlinkRootIsRejected() throws {
        try fixture { parent, _ in
            let linkURL = parent.appendingPathComponent("redirect")
            try FileManager.default.createSymbolicLink(at: linkURL, withDestinationURL: parent)
            let redirected = try PrivateFileStore(root: linkURL)
            #expect(throws: PrivateFileError.unavailable) { try redirected.prepare() }
        }
    }
    @Test func externalOversizeAndDirectoryAreRejected() throws {
        try fixture { parent, _ in
            let file = parent.appendingPathComponent("large")
            try Data(count: 1025).write(to: file)
            #expect(throws: PrivateFileError.tooLarge) { try PrivateFileStore.readExternal(file, maximum: 1024) }
            #expect(throws: PrivateFileError.unsafeFile) { try PrivateFileStore.readExternal(parent) }
        }
    }
    #if os(iOS) || os(tvOS)
    @Test func actualIOSProtectionAndBackupExclusion() throws {
        try fixture { _, store in
            try store.write(Data([1]), named: "pair.plist")
            let attrs = try FileManager.default.attributesOfItem(atPath: store.root.appendingPathComponent("pair.plist").path)
            #expect(attrs[.protectionKey] as? FileProtectionType == .completeUntilFirstUserAuthentication)
            #expect(try store.root.resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup == true)
        }
    }
    #endif
}

@Suite("Pairing type validation; fixtures contain synthetic bytes, never live keys")
struct PairingRecordTests {
    private var remote: [String: Any] { ["identifier": "SYNTHETIC", "private_key": Data([1]), "public_key": Data([2])] }
    private func encode(_ value: [String: Any], _ format: PropertyListSerialization.PropertyListFormat = .xml) throws -> Data {
        try PropertyListSerialization.data(fromPropertyList: value, format: format, options: 0)
    }
    @Test func remoteXMLAndBinaryNormalizeIdentically() throws {
        let xml = try PairingRecord(data: encode(remote))
        let binary = try PairingRecord(data: encode(remote, .binary))
        #expect(xml.kind == .remote)
        #expect(xml.xml == binary.xml)
        #expect(xml.content.contains("<plist"))
    }
    @Test func lockdownRequiresTypedNonemptySecrets() throws {
        var value: [String: Any] = ["WiFiMACAddress": "SYNTHETIC", "SystemBUID": "SYNTHETIC", "HostID": "SYNTHETIC", "UDID": "SYNTHETIC"]
        for key in ["RootPrivateKey", "HostPrivateKey", "RootCertificate", "EscrowBag", "HostCertificate", "DeviceCertificate"] { value[key] = Data([1]) }
        #expect(try PairingRecord(data: encode(value)).kind == .lockdown)
        value["HostPrivateKey"] = "not data"
        #expect(throws: PrivateFileError.invalidContent) { try PairingRecord(data: encode(value)) }
    }
    @Test func rejectsAmbiguousOrWrongProtocol() throws {
        var value = remote; value["UDID"] = "SYNTHETIC"
        #expect(throws: PrivateFileError.invalidContent) { try PairingRecord(data: encode(value)) }
        #expect(throws: PrivateFileError.invalidContent) { try PairingRecord(data: encode(remote), expected: .lockdown) }
    }
    @Test func rejectsEmptyAndWrongTypeKeys() throws {
        for key in remote.keys {
            var value = remote; value[key] = Data()
            #expect(throws: PrivateFileError.invalidContent) { try PairingRecord(data: encode(value)) }
        }
    }
    @Test func rejectsEntityExpansionAndExcessiveDepth() throws {
        let xml = Data("<!DOCTYPE plist [<!ENTITY x 'unsafe'>]><plist/>".utf8)
        #expect(throws: PrivateFileError.invalidContent) { try PairingRecord(data: xml) }
        var value = remote
        var nested: Any = "leaf"
        for _ in 0..<20 { nested = [nested] }
        value["extra"] = nested
        #expect(throws: PrivateFileError.invalidContent) { try PairingRecord(data: encode(value)) }
    }
    @Test func extraFieldsPreserved() throws {
        var value = remote; value["future-key"] = Data([7,8,9])
        let record = try PairingRecord(data: encode(value))
        let decoded = try PropertyListSerialization.propertyList(from: record.xml, format: nil) as? [String: Any]
        #expect(decoded?["future-key"] as? Data == Data([7,8,9]))
    }
}

@Suite("Synchronous import shares its admitted async mutation lease")
struct SynchronousMutationTests {
    @Test func nestedSyncDoesNotTryToRelock() async throws {
        let result = try await MutationScope.withLease(identity: "pair", acquire: { {} }) {
            try MutationScope.withSynchronousLease(identity: "pair", acquire: { throw RenewalFailure.busy }) { 17 }
        }
        #expect(result == 17)
    }
    @Test func standaloneSyncActuallyAcquiresAndReleasesOSLease() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let url = root.appendingPathComponent("lock")
        try MutationScope.withSynchronousLease(identity: url.path, acquire: {
            let lease = try ProcessLease.acquire(at: url); return { lease.release() }
        }) {
            #expect(throws: RenewalFailure.busy) { try ProcessLease.acquire(at: url) }
        }
        let new = try ProcessLease.acquire(at: url); new.release()
    }
}
