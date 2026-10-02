#!/usr/bin/env python3
"""Checked certificate storage; applied after existing account/update transforms."""
from pathlib import Path
import hashlib
import sys

KEYCHAIN = 'AltStore/Core/Components/Keychain.swift'
MANAGER = 'SideStore/Core/Certificates/CertificateManager.swift'
FLOW = 'SideStore/Core/Auth/Flows/CertificateProvisioningFlow.swift'
PROXY = 'SideStore/Core/Auth/DeveloperPortalProxy.swift'
AUTH = 'SideStore/Core/Auth/AuthManager.swift'
VIEW = 'SideStore/Views/Settings/Advanced/Certificates/CertificatesViewModel.swift'
DATABASE = 'AltStore/Core/Model/DatabaseManager/DatabaseManager.swift'
KEY_INPUT = 'SideStore/Views/Settings/Advanced/Certificates/PrivateKeyTextInputView.swift'
ROOT = Path(__file__).parent


def once(source, old, new):
    if source.count(old) != 1: raise ValueError('Certificate anchor changed: ' + old[:70])
    return source.replace(old, new, 1)


def span(source, start, end, body):
    if source.count(start) != 1 or source.count(end) != 1: raise ValueError('Certificate boundaries changed')
    prefix, tail = source.split(start)
    _, suffix = tail.split(end)
    return prefix + body + end + suffix


KEYCHAIN_METHODS = r'''
// Read/write failures propagate. New signer/cache items never use the legacy
// subscript that discards OSStatus. Public DER cannot overwrite a private P12.
extension Keychain {
    private func checkedSerial(_ serial: String) throws -> String {
        guard !serial.isEmpty, serial.utf8.count <= 128,
              serial.utf8.allSatisfy({ (48...57).contains($0) || (65...70).contains($0) || (97...102).contains($0) }) else {
            throw AuthenticationStorageFailure.invalidRecord
        }
        return serial.lowercased()
    }
    private func cacheStorage(serial: String, publicOnly: Bool = false) throws -> KeychainAuthenticationStorage {
        let serial = try checkedSerial(serial)
        let key = NativeRenewalStorage.digest(Data(serial.utf8))
        return try KeychainAuthenticationStorage(service: "org.tetherless.credentials." + Bundle.Info.appbundleIdentifier,
            account: (publicOnly ? "public-certificate-v1." : "cached-signing-v1.") + key)
    }
    private func legacySerialVariants(_ serial: String) throws -> [String] {
        _ = try checkedSerial(serial)
        // The legacy password was the original serial's spelling. Preserve it.
        let registry = UserDefaults.standard.stringArray(forKey: "importedCertificateSerials") ?? []
        guard registry.count <= 4096 else { throw AuthenticationStorageFailure.invalidRecord }
        let matches = registry.filter { $0.caseInsensitiveCompare(serial) == .orderedSame }
        return Array(Set([serial, serial.lowercased(), serial.uppercased()] + matches)).sorted()
    }
    func readLegacyActiveSigningVerified() throws -> (Data, String?)? {
        guard let bytes = try self.keychain.getData("signingCertificate") else {
            // Incomplete split records are not a trustworthy "no certificate".
            if try self.keychain.getData("signingCertificatePrivateKey") != nil {
                throw AuthenticationStorageFailure.invalidRecord
            }
            return nil
        }
        guard !bytes.isEmpty, bytes.count <= 32_768 else { throw AuthenticationStorageFailure.invalidRecord }
        let password = try self.keychain.getString("signingCertificatePassword")
        if bytes.isPKCS12 { return (bytes, password) }
        // Checked migration of the earlier DER+private-key format. No writes or
        // deletions occur here; the caller first commits a verified new envelope.
        guard let x509 = ALTX509Certificate(data: bytes),
              let privateKey = try self.keychain.getData("signingCertificatePrivateKey"),
              !privateKey.isEmpty, privateKey.count <= 32_768 else { throw AuthenticationStorageFailure.invalidRecord }
        let signer = ALTCertificate(x509: x509, privateKey: privateKey)
        return (try CertificateManager.convert(signer, password: nil), nil)
    }
    func writeImportedCertificateVerified(_ bytes: Data, serial: String) throws {
        let record = try StoredSigningIdentity(serial: serial, p12: bytes, password: serial)
        try VerifiedSigningIdentityStore(storage: cacheStorage(serial: serial)).save(record)
        // A checked new cache record is authoritative, so stale old entries are
        // unnecessary. Cleanup failure is reported but does not erase the key.
        try removeVerified(legacySerialVariants(serial).map { "importedCert_" + $0 })
    }
    func readCachedSigningIdentityVerified(serial: String) throws -> StoredSigningIdentity? {
        let storage = try VerifiedSigningIdentityStore(storage: cacheStorage(serial: serial))
        if let envelope = try storage.read() {
            if let identity = envelope.identity {
                guard identity.serial.caseInsensitiveCompare(serial) == .orderedSame else { throw AuthenticationStorageFailure.invalidRecord }
            }
            return envelope.identity // Explicit tombstone never falls back.
        }
        var candidate: StoredSigningIdentity?
        for variant in try legacySerialVariants(serial) {
            guard let bytes = try self.keychain.getData("importedCert_" + variant) else { continue }
            guard !bytes.isEmpty, bytes.count <= 32_768 else { throw AuthenticationStorageFailure.invalidRecord }
            guard bytes.isPKCS12 else {
                guard let cert = ALTX509Certificate(data: bytes),
                      cert.serialNumber.caseInsensitiveCompare(serial) == .orderedSame else { throw AuthenticationStorageFailure.invalidRecord }
                continue // Legacy public-only record, not a missing private write.
            }
            let record = try StoredSigningIdentity(serial: serial, p12: bytes, password: variant)
            if let previous = candidate, previous.p12 != record.p12 { throw AuthenticationStorageFailure.invalidRecord }
            candidate = record
        }
        return candidate
    }
    func writePublicCertificateVerified(_ bytes: Data, serial: String) throws {
        guard !bytes.isEmpty, bytes.count <= 32_768, let cert = ALTX509Certificate(data: bytes),
              cert.serialNumber.caseInsensitiveCompare(serial) == .orderedSame else { throw AuthenticationStorageFailure.invalidRecord }
        let storage = try cacheStorage(serial: serial, publicOnly: true)
        try storage.write(bytes)
        guard try storage.read() == bytes else { throw AuthenticationStorageFailure.readbackMismatch }
    }
    func readPublicCertificateVerified(serial: String) throws -> Data? {
        if let bytes = try cacheStorage(serial: serial, publicOnly: true).read() { return bytes }
        for variant in try legacySerialVariants(serial) {
            guard let bytes = try self.keychain.getData("importedCert_" + variant) else { continue }
            guard !bytes.isEmpty, bytes.count <= 32_768 else { throw AuthenticationStorageFailure.invalidRecord }
            if !bytes.isPKCS12 { return bytes }
        }
        return nil
    }
    func removeCachedCertificateVerified(serial: String, includePublic: Bool) throws {
        // Persist a private-key tombstone BEFORE deleting legacy cache entries.
        try VerifiedSigningIdentityStore(storage: cacheStorage(serial: serial)).save(nil)
        try removeVerified(legacySerialVariants(serial).map { "importedCert_" + $0 })
        if includePublic { try cacheStorage(serial: serial, publicOnly: true).remove() }
    }
}
'''


