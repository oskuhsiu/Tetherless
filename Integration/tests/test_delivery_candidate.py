"""Synthetic byte/source evidence only, never native compilation or device acceptance."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('delivery_candidate_tests', ROOT / 'delivery_candidate.py')
d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
spec = importlib.util.spec_from_file_location('unsigned_package_tests', ROOT / 'package_unsigned.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, root, *args):
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()

    def repository(self, name='repo'):
        root = self.root / name; root.mkdir()
        self.git(root, 'init', '-q')
        self.git(root, 'config', 'user.email', 'fixture@example.invalid')
        self.git(root, 'config', 'user.name', 'Fixture')
        (root / 'source.mm').write_text('// objective C++ input\n')
        (root / 'LICENSE').write_text('license fixture\n')
        self.commit(root)
        return root

    def commit(self, root):
        self.git(root, 'add', '.')
        self.git(root, 'commit', '-qm', 'fixture')
        return self.git(root, 'rev-parse', 'HEAD')

    def zip_bytes(self, files):
        result = io.BytesIO()
        with zipfile.ZipFile(result, 'w') as archive:
            for name, data in files:
                archive.writestr(name, data)
        return result.getvalue()

    def ipa(self):
        info = plistlib.dumps({'CFBundleIdentifier': 'fixture.app', 'CFBundleExecutable': 'Fixture'})
        nested = self.zip_bytes([('Payload/Nested.app/Info.plist', info), ('Payload/Nested.app/Nested', b'nested')])
        ipa = self.root / 'candidate.ipa'
        ipa.write_bytes(self.zip_bytes([('Payload/Main.app/Info.plist', info),
            ('Payload/Main.app/Fixture', b'fixture'), ('Payload/Main.app/SideBackup.ipa', nested),
            ('Payload/Main.app/Frameworks/Example.framework/Info.plist', info),
            ('Payload/Main.app/Frameworks/Example.framework/Example', b'framework')]))
        return ipa

    def collect(self, root):
        entries, repos, omissions = [], [], []
        d.collect_git(root, 'repository', entries, repos, omissions, d.Budget(), d.revision(root))
        return entries, repos, omissions

    def test_sources_include_all_extensions_and_recursive_gitlinks(self):
        root = self.repository()
        child = self.repository('child')
        self.git(root, '-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', str(child), 'Vendor/Child')
        self.commit(root)
        (root / 'untracked-secret').write_text('not a source input')
        entries, repos, _ = self.collect(root)
        names = {e['path'] for e in entries}
        self.assertIn('repository/source.mm', names)
        self.assertIn('repository/Vendor/Child/source.mm', names)
        self.assertNotIn('repository/untracked-secret', names)
        self.assertFalse(any('/.git/' in name for name in names))
        self.assertEqual(len(repos), 2)
        self.assertTrue(all(e['matchesGitBlob'] for e in entries))

    def test_rejects_wrong_source_commit(self):
        root = self.repository()
        with self.assertRaises(ValueError):
            d.collect_git(root, 'repository', [], [], [], d.Budget(), '0' * 40)

    def test_dirty_bytes_preserved_but_never_called_same_commit(self):
        root = self.repository(); (root / 'source.mm').write_text('modified input')
        entries, _, omissions = self.collect(root)
        source = next(e for e in entries if e['path'].endswith('source.mm'))
        self.assertFalse(source['matchesGitBlob'])
        self.assertIn('working-bytes-differ-from-commit', [o['reason'] for o in omissions])

    def test_staged_file_is_compared_to_committed_tree(self):
        root = self.repository()
        committed = self.git(root, 'rev-parse', 'HEAD:source.mm')
        (root / 'source.mm').write_text('different staged text')
        self.git(root, 'add', 'source.mm')
        entries, _, omissions = self.collect(root)
        record = next(e for e in entries if e['path'].endswith('source.mm'))
        self.assertEqual(record['gitBlob'], committed)
        self.assertFalse(record['matchesGitBlob'])
        self.assertIn('working-bytes-differ-from-commit', [o['reason'] for o in omissions])

    def test_staged_mode_is_compared_to_committed_tree(self):
        root = self.repository()
        (root / 'source.mm').chmod(0o755)
        self.git(root, 'add', 'source.mm')
        entries, _, omissions = self.collect(root)
        record = next(e for e in entries if e['path'].endswith('source.mm'))
        self.assertEqual(record['gitMode'], '100644')
        self.assertTrue(record['matchesGitBlob'])
        self.assertFalse(record['matchesGitMode'])
        self.assertIn('working-mode-differs-from-commit', [o['reason'] for o in omissions])

    def test_staged_gitlink_cannot_replace_committed_child_revision(self):
        root = self.repository(); child = self.repository('child')
        self.git(root, '-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', str(child), 'Vendor/Child')
        self.commit(root)
        checkout = root / 'Vendor/Child'
        self.git(checkout, 'config', 'user.name', 'Fixture')
        self.git(checkout, 'config', 'user.email', 'fixture@example.invalid')
        (checkout / 'source.mm').write_text('later child commit')
        self.commit(checkout)
        self.git(root, 'add', 'Vendor/Child')
        with self.assertRaisesRegex(ValueError, 'requested commit/gitlink'): self.collect(root)

    def test_excluded_records_and_gitlinks_count_against_budget(self):
        root = self.repository()
        for index in range(3): (root / f'fixture{index}.p12').write_text('plain text, not credential data')
        self.commit(root)
        with patch.object(d, 'MAX_FILES', 3):
            with self.assertRaisesRegex(ValueError, 'size/count budget'): self.collect(root)
        root = self.repository('gitlinks'); child = self.repository('child')
        self.git(root, '-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', str(child), 'Vendor/Child')
        self.commit(root)
        entries, repos, omissions, budget = [], [], [], d.Budget()
        d.collect_git(root, 'repository', entries, repos, omissions, budget)
        self.assertEqual(budget.files, len(entries) + 1)

    def test_subprocess_output_is_capped_during_execution_and_child_reaped(self):
        real_popen = d.subprocess.Popen; processes = []
        def capture(*args, **kwargs):
            process = real_popen(*args, **kwargs); processes.append(process); return process
        command = [sys.executable, '-c', 'import sys,time; sys.stdout.write("x" * 1024); sys.stdout.flush(); time.sleep(10)']
        with patch.object(d.subprocess, 'Popen', side_effect=capture):
            with self.assertRaisesRegex(ValueError, 'size budget'):
                d.bounded_output(command, 64, timeout=2)
        self.assertIsNotNone(processes[0].poll())
        self.assertEqual(d.bounded_output([sys.executable, '-c', 'print("okay",end="")'], 4), b'okay')
        with patch.object(d, 'MAX_GIT_BYTES', 3):
            with self.assertRaisesRegex(ValueError, 'size budget'): d.git(self.root, '--version')

    def test_subprocess_timeout_reaps_child(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            d.bounded_output([sys.executable, '-c', 'import time; time.sleep(10)'], 64, timeout=0.05)

    def test_missing_submodule_rejected(self):
        root = self.repository()
        self.git(root, 'update-index', '--add', '--cacheinfo', '160000,' + '1' * 40 + ',Vendor/Missing')
        self.git(root, 'commit', '-qm', 'missing gitlink')
        with self.assertRaises(ValueError): self.collect(root)

    def test_tree_omits_private_generated_inputs_but_retains_exact_sample(self):
        root = self.root / 'prepared'; root.mkdir()
        for name in ('payload.p12', 'pair.mobiledevicepairing', '.env', 'key.pem'):
            (root / name).write_text('secret fixture')
        (root / '.git').mkdir(); (root / '.git/config').write_text('credential fixture')
        (root / 'CodeSigning.xcconfig.sample').write_text('EMPTY = YES')
        (root / 'CodeSigning.xcconfig').write_text('EMPTY = YES')
        (root / 'source.S').write_text('assembly fixture')
        entries, omissions = [], []
        d.collect_tree(root, 'prepared', entries, omissions, d.Budget())
        self.assertEqual({e['path'] for e in entries}, {'prepared/CodeSigning.xcconfig.sample', 'prepared/CodeSigning.xcconfig', 'prepared/source.S'})
        self.assertEqual(len(omissions), 5)
        self.assertNotIn('secret fixture', json.dumps([d.public_entry(e) for e in entries]))

    def test_safe_symlinks_preserved_and_escaping_links_rejected(self):
        root = self.repository(); (root / 'link').symlink_to('source.mm'); self.commit(root)
        entries, _, _ = self.collect(root)
        self.assertEqual(next(e for e in entries if e['type'] == 'symlink')['target'], 'source.mm')
        (root / 'outside').symlink_to('../outside'); self.commit(root)
        with self.assertRaises(ValueError): self.collect(root)

    def test_dangling_in_root_link_keeps_identity_and_explicit_missing_status(self):
        root = self.root / 'prepared'; root.mkdir()
        (root / 'pointer').symlink_to('future/input.txt')
        entries, omissions = [], []
        d.collect_tree(root, 'prepared', entries, omissions, d.Budget())
        entry = entries[0]
        self.assertEqual(entry['target'], 'future/input.txt')
        self.assertEqual(entry['sha256'], hashlib.sha256(b'future/input.txt').hexdigest())
        self.assertEqual(entry['targetResolution'], {'path': 'future/input.txt', 'existence': 'missing',
            'pathPolicy': 'included', 'crossedExcludedPath': False, 'contentRead': False, 'missingAt': 'future'})
        self.assertEqual(omissions, [])
        self.assertFalse((root / 'future').exists())

    def test_pinned_sidebackup_link_before_and_after_build_stays_metadata_only(self):
        root = self.root / 'prepared'; resources = root / 'AltStore/Resources'; resources.mkdir(parents=True)
        target = '../../build/SideBackup.ipa'
        self.assertEqual(hashlib.sha1(b'blob 26\0' + target.encode()).hexdigest(), '54a080c4e8a5029ad8d22842c16acde4d6d01b43')
        (resources / 'SideBackup.ipa').symlink_to(target)
        first, second = self.root / 'before.tar.gz', self.root / 'after.tar.gz'
        d.snapshot_prepared(root, first, '1' * 40)
        before = json.loads(first.with_name(first.name + '.json').read_text())
        entry = before['files'][0]
        self.assertEqual(entry['targetResolution']['existence'], 'missing')
        self.assertEqual(entry['targetResolution']['pathPolicy'], 'excluded')
        self.assertEqual(entry['targetResolution']['path'], 'build/SideBackup.ipa')
        self.assertEqual(entry['targetResolution']['missingAt'], 'build')
        (root / 'build').mkdir(); (root / 'build/SideBackup.ipa').write_text('ordinary generated-output fixture')
        real_open = d.open_regular
        def reject_generated_content(path):
            if path.is_relative_to(root / 'build'):
                raise AssertionError('Generated output content was read through a source link')
            return real_open(path)
        with patch.object(d, 'open_regular', side_effect=reject_generated_content):
            d.snapshot_prepared(root, second, '1' * 40)
        after = json.loads(second.with_name(second.name + '.json').read_text())
        self.assertEqual(after['files'][0]['targetResolution']['existence'], 'present')
        self.assertEqual(after['files'][0]['targetResolution']['pathPolicy'], 'excluded')
        self.assertFalse(after['files'][0]['targetResolution']['contentRead'])
        self.assertEqual(entry['sha256'], after['files'][0]['sha256'])
        self.assertEqual(before['archive']['sha256'], after['archive']['sha256'])
        with tarfile.open(second) as archive:
            self.assertEqual(archive.getnames(), ['prepared/AltStore/Resources/SideBackup.ipa'])
            member = archive.getmembers()[0]
            self.assertTrue(member.issym()); self.assertEqual(member.linkname, target)

    def test_source_link_chain_escape_and_private_targets_are_rejected_before_read(self):
        root = self.root / 'prepared'; root.mkdir()
        (root / 'pointer').symlink_to('build/hop')
        (root / 'build').mkdir()
        for destination in ('../../outside', '../.git/config', '../.env', '../private.pem', '../CodeSigning.xcconfig'):
            with self.subTest(destination=destination):
                hop = root / 'build/hop'; hop.symlink_to(destination)
                with patch.object(d, 'open_regular', side_effect=AssertionError('No target bytes may be read')):
                    with self.assertRaises(ValueError):
                        d.collect_file(root, 'pointer', 'prepared', d.Budget())
                hop.unlink()
        (root / 'build').rmdir(); (root / 'build').symlink_to('../outside', target_is_directory=True)
        with self.assertRaises(ValueError): d.collect_file(root, 'pointer', 'prepared', d.Budget())

    def test_source_link_chain_can_end_at_missing_in_root_target(self):
        root = self.root / 'prepared'; root.mkdir(); (root / 'dir').mkdir()
        (root / 'pointer').symlink_to('dir/hop')
        (root / 'dir/hop').symlink_to('../future/output')
        entry = d.collect_file(root, 'pointer', 'prepared', d.Budget())
        self.assertEqual(entry['target'], 'dir/hop')
        self.assertEqual(entry['targetResolution']['path'], 'future/output')
        self.assertEqual(entry['targetResolution']['existence'], 'missing')
        self.assertEqual(entry['targetResolution']['pathPolicy'], 'included')

    def test_source_link_expansion_precedes_parent_components(self):
        root = self.root / 'prepared'; (root / 'deep/dir').mkdir(parents=True)
        (root / 'deep/result.txt').write_text('ordinary source')
        (root / 'alias').symlink_to('deep/dir')
        (root / 'pointer').symlink_to('alias/../result.txt')
        entry = d.collect_file(root, 'pointer', 'prepared', d.Budget())
        self.assertEqual(entry['targetResolution']['path'], 'deep/result.txt')
        self.assertEqual(entry['targetResolution']['existence'], 'present')
        self.assertFalse((root / 'result.txt').exists())

    def test_source_link_loops_special_targets_and_unrelated_errors_stay_fail_closed(self):
        root = self.root / 'prepared'; root.mkdir()
        (root / 'first').symlink_to('second'); (root / 'second').symlink_to('first')
        with patch.object(d, 'MAX_LINK_HOPS', 2):
            with self.assertRaisesRegex(ValueError, 'hop budget'):
                d.collect_file(root, 'first', 'prepared', d.Budget())
        os.mkfifo(root / 'fifo'); (root / 'fifo-link').symlink_to('fifo')
        with self.assertRaisesRegex(ValueError, 'special file'):
            d.collect_file(root, 'fifo-link', 'prepared', d.Budget())
        (root / 'file').write_text('ordinary source')
        with self.assertRaisesRegex(ValueError, 'non-directory'):
            d.inspect_source_link(root, 'pointer', 'file/child')
        with patch.object(Path, 'lstat', side_effect=PermissionError('synthetic denied metadata')):
            with self.assertRaises(PermissionError):
                d.inspect_source_link(root, 'pointer', 'unreadable')

    def test_committed_dangling_source_link_is_recorded_against_exact_blob(self):
        root = self.repository(); (root / 'pointer').symlink_to('future/input.txt'); self.commit(root)
        entries, _, omissions = self.collect(root)
        entry = next(e for e in entries if e['path'].endswith('/pointer'))
        self.assertTrue(entry['matchesGitBlob']); self.assertTrue(entry['matchesGitMode'])
        self.assertEqual(entry['targetResolution']['existence'], 'missing')
        self.assertEqual(omissions, [])

    def test_no_symlink_directory_traversal_or_special_files(self):
        root = self.repository(); (root / 'dir').mkdir(); (root / 'dir/file').write_text('source')
        self.commit(root)
        (root / 'dir/file').unlink(); (root / 'dir').rmdir(); (root / 'dir').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError): self.collect(root)
        tree = self.root / 'special'; tree.mkdir(); os.mkfifo(tree / 'fifo')
        with self.assertRaises(ValueError): d.collect_tree(tree, 'prepared', [], [], d.Budget())

    def test_bounds_apply_to_files_and_tree_depth(self):
        root = self.repository()
        with patch.object(d, 'MAX_FILE_BYTES', 2):
            with self.assertRaises(ValueError): self.collect(root)
        with patch.object(d, 'MAX_FILES', 1):
            with self.assertRaises(ValueError): self.collect(root)
        root = self.root / 'deep'; (root / 'a/b').mkdir(parents=True)
        with patch.object(d, 'MAX_DEPTH', 1):
            with self.assertRaises(ValueError): d.collect_tree(root, 'prepared', [], [], d.Budget())

    def test_source_tar_is_deterministic_and_identity_matches_bytes(self):
        entries, _, _ = self.collect(self.repository())
        first = self.root / 'first.tar.gz'; second = self.root / 'second.tar.gz'
        a = d.write_tar(first, entries); b = d.write_tar(second, list(reversed(entries)))
        self.assertEqual(a['sha256'], b['sha256'])
        self.assertEqual(a['sha256'], hashlib.sha256(first.read_bytes()).hexdigest())
        with tarfile.open(first) as archive:
            self.assertEqual(set(archive.getnames()), {e['path'] for e in entries})
            for entry in entries:
                member = archive.getmember(entry['path'])
                self.assertEqual(member.uid, 0); self.assertEqual(member.mtime, 0)
                self.assertEqual(hashlib.sha256(archive.extractfile(member).read()).hexdigest(), entry['sha256'])

    def test_archive_fails_when_sources_change_after_inventory(self):
        root = self.repository(); entries, _, _ = self.collect(root)
        (root / 'source.mm').write_text('different')
        with self.assertRaises((ValueError, OSError)):
            d.write_tar(self.root / 'changed.tar.gz', entries)

    def test_actual_lock_and_checkout_revisions_are_retained(self):
        root = self.repository()
        payload = {'version': 2, 'pins': [{'identity': 'example', 'location': 'https://github.com/example/source.git',
            'state': {'revision': 'a' * 40, 'version': '1.2.3'}}]}
        (root / 'Package.resolved').write_text(json.dumps(payload)); self.commit(root)
        entries, repos, _ = self.collect(root)
        result = d.dependency_metadata(entries, repos)
        self.assertEqual(result['lockfiles'][0]['pins'][0]['state']['revision'], 'a' * 40)
        self.assertEqual(result['repositories'][0]['revision'], d.revision(root))
        self.assertIsNone(d.public_location('https://user:password@example.invalid/path'))
        self.assertIsNone(d.public_location('/Users/private/checkout'))

    def test_final_inventory_binds_nested_ipa_framework_and_file_bytes(self):
        ipa = self.ipa(); result = d.archive_inventory(ipa)
        self.assertEqual(result['artifact']['sha256'], hashlib.sha256(ipa.read_bytes()).hexdigest())
        self.assertEqual(len(result['containers']), 2)
        outer = result['containers'][0]
        self.assertEqual({b['type'] for b in outer['bundles']}, {'app', 'framework'})
        self.assertEqual(len(outer['nestedIPAs']), 1)
        nested = next(f for f in outer['files'] if f['path'].endswith('.ipa'))
        self.assertEqual(nested['sha256'], outer['nestedIPAs'][0]['sha256'])

    def test_archive_rejects_paths_duplicates_unsafe_links_and_unbounded_nested(self):
        for name in ('../escape', '/absolute', 'a/../escape', 'a\\escape'):
            with self.subTest(name=name):
                path = self.root / 'bad.ipa'; path.write_bytes(self.zip_bytes([(name, b'fixture')]))
                with self.assertRaises(ValueError): d.archive_inventory(path)
        path = self.root / 'bad.ipa'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            path.write_bytes(self.zip_bytes([('same', b'a'), ('same', b'b')]))
        with self.assertRaises(ValueError): d.archive_inventory(path)
        link = zipfile.ZipInfo('Payload/Main.app/link'); link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        path.write_bytes(self.zip_bytes([(link, b'../../../escape')]))
        with self.assertRaises(ValueError): d.archive_inventory(path)
        ipa = self.ipa()
        with patch.object(d, 'MAX_NESTED_IPA_BYTES', 1):
            with self.assertRaises(ValueError): d.archive_inventory(ipa)
        with patch.object(d, 'MAX_ARCHIVE_READ', 64):
            with self.assertRaises(ValueError): d.archive_inventory(ipa)
        with patch.object(d, 'MAX_TOTAL_BYTES', 20):
            with self.assertRaises(ValueError): d.archive_inventory(ipa)

    def test_nested_ipa_cannot_hide_signing_material(self):
        nested = self.zip_bytes([('Payload/Nested.app/private.p12', b'fixture')])
        ipa = self.root / 'private.ipa'
        ipa.write_bytes(self.zip_bytes([('Payload/Main.app/nested.ipa', nested)]))
        with self.assertRaises(ValueError): d.archive_inventory(ipa)
        ipa.write_bytes(self.zip_bytes([('Payload/Main.app/private.pem', b'-----BEGIN PRIVATE KEY-----')]))
        with self.assertRaises(ValueError): d.archive_inventory(ipa)

    def test_preserved_prior_review_hashes_are_checked_without_claiming_currentness(self):
        source = ROOT.parent / 'docs/supply-chain'
        result = d.prior_review(ROOT.parent)
        self.assertEqual(result['status'], 'hash-consistent-prior-review')
        self.assertEqual(result['baseline'], '3dd8641e84698b97f96d53a6c53ed8c6ca4675bd')
        import shutil
        root = self.root / 'review'; (root / 'docs').mkdir(parents=True)
        shutil.copytree(source, root / 'docs/supply-chain')
        (root / 'docs/supply-chain/REPORT.md').write_text('modified review')
        with self.assertRaises(ValueError): d.prior_review(root)

    def test_prebuild_snapshot_preserves_source_extensions_and_hashes(self):
        root = self.root / 'prepared'; root.mkdir()
        for name in ('source.mm', 'assembly.S', 'Makefile', 'LICENSE', 'project.yml'):
            (root / name).write_text('fixture')
        output = self.root / 'review.tar.gz'
        d.snapshot_prepared(root, output, '1' * 40)
        manifest = json.loads(output.with_name(output.name + '.json').read_text())
        self.assertEqual(manifest['archive']['sha256'], hashlib.sha256(output.read_bytes()).hexdigest())
        self.assertEqual(len(manifest['files']), 5)
        self.assertEqual(manifest['status'], 'candidate-incomplete')

    def test_snapshot_refuses_either_existing_target_without_overwriting(self):
        root = self.root / 'prepared'; root.mkdir(); (root / 'source.txt').write_text('ordinary source')
        for existing in ('review.tar.gz', 'review.tar.gz.json'):
            with self.subTest(existing=existing):
                output = self.root / 'review.tar.gz'; target = self.root / existing
                target.write_bytes(b'preserve original')
                with self.assertRaisesRegex(ValueError, 'already exists'):
                    d.snapshot_prepared(root, output, '1' * 40)
                self.assertEqual(target.read_bytes(), b'preserve original')
                other = self.root / ('review.tar.gz.json' if existing == 'review.tar.gz' else 'review.tar.gz')
                self.assertFalse(other.exists()); target.unlink()

    def test_snapshot_manifest_failure_leaves_no_published_files(self):
        root = self.root / 'prepared'; root.mkdir(); (root / 'source.txt').write_text('ordinary source')
        output = self.root / 'review.tar.gz'
        with patch.object(d, 'write_json', side_effect=OSError('synthetic write failure')):
            with self.assertRaises(OSError): d.snapshot_prepared(root, output, '1' * 40)
        self.assertFalse(output.exists()); self.assertFalse(output.with_name(output.name + '.json').exists())
        self.assertFalse(any(p.name.startswith('.tetherless-snapshot-') for p in self.root.iterdir()))

    def test_snapshot_publication_failure_rolls_back_only_owned_file(self):
        root = self.root / 'prepared'; root.mkdir(); (root / 'source.txt').write_text('ordinary source')
        output = self.root / 'review.tar.gz'; sidecar = output.with_name(output.name + '.json')
        real_link = d.os.link
        def fail_second(source, target):
            if target == sidecar:
                target.write_bytes(b'concurrent existing output')
                raise FileExistsError('synthetic race')
            return real_link(source, target)
        with patch.object(d.os, 'link', side_effect=fail_second):
            with self.assertRaises(FileExistsError): d.snapshot_prepared(root, output, '1' * 40)
        self.assertFalse(output.exists()); self.assertEqual(sidecar.read_bytes(), b'concurrent existing output')

    def test_app_metadata_is_bounded_and_special_files_refused(self):
        _, _, app = self.package_inputs()
        with patch.object(p.delivery, 'MAX_METADATA_BYTES', 16):
            with self.assertRaisesRegex(ValueError, 'Metadata exceeds'): p.validate_app(app)
        (app / 'Info.plist').unlink(); os.mkfifo(app / 'Info.plist')
        with self.assertRaisesRegex(ValueError, 'regular input file'): p.validate_app(app)

    def test_uppercase_nested_ipa_is_inventoried_and_checked(self):
        nested = self.zip_bytes([('Payload/Child.app/plain.txt', b'ordinary text')])
        ipa = self.root / 'upper.ipa'
        ipa.write_bytes(self.zip_bytes([('Payload/Main.app/Child.IPA', nested)]))
        result = d.archive_inventory(ipa)
        self.assertEqual(len(result['containers']), 2)
        self.assertEqual(result['containers'][0]['nestedIPAs'][0]['path'], 'Payload/Main.app/Child.IPA')
        nested = self.zip_bytes([('Payload/Child.app/.env', b'ordinary fixture, not a secret')])
        ipa.write_bytes(self.zip_bytes([('Payload/Main.app/Child.IPA', nested)]))
        with self.assertRaisesRegex(ValueError, 'Private/signing'): d.archive_inventory(ipa)

    def test_toolchain_is_explicitly_unavailable_without_tools_and_no_host_dump(self):
        with patch.object(d.subprocess, 'run', side_effect=FileNotFoundError):
            result = d.toolchain()
        self.assertEqual(result['xcode']['status'], 'unavailable')
        self.assertEqual(result['python']['status'], 'observed')
        self.assertNotIn(str(self.root), json.dumps(result))

    def package_inputs(self):
        root = self.repository()
        prepared = self.root / 'prepared'; prepared.mkdir()
        (prepared / 'source.swift').write_text('// generated input')
        app = self.root / 'Main.app'; app.mkdir()
        (app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'fixture.app', 'CFBundleExecutable': 'Main'}))
        (app / 'Main').write_bytes(b'fixture, not executable code')
        return root, prepared, app

    def test_package_manifest_checksums_bundles_and_open_gates_are_consistent(self):
        root, prepared, app = self.package_inputs()
        output = self.root / 'output'
        real_run = subprocess.run
        def run(command, **kwargs):
            if command[0] == 'ditto':
                with zipfile.ZipFile(command[-1], 'w') as archive:
                    payload = Path(command[-2])
                    for source in payload.rglob('*'):
                        if source.is_file(): archive.write(source, source.relative_to(payload.parent).as_posix())
                return subprocess.CompletedProcess(command, 0)
            return real_run(command, **kwargs)
        with patch.object(p.subprocess, 'run', side_effect=run), patch.object(p.delivery, 'toolchain', return_value={'fixture': True}):
            ipa = p.package(app, output, d.revision(root), 'Debug', repository=root, prepared=prepared,
                            source_packages=self.root / 'absent-packages')
        manifest = json.loads((output / 'manifest.json').read_text())
        self.assertEqual(manifest['candidateStatus'], 'candidate-incomplete')
        self.assertFalse(manifest['releaseReady']); self.assertFalse(manifest['deviceValidated'])
        self.assertTrue(all(gate['status'] == 'unresolved' for gate in manifest['releaseGates']))
        self.assertEqual(manifest['sha256'], hashlib.sha256(ipa.read_bytes()).hexdigest())
        self.assertEqual(manifest['sha256'], json.loads((output / 'ipa-inventory.json').read_text())['artifact']['sha256'])
        for artifact in manifest['artifacts']:
            self.assertEqual(artifact['sha256'], hashlib.sha256((output / artifact['path']).read_bytes()).hexdigest())
        for line in (output / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ')
            self.assertEqual(digest, hashlib.sha256((output / name).read_bytes()).hexdigest())
        self.assertEqual(len((output / 'SHA256SUMS').read_text().splitlines()), len(list(output.iterdir())) - 1)
        inputs = json.loads((output / 'inputs.json').read_text())
        self.assertEqual(len(inputs['missingEvidence']), 2)
        self.assertNotIn(str(self.root), json.dumps(inputs))

    def test_package_failure_never_publishes_partial_destination(self):
        root, prepared, app = self.package_inputs(); output = self.root / 'output'
        with patch.object(p.subprocess, 'run', side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):
                p.package(app, output, d.revision(root), 'Debug', repository=root, prepared=prepared)
        self.assertFalse(output.exists())
        self.assertFalse(any(p.name.startswith('.tetherless-package-') for p in self.root.iterdir()))


if __name__ == '__main__': unittest.main()
