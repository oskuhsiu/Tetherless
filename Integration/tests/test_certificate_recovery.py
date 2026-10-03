"""Native wiring contracts; not a substitute for actual Apple/UI execution."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('issuance_recovery', ROOT / 'certificate_issuance.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


class CertificateRecoveryIntegrationTests(unittest.TestCase):
    def test_recovery_uses_the_normal_issuance_namespace(self):
        source = (ROOT / 'Native/NativeCertificateIssuance.swift').read_text()
        recovery = (ROOT / 'Native/NativeCertificateRecovery.swift').read_text()
        self.assertIn('let requestStore = try store(owner: owner)', source)
        self.assertIn('NativeCertificateIssuance.store(owner: owner)', recovery)
        self.assertNotIn('KeychainAuthenticationStorage(', recovery)
        self.assertIn('CertificateIssuanceBackend, CertificateIssuanceLookup', source)

    def test_portal_methods_check_request_before_fetching_auth_headers(self):
        source = (ROOT / 'certificate_issuance.py').read_text()
        for name in ['checkCertificateRequest', 'resolveCertificateRequest']:
            body = source.split('func ' + name, 1)[1].split('\n    }', 1)[0]
            self.assertIn('NativeMutationGate.withLease', body)
            self.assertLess(body.index('requestID == expectedID'), body.index('self.getSession()'))
            self.assertNotIn('createCertificate(', body)
            self.assertNotIn('revokeCertificate(', body)
        body = source.split('func checkCertificateRequest', 1)[1].split('\n    }', 1)[0]
        self.assertIn('NativeCertificateRecovery.check(', body)
        self.assertNotIn('allowNew:', body)
        self.assertNotIn('.resolve(', body)

    def test_local_discard_never_fetches_session_or_changes_active_signer(self):
        source = (ROOT / 'Native/NativeCertificateRecovery.swift').read_text()
        body = source.split('static func discardPrepared', 1)[1].split('\n    }', 1)[0]
        self.assertIn('NativeMutationGate.withSynchronousLease', body)
        self.assertIn('expectedID: expectedID', body)
        for value in ['getSession', 'ALTAppleAPI', 'Anisette', 'setActiveCertificate']:
            self.assertNotIn(value, body)
        self.assertNotIn('setActiveCertificate', source)
        self.assertNotIn('revokeCertificate', source)
        self.assertNotIn('renewalPermitted', source)

    def test_confirmation_freezes_request_and_type(self):
        source = (ROOT / 'Native/NativeCertificateRecoveryControls.swift').read_text()
        self.assertIn('Confirmation(id: id, type: type, action: action', source)
        self.assertIn('expectedID: value.id', source)
        self.assertIn('type: value.type', source)
        self.assertIn('generation == current', source)
        self.assertIn('operation?.cancel()', source)
        self.assertIn('presenting: confirmation', source)
        self.assertNotIn('debugLog', source)
        self.assertNotIn('allowNew:', source)
        self.assertNotIn('launchEnvironment', source)

    def test_controls_have_true_missing_account_gates(self):
        source = (ROOT / 'Native/NativeCertificateRecoveryControls.swift').read_text()
        for value in ['observation?.requestID == nil', 'observation?.canSave != true',
                      'observation?.canSubmit != true', 'observation?.canDiscard != true']:
            self.assertIn(value, source)
        self.assertIn('NativeCertificateRecoveryControls()', (ROOT / 'Native/NativeRenewalSettings.swift').read_text())
        test = (ROOT / 'UITests/TetherlessUITests.swift').read_text()
        self.assertIn('Sign in to inspect requests for this account.', test)
        self.assertIn('XCTAssertFalse(control.isEnabled', test)
        self.assertIn('07-certificate-recovery-signed-out', test)
        self.assertNotIn('typeText(', test)
