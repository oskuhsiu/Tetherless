"""Transformation invariants; not live Apple or physical signing evidence."""
import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('certs',ROOT/'certificate_safety.py')
c=importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
class CertificateSafetyTests(unittest.TestCase):
    def test_source_drift_rejected(self):
        for patch in c.PATCHES.values():
            with self.assertRaises(ValueError): patch('unexpected source')
    def test_returned_key_is_checked_before_proxy_returns(self):
        line='            return try await ALTAppleAPI.shared.addCertificate(machineName: machineName, type: type, to: team, session: session)'
        result=c.patch_proxy(line)
        self.assertLess(result.index('saveCertificate(created)'),result.index('return created'))
        self.assertNotIn('try?',result)
        self.assertNotIn('fetchCertificates',result)
    def test_public_namespace_cannot_overwrite_private_cache(self):
        source=(ROOT/'Overrides/CertificateManager.swift').read_text()
        public=source.split('public func saveX509Certificate(')[1].split('public func getLocalCertificateVerified')[0]
        self.assertIn('writePublicCertificateVerified',public)
        self.assertNotIn('writeImportedCertificateVerified',public)
        self.assertNotIn('certificateSerial:',source)
        self.assertIn('public-certificate-v1.',c.KEYCHAIN_METHODS)
        self.assertIn('cached-signing-v1.',c.KEYCHAIN_METHODS)
    def test_clear_key_is_explicit_not_an_accidental_public_save(self):
        source=(ROOT/'Overrides/CertificateManager.swift').read_text()
        method=source.split('public func removePrivateKey(')[1].split('public func getSignableCertificate')[0]
        self.assertIn('clearActiveCertificate()',method)
        self.assertIn('includePublic: false',method)
    def test_corrupt_storage_is_not_a_new_certificate_decision(self):
        source=(ROOT/'Overrides/CertificateProvisioningFlow.swift').read_text()
        self.assertIn('error is AuthenticationStorageFailure',source)
        self.assertIn('getLocalCertificateVerified',source)
        self.assertNotIn('isCustomCert',source)
        self.assertNotIn('getSignableCertificate',source)
        self.assertLess(source.index('loadActiveCertificate()'),source.index('requestCertificate(for:'))
    def test_revoke_only_after_actual_quota_and_explicit_selection(self):
        source=(ROOT/'Overrides/CertificateProvisioningFlow.swift').read_text()
        self.assertLess(source.index('guard case .tooManyCertificates'),source.index('resolveRevocation(certificates: current'))
        self.assertIn('case .keepExisting: throw error',source)
        self.assertIn('$0.data == cert.data',source)
        self.assertIn('guard !selected.isEmpty',source)
    def test_active_envelope_read_is_not_split_field_fallback(self):
        source=(ROOT/'Native/NativeCertificatePersistence.swift').read_text()
        self.assertIn('if let envelope = try store().read() { return try decode(envelope.identity) }',source)
        self.assertNotIn('try?',source)
        self.assertIn('removeActiveCertificateVerified()',source)
    def test_chain_runs_after_manager_update(self):
        source=(ROOT/'network_safety.py').read_text()
        self.assertLess(source.index('"manager_update.py"'),source.index('"certificate_safety.py"'))
