// SPDX-License-Identifier: AGPL-3.0-only
#if canImport(Darwin)
import Foundation
import Testing
@testable import TetherlessCore

@Suite("Backup exclusion is testable separately from hardware Data Protection")
struct BackupExclusionTests {
    @Test func protectedStoreIsExcludedFromBackup() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try PrivateFileStore(root: root)
        try store.prepare()
        try store.write(Data([1]), named: "record.plist")
        #expect(try root.resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup == true)
        #expect(try store.read("record.plist") == Data([1]))
    }
}
#endif
