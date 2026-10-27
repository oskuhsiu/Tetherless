#!/usr/bin/env python3
"""Atomic account envelope and checked sign-out over hash-pinned native code."""
from pathlib import Path
import hashlib
import sys
import re

PORTAL = 'SideStore/Core/Auth/DeveloperPortalProxy.swift'
AUTH = 'SideStore/Core/Auth/AuthManager.swift'
LOGIN = 'SideStore/Core/Operations/StandaloneOperations/SignInOperation.swift'
KEYCHAIN = 'AltStore/Core/Components/Keychain.swift'
APP = 'AltStore/AppDelegate.swift'
MAINT = 'SideStore/MaintenanceManager.swift'
SETTINGS = 'AltStore/Settings/SettingsViewController.swift'
CUSTOM = 'SideStore/Views/Settings/Advanced/UserCustomizations/UserCustomizationsView.swift'
DEV = 'SideStore/Views/Settings/Diagnostics/DeveloperOptionsView.swift'
ARCHIVE = 'SideStore/Utils/importexport/ImportExport.swift'
BACKUP = 'SideStore/Views/Settings/Advanced/BackupRestore/BackupAndRestoreView.swift'

def once(source, old, new):
    if source.count(old) != 1: raise ValueError('Auth patch anchor changed: ' + old[:80])
    return source.replace(old, new, 1)

def span(source, start, end, replacement):
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError('Auth function boundary changed')
    prefix, tail = source.split(start)
    _, suffix = tail.split(end)
    return prefix + replacement + end + suffix

def patch_auth(source):
    source = span(source, '    private var team: ALTTeam?', '    @discardableResult\n    func signIn(', '''    public var isAuthenticated: Bool { (try? NativeAuthenticationStore.ready()) != nil }
    public var currentAppleID: String? { NativeAuthenticationStore.prefillingCredentials()?.email }
    public var password: String? { NativeAuthenticationStore.prefillingCredentials()?.password }
    public var adsid: String? { (try? NativeAuthenticationStore.ready())?.credentials?.dsid }
    public var xcodeToken: String? { (try? NativeAuthenticationStore.ready())?.credentials?.token }
    public var hasStoredPassword: Bool { password != nil }
    public var hasStoredXcodeToken: Bool { xcodeToken != nil }

    /// Boot/legacy maintenance may run after a user has already signed in.
    /// Never destroy a new coherent record merely because an old counter is absent.
    func initializeAccountStorageIfNeeded() async throws {
        try await NativeMutationGate.withLease {
            if try NativeAuthenticationStore.make().read() != nil {
                try NativeAuthenticationStore.make().discardRetainedPassword()
                return
            }
            try NativeAuthenticationStore.make().signOut()
            try Keychain.shared.removeLegacyAuthentication(keepAnisetteData: true)
        }
    }

    public func signOut(
        keepCertificate: Bool = false,
        keepAnisetteData: Bool = true,
        keepAnisetteHeaders: Bool = true,
        keepSideSignHeaders: Bool = true
    ) async throws {
        try await NativeMutationGate.withLease {
            // Commit and read back the authoritative tombstone BEFORE cleanup.
            // A failed write throws, rather than pretending the account is gone.
            try NativeAuthenticationStore.make().signOut()
            try Keychain.shared.removeLegacyAuthentication(keepAnisetteData: keepAnisetteData)
            if !keepCertificate {
                try Keychain.shared.removeActiveCertificateVerified()
                CertificateManager.shared.clearActiveCertificate()
            }
            try await DatabaseManager.shared.deactivateActiveAccountAndTeam()
            if !keepAnisetteHeaders { AnisetteConfigManager.shared.resetToDefaults() }
            if !keepSideSignHeaders { SideSignConfigManager.shared.resetToDefaults() }
            AnisetteDataManager.shared.clearCache()
        }
    }

    @discardableResult
    public func getAuthenticatedSession() async throws -> ALTAppleAPISession {
        let record = try NativeAuthenticationStore.ready()
        guard let credentials = record.credentials else { throw AuthenticationStorageFailure.notReady }
        let anisetteData = try await AnisetteProvider.fetch()
        let xcodeVersion = await AnisetteConfigManager.shared.resolvedXcodeVersion()
        try NativeAuthenticationStore.assertCurrent(record)
        return ALTAppleAPISession(dsid: credentials.dsid, authToken: credentials.token,
                                 anisetteData: anisetteData, xcodeVersion: xcodeVersion)
    }

    public func getAuthenticatedTeam() async throws -> ALTTeam {
        let record = try NativeAuthenticationStore.ready()
        let team = try await DatabaseManager.shared.persistentContainer.performBackgroundTask { context in
            guard let dbTeam = DatabaseManager.shared.activeTeam(in: context),
                  dbTeam.identifier == record.teamID else { throw AuthenticationStorageFailure.notReady }
            return ALTTeam(identifier: dbTeam.identifier, name: dbTeam.name, type: dbTeam.type)
        }
        try NativeAuthenticationStore.assertCurrent(record)
        return team
    }

''')
    source = once(source, '        self.team = result.team\n        self.session = result.session\n', '')
    start = 'fileprivate extension DatabaseManager {'
    if source.count(start) != 1: raise ValueError('Database helper changed')
    return source.split(start)[0] + '''fileprivate extension DatabaseManager {
    func deactivateActiveAccountAndTeam() async throws {
        guard self.isStarted else { return } // Keychain tombstone remains authoritative.
        let context = self.persistentContainer.newBackgroundContext()
        try await context.perform {
            if let account = self.activeAccount(in: context) { account.isActiveAccount = false }
            if let team = self.activeTeam(in: context) { team.isActiveTeam = false }
            try context.save()
        }
        await self.viewContext.perform {
            self.viewContext.processPendingChanges()
            self.viewContext.refreshAllObjects()
        }
    }
}
'''

