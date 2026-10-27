"""Actual prepared-source patches are checked separately; no Apple credentials."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
ROOT = Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('issuance', ROOT/'certificate_issuance.py')
i=importlib.util.module_from_spec(spec); spec.loader.exec_module(i)

class IssuanceIntegrationTests(unittest.TestCase):
    def test_unknown_inputs_are_rejected_before_any_patch(self):
        for patch in i.PATCHES.values():
            with self.assertRaises(ValueError): patch('unreviewed source')
    def test_recovery_precedes_existing_key_selection(self):
        code=(ROOT/'Overrides/CertificateProvisioningFlow.swift').read_text()
        body=code.split('private func fetchCertificate(for team: ALTTeam)')[1]
        self.assertLess(body.index('recoverPendingCertificate('), body.index('loadActiveCertificate()'))
    def test_native_creation_never_uses_generate_and_submit_in_one_call(self):
        code=(ROOT/'Native/NativeCertificateIssuance.swift').read_text()
        self.assertIn('.issue(owner: owner, backend: backend, allowNew: allowNew)', code)
        self.assertIn('submitCertificateRequest(csrData: record.material.csrPEM', code)
        self.assertIn('record.id.uuidString.uppercased()', code)
        self.assertNotIn('.addCertificate(', code)
        self.assertNotIn('revokeCertificate', code)
    def test_key_binding_is_verified_before_and_after_server_call(self):
        code=(ROOT/'Native/NativeCertificateIssuance.swift').read_text()
        self.assertIn('CertificateKeyBinding.validate(', code)
        self.assertIn('CertificateKeyBinding.certificatePublicKey(certificate.der)', code)
        self.assertIn('saved.privateKey == expected.privateKey', code)
    def test_secrets_are_only_stored_in_scoped_keychain(self):
        code=(ROOT/'Native/NativeCertificateIssuance.swift').read_text()
        self.assertIn('KeychainAuthenticationStorage(', code)
        self.assertIn('accountID: session.dsid, teamID: team.identifier, certificateType: type.rawValue', code)
        self.assertNotIn('UserDefaults', code)
        self.assertNotIn('debugLog', code)
    def test_patch_runs_after_prior_certificate_safety(self):
        code=(ROOT/'network_safety.py').read_text()
        self.assertLess(code.index('"certificate_safety.py"'), code.index('"certificate_issuance.py"'))
    def test_receipt_is_not_reset_by_account_login_or_age(self):
        code=(ROOT.parents[0]/'Sources/TetherlessCore/CertificateIssuance.swift').read_text()
        self.assertNotIn('timeIntervalSince', code)
        self.assertNotIn('authToken', code)
        self.assertIn('pending.owner == owner', code)
        self.assertIn('case .submitted', code.replace('record.phase == .submitted','case .submitted'))
