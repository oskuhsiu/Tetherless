import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('triage', ROOT/'scripts/triage.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
SHA = 'a' * 40


def data(fail=6):
    run = {'id': 10, 'head_sha': SHA, 'run_attempt': 1, 'status': 'completed'}
    labels = ['Build', 'Sign', 'Boot', 'Install', 'Launch', 'UI', 'Evidence']
    steps = [{'number': i, 'name': name, 'status': 'completed',
              'conclusion': 'failure' if i == fail else 'success'} for i, name in enumerate(labels, 1)]
    job = {'id': 20, 'run_id': 10, 'status': 'completed', 'conclusion': 'failure' if fail else 'success', 'steps': steps}
    mapping = dict(build=['Build'], signature=['Sign'], boot=['Boot'], install_launch=['Install', 'Launch'], ui=['UI'], evidence=['Evidence'])
    return run, {'jobs': [job]}, mapping


class TriageTests(unittest.TestCase):
    def test_ui_failure_is_never_a_boot_failure(self):
        r = m.classify(*data(), 20)
        self.assertEqual(r['firstFailureStage'], 'ui')
        self.assertIn('not-boot', r['nextAction'])
        self.assertFalse(r['automaticRetryAllowed'])
        self.assertFalse(r['productAccepted'])

    def test_all_first_failure_boundaries(self):
        for n, stage in [(1,'build'),(2,'signature'),(3,'boot'),(4,'install_launch'),(6,'ui'),(7,'evidence')]:
            with self.subTest(n=n): self.assertEqual(m.classify(*data(n),20)['firstFailureStage'], stage)

    def test_later_diagnostic_failure_cannot_replace_original(self):
        run,jobs,mapping=data()
        jobs['jobs'][0]['steps'][-1]['conclusion']='failure'
        self.assertEqual(m.classify(run,jobs,mapping,20)['firstFailureStep'],6)

    def test_smoke_pass_is_not_ui_pass(self):
        smoke=dict(sourceCommit=SHA,simulatorReady=True,installed=True,launched=True,smokePassed=True)
        report=m.classify(*data(),20,smoke)
        self.assertTrue(report['smoke']['smokePassed']); self.assertEqual(report['outcome'],'failed')
        self.assertFalse(report['productAccepted'])

    def test_mixed_sha_run_attempt_and_job_are_rejected(self):
        for what in ['sha','run','attempt']:
            run,jobs,mapping=data()
            jobs['jobs'][0][{'sha':'head_sha','run':'run_id','attempt':'run_attempt'}[what]]={'sha':'b'*40,'run':11,'attempt':2}[what]
            with self.assertRaises(ValueError):m.classify(run,jobs,mapping,20)
        with self.assertRaises(ValueError):m.classify(*data(),20,dict(sourceCommit='b'*40))

    def test_pending_is_checkpoint_not_rerun(self):
        run,jobs,mapping=data();run['status']='in_progress'
        report=m.classify(run,jobs,mapping,20)
        self.assertEqual(report['outcome'],'pending'); self.assertFalse(report['automaticRetryAllowed'])

    def test_cancellation_without_failure_is_not_a_product_failure(self):
        run,jobs,mapping=data(0);jobs['jobs'][0]['conclusion']='cancelled'
        report=m.classify(run,jobs,mapping,20)
        self.assertEqual(report['outcome'],'cancelled'); self.assertIsNone(report['firstFailureStage'])

    def test_unknown_step_does_not_guess_stage(self):
        run,jobs,mapping=data();jobs['jobs'][0]['steps'][5]['name']='Unmapped operation'
        self.assertEqual(m.classify(run,jobs,mapping,20)['firstFailureStage'],'unknown')

    def test_duplicate_or_missing_steps_jobs_are_rejected(self):
        run,jobs,mapping=data(); jobs['jobs']*=2
        with self.assertRaises(ValueError):m.classify(run,jobs,mapping,20)
        for steps in [[],[{'number':1},{'number':1}]]:
            run,jobs,mapping=data(); jobs['jobs'][0]['steps']=steps
            with self.assertRaises(ValueError):m.classify(run,jobs,mapping,20)

    def test_repeat_fingerprint_survives_new_sha_and_run(self):
        old=m.classify(*data(),20,symptom='selection-not-observed')
        run,jobs,mapping=data(); run['head_sha']='b'*40;run['id']=11;jobs['jobs'][0]['run_id']=11
        report=m.classify(run,jobs,mapping,20,symptom='selection-not-observed',previous=old)
        self.assertTrue(report['sameFailureAsPrevious']);self.assertTrue(report['nextAction'].startswith('stop-repeat'))
        report=m.classify(run,jobs,mapping,20,symptom='new-symptom',previous=old)
        self.assertFalse(report['sameFailureAsPrevious'])

    def test_wrappers_and_fixed_fields_do_not_echo_raw_secrets(self):
        run,jobs,mapping=data();jobs['jobs'][0]['steps'][-1]['name']='SYNTHETIC_TOKEN'
        report=m.classify({'content':json.dumps(run)},{'result':jobs},mapping,20)
        self.assertNotIn('SYNTHETIC_TOKEN',json.dumps(report))
        with self.assertRaises(ValueError):m.classify(*data(),20,symptom='token=https://secret')

    def test_contradictory_or_untyped_smoke_is_refused(self):
        for s in [dict(sourceCommit=SHA,smokePassed=True),dict(sourceCommit=SHA,installed='true')]:
            with self.assertRaises(ValueError):m.classify(*data(),20,s)

    def test_job_green_never_means_product_accepted(self):
        report=m.classify(*data(0),20)
        self.assertEqual(report['outcome'],'job_passed');self.assertFalse(report['productAccepted'])

    def test_invalid_mapping_and_run_identity_are_rejected(self):
        run,jobs,mapping=data();mapping['ui']+=['Build']
        with self.assertRaises(ValueError):m.classify(run,jobs,mapping,20)
        run,jobs,mapping=data();run['head_sha']='develop'
        with self.assertRaises(ValueError):m.classify(run,jobs,mapping,20)

    def test_untrusted_status_is_not_exported(self):
        run,jobs,mapping=data();jobs['jobs'][0]['steps'][0]['status']='SYNTHETIC_SECRET'
        with self.assertRaises(ValueError):m.classify(run,jobs,mapping,20)

    def test_real_cli_does_not_overwrite_previous_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name, value in zip(['run','jobs','map'],data()): (root/(name+'.json')).write_text(json.dumps(value))
            args=[sys.executable,str(ROOT/'scripts/triage.py'),'--run',str(root/'run.json'),'--jobs',str(root/'jobs.json'),'--map',str(root/'map.json'),'--job-id','20','--output',str(root/'out.json')]
            first=subprocess.run(args,capture_output=True,text=True);self.assertEqual(first.returncode,0,first.stderr)
            original=(root/'out.json').read_bytes()
            second=subprocess.run(args,capture_output=True,text=True);self.assertEqual(second.returncode,2)
            self.assertEqual((root/'out.json').read_bytes(),original)


if __name__=='__main__':unittest.main()
