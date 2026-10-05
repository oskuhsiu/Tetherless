# One constrained composition-fixture infrastructure retry

## Reported boundary

The first composition workflow 37365518696, attempt 1, source
ad9b33f4c00764bd738e1912389cbe08cedd2c7e, finished with workflow conclusion
failure. Its only job 111949572665 reports conclusion cancelled, runner_id 0,
an empty runner name and an empty step list. Reported job timestamps are
2026-10-05T19:46:05Z through 20:01:07Z. No artifact was produced. The supported
job-log read returned BlobNotFound. These facts provide no reported execution
or Swift fixture result; they do not identify an application failure.

The roughly 15-minute interval is consistent with the workflow's existing job
ceiling. GitHub documents that timeout-minutes automatically cancels a job, but
available metadata does not expose the exact cancellation cause or a cancellation
actor. The triggering actor is not evidence about who cancelled a job. Do not
label this as an explicit owner cancellation, a proven compiler hang or a Swift
failure. A later explicit user stop instruction overrides this record.

## Single retry and unchanged acceptance

Within the owner's authorized development/CI task, retry only that cancelled job
once through GitHub's specific-job retry operation, on its original source SHA.
The purpose is to obtain the missing first execution after a reported
pre-execution infrastructure failure. Do not rerun the whole workflow matrix,
change selectors or raise the 60-second command, six-minute execution-step or
15-minute job bounds. The exact 41-fixture acceptance and join/output requirements
remain unchanged. Record the new attempt/job identity after the operation.

If the same no-runner/no-step outcome recurs, stop this retry loop and retain the
platform blocker; another unchanged retry is not authorized by this record.
If execution actually starts, diagnose the earliest compiler/fixture/evidence
failure from its new complete logs. The separate native stack-storage correction
and EMProxy source slice do not match this workflow's explicit paths and must
not be used as a disguised retry trigger. Their distinct CI remains independent.

The original host/iOS Core checks at ad9b33f both pass. They do not replace the
missing 41-fixture Swift/C-spy result, real native ABI, UIKit composition compilation
or device acceptance. No successful result is inferred from this decision.

Primary timeout reference: [GitHub workflow syntax](https://docs.github.com/en/enterprise-cloud%40latest/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes).

The single specific-job retry operation was accepted on 2026-10-05 at 20:12 UTC.
Read back the original run for its new attempt/job; acceptance is not test success.