def patch_login(source):
    source = once(source, '    private var requiresPostAuthFlow = false',
                  '    private var requiresPostAuthFlow = false\n    private var authenticationGeneration: UUID?')
    source = once(source, '''            let authResult = try await self.startAuthentication { [weak self] progress in
                self?.setProgress(progress)
            }''', '''            let authResult = try await NativeMutationGate.withLease {
                try await self.startAuthentication { [weak self] progress in
                    self?.setProgress(progress)
                }
            }''')
    source = once(source, """            if !AuthManager.shared.hasStoredPassword &&
               !AuthManager.shared.hasStoredXcodeToken
            {
                await AuthManager.shared.signOut()
            }""", """            if let generation = self.authenticationGeneration {
                try? await NativeMutationGate.withLease {
                    // Do not discard a session established after this attempt.
                    _ = try NativeAuthenticationStore.make().discardStaged(generation: generation)
                }
            }""")
    source = once(source, '''        AuthManager.shared.adsid = session.dsid
        AuthManager.shared.xcodeToken = session.authToken
        AuthManager.shared.currentAppleID = appleID
        AuthManager.shared.password = password''', '''        self.authenticationGeneration = try NativeAuthenticationStore.make().stage(
            AuthenticationCredentials(email: appleID, password: password,
                                      dsid: session.dsid, token: session.authToken))''')
    source = once(source, '        try await self.saveTeamAndAccount(team, makeActive: true)', '''        try await self.saveTeamAndAccount(team, makeActive: true)
        guard let generation = self.authenticationGeneration else { throw AuthenticationStorageFailure.notReady }
        try NativeAuthenticationStore.make().activate(generation: generation, teamID: team.identifier)
        // No split credentials remain available to old helper routes.
        try Keychain.shared.removeLegacyAuthentication(keepAnisetteData: true)''')
    source = once(source, '        let teams = try await DeveloperPortalProxy.shared.fetchTeams(for: account)',
                  '        let teams = try await ALTAppleAPI.shared.fetchTeams(for: account, session: session)')
    source = once(source, '                await handler.handleSignInResult(.failure(error))', '''                await handler.handleSignInResult(.failure(error))
                if error is AuthenticationStorageFailure || error is CancellationError || self.isCancelled {
                    throw error
                }''')
    # No raw account IDs, device IDs or unclassified auth errors in these logs.
    source = span(source, '        self.debugLog("""', '    private func getAnisetteData()', '    }\n\n')
    source = '\n'.join(line for line in source.split('\n')
                       if not any(key in line for key in ('debugLog(', 'verboseLog(')))
    source = once(source, "        let startTime = CFAbsoluteTimeGetCurrent()\n        defer {\n            let elapsed = CFAbsoluteTimeGetCurrent() - startTime\n        }\n", "")
    return source

