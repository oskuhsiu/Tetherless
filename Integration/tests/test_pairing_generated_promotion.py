"""Source checks plus Darwin execution of the actual generated-record manager path.

The Darwin harness uses explicit synthetic app/parser/process-acquisition seams.
It is neither a real MinimuxerCommon parser test nor an OS-lock/device proof.
A non-Darwin skip is recorded as unrun, never as executed native coverage.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MANAGER = ROOT / 'Integration/Overrides/PairingFileManager.swift'
MODEL = ROOT / 'Integration/Native/PairingSetupModel.swift'
ENTRY_START = '    /// Generated remote records reach this entry only after joined staged\n'
ENTRY_END = '    /// Internal capability: a wireless session owns the same process lease until\n'
FIXTURES = {
    'typed_rejection_before_mutation',
    'parser_failure_preserves_old_target',
    'ordinary_replacement_keeps_fallback',
    'reset_marked_recovery_cleans_leftovers',
    'exact_bytes_and_inherited_lease',
    'validation_and_cancellation_preserve_old_target',
    'post_write_cleanup_failure_requires_recovery',
    'unavailable_lease_blocks_mutation',
}
HELPER_HASHES = {
    'bounded_process.py': '7724f6c3eb7d624f49a2651b30f1d6e6bb2c47d356449cd495fad28b2dd144e4',
    'apply_patch.py': '552c1f309ee7a782be9e0aafd84dc70c580a5aedea342225d5a2d7b714a8dd9d',
}


def fixture_evidence_root(temporary, configured):
    """Keep only this fixture's fixed logs/status/source hashes in an opt-in root."""
    if configured is None:
        return temporary, False
    if not configured.strip():
        raise ValueError('fixture evidence root must not be empty')
    selected = Path(configured).absolute()
    if any(path.is_symlink() for path in [selected, *selected.parents]):
        raise ValueError('fixture evidence root must not contain symlink aliases')
    evidence = selected.resolve(strict=False)
    private = temporary.resolve(strict=True)
    if evidence.is_relative_to(private) or private.is_relative_to(evidence):
        raise ValueError('fixture evidence and private work directories must be disjoint')
    if evidence.exists() or not evidence.parent.is_dir():
        raise ValueError('fixture evidence root must be a new plain directory under an existing parent')
    evidence.mkdir(mode=0o700)
    return evidence, True


