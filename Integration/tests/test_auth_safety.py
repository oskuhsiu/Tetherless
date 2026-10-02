from pathlib import Path
import importlib.util
import re
import tempfile
import unittest
ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('auth', ROOT/'auth_safety.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class AuthenticationIntegrationTests(unittest.TestCase):
    def test_guarded_hashes_cover_all_reviewed_routes(self):
        self.assertEqual(set(m.PATCHES), set(m.BLOBS))
        self.assertEqual(len(m.BLOBS), 11)
        self.assertTrue(all(re.fullmatch('[a-f0-9]{40}', value) for value in m.BLOBS.values()))
    def test_mismatch_cannot_partially_mutate_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for path in m.BLOBS:
                p=root/path; p.parent.mkdir(parents=True,exist_ok=True); p.write_text('unreviewed')
            with self.assertRaises(ValueError): m.apply(root)
            self.assertTrue(all((root/p).read_text() == 'unreviewed' for p in m.BLOBS))
    def test_auth_manager_replacement_has_no_split_or_cached_credentials(self):
        source='''    private var team: ALTTeam?
OLD SESSION AND FOUR KEYCHAIN FIELDS
    @discardableResult
    func signIn(
        self.team = result.team
        self.session = result.session
fileprivate extension DatabaseManager {
OLD DATABASE SAVE SWALLOWING
'''
        result=m.patch_auth(source)
        self.assertNotIn('OLD',result)
        self.assertNotIn('self.team =',result)
        self.assertNotIn('Keychain.shared.appleID',result)
        self.assertIn('dbTeam.identifier == record.teamID',result)
        self.assertIn('assertCurrent(record)',result)
        signout=result[result.index('    public func signOut('):]
        self.assertLess(signout.index('make().signOut()'),signout.index('removeLegacyAuthentication('))
        self.assertLess(signout.index('make().signOut()'),signout.index('deactivateActiveAccountAndTeam()'))
        self.assertIn('try context.save()',result)
        self.assertIn('make().read() != nil {',result)
        self.assertIn('discardRetainedPassword()',result)
    def test_account_archive_routes_fail_without_decrypting_or_writing(self):
        source='''    public static func exportAccount(password:
UNSAFE P12/JSON EXPORT OR IMPORT
    public static func getPreviousBackupURL(
PRESERVED APP BACKUP
#if DEBUG
extension ImportExport {
UNSAFE RAW JSON EXPORT OR IMPORT
#if !os(tvOS)
private struct AssociatedKeys {
'''
        result=m.patch_archive(source)
        self.assertNotIn('UNSAFE',result)
        self.assertIn('PRESERVED APP BACKUP',result)
        self.assertIn('Account archives are not supported',result)
        self.assertNotIn('AuthManager.shared.password =',result)
    def test_new_backend_uses_same_coherent_record(self):
        source=(ROOT/'Native/NativeRenewalBackend.swift').read_text()
        self.assertIn('let account = try NativeAuthenticationStore.ready()',source)
        self.assertIn('NativeAuthenticationStore.assertCurrent(account)',source)
        self.assertNotIn('Keychain.shared.appleIDAdsid',source)
        self.assertNotIn('Keychain.shared.appleIDXcodeToken',source)
    def test_new_service_does_not_share_legacy_clear_all_scope(self):
        source=(ROOT/'Native/NativeAuthenticationStore.swift').read_text()
        self.assertIn('"org.tetherless.session."',source)
        self.assertNotIn('try!',source)
        self.assertIn('ready().generation == record.generation',source)
    def test_portal_sessions_are_read_only_inside_the_mutation_lease(self):
        source = '        if let team { return team }\n'
        for index in range(18):
            source += f"""    public func change{index}() async throws -> Bool {{
        let session = try await self.getSession()
        let team = try await self.getTeam(team)
        return try await NativeMutationGate.withLease {{ try await ALTAppleAPI.shared.mutate(team: team, session: session) }}
    }}
"""
        for index in range(2):
            source += f"""    public func downloadProvisioningProfile(for appID: AppID, mode: Mode{index}) async throws -> Profile {{
        let session = try await self.getSession()
        let team = try await self.getTeam(team)
        return try await ALTAppleAPI.shared.downloadProvisioningProfile(team: team, session: session)
    }}
"""
        result = m.patch_portal(source)
        self.assertEqual(result.count('return try await NativeMutationGate.withLease {'),20)
        self.assertEqual(result.count('            let session = try await self.getSession()'),20)
        self.assertIn('NativeAuthenticationStore.ready().teamID == team.identifier',result)
        self.assertNotIn('return try await NativeMutationGate.withLease { try await ALTAppleAPI', result)

    def test_preparation_invokes_auth_after_other_hash_locked_boundaries(self):
        source=(ROOT/'network_safety.py').read_text()
        self.assertLess(source.index('file.write_text('),source.index('with_name("auth_safety.py")'))

if __name__=='__main__': unittest.main()
