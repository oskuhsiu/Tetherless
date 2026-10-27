#!/usr/bin/env python3
"""Run existing native/source contract tests against verified stage snapshots.

A missing Swift compiler, missing contract, loader error, skipped test, failure,
or unexpected success fails this gate. Original assertions are not modified.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import unittest

# This entry point runs as a script; loading by path also supports unit tests.
INTEGRATION = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('prepared_contract_inputs', INTEGRATION / 'prepared_contract_inputs.py')
inputs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inputs)

REQUIRED_TESTS = {
    'test_ipa_input_safety.IPAInputIntegrationTests.test_exact_native_input_uses_same_snapshot_and_no_second_source_copy',
    'test_anisette_cache_safety.AnisetteCacheSafetyTests.test_real_transformation_and_byte_identical_cache',
    'test_anisette_cache_safety.AnisetteCacheSafetyTests.test_unexpected_generated_file_is_not_overwritten',
    'test_oda_metadata_safety.ODAMetadataIntegrationTests.test_real_transformation_all_routes_and_source_identity',
    'test_oda_metadata_safety.ODAMetadataIntegrationTests.test_generated_destination_collision_preserves_all_bytes',
    'test_oda_metadata_safety.ODAMetadataIntegrationTests.test_actual_native_models_and_adapter_compile_and_reject_fallback',
}


def test_ids(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from test_ids(test)
        else:
            yield test.id()


def load_suite():
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    for stage in inputs.STAGES:
        name = 'test_' + stage
        spec = importlib.util.spec_from_file_location(name, INTEGRATION / 'tests' / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite.addTests(loader.loadTestsFromModule(module))
    if loader.errors or not REQUIRED_TESTS.issubset(set(test_ids(suite))):
        raise ValueError('Required prepared source contracts were not loaded')
    return suite


def run(root: Path, *, stream=None) -> int:
    stream = stream or sys.stderr
    if not shutil.which('swiftc'):
        raise ValueError('Swift compiler is required for prepared source contracts')
    # Set every input before imports evaluate their existing skip decorators.
    environment = inputs.verify(root)
    previous = {key: os.environ.get(key) for key in environment}
    try:
        os.environ.update(environment)
        suite = load_suite()
        result = unittest.TextTestRunner(verbosity=2, stream=stream).run(suite)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    if result.skipped:
        print('Prepared source contracts must execute without skips', file=stream)
    if result.expectedFailures:
        print('Prepared source contracts must not contain expected failures', file=stream)
    return 0 if result.wasSuccessful() and not result.skipped and not result.expectedFailures else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, default=INTEGRATION.parent / '.generated' / inputs.DIRECTORY)
    args = parser.parse_args()
    try:
        return run(args.inputs)
    except (OSError, ValueError) as error:
        print('Prepared source contract gate failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
