import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('catalog_safety', ROOT / 'catalog_safety.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


class CatalogSafetyTests(unittest.TestCase):
    def test_unknown_conflict_throws_instead_of_debug_trap(self):
        original = '''                // Unknown context-level conflict.
                let entityName = conflict.conflictingObjects.first?.entity.name ?? "Unknown"
                assertionFailure("Context Conflict Detected for table '\\(entityName)': is there ambiguous data?\\nConflict:\\(conflict)")'''
        result = module.patch_merge(original)
        self.assertIn('throw CatalogImportError.unresolvedConstraint', result)
        self.assertNotIn('assertionFailure(', result)
        self.assertNotIn('conflictingObjects.first', result)
        with self.assertRaises(ValueError): module.patch_merge(result)

    def test_failed_parent_save_cannot_return_success(self):
        anchor = '                    debugLog("Failed to save managedObjectContext in fetchSources: \\(error.localizedDescription)")'
        result = module.patch_manager(anchor)
        self.assertIn('managedObjectContext.rollback()', result)
        self.assertIn('completionHandler(.failure(.init(error)))', result)
        self.assertTrue(result.rstrip().endswith('return'))
        self.assertNotIn('debugLog', result)

    def test_entire_graph_validation_precedes_saving_and_legacy_dedup(self):
        source = (ROOT / 'catalog_safety.py').read_text()
        self.assertIn('CatalogImportSafety.validateNewVersions(in: childContext)', source)
        self.assertIn('childContext.rollback()', source)
        self.assertIn('throw CatalogImportError.duplicateApp', source)
        core = (ROOT.parent / 'Sources/TetherlessCore/CatalogImportSafety.swift').read_text()
        self.assertIn('context.insertedObjects', core)
        self.assertIn('!$0.isDeleted', core)
        self.assertNotIn('versionID', core)

    def test_last_unreviewed_input_cannot_partially_patch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contents = {module.MERGE: b'merge', module.FETCH: b'fetch', module.MANAGER: b'manager-drift'}
            pins = {}
            for name, data in contents.items():
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
                pins[name] = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            pins[module.MANAGER] = '0' * 40
            with patch.dict(module.BLOBS, pins), patch.object(module, 'patch_merge', return_value='changed'), \
                 patch.object(module, 'patch_fetch', return_value='changed'):
                with self.assertRaises(ValueError): module.apply(root)
            for name, data in contents.items(): self.assertEqual((root / name).read_bytes(), data)

    def test_native_preparation_includes_catalog_guard(self):
        source = (ROOT / 'network_safety.py').read_text()
        self.assertLess(source.index('"launch_safety.py"'), source.index('"catalog_safety.py"'))
        tests = (ROOT.parent / 'Tests/TetherlessCoreTests/CatalogImportSafetyTests.swift').read_text()
        self.assertIn('NSSQLiteStoreType', tests)
        self.assertIn('CatalogImportSafety.validateNewVersions(in: child)', tests)
        self.assertIn('child.rollback()', tests)
