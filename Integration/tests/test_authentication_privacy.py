"""Real compiled logging/error boundary, synthetic responses, no Apple login."""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('auth_privacy', ROOT/'authentication_privacy.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
REVIEW=Path(os.environ.get('TETHERLESS_AUTH_REVIEW_ROOT',ROOT.parent/'Vendor/SideStore'))
SOURCE=REVIEW/module.AUTH

class AuthenticationPrivacyTests(unittest.TestCase):
    def test_unknown_inputs_fail_before_any_write(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in module.BLOBS:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('unreviewed')
            with self.assertRaises(ValueError): module.apply(root)
            for name in module.BLOBS: self.assertEqual((root/name).read_text(),'unreviewed')

    def test_integration_runs_privacy_after_prior_source_changes(self):
        t=(ROOT/'network_safety.py').read_text()
        self.assertIn('"authentication_privacy.py"',t)
        self.assertLess(t.index('"certificate_issuance.py"'),t.index('"authentication_privacy.py"'))

    def compile_run(self, main, extra_sources=()):
        compiler=shutil.which('swiftc')
        if not compiler: self.skipTest('Swift compiler unavailable; boundary not executed')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'main.swift').write_text(main)
            # The identical Logging.swift is copied into SideSign by the patch.
            result=subprocess.run([compiler,'-swift-version','6',str(ROOT/'Overrides/SideSignLogging.swift'),*map(str,extra_sources),str(p/'main.swift'),'-o',str(p/'test')],capture_output=True,text=True,timeout=45)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(p/'test')],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            return result.stdout

    def test_free_form_log_arguments_never_evaluate_in_either_mode(self):
        text=self.compile_run(r'''
import Foundation
var evaluations = 0
@MainActor func secret() -> String { evaluations += 1; return "SYNTHETIC_PASSWORD_TOKEN_9F03" }
for enabled in [false, true] {
    SideSignLogging.setLogging(enabled)
    debugLog(secret()); verboseLog(secret())
    precondition(evaluations == 0)
    SideSignLogging.authentication(.started)
    precondition(prettyJSONString(from: ["unknown": secret()]) == "[payload omitted]")
    precondition(formatPayload(Data(secret().utf8)) == "[payload omitted]")
    precondition(sanitizeTokens(["unknown": secret()]).isEmpty)
    precondition(sanitizeHeadersForLogging([secret(): secret()]).isEmpty)
    evaluations = 0
}
print("PASS")
''')
        self.assertEqual(text,'[Tetherless authentication] started\nPASS\n')

    def test_interactive_repair_url_rejects_untrusted_destinations(self):
        text=self.compile_run(r'''
import Foundation
let fallback=URL(string:"https://developer.apple.com/account/")!
for raw in ["http://account.apple.com", "https://account.apple.com.evil.test", "https://account.apple.com@evil.test", "https://user:password@account.apple.com", "https://account.apple.com:8443", "file:///tmp/test", String(repeating:"X",count:8193)] {
    precondition(authenticationRepairURL(raw,fallback:fallback) == fallback)
}
let original="https://account.apple.com/?synthetic-session=private"
precondition(authenticationRepairURL(original,fallback:fallback).absoluteString == original)
precondition(authenticationRepairURL(nil,fallback:fallback) == fallback)
print("PASS")
''')
        self.assertEqual(text,'PASS\n')

    @unittest.skipUnless(SOURCE.is_file(),'Pinned SideSign not mounted; executed separately in native CI')
    def test_exact_reviewed_authentication_has_no_payload_or_dynamic_logger(self):
        raw=SOURCE.read_bytes()
        self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),module.BLOBS[module.AUTH])
        t=module.patch_auth(raw.decode())
        self.assertNotIn('verboseLog(',t);self.assertNotIn('debugLog(',t)
        self.assertNotIn('prettyJSONString(',t)
        self.assertEqual(t.count('[authentication payload omitted]'),18)
        self.assertIn('"u": sanitizedAppleID',t)
        self.assertIn('"t": idmsToken',t)
        self.assertIn('srpClient.verifyServerProof(serverVerificationMessage)',t)
        self.assertIn('cause: "Apple rejected the verification request.',t)
        self.assertIn('accountRepairRequired(url: Constants.URLs.developerAccount',t)
        self.assertNotIn('let errorMsg =',t)
        self.assertNotIn('let errorDesc = status',t)
        # A second apply must not partially rewrite a previously secured source.
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in module.BLOBS:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((REVIEW/name).read_bytes())
            module.apply(root);before={name:(root/name).read_bytes() for name in module.BLOBS}
            with self.assertRaises(ValueError): module.apply(root)
            self.assertEqual(before,{name:(root/name).read_bytes() for name in module.BLOBS})

    @unittest.skipUnless(SOURCE.is_file(),'Pinned SideSign not mounted; executed separately in native CI')
    def test_actual_error_boundary_drops_all_payloads_and_keeps_decisions(self):
        # Use the original upstream error types and the exact deployed policy.
        text=self.compile_run(r'''
import Foundation
struct Constants {
    struct URLs { static let developerAccount=URL(string:"https://developer.apple.com/account/")! }
    static let defaultAccountRepairMessage="Repair your Apple account."
}
let secret="SYNTHETIC_SECRET_PASSWORD_TOKEN_DSID_16EC"
let errors: [Error] = [
    ServerError.underlyingError(code: -22406,message:secret),
    ServerError.badServerResponse(reason:secret,jsonPayload:secret),
    ServerError.invalidResponseFormat(rawPayload:secret),
    ServerError.missingKey(key:secret,jsonPayload:secret),
    DeveloperPortalError.incorrectCredentials(cause:secret),
    DeveloperPortalError.invalid2FAResponse(cause:secret),
    DeveloperPortalError.accountRepairRequired(url:URL(string:"https://account.apple.com/?token="+secret),message:secret),
    NSError(domain:secret,code:1,userInfo:[NSLocalizedDescriptionKey:secret]),
    URLError(.timedOut,userInfo:[NSLocalizedDescriptionKey:secret])
]
for enabled in [false,true] {
    SideSignLogging.setLogging(enabled)
    for error in errors {
        let safe=sanitizedAuthenticationError(error)
        precondition(!String(reflecting:safe).contains(secret))
        precondition(!safe.localizedDescription.contains(secret))
        precondition(!String(reflecting:(safe as NSError).userInfo).contains(secret))
    }
}
if case ServerError.underlyingError(let code,_) = sanitizedAuthenticationError(errors[0]) { precondition(code == -22406) } else { fatalError("Lost server code") }
if case DeveloperPortalError.incorrectCredentials = sanitizedAuthenticationError(errors[4]) {} else { fatalError("Lost credential decision") }
precondition((sanitizedAuthenticationError(URLError(.cancelled)) as? URLError)?.code == .cancelled)
precondition(sanitizedAuthenticationError(CancellationError()) is CancellationError)
print("PASS")
''', [REVIEW/'Dependencies/SideSign/Sources/Models/Errors.swift',ROOT/'Overrides/AuthenticationErrorPolicy.swift'])
        self.assertEqual(text,'PASS\n')
