"""Portable active-source identity checks; no Swift or diagnostic execution.

Stopped historical picker tools and the completed toy packaging diagnostic keep
their original loader pins. They are inventoried separately, never required to
follow the active helper, and must receive a separate review before reuse. This
test does not import those tools or replace the Darwin promotion scenarios.
"""
import ast
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
HELPER_ROOT = ROOT / 'Integration/Dependencies/idevice'
CURRENT_HELPER_SHA = '552c1f309ee7a782be9e0aafd84dc70c580a5aedea342225d5a2d7b714a8dd9d'
ACTIVE_HELPER_PIN_FILES = {
    'Integration/Dependencies/idevice/apple-recipe-files.json',
    'Integration/fixtures/ColdPairingParser/source-lock.json',
    'Integration/tests/test_pairing_generated_promotion.py',
    'Integration/verify_pairing_composition.py',
    'Integration/verify_pairing_host_app.py',
}
DORMANT_HELPER_PIN_FILES = {
    'Integration/Diagnostics/picker_archive.py': 'stopped historical picker analysis',
    'Integration/packaging-diagnostic/run_diagnostic.py': 'completed toy packaging diagnostic',
}
# picker_archive_event.py pins the historical picker wrapper, not apply_patch.py.
# Its transitive identity remains historical too; no current-wrapper requirement
# or diagnostic execution is introduced here.


def assignment(relative, name):
    """Read literal metadata without importing or running the source module."""
    tree = ast.parse((ROOT / relative).read_text())
    values = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    if len(values) != 1:
        raise AssertionError('expected one literal identity assignment: ' + relative + ':' + name)
    return ast.literal_eval(values[0])


def identity(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def helper_pin_inventory():
    """Include nested/platform-skipped dictionaries, but not historical prose."""
    found = []
    for path in sorted((ROOT / 'Integration').rglob('*')):
        if path.suffix == '.py':
            dictionaries = [node for node in ast.walk(ast.parse(path.read_text())) if isinstance(node, ast.Dict)]
            pairs = ((key.value, value.value) for node in dictionaries for key, value in zip(node.keys, node.values)
                     if isinstance(key, ast.Constant) and isinstance(value, ast.Constant))
        elif path.suffix == '.json':
            pending, pairs = [json.loads(path.read_text())], []
            while pending:
                value = pending.pop()
                if isinstance(value, dict):
                    pairs.extend(value.items()); pending.extend(value.values())
                elif isinstance(value, list):
                    pending.extend(value)
        else:
            continue
        for name, expected in pairs:
            if (isinstance(name, str) and Path(name).name == 'apply_patch.py'
                    and isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected)):
                found.append((path.relative_to(ROOT).as_posix(), expected))
    return found


class NativeHelperMetadataTests(unittest.TestCase):
    def test_active_helper_and_loader_tables_match_current_bytes(self):
        tables = (
            ('Integration/tests/test_pairing_generated_promotion.py', 'HELPER_HASHES', HELPER_ROOT),
            ('Integration/verify_pairing_composition.py', 'EXPECTED', ROOT),
            ('Integration/verify_pairing_host_app.py', 'EXPECTED', ROOT),
        )
        for source, name, root in tables:
            for relative, expected in assignment(source, name).items():
                with self.subTest(source=source, helper=relative):
                    self.assertEqual(identity(root / relative), expected)

    def test_generated_swift_test_uses_the_same_portable_identity_constant(self):
        tree = ast.parse((ROOT / 'Integration/tests/test_pairing_generated_promotion.py').read_text())
        method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                      and node.name == 'test_actual_manager_debug_and_optimized_swift_fixtures')
        selected = next(node.value for node in ast.walk(method) if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == 'helper_hashes' for target in node.targets))
        self.assertIsInstance(selected, ast.Name)
        self.assertEqual(selected.id, 'HELPER_HASHES')
        self.assertTrue(any(isinstance(node, ast.FunctionDef)
                            and node.name == 'test_supervisor_helper_identities_without_swift' for node in ast.walk(tree)))
        self.assertIn('skipUnless', ast.unparse(method.decorator_list[0]))
        self.assertIn('darwin', ast.unparse(method.decorator_list[0]))

    def test_every_literal_helper_pin_has_an_explicit_active_or_dormant_scope(self):
        found = helper_pin_inventory()
        self.assertTrue(ACTIVE_HELPER_PIN_FILES.isdisjoint(DORMANT_HELPER_PIN_FILES))
        known = ACTIVE_HELPER_PIN_FILES | DORMANT_HELPER_PIN_FILES.keys()
        self.assertEqual({path for path, _ in found}, known)
        self.assertEqual(len(found), len(known))

    def test_only_active_helper_pins_are_required_to_match_current_source(self):
        self.assertEqual(identity(HELPER_ROOT / 'apply_patch.py'), CURRENT_HELPER_SHA)
        for source, expected in helper_pin_inventory():
            if source in ACTIVE_HELPER_PIN_FILES:
                with self.subTest(source=source):
                    self.assertEqual(expected, CURRENT_HELPER_SHA)


if __name__ == '__main__':
    unittest.main()
