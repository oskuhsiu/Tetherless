"""Exact branch-only execution contract for the separately scoped manager fixtures."""
import ast
import hashlib
from pathlib import Path
import re
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github/workflows/pairing-composition-swift.yml'


class PairingGeneratedPromotionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text()
        self.header, jobs = self.text.split('jobs:\n', 1)
        self.original, self.job = jobs.split('  generated-promotion-fixtures:\n', 1)

    def test_existing_composition_job_is_byte_identical(self):
        self.assertEqual(hashlib.sha256(self.original.encode()).hexdigest(),
                         'd4519656e0dd1a99a2364cabfe744c6cfea6d9eda39a97febc98425a0625274f')

    def test_branch_and_exact_source_paths(self):
        self.assertIn('branches: [verify/staged-pairing-native]', self.header)
        self.assertIn("if: github.ref == 'refs/heads/verify/staged-pairing-native'", self.job)
        expected = [
            'Integration/Native/NativePairingMutation.swift',
            'Integration/Native/PairingSetupModel.swift',
            'Integration/Overrides/PairingFileManager.swift',
            'Integration/fixtures/PairingGeneratedPromotionCommon.swift',
            'Integration/fixtures/PairingGeneratedPromotionMain.swift',
            'Integration/fixtures/PairingGeneratedPromotionSupport.swift',
            'Integration/tests/test_pairing_generated_promotion.py',
            'Integration/tests/test_pairing_generated_promotion_workflow.py',
            'Sources/TetherlessCore/MutationScope.swift',
            'Sources/TetherlessCore/PairingReset.swift',
            'Tests/TetherlessCoreTests/PairingPromotionBoundaryTests.swift',
        ]
        for path in expected:
            self.assertEqual(self.header.count("      - '" + path + "'"), 1, path)
        self.assertNotIn('paths-ignore:', self.header)

    def test_pinned_execution_and_read_only_permissions(self):
        self.assertIn('permissions:\n  contents: read\n', self.header)
        self.assertNotIn('write', self.header)
        self.assertIn('cancel-in-progress: false', self.header)
        self.assertIn('runs-on: macos-15', self.job)
        self.assertIn('DEVELOPER_DIR: /Applications/Xcode_26.3.app/Contents/Developer', self.job)
        self.assertEqual(re.findall(r'uses: ([^\s]+)', self.job), [
            'actions/checkout@11d5960a326750d5838078e36cf38b85af677262',
            'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02',
        ])
        self.assertIn('persist-credentials: false', self.job)
        self.assertIn('submodules: false', self.job)
        self.assertNotIn('continue-on-error', self.job)
        self.assertNotIn('needs:', self.job)

    def test_bounded_steps_and_exact_test_execution(self):
        budgets = list(map(int, re.findall(r'timeout-minutes: (\d+)', self.job)))
        self.assertEqual(budgets, [20, 3, 1, 9, 1, 2])
        self.assertLess(sum(budgets[1:]), budgets[0])
        self.assertIn('-p test_pairing_generated_promotion.py -v', self.job)
        self.assertLess(self.job.index('test "$(uname -s)" = Darwin'),
                        self.job.index('-p test_pairing_generated_promotion.py -v'))
        self.assertIn('-p test_pairing_generated_promotion_workflow.py -v', self.job)
        self.assertEqual(self.job.count('set -euo pipefail'), 3)
        self.assertIn('TETHERLESS_PAIRING_GENERATED_EVIDENCE_ROOT: ${{ github.workspace }}/.pairing-generated-promotion-evidence/fixtures', self.job)

    def test_evidence_precedes_tests_and_always_uploads(self):
        self.assertLess(self.job.index('run-context.json'), self.job.index('-p test_pairing_generated_promotion.py'))
        self.assertIn('test ! -e .pairing-generated-promotion-evidence', self.job)
        self.assertIn('if: always()\n        uses: actions/upload-artifact@', self.job)
        self.assertIn('name: pairing-generated-promotion-${{ github.sha }}-${{ github.run_attempt }}', self.job)
        self.assertIn('path: .pairing-generated-promotion-evidence/\n', self.job)
        self.assertIn('if-no-files-found: error', self.job)
        self.assertNotIn('path: /tmp', self.job)
        self.assertNotIn('path: ${{ runner.temp }}', self.job)

    def test_embedded_context_is_syntactic_and_honest_about_seams(self):
        program = self.job.split("python3 - <<'PY'\n", 1)[1].split('\n          PY', 1)[0]
        tree = ast.parse(textwrap.dedent(program))
        values = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)]
        for expected in ['source_commit', 'run_id', 'run_attempt', 'source_sha256',
                         'expected_cases_per_configuration', 'debug', 'optimized',
                         'actual_idevice_ffi', 'real_parser_or_os_process_lock', 'device_or_product_acceptance']:
            self.assertIn(expected, values)
        self.assertIn("'actual_idevice_ffi': False", program)
        self.assertIn("'real_parser_or_os_process_lock': False", program)
        self.assertIn("'device_or_product_acceptance': False", program)
        self.assertIn('synthetic external parser, app state and process-lease acquisition', program)


if __name__ == '__main__':
    unittest.main()