def patch_keychain(source):
    source = span(source, '    private init()\n', '    // Checked removal is used',
                  '    private init() {} // No unchecked destructive migration during singleton initialization.\n\n')
    # The old subscript and wrappers are not used by the new manager; retain
    # their declaration for source compatibility but remove the destructive path.
    return source + KEYCHAIN_METHODS


def patch_proxy(source):
    return once(source,
        '            return try await ALTAppleAPI.shared.addCertificate(machineName: machineName, type: type, to: team, session: session)',
        '''            let created = try await ALTAppleAPI.shared.addCertificate(machineName: machineName, type: type, to: team, session: session)
            // Preserve the returned key BEFORE any extra portal fetch or caller cancellation.
            // A failure here propagates; it must not become "created successfully".
            try CertificateManager.shared.saveCertificate(created)
            return created''')


def patch_auth(source):
    return once(source, '                CertificateManager.shared.clearActiveCertificate()',
                       '                try CertificateManager.shared.clearActiveCertificate()')


def patch_database(source):
    source = once(source,
        '            self.reconcileSelfFromSelfBinary(installedApp: installedApp, localAppBundle: localAppBundle, serialNumber: serialNumber)',
        '            try self.reconcileSelfFromSelfBinary(installedApp: installedApp, localAppBundle: localAppBundle, serialNumber: serialNumber)')
    source = once(source,
        '    private func reconcileSelfFromSelfBinary(installedApp: InstalledApp, localAppBundle: ALTApplication, serialNumber: String?) {',
        '    private func reconcileSelfFromSelfBinary(installedApp: InstalledApp, localAppBundle: ALTApplication, serialNumber: String?) throws {')
    return once(source, '            CertificateManager.shared.saveX509Certificate(binaryCert)',
                       '            try CertificateManager.shared.saveX509Certificate(binaryCert)')


