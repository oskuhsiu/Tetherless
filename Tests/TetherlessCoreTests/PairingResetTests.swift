// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore

@Suite("Durable pairing reset, not a UserDefaults flag")
struct PairingResetTests {
    private func fixture(_ body: (PrivateFileStore) throws -> Void) throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try PrivateFileStore(root: root)
        try store.prepare()
        try body(store)
    }
    @Test func failedCleanupStillBlocksLegacyReactivation() throws {
        try fixture { store in
            try store.write(Data([7]), named: "first")
            try FileManager.default.createSymbolicLink(at: store.root.appendingPathComponent("second"), withDestinationURL: store.root)
            #expect(throws: PrivateFileError.unsafeFile) { try PairingReset.begin(in: store, deleting: ["first", "second"]) }
            // Reopen like a new process, without consulting in-memory state.
            let reopened = try PrivateFileStore(root: store.root)
            #expect(try PairingReset.isMarked(in: reopened))
            #expect(try reopened.read("first") == nil)
            #expect(FileManager.default.fileExists(atPath: store.root.path))
        }
    }
    @Test func onlyVerifiedNewImportCanClearMarker() throws {
        try fixture { store in
            try PairingReset.begin(in: store, deleting: ["pairing"])
            #expect(throws: PrivateFileError.invalidContent) { try PairingReset.finishImport(in: store, name: "pairing", expected: Data([8])) }
            #expect(try PairingReset.isMarked(in: store))
            try store.write(Data([8]), named: "pairing")
            try PairingReset.finishImport(in: store, name: "pairing", expected: Data([8]))
            #expect(try !PairingReset.isMarked(in: store))
        }
    }
    @Test func invalidResetDoesNotDeleteOrMark() throws {
        try fixture { store in
            try store.write(Data([1]), named: "pairing")
            #expect(throws: PrivateFileError.invalidName) { try PairingReset.begin(in: store, deleting: ["pairing", "../outside"]) }
            #expect(try !PairingReset.isMarked(in: store))
            #expect(try store.read("pairing") == Data([1]))
        }
    }
    @Test func failedLegacyCleanupCannotReactivateOldPairing() throws {
        try fixture { store in
            try PairingReset.begin(in: store, deleting: ["new"])
            try store.write(Data([1]), named: "legacy-leftover")
            try store.write(Data([2]), named: "new")
            do {
                try PairingReset.finishImport(in: store, name: "new", expected: Data([2])) {
                    throw PrivateFileError.unavailable
                }
                Issue.record("Expected cleanup failure to preserve reset marker")
            } catch let error as PrivateFileError {
                #expect(error == .unavailable)
            }
            #expect(try PairingReset.isMarked(in: store))
            #expect(try store.read("legacy-leftover") == Data([1]))
            try PairingReset.finishImport(in: store, name: "new", expected: Data([2])) {
                try store.remove("legacy-leftover")
            }
            #expect(try !PairingReset.isMarked(in: store))
            #expect(try store.read("legacy-leftover") == nil)
            #expect(try store.read("new") == Data([2]))
        }
    }
    @Test func ordinaryReplacementDoesNotRunResetCleanup() throws {
        try fixture { store in
            try store.write(Data([1]), named: "pairing")
            try PairingReset.finishImport(in: store, name: "pairing", expected: Data([1])) {
                throw PrivateFileError.unavailable
            }
            #expect(try store.read("pairing") == Data([1]))
        }
    }
}
