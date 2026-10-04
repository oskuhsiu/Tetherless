#!/usr/bin/env python3
"""Read-only CI stage classification. No network, simulator control, or retry.

Inputs are saved GitHub run/jobs responses plus an exact step-name map.
This reports the first failing boundary, NOT its root cause or product safety.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

STAGES = frozenset(('environment', 'prepare', 'build', 'signature', 'boot',
                    'install_launch', 'fixture', 'ui', 'postcheck', 'evidence', 'cleanup'))
FAILURES = frozenset(('failure', 'timed_out', 'action_required', 'startup_failure'))
SHA = re.compile(r'^[0-9a-f]{40}$')


def unwrap(value):
    """Accept raw REST or documented connector wrappers, not arbitrary nesting."""
    for _ in range(4):
        if not isinstance(value, dict):
            raise ValueError('Expected JSON object')
        if isinstance(value.get('content'), str):
            value = json.loads(value['content'])
        elif isinstance(value.get('result'), dict):
            value = value['result']
        else:
            return value
    raise ValueError('Too many response wrappers')


def read_json(path):
    with Path(path).open('rb') as file:
        data = file.read(4_194_305)
    if len(data) > 4_194_304:
        raise ValueError('JSON evidence exceeds limit')
    return unwrap(json.loads(data))


def hash_record(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def stage_names(mapping):
    result = {}
    for stage, names in mapping.items():
        if stage not in STAGES or not isinstance(names, list):
            raise ValueError('Invalid stage map')
        for name in names:
            if not isinstance(name, str) or not name or name in result:
                raise ValueError('Ambiguous stage name')
            result[name] = stage
    return result


def classify(run, jobs, mapping, job_id, smoke=None, symptom='unclassified', previous=None):
    run, jobs = unwrap(run), unwrap(jobs)
    names = stage_names(mapping)
    if not SHA.fullmatch(run.get('head_sha', '')) or type(run.get('id')) is not int:
        raise ValueError('Run identity missing')
    candidates = [j for j in jobs.get('jobs', []) if j.get('id') == job_id]
    if len(candidates) != 1:
        raise ValueError('Select exactly one observed job')
    job = candidates[0]
    if job.get('run_id') != run['id']:
        raise ValueError('Run and job do not match')
    if job.get('head_sha', run['head_sha']) != run['head_sha']:
        raise ValueError('Job SHA does not match run')
    if job.get('run_attempt', run.get('run_attempt')) != run.get('run_attempt'):
        raise ValueError('Mixed run attempts')
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', symptom):
        raise ValueError('Use a fixed symptom code, not raw log text')
    steps = sorted(job.get('steps', []), key=lambda s: s['number'])
    if not steps or len({s['number'] for s in steps}) != len(steps):
        raise ValueError('Missing or duplicate steps')
    for step in steps:
        if (type(step['number']) is not int or step['number'] < 1 or
                step.get('status') not in ('queued', 'pending', 'in_progress', 'completed') or
                step.get('conclusion') not in (None, 'success', 'failure', 'skipped', 'cancelled',
                                               'timed_out', 'neutral', 'action_required', 'startup_failure')):
            raise ValueError('Invalid step status')
    first = next((s for s in steps if s.get('conclusion') in FAILURES), None)
    complete = run.get('status') == 'completed' and job.get('status') == 'completed'
    if not complete:
        outcome, failure_stage = 'pending', None
    elif first is not None:
        outcome, failure_stage = 'failed', names.get(first['name'], 'unknown')
    elif job.get('conclusion') == 'success':
        outcome, failure_stage = 'job_passed', None
    elif job.get('conclusion') == 'cancelled':
        outcome, failure_stage = 'cancelled', None
    else:
        outcome, failure_stage = 'incomplete', 'unknown'
    observations = []
    for step in steps:
        # Only fixed mapped stage identifiers enter the report, not arbitrary
        # workflow titles which could contain account or file data.
        observations.append({'number': step['number'], 'stage': names.get(step['name'], 'unknown'),
                             'status': step.get('status'), 'conclusion': step.get('conclusion')})
    smoke_flags = None
    if smoke is not None:
        if smoke.get('sourceCommit') != run['head_sha']:
            raise ValueError('Smoke evidence belongs to another SHA')
        fields = ('simulatorReady', 'installed', 'launched', 'smokePassed')
        if any(k in smoke and type(smoke[k]) is not bool for k in fields):
            raise ValueError('Smoke flags must be booleans')
        smoke_flags = {k: smoke.get(k) for k in fields}
        if smoke_flags['smokePassed'] is True and not all(smoke_flags[k] is True for k in fields):
            raise ValueError('Contradictory smoke evidence')
    fingerprint = None
    if outcome == 'failed':
        fingerprint = hash_record({'stage': failure_stage, 'symptom': symptom})
    repeated = bool(previous and fingerprint and fingerprint == previous.get('failureFingerprint'))
    if outcome == 'pending':
        action = 'checkpoint-existing-run-do-not-dispatch'
    elif outcome == 'cancelled':
        action = 'inspect-cancellation-not-a-product-failure'
    elif repeated:
        action = 'stop-repeat-review-new-evidence-before-any-run'
    elif failure_stage in ('ui', 'postcheck'):
        action = 'inspect-test-log-xcresult-and-app-lifecycle-not-boot'
    elif failure_stage in ('evidence', 'cleanup'):
        action = 'repair-evidence-or-owned-cleanup-preserve-test-result'
    elif outcome == 'job_passed':
        action = 'verify-exact-test-assertions-and-artifacts'
    else:
        action = 'inspect-first-failing-stage-before-changing-anything'
    report = {'schemaVersion': 1, 'runID': run['id'], 'runAttempt': run.get('run_attempt'),
              'jobID': job_id, 'sourceCommit': run['head_sha'], 'outcome': outcome,
              'firstFailureStage': failure_stage, 'firstFailureStep': first['number'] if first else None,
              'observations': observations, 'smoke': smoke_flags, 'symptomCode': symptom,
              'symptomSource': 'agent-selected-after-reading-evidence-not-inferred',
              'failureFingerprint': fingerprint, 'sameFailureAsPrevious': repeated,
              'nextAction': action, 'automaticRetryAllowed': False,
              'rootCauseInferred': False, 'productAccepted': False}
    report['reportSHA256'] = hash_record(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--jobs', required=True, type=Path)
    parser.add_argument('--map', required=True, type=Path)
    parser.add_argument('--job-id', required=True, type=int)
    parser.add_argument('--smoke', type=Path)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--symptom', default='unclassified')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = classify(read_json(args.run), read_json(args.jobs), read_json(args.map), args.job_id,
                          read_json(args.smoke) if args.smoke else None, args.symptom,
                          read_json(args.previous) if args.previous else None)
        # Never overwrite old diagnostic evidence or silently create its parent.
        with args.output.open('x', encoding='utf-8') as file:
            json.dump(report, file, indent=2); file.write('\n')
        print(report['outcome'], report['firstFailureStage'], report['nextAction'])
        return 0  # Successful reporting is not a successful product test.
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        print('Invalid, mismatched, or unavailable evidence; no retry authorized.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