def patch_keychain(source):
    source = once(source, 'import Foundation', 'import Foundation\nimport Security\nimport LocalAuthentication')
    marker = '    public func clearCertificates()'
    return once(source, marker, '''    // Checked removal is used by the serialized account transaction.
    private func removeVerified(_ keys: [String]) throws {
        for key in keys {
            try self.keychain.remove(key)
            guard try self.keychain.getData(key) == nil else {
                throw AuthenticationStorageFailure.readbackMismatch
            }
        }
    }
    func removeLegacyAuthentication(keepAnisetteData: Bool) throws {
        var keys = ["appleIDEmailAddress", "appleIDPassword", "appleIDAdsid", "appleIDXcodeToken"]
        if !keepAnisetteData { keys.append("adiPb") }
        try removeVerified(keys)
    }
    func removeActiveCertificateVerified() throws {
        try removeVerified(["signingCertificate", "signingCertificatePassword",
                            "signingCertificatePrivateKey", "signingCertificateSerialNumber"])
    }
    func clearAllVerified() throws {
        try self.keychain.removeAll()
        let context = LAContext()
        context.interactionNotAllowed = true
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "org.tetherless.credentials." + Bundle.Info.appbundleIdentifier,
            kSecAttrSynchronizable as String: false, kSecMatchLimit as String: kSecMatchLimitOne,
            kSecReturnAttributes as String: true, kSecUseAuthenticationContext as String: context]
        let status = SecItemCopyMatching(query as CFDictionary, nil)
        guard status == errSecItemNotFound else { throw AuthenticationStorageFailure.unavailable }
    }

''' + marker)

def patch_settings(source):
    source = once(source, '                await AuthManager.shared.signOut(', '                do {\n                    try await AuthManager.shared.signOut(')
    return once(source, '''                await MainActor.run {
                    self?.update()
                }
            }
        }
        
        alertController.addAction(cancelAction)''', '''                await MainActor.run { self?.update() }
                } catch { await NativeAuthenticationStore.showFailure(error) }
            }
        }
        
        alertController.addAction(cancelAction)''')

def patch_maintenance(source):
    source = once(source, '                await self.performMaintenanceWithLease()', '                try await self.performMaintenanceWithLease()')
    source = once(source, '    private func performMaintenanceWithLease() async {', '    private func performMaintenanceWithLease() async throws {')
    source = once(source, '''                Keychain.shared.clearAll()
                await AuthManager.shared.signOut(keepCertificate: false, keepAnisetteData: false)''', '''                try await AuthManager.shared.initializeAccountStorageIfNeeded()''')
    return once(source, '                await AuthManager.shared.signOut(keepCertificate: true, keepAnisetteData: false)',
                '                try await AuthManager.shared.initializeAccountStorageIfNeeded()')

def patch_custom(source):
    source = once(source, '''                    await AuthManager.shared.signOut(keepCertificate: true, keepAnisetteData: false)
                    UserDefaults.standard.useOnDeviceAnisette = useOnDeviceAnisette
                    exit(0)''', '''                    do {
                        try await AuthManager.shared.signOut(keepCertificate: true, keepAnisetteData: false)
                        UserDefaults.standard.useOnDeviceAnisette = useOnDeviceAnisette
                        exit(0)
                    } catch { await NativeAuthenticationStore.showFailure(error) }''')
    source = once(source, '                await AuthManager.shared.signOut(keepCertificate: true, keepAnisetteData: false, keepAnisetteHeaders: keepHeaders)',
                  '                do {\n                try await AuthManager.shared.signOut(keepCertificate: true, keepAnisetteData: false, keepAnisetteHeaders: keepHeaders)')
    return once(source, '''                    ).show(in: topVC)
                }
            }
        }
        
        alertController.addAction(cancelAction)
        alertController.addAction(resetAction)''', '''                    ).show(in: topVC)
                }
                } catch { await NativeAuthenticationStore.showFailure(error) }
            }
        }
        
        alertController.addAction(cancelAction)
        alertController.addAction(resetAction)''')

def patch_developer(source):
    return once(source, '                Keychain.shared.clearAll()', '''                Task {
                    do {
                        try await NativeMutationGate.withLease {
                            try await AuthManager.shared.signOut(keepAnisetteData: false)
                            try Keychain.shared.clearAllVerified()
                        }
                    } catch { await NativeAuthenticationStore.showFailure(error) }
                }''')

def patch_archive(source):
    source = span(source, '    public static func exportAccount(password:', '    public static func getPreviousBackupURL(', '''    public static func exportAccount(password: String, includeApplePassword: Bool) throws -> Data {
        throw OperationError.invalidParameters("Account archives are not supported. Credentials remain on this device.")
    }
    public static func importAccount(_ encryptedData: Data, filePassword: String) async throws -> ImportedAccount {
        throw OperationError.invalidParameters("Account archives are not supported. Sign in using the account setup screen.")
    }

''')
    return span(source, '#if DEBUG\nextension ImportExport {', '#if !os(tvOS)\nprivate struct AssociatedKeys {', '''#if DEBUG
extension ImportExport {
    static func exportAccountJSON(password: String) -> ImportedAccount? { nil }
    static func importAccountJSON(from file: URL) async throws {
        throw OperationError.invalidParameters("Account archives are not supported. Sign in using the account setup screen.")
    }
}
#endif

''')

