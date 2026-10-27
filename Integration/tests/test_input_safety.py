"""Pinned transformations and API contracts, not claims of device behavior."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('input_safety', ROOT / 'input_safety.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class PairingIntegrationTests(unittest.TestCase):
    def test_override_retains_native_apis_and_is_not_in_duplicate_source_group(self):
        s = (ROOT / 'Overrides/PairingFileManager.swift').read_text()
        for symbol in ['func fetchPairingFile(', 'func importPairingFile(', 'func inspectPairingFile(',
                       'func savePairingFile(', 'func resetAllPairingFiles()', 'func migrateLegacyFiles()']:
            self.assertIn(symbol, s)
        self.assertNotIn('debugLog(', s)
        self.assertNotIn('try? fm.removeItem', s)
        self.assertNotIn('isShareSheetPresented = true', s)
        self.assertIn('NativeMutationGate.withSynchronousLease', s)
        self.assertNotIn('Data(contentsOf:', s)
    def test_preparation_invokes_pairing_hardening(self):
        self.assertIn('input_safety.py', (ROOT / 'prepare.py').read_text())
    def test_cold_boot_migrates_before_missing_pairing_prompt(self):
        prepare_spec = importlib.util.spec_from_file_location('boot_prepare', ROOT / 'prepare.py')
        prepare = importlib.util.module_from_spec(prepare_spec)
        prepare_spec.loader.exec_module(prepare)
        fixture = "PREFIX\n    public nonisolated func performBootSequence() async {\nOLD\n}\n}"
        result = prepare.patch_boot(fixture)
        self.assertLess(result.index('migrateLegacyFiles()'), result.index('guard let pairing ='))
        self.assertLess(result.index('NativeMutationGate.withLease'), result.index('migrateLegacyFiles()'))
        self.assertIn('if !PairingFileManager.shared.hasPairingFile()', result)

    def test_every_transformation_input_is_hash_pinned(self):
        self.assertEqual(set(m.BLOBS), {m.PAIR, *m.PATCHES})
        self.assertTrue(all(len(value) == 40 for value in m.BLOBS.values()))
    def test_unknown_input_does_not_partially_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / m.PAIR
            path.parent.mkdir(parents=True)
            path.write_text('unreviewed')
            with self.assertRaisesRegex(ValueError, 'Unreviewed'): m.apply(root)
            self.assertEqual(path.read_text(), 'unreviewed')
    def test_maintenance_migration_precedes_counter_check(self):
        fixture = '    public func performMaintenanceIfNeeded() async {\nCOUNTER\n}\n    func migratePairingFiles() async {\nUNSAFE\n}\n}'
        result = m.patch_maintenance(fixture)
        self.assertNotIn('UNSAFE', result)
        self.assertLess(result.index('try PairingFileManager.shared.migrateLegacyFiles()'), result.index('COUNTER'))
    def test_protocol_switch_holds_device_lease(self):
        result = m.patch_wrapper('func minimuxerSwitchPairingProtocol(to proto: PairingProtocol) async throws {\nBODY\n}')
        self.assertIn('NativeMutationGate.withLease', result)
        self.assertEqual(result.count('BODY'), 1)

if __name__ == '__main__': unittest.main()