class PairingGeneratedPromotionTests(unittest.TestCase):
    def test_supervisor_helper_identities_without_swift(self):
        # Keep the Darwin prerequisite visible even when Swift execution is unrun.
        helper_root = ROOT / 'Integration/Dependencies/idevice'
        for name, digest in HELPER_HASHES.items():
            self.assertEqual(hashlib.sha256((helper_root / name).read_bytes()).hexdigest(), digest, name)

    def test_evidence_root_is_opt_in_new_and_separate_from_private_work(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            private = parent / 'private'; private.mkdir()
            self.assertEqual(fixture_evidence_root(private, None), (private, False))
            selected = parent / 'evidence'
            self.assertEqual(fixture_evidence_root(private, str(selected)), (selected, True))
            self.assertTrue(selected.is_dir())
            self.assertEqual(selected.stat().st_mode & 0o777, 0o700)
            self.assertEqual(list(selected.iterdir()), [])
            with self.assertRaises(ValueError): fixture_evidence_root(private, str(selected))
            with self.assertRaises(ValueError): fixture_evidence_root(private, str(private))
            with self.assertRaises(ValueError): fixture_evidence_root(private, str(private / 'nested-evidence'))
            with self.assertRaises(ValueError): fixture_evidence_root(private, str(parent / 'private' / '..' / 'private' / 'nested-evidence'))
            self.assertFalse((private / 'nested-evidence').exists())
            with self.assertRaises(ValueError): fixture_evidence_root(private, '')

    def test_evidence_root_rejects_aliases_files_and_missing_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            private = parent / 'private'; private.mkdir()
            existing = parent / 'file'; existing.write_text('fixture')
            alias = parent / 'alias'; alias.symlink_to(private, target_is_directory=True)
            for path in [existing, alias, alias / 'evidence', parent / 'missing' / 'evidence']:
                with self.assertRaises(ValueError): fixture_evidence_root(private, str(path))

    def test_typed_entry_preserves_exact_xml_with_explicit_remote_bound(self):
        source = MANAGER.read_text()
        self.assertEqual(source.count(ENTRY_START), 1)
        entry = source.split(ENTRY_START, 1)[1].split(ENTRY_END, 1)[0]
        self.assertIn('func saveValidatedRemotePairingRecord(_ record: PairingRecord)', entry)
        self.assertIn('guard record.kind == .remote else { throw PrivateFileError.invalidContent }', entry)
        self.assertIn('guard record.xml.count <= 4096 else { throw PrivateFileError.tooLarge }', entry)
        self.assertIn('return try NativeMutationGate.withSynchronousLease { try commit(record) }', entry)
        self.assertLess(entry.index('guard record.kind'), entry.index('guard record.xml.count'))
        self.assertLess(entry.index('guard record.xml.count'), entry.index('withSynchronousLease'))
        for forbidden in ['PairingRecord(data:', 'record.content', 'Data(', 'preferredProtocol =', 'persistedActiveProtocol =']:
            self.assertNotIn(forbidden, entry)

    def test_existing_manager_and_lease_sources_remain_identical_outside_added_entry(self):
        source = MANAGER.read_text()
        before, suffix = source.split(ENTRY_START, 1)
        _, after = suffix.split(ENTRY_END, 1)
        unchanged = (before + ENTRY_END + after).encode()
        self.assertEqual(hashlib.sha256(unchanged).hexdigest(),
                         '6ef6d342f3fd2f291b3e935a190cd4dd00b40c74bdf5cceb4a779d6c9f9cf84a')
        expected = {
            'Integration/Native/NativePairingMutation.swift': 'ed5460b5ccbc2c61d6284c1f991b2a3164ff80f250c2dcedf4b2903db3bc7aa2',
            'Sources/TetherlessCore/MutationScope.swift': '5c1c44104983f4111c8e9c5db9361a0b8b40b556eec8cff1fc9eda9f92768bbc',
            'Sources/TetherlessCore/PairingPromotion.swift': '26a86c9bca1f8147c1d04db8d8f79a5045681672041fed96745b1592e842d6b4',
        }
        for relative, digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest, relative)

    def test_app_caller_uses_typed_record_after_cancellation_winner(self):
        source = MODEL.read_text()
        commit = source.split('}, commit: { [self] record in', 1)[1].split('})', 1)[0]
        self.assertLess(commit.index('cancellation.beginPromotion()'), commit.index('saveValidatedRemotePairingRecord(record)'))
        self.assertLess(commit.index('saveValidatedRemotePairingRecord(record)'), commit.index('preferredProtocol = .rppairing'))
        self.assertNotIn('savePairingFile(contents:', commit)
        self.assertNotIn('record.content', commit)
        self.assertIn('default: return cancellation.isCancelled ? .cancelled : .failed', source)
        self.assertNotIn('await ', '\n'.join(line for line in commit.splitlines() if not line.strip().startswith('//')))
        # This check is deliberately bounded to the two owned production files.
        self.assertEqual(source.count('saveValidatedRemotePairingRecord('), 1)
        self.assertEqual(MANAGER.read_text().count('saveValidatedRemotePairingRecord('), 1)

    def test_fixture_executes_production_sources_and_marks_synthetic_seams(self):
        common = (ROOT / 'Integration/fixtures/PairingGeneratedPromotionCommon.swift').read_text()
        support = (ROOT / 'Integration/fixtures/PairingGeneratedPromotionSupport.swift').read_text()
        main = (ROOT / 'Integration/fixtures/PairingGeneratedPromotionMain.swift').read_text()
        self.assertIn('does not exercise or model the real MinimuxerCommon parser', common)
        self.assertIn('not real OS process-lock behavior', support)
        self.assertNotIn('class PairingFileManager', support + main)
        self.assertNotIn('func saveValidatedRemotePairingRecord', support + main)
        self.assertEqual(set(re.findall(r'report\("([a-z_]+)"\)', main)), FIXTURES)
        self.assertIn('createSymbolicLink', main)
        self.assertIn('outcome == .recoveryRequired', main)
        self.assertIn('counts.released + 1', main)

    @unittest.skipUnless(sys.platform == 'darwin', 'UNRUN: actual-manager Swift fixture requires Apple Foundation/UniformTypeIdentifiers')
    def test_actual_manager_debug_and_optimized_swift_fixtures(self):
        self.assertIsNotNone(shutil.which('xcrun'), 'Apple toolchain is required; do not silently skip on Darwin')
        production = [
            'Integration/Overrides/PairingFileManager.swift',
            'Integration/Native/NativePairingMutation.swift',
            'Sources/TetherlessCore/PairingRecord.swift',
            'Sources/TetherlessCore/PrivateFileStore.swift',
            'Sources/TetherlessCore/PairingReset.swift',
            'Sources/TetherlessCore/MutationScope.swift',
            'Sources/TetherlessCore/PairingPromotion.swift',
            'Sources/TetherlessCore/PairingCancellationController.swift',
        ]
        helper_root = ROOT / 'Integration/Dependencies/idevice'
        helper_hashes = HELPER_HASHES
        for name, digest in helper_hashes.items():
            self.assertEqual(hashlib.sha256((helper_root / name).read_bytes()).hexdigest(), digest)
        spec = importlib.util.spec_from_file_location('pairing_generated_supervisor_loader', ROOT / 'Integration/verify_pairing_composition.py')
        loader = importlib.util.module_from_spec(spec); spec.loader.exec_module(loader)
        invoke = loader.load_supervisor(helper_root)
        temporary = Path(tempfile.mkdtemp(prefix='pairing-generated-fixtures-')).resolve()
        try:
            evidence, retained_evidence = fixture_evidence_root(temporary, os.environ.get('TETHERLESS_PAIRING_GENERATED_EVIDENCE_ROOT'))
        except BaseException:
            shutil.rmtree(temporary) # No process or private fixture has started.
            raise
        safe_cleanup = True
        completed = False
        source_paths = production + ['Integration/fixtures/PairingGeneratedPromotion' + suffix + '.swift'
                                     for suffix in ['Common', 'Support', 'Main']] + [
                                         'Integration/tests/test_pairing_generated_promotion.py']
        source_hashes = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in source_paths}
        (evidence / 'source-hashes.json').write_text(json.dumps(source_hashes, indent=2) + '\n')
        environment = os.environ.copy()
        environment['TETHERLESS_PAIRING_FIXTURE_ROOT'] = str(temporary / 'owned-fixture')
        environment['HOME'] = environment['CFFIXED_USER_HOME'] = str(temporary / 'home')
        (temporary / 'home').mkdir()

        def run(name, command, timeout):
            nonlocal safe_cleanup
            for path, digest in source_hashes.items():
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)
            log = evidence / (name + '.log')
            safe_cleanup = False
            try:
                invoke(command, source=temporary, env=environment, log=log,
                       timeout_seconds=timeout, max_log_bytes=16 * 1024 * 1024,
                       tail_bytes=128 * 1024, term_grace_seconds=5, kill_join_seconds=5)
            finally:
                status_path = log.with_name(log.name + '.status.json')
                status = json.loads(status_path.read_bytes()) if status_path.is_file() else {}
                cleanup = status.get('cleanup') or {}
                safe_cleanup = cleanup.get('direct_child_reaped') is True and cleanup.get('group_empty') is True
            self.assertTrue(safe_cleanup)
            self.assertEqual(status.get('outcome'), 'success')
            self.assertEqual(status.get('returncode'), 0)
            self.assertTrue(status.get('output_complete'))
            for path, digest in source_hashes.items():
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)
            self.assertLessEqual(log.stat().st_size, 16 * 1024 * 1024)
            return log.read_text()

        try:
            common = ROOT / 'Integration/fixtures/PairingGeneratedPromotionCommon.swift'
            command = ['xcrun', '--sdk', 'macosx', 'swiftc', '-swift-version', '5', '-parse-as-library',
                       '-emit-library', '-emit-module', '-module-name', 'MinimuxerCommon',
                       '-emit-module-path', str(temporary / 'MinimuxerCommon.swiftmodule'),
                       str(common), '-o', str(temporary / 'libMinimuxerCommon.dylib')]
            run('synthetic-common-compile', command, 120)
            for configuration, optimization in [('debug', '-Onone'), ('optimized', '-O')]:
                binary = temporary / configuration
                command = ['xcrun', '--sdk', 'macosx', 'swiftc', '-swift-version', '5', '-parse-as-library', optimization,
                           '-I', str(temporary), '-L', str(temporary), '-lMinimuxerCommon',
                           '-Xlinker', '-rpath', '-Xlinker', str(temporary),
                           *[str(ROOT / path) for path in production],
                           str(ROOT / 'Integration/fixtures/PairingGeneratedPromotionSupport.swift'),
                           str(ROOT / 'Integration/fixtures/PairingGeneratedPromotionMain.swift'), '-o', str(binary)]
                run(configuration + '-compile', command, 120)
                lines = run(configuration + '-fixtures', [str(binary)], 30).splitlines()
                self.assertCountEqual(lines, ['pairing_generated_fixture passed=' + name for name in FIXTURES])
                for name in sorted(FIXTURES):
                    print('pairing_generated_fixture configuration=' + configuration + ' passed=' + name)
            completed = True
        finally:
            if safe_cleanup and (completed or retained_evidence):
                shutil.rmtree(temporary)
            else:
                # Keep failed evidence, and never clean while descendants may own files.
                print('pairing_generated_fixture retained_scratch=' + str(temporary))
            if retained_evidence:
                print('pairing_generated_fixture evidence_root=' + str(evidence))



if __name__ == '__main__':
    unittest.main()