def patch_backup(source):
    return span(source, '    private func performAppleSignIn() {', '    private func showAlert(', '''    private func performAppleSignIn() {
        showAlert(title: "Account setup", message: "Sign in through the account setup screen. Account archive imports are not supported.")
    }

''')

def patch_portal(source):
    source = once(source, '        if let team { return team }', """        if let team {
            guard try NativeAuthenticationStore.ready().teamID == team.identifier else {
                throw AuthenticationStorageFailure.staleAttempt
            }
            return team
        }""")
    pattern = re.compile(r'(    public func [^\n]+\{\n)(.*?)(    \}\n)', re.S)
    count = 0
    def replace(match):
        nonlocal count
        body = match[2]
        # Dynamic team profiles are a portal mutation despite the download name.
        if 'NativeMutationGate.withLease' not in body and not (
            'downloadProvisioningProfile(for ' in match[1]
        ):
            return match[0]
        guarded = re.sub(r'        return try await NativeMutationGate.withLease \{ try await (ALTAppleAPI[^\n]+) \}\n',
                         r'        return try await \1\n', body)
        if 'NativeMutationGate.withLease' in guarded:
            raise ValueError('Unreviewed nested portal mutation wrapper')
        if guarded.count('let session = try await self.getSession()') != 1:
            raise ValueError('Portal account boundary changed')
        count += 1
        return match[1] + '        return try await NativeMutationGate.withLease {\n' + \
               ''.join('    '+line if line.strip() else line for line in guarded.splitlines(keepends=True)) + \
               '        }\n' + match[3]
    result = pattern.sub(replace, source)
    if count != 20:
        raise ValueError(f'Expected 20 portal mutations, found {count}')
    return result

def patch_app(source):
    return once(source, """                if isFirstLaunch
                {
                    await AuthManager.shared.signOut()
                }""", """                // Retry checked credential-format cleanup on every launch,
                // independent of old first-launch/maintenance counters.
                try await AuthManager.shared.initializeAccountStorageIfNeeded()""")

PATCHES = {PORTAL: patch_portal, AUTH: patch_auth, LOGIN: patch_login, KEYCHAIN: patch_keychain,
           APP: patch_app,
           MAINT: patch_maintenance, SETTINGS: patch_settings, CUSTOM: patch_custom,
           DEV: patch_developer, ARCHIVE: patch_archive, BACKUP: patch_backup}
BLOBS = {PORTAL: '702759f52dae5dfc7e3a88f57668d7a83e30f354', 'SideStore/Core/Auth/AuthManager.swift': 'c426783db44eda9a183562cddbd446f57cecc93a', 'SideStore/Core/Operations/StandaloneOperations/SignInOperation.swift': '1ff9135ea725cc45481d82a96af1de8418726ef8', 'AltStore/Core/Components/Keychain.swift': '440f4a763cc3a95b10c696f432129f8570b4116a', 'AltStore/AppDelegate.swift': '466ba57a35e67b1a93961b5d4553d24d7c5e73ff', 'SideStore/MaintenanceManager.swift': '55dbd051aeff41e6f2859ca1ebe357c76f378bf5', 'AltStore/Settings/SettingsViewController.swift': '6b7a4c28ed942089a38c8f1a870345b57e47bad6', 'SideStore/Views/Settings/Advanced/UserCustomizations/UserCustomizationsView.swift': '6d6a72327aa0d19dab23e63576abadccc6909c61', 'SideStore/Views/Settings/Diagnostics/DeveloperOptionsView.swift': '5826d7d2ecca2776ac823ae516322016ba8eb944', 'SideStore/Utils/importexport/ImportExport.swift': '509c0ef993239e0ef61eff19fc8cc1f86d854b92', 'SideStore/Views/Settings/Advanced/BackupRestore/BackupAndRestoreView.swift': '861f17b0fa0abb4ead5f679b021747c985bd9598'}  # Filled from the reviewed prepared baseline, not the evolving remote branch.

def apply(root: Path):
    outputs = {}
    for path, patch in PATCHES.items():
        raw = (root/path).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != BLOBS[path]: raise ValueError('Unreviewed prepared auth source: ' + path)
        outputs[root/path] = patch(raw.decode())
    for path, content in outputs.items(): path.write_text(content)

if __name__ == '__main__': apply(Path(sys.argv[1]))
