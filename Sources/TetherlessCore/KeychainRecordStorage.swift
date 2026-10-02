// SPDX-License-Identifier: AGPL-3.0-only
#if canImport(Security)
import Foundation
import Security
import LocalAuthentication

/// System Keychain adapter. Never interacts with shared/synchronizing items;
/// no prompt fallback is allowed during an unattended read.
public struct KeychainAuthenticationStorage: AuthenticationRecordStorage {
    private let service: String
    private let account: String
    public init(service: String, account: String = "authentication-v1") throws {
        guard !service.isEmpty, service.utf8.count <= 200,
              !account.isEmpty, account.utf8.count <= 128 else { throw AuthenticationStorageFailure.invalidRecord }
        self.service = service; self.account = account
    }
    private var query: [String: Any] {
        let context = LAContext()
        context.interactionNotAllowed = true
        return [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
         kSecAttrAccount as String: account, kSecAttrSynchronizable as String: false,
         kSecUseAuthenticationContext as String: context]
    }
    public func read() throws -> Data? {
        var query = query
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var value: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &value)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = value as? Data, data.count <= 65_536 else {
            throw AuthenticationStorageFailure.unavailable
        }
        return data
    }
    public func write(_ data: Data) throws {
        guard !data.isEmpty, data.count <= 65_536 else { throw AuthenticationStorageFailure.invalidRecord }
        let attributes: [String: Any] = [kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        let updated = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if updated == errSecSuccess { return }
        guard updated == errSecItemNotFound else { throw AuthenticationStorageFailure.unavailable }
        var add = query
        add.removeValue(forKey: kSecUseAuthenticationContext as String)
        for (key, value) in attributes { add[key] = value }
        guard SecItemAdd(add as CFDictionary, nil) == errSecSuccess else {
            throw AuthenticationStorageFailure.unavailable
        }
    }
    /// For explicit cleanup of this exact item only. Normal sign-out uses a
    /// tombstone, not deletion or a fallback to old credential fields.
    public func remove() throws {
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw AuthenticationStorageFailure.unavailable }
        guard try read() == nil else { throw AuthenticationStorageFailure.readbackMismatch }
    }
}
#endif
