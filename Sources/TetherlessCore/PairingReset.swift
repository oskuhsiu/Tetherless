// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// A durable reset marker prevents crash/failed cleanup from reimporting a
/// legacy record. UserDefaults alone is not a write-ahead transaction boundary.
public enum PairingReset {
    public static let marker = "reset.marker"
    public static func isMarked(in store: PrivateFileStore) throws -> Bool {
        try store.read(marker) != nil
    }
    public static func begin(in store: PrivateFileStore, deleting names: [String]) throws {
        guard !names.isEmpty, Set(names).count == names.count,
              names.allSatisfy({ PrivateFileStore.validName($0) && $0 != marker }) else {
            throw PrivateFileError.invalidName
        }
        try store.write(Data([1]), named: marker)
        for name in names { try store.remove(name) }
    }
    /// Only after a new record has been durably committed and read back.
    public static func finishImport(in store: PrivateFileStore, name: String, expected: Data) throws {
        guard PrivateFileStore.validName(name), name != marker,
              !expected.isEmpty, try store.read(name) == expected else { throw PrivateFileError.invalidContent }
        try store.remove(marker)
    }
}