def patch_view(source):
    source = once(source, '    func saveLocalCertificate(_ cert: ALTCertificate) {',
                         '    func saveLocalCertificate(_ cert: ALTCertificate) throws {')
    source = once(source, '    func deleteLocalCertificate(serialNumber: String) {',
                         '    func deleteLocalCertificate(serialNumber: String) throws {')
    # Every old call was inspected: either already in do/catch or wrapped below.
    import re
    source, calls = re.subn(r'(?m)^(\s*)((?:self\.)?(?:saveLocalCertificate|deleteLocalCertificate)|CertificateManager\.shared\.(?:saveCertificate|saveX509Certificate|deleteCertificate|clearActiveCertificate))\(', r'\1try \2(', source)
    if calls != 16: raise ValueError('Certificate write call inventory changed: ' + str(calls))
    source = once(source, '''                try CertificateManager.shared.saveX509Certificate(rawCert)
                recordSuccessfulImport(serial: rawCert.serialNumber, hasPrivateKey: false, filename: pending.filename)''',
        '''                do {
                    try CertificateManager.shared.saveX509Certificate(rawCert)
                    recordSuccessfulImport(serial: rawCert.serialNumber, hasPrivateKey: false, filename: pending.filename)
                } catch {
                    failedImportsList.append("\\(pending.filename): Certificate could not be saved.")
                    importFailedCount += 1
                }''')
    # These user actions formerly reported success unconditionally.
    for start, end in [('    func deleteCertificate(_ certificate: ALTX509Certificate) {',
                        '    func makeCertificateActive('),
                       ('    func deactivateActiveCertificate() {', '    func isCertificateLocallyCached('),
                       ('    func clearPrivateKey(for cert: ALTX509Certificate) {', '    private func recordSuccessfulImport(')]:
        a = source.index(start) + len(start)
        b = source.index(end, a)
        middle = source[a:b]
        close = middle.rfind('    }')
        if close < 0: raise ValueError('Certificate action boundary changed')
        body = middle[:close]
        if 'clearPrivateKey' in start:
            body = once(body, 'try CertificateManager.shared.saveX509Certificate(cert)',
                              'try CertificateManager.shared.removePrivateKey(for: cert)')
        wrapped = '\n        do {' + '\n'.join('    ' + line if line.strip() else line for line in body.splitlines())
        wrapped += '\n        } catch { self.errorMessage = "Certificate change failed. Local signing material was not reported as removed." }\n    }\n\n'
        source = source[:a] + wrapped + source[b:]
    source = once(source, '    func startBulkImport(urls: [URL]) {', '''    func startBulkImport(urls: [URL]) {
        guard urls.count <= 128 else { self.errorMessage = "Import at most 128 certificate files at a time."; return }''')
    if source.count('try? Data(contentsOf: pending.url)') != 2: raise ValueError('Certificate file reads changed')
    source = source.replace('try? Data(contentsOf: pending.url)', 'try? PrivateFileStore.readExternal(pending.url, maximum: 32_768)')
    source = once(source, '            self.pendingImports = []', '            self.pendingImports = []\n            self.lastUsedPassword = ""\n            self.importPasswordInput = ""')
    source = once(source, '    func cancelImport() {', '''    func cancelImport() {
        self.importPasswordInput = ""
        guard currentImportIndex < pendingImports.count else { return }''')
    return source


def patch_key_input(source):
    source = once(source, '                                viewModel.saveLocalCertificate(signableCert)',
                         '                                try viewModel.saveLocalCertificate(signableCert)')
    return source


PATCHES = {KEYCHAIN: patch_keychain, PROXY: patch_proxy, AUTH: patch_auth, DATABASE: patch_database, VIEW: patch_view, KEY_INPUT: patch_key_input}
OVERRIDES = {MANAGER: 'CertificateManager.swift', FLOW: 'CertificateProvisioningFlow.swift'}
BLOBS = {'AltStore/Core/Components/Keychain.swift': 'd6b7f84eec7909bb1f57f91b5f76bdb13e8a2a48', 'SideStore/Core/Auth/DeveloperPortalProxy.swift': '084b6b7a694135e90f783389dcd9f6796d76bd84', 'SideStore/Core/Auth/AuthManager.swift': 'bb88d8b99908e6fd3da9bc47f5de3917a428fe6c', 'AltStore/Core/Model/DatabaseManager/DatabaseManager.swift': 'e5b1afef2dd9e583c0ebdad39044968232f747bf', 'SideStore/Views/Settings/Advanced/Certificates/CertificatesViewModel.swift': '412e4b61aa7ef58852207d2ba52921e83bc3bdab', 'SideStore/Core/Certificates/CertificateManager.swift': '8505f49fabd6fa226392453e96edb36346b76b4e', 'SideStore/Core/Auth/Flows/CertificateProvisioningFlow.swift': '9412a17cb46454c3399940ce2e29352fbda38ac0', 'SideStore/Views/Settings/Advanced/Certificates/PrivateKeyTextInputView.swift': '5e1e86ad67a39dc7022c9709b61beb53f51238d2'}


def apply(root: Path):
    changes = {}
    for path, expected in BLOBS.items():
        raw = (root/path).read_bytes()
        digest = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if digest != expected: raise ValueError('Unreviewed certificate source: ' + path)
        changes[root/path] = PATCHES[path](raw.decode()) if path in PATCHES else (ROOT/'Overrides'/OVERRIDES[path]).read_text()
    for path, content in changes.items(): path.write_text(content)

if __name__ == '__main__': apply(Path(sys.argv[1]))
