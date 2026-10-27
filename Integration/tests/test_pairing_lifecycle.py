from pathlib import Path
import importlib.util
import io
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('pairing_diagnostic_selection', ROOT/'retain_ui_diagnostics.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class PairingLifecycleTests(unittest.TestCase):
    def test_mid_file_markers_survive_raw_excerpt_truncation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'raw'; root.mkdir()
            source = root/'StandardOutputAndStandardError-org.tetherless.Tetherless.txt'
            data = b'noise\n' * 20 + m.PAIRING_PREFIX + b'selectionReceived\n' + m.PAIRING_PREFIX + b'importFailed\n' + b'noise\n' * 20
            source.write_bytes(data)
            output = root.parent/'retained'
            result = m.retain(root, output, limit=8)
            entry = result['files'][0]
            self.assertTrue(entry['truncated'])
            self.assertEqual(entry['pairingLifecycle']['events'], ['selectionReceived', 'importFailed'])
            self.assertTrue(entry['pairingLifecycle']['scanComplete'])
            self.assertFalse(entry['pairingLifecycle']['uiResultInferred'])
            self.assertEqual(source.read_bytes(), data)

    def test_only_fixed_whole_line_markers_can_be_exported(self):
        secret = b'SYNTHETIC_PRIVATE_FILENAME_TOKEN'
        data = (m.PAIRING_PREFIX + secret + b'\n' + m.PAIRING_PREFIX + b'importFailed ' + secret + b'\n' +
                b'other log ' + m.PAIRING_PREFIX + b'importSucceeded\n' +
                m.PAIRING_PREFIX + b'importFailed\r\n' + m.PAIRING_PREFIX + b'importSucceeded')
        result = m.pairing_lifecycle(io.BytesIO(data), len(data))
        self.assertEqual(result['events'], ['importFailed'])
        self.assertNotIn(secret.decode(), repr(result))

    def test_oversized_line_suffix_is_not_a_callback(self):
        data = b'x' * 4096 + m.PAIRING_PREFIX + b'importSucceeded\n' + m.PAIRING_PREFIX + b'pickerCreated\n'
        result = m.pairing_lifecycle(io.BytesIO(data), len(data))
        self.assertEqual(result['events'], ['pickerCreated'])

    def test_scan_and_event_limits_are_explicit_not_success(self):
        line = m.PAIRING_PREFIX + b'pickerCreated\n'
        data = line * 4
        result = m.pairing_lifecycle(io.BytesIO(data), len(data), scan_limit=len(line)*3, event_limit=2)
        self.assertEqual(result['events'], ['pickerCreated'] * 2)
        self.assertEqual(result['observedEventCount'], 3)
        self.assertFalse(result['scanComplete']); self.assertTrue(result['eventsTruncated'])
        self.assertFalse(result['uiResultInferred'])
        partial = m.pairing_lifecycle(io.BytesIO(data), len(data), scan_limit=len(line)-1)
        self.assertEqual(partial['events'], [])
        with self.assertRaises(ValueError): m.pairing_lifecycle(io.BytesIO(b''), 1)

    def test_actual_swift_logger_outputs_only_the_declared_events(self):
        source = ROOT/'Native/PairingImportDiagnostic.swift'
        text = source.read_text()
        cases = []
        for line in text.splitlines():
            if line.strip().startswith('case '):
                cases.extend(part.strip() for part in line.strip()[5:].split(','))
        self.assertEqual(set(cases), m.PAIRING_EVENTS)
        self.assertEqual(len(cases), len(set(cases)))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root/'Main.swift'
            main.write_text('@main struct Main { @MainActor static func main() { for e in PairingImportDiagnostic.allCases { e.record() } } }')
            for optimization in ['-Onone', '-O']:
                compiled = subprocess.run(['swiftc', '-swift-version', '6', optimization, str(source), str(main), '-o', str(root/'check')],
                                          capture_output=True, text=True, timeout=30)
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                ran = subprocess.run([str(root/'check')], capture_output=True, timeout=10)
                self.assertEqual(ran.returncode, 0, ran.stderr)
                self.assertEqual(ran.stdout, b''.join(m.PAIRING_PREFIX + e.encode() + b'\n' for e in cases))
                self.assertEqual(m.pairing_lifecycle(io.BytesIO(ran.stdout), len(ran.stdout))['events'], cases)

    def test_events_cover_real_delegate_resolution_dismissal_and_import(self):
        picker = (ROOT/'Native/PairingDocumentPicker.swift').read_text()
        selection = picker.split('didPickDocumentsAt urls:')[1].split('func documentPickerWasCancelled')[0]
        self.assertLess(selection.index('selectionReceived.record()'), selection.index('finish(outcome)'))
        finish = picker.split('private func finish(')[1]
        self.assertIn('relay.resolve(outcome)', finish)
        self.assertIn('lateCallbackIgnored', finish)
        core = (ROOT.parent/'Sources/TetherlessCore/PairingImportFlow.swift').read_text()
        relay = core.split('public final class PairingImportResultRelay')[1]
        delivery = relay.split('public func resolve(')[1].split('public func invalidate(')[0]
        self.assertLess(delivery.index('onResolve = nil; onAbandon = nil'), delivery.index('callback(request, outcome)'))
        delivered = picker.split('relay = PairingImportResultRelay(')[1].split('onAbandon: onAbandon')[0]
        self.assertLess(delivered.index('resultDelivered.record()'), delivered.index('onResolve(request, outcome)'))
        self.assertIn('coordinatorInvalidated.record()', picker)
        view = (ROOT/'Overrides/OnboardingView.swift').read_text()
        selected = view.split('case .selected(let url):')[1].split('@ViewBuilder')[0]
        self.assertLess(selected.index('importStarted.record()'), selected.index('importPairingFile(from: url)'))
        self.assertLess(selected.index('importPairingFile(from: url)'), selected.index('importSucceeded.record()'))
        self.assertIn('importFailed.record()\n                    throw error', selected)
        self.assertIn('coverDismissed.record()', view)
        self.assertIn('dismissalUnbound.record()', view)
        self.assertIn('dismissalObserved.record()', view)
        self.assertIn('dismissalIgnored.record()', view)
        self.assertIn('resolutionIgnored.record()', view)
        self.assertIn('resolutionAccepted.record()', view)
        # The lifecycle API has no untrusted string/URL/error argument.
        arguments = re.findall(r'\.record\(([^)\n]*)\)', picker + view)
        self.assertGreaterEqual(len(arguments), 10)
        self.assertTrue(all(argument == '' for argument in arguments))


if __name__ == '__main__': unittest.main()
