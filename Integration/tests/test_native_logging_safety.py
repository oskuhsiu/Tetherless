"""Actual native logger sink; no real account, PIN, device ID or network."""
from pathlib import Path
import hashlib
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('native_logging_safety', ROOT/'native_logging_safety.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
REVIEW = Path(os.environ.get('TETHERLESS_NATIVE_LOGGING_REVIEW_ROOT', ROOT.parent/'Vendor/SideStore'))


class NativeLoggingSafetyTests(unittest.TestCase):
    def test_unreviewed_source_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root/m.SOURCE
            source.parent.mkdir(parents=True); source.write_text('unreviewed source')
            with self.assertRaises(ValueError): m.apply(root)
            self.assertEqual(source.read_text(), 'unreviewed source')

    @unittest.skipUnless((REVIEW/m.SOURCE).is_file(), 'Pinned native logger unavailable')
    def test_exact_source_and_fail_closed_reapplication(self):
        originals = {name: (REVIEW/name).read_bytes() for name in m.BLOBS}
        for name, raw in originals.items():
            self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(), m.BLOBS[name])
        for bad_second in [False, True]:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for name, raw in originals.items():
                    target = root/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
                if bad_second:
                    (root/m.OPERATIONS).write_text('changed second source')
                    with self.assertRaises(ValueError): m.apply(root)
                    self.assertEqual((root/m.SOURCE).read_bytes(), originals[m.SOURCE])
                    self.assertEqual((root/m.OPERATIONS).read_text(), 'changed second source')
                else:
                    m.apply(root)
                    outputs = {name: (root/name).read_bytes() for name in m.BLOBS}
                    self.assertEqual(outputs, {name: path.read_bytes() for name, path in m.OVERRIDES.items()})
                    with self.assertRaises(ValueError): m.apply(root)
                    self.assertEqual(outputs, {name: (root/name).read_bytes() for name in m.BLOBS})

    def test_product_chain_and_structured_diagnostics_stay_separate(self):
        source = (ROOT/'network_safety.py').read_text()
        self.assertEqual(source.count('with_name("native_logging_safety.py")'), 1)
        events = (ROOT/'Native/PairingImportDiagnostic.swift').read_text()
        self.assertIn('print(', events)
        self.assertNotIn('debugLog(', events)
        runtime = (ROOT/'Native/NativeRenewalRuntime.swift').read_text()
        self.assertIn('NativeRenewalStorage.record(summary)', runtime)
        self.assertNotIn('NativeRenewalRuntime', m.OVERRIDE.read_text())

    @unittest.skipUnless(shutil.which('swiftc'), 'Swift compiler unavailable; native logger not executed')
    def test_actual_logger_does_not_evaluate_or_print_payloads_in_either_mode(self):
        source = r'''
import Foundation
struct OperationProbe: OperationLogging {}
struct UnprintableFailure: LocalizedError {
    var errorDescription: String? { fatalError("Diagnostic evaluated an Error payload") }
}
@main struct Main {
    static func main() {
        var evaluations = 0
        func secret() -> String {
            evaluations += 1
            return "SYNTHETIC_EMAIL_UDID_PIN_TOKEN https://example.invalid/?token=SECRET"
        }
        for enabled in [false, true] {
            SideStoreLogging.setLogging(enabled)
            precondition(!SideStoreLogging.isLoggingEnabled)
            debugLog(secret())
            verboseLog(secret())
            OperationProbe().debugLog(secret())
            OperationProbe().verboseLog(secret())
            precondition(evaluations == 0)
            let value = formatLogMessage("Error Domain=SECRET Code=1 UserInfo={token=SECRET}")
            precondition(value == "[diagnostic payload omitted]")
            precondition(!value.contains("SECRET"))
        }
        for outcome in ["SUCCESS", "FAILED", "CANCELLED"] {
            logOperationSummary(operation: "SYNTHETIC_SECRET", target: "SYNTHETIC_SECRET",
                                status: outcome, elapsed: 1.25, error: UnprintableFailure())
        }
        for duration in [Double.nan, Double.infinity, -1, 86_401] {
            logOperationSummary(operation: "SYNTHETIC_SECRET", target: "SYNTHETIC_SECRET",
                                status: "SUCCESS", elapsed: duration, error: UnprintableFailure())
        }
        logOperationSummary(operation: "SYNTHETIC_SECRET", target: "SYNTHETIC_SECRET",
                            status: "SYNTHETIC_SECRET", elapsed: 1, error: UnprintableFailure())
        print("native diagnostic privacy passed")
    }
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); main = root/'main.swift'; main.write_text(source)
            binary = root/'check'
            built = subprocess.run([shutil.which('swiftc'), '-swift-version', '6', '-parse-as-library',
                str(m.OVERRIDE), str(m.OPERATIONS_OVERRIDE), str(main), '-o', str(binary)], capture_output=True, text=True, timeout=45)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '[Tetherless operation] SUCCESS elapsed=1.250s\n'
                             '[Tetherless operation] FAILED elapsed=1.250s\n'
                             '[Tetherless operation] CANCELLED elapsed=1.250s\n'
                             'native diagnostic privacy passed\n')
            self.assertEqual(result.stderr, '')


if __name__ == '__main__': unittest.main()
