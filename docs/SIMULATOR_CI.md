# Simulator CI: mandatory skill and current evidence

Updated 2026-10-05. Read `.agents/skills/ios-simulator-ci/SKILL.md` before changing or rerunning any Simulator-related job. The skill is reusable; Tetherless paths, step mappings and incident evidence belong here. No production Swift or existing Simulator workflow changes in this increment.

## Current boundary and evidence

The current completed full-product run is **37247923030**, attempt 1, job **111569414544**, source **89c157dbc6acd3c16eb31a32bdc6d73af6c40f57**. Build, signature, boot, installation, launch and fixture passed; XCTest failed at document selection. Original-file verification passed. Both product and independent UIKit recipient remained in the picker without callback delivery; the control used its own source container. Full details and artifact digest are in [STATUS.md](STATUS.md).

The current `simulator-ci/observed-run.json`, `observed-jobs.json` and `latest-report.json` were regenerated from rechecked connector results plus the matching saved smoke evidence. The report's first failure is `ui`; it authorizes no automatic retry and makes no root-cause or product-acceptance claim. No record from the earlier install timeout is being used to classify this UI run.

The recovered iOS 18.6 patch is not adopted unchanged: a normal-job runtime substitution and separate rebuilds cannot establish a runtime-only cause. A separately reviewed cross-container, same-host, same-binary diagnostic is the next planned evidence step. It must preserve regular full-product coverage, the original selection/timeout/data-preservation assertions and focused resolver/provider evidence. See [next-run decision](simulator-ci/next-run-decision.md).

The sections below preserve the earlier 20faee9 observation as historical context. Their run IDs and reproduction command are not the current classifier inputs.

## Use existing reviewed components

- `.github/workflows/native-simulator.yml`: complete app workflow, owned destination, actual signing check, UI and artifact collection.
- `Integration/simulator_environment.py`: owned-device allocation/shutdown and bounded service diagnostics.
- `Integration/simulator_smoke.py`: readiness, install/launch/screenshot with explicit stage evidence.
- `Integration/simulator_signing.py`: actual built Simulator signature and Keychain identity.
- `Integration/retain_ui_diagnostics.py`: bounded raw excerpts and fixed pairing lifecycle trace, with completeness information.
- `Integration/UITests/TetherlessUITests.swift`: unchanged acceptance assertions. Logs/markers cannot replace these assertions.

Do not create another launcher, switch to a generic architecture target, pick newer Xcode/runtime implicitly, or repeat changed click targets without a discriminating hypothesis. The current environment workflow still selects from installed toolchains: recording/enforcing a fully fixed runtime fingerprint is not implemented merely by adding this skill. Any such change requires its own scoped verification.

## Historical observation at 20faee9, not the current failure

Live run **37195486462**, attempt **1**, job **111416356929**, source **20faee940c802acb1cd2efc18e921ea3c4598636** completed with failure. The run's own number is 38 for this named workflow; this is NOT a count of all repository failures/retries. No repository-wide claim of approximately 100 startup failures was independently established.

The job passed compilation, signature checking, boot, installation and launch. It failed step 11, the actual XCTest. Original-document verification was skipped. Later artifact collection/shutdown succeeded but do not erase the test failure.

Artifact **11300687557** was downloaded through GitHub and independently SHA-256 checked: `24d2445d0453ea7876d931098a47437deefa0b8dd6f08af697180e082c3baecd`. Actual smoke evidence reports simulatorReady, installed, launched and smokePassed true; its uiFlowsTested false is the earlier smoke scope, not a later test result. The actual XCTest log fails at TetherlessUITests.swift:59: no import outcome, system picker still visible, after the original ten-second deadline. The test failed in 73.604 seconds.

The trace manifest scanned all 4,423,416 stdout bytes; scanComplete=true, eventsTruncated=false, 23 fixed events. For each of the first two cancellations, coverDismissed/dismissalObserved/cancelFinished occurs before cancellationReceived/resultDelivered/resolutionIgnored. The third request records requestBegan/pickerCreated/plistTypeAllowed but no selectionReceived, resolutionAccepted or importStarted before the failing result. This is an observed absence in the retained complete scan, not proof of a particular UIKit, provider or production root cause. Plist acceptance was recorded as allowed. Do not weaken that policy or return to guessing preview taps. A separate selected-file lifecycle/provider diagnosis is the next product item.

## Applied read-only classification

`simulator-ci/observed-run.json` and `observed-jobs.json` are minimal projections of the live connector responses (no success statuses synthesized). `stages.json` maps current exact job step names; unknown future steps remain unknown until reviewed. `latest-report.json` was generated by the skill's actual script against these responses and the downloaded smoke JSON. Result: `failed`, first stage `ui`, next action `inspect-test-log-xcresult-and-app-lifecycle-not-boot`, automaticRetryAllowed=false, rootCauseInferred=false, productAccepted=false.

Historical reproduction (retrieve the matching historical JSON and smoke before use; current files refer to 89c157d):

```sh
S=.agents/skills/ios-simulator-ci
python3 "$S/scripts/triage.py" --run docs/simulator-ci/observed-run.json \
  --jobs docs/simulator-ci/observed-jobs.json --map docs/simulator-ci/stages.json \
  --job-id 111416356929 --smoke /path/to/native-launch-evidence.json \
  --symptom selection-not-observed --output /path/to/new-diagnosis.json
python3 -m unittest discover -s "$S/tests" -v
```

The 16 portable tests executed locally, including a real CLI subprocess, immutable output checks, mismatched run/SHA rejection, pending/cancelled states, evidence failures, repeated fingerprints and smoke-vs-UI separation. They are not native Simulator or XCUITest executions. The new lightweight Linux-only skill workflow validates the helper; it does not repair or rerun the failing iOS job.

## Next-run operating rule

Before dispatch, complete the skill's decision template using this run and the trace above. Record one hypothesis, new evidence/discriminating change, expected observation and unchanged acceptance. Same failed boundary without new evidence means stop, not another full run. Handle one long item per turn and checkpoint its IDs. The classifier has no GitHub mutation capability; this is an agent operating rule, not a server-side ban on human reruns.

The skill-only increment closes no product acceptance condition. Live Apple login, valid pairing, profile installation and unattended renewal still require the agreed later acceptance. `docs/PLAN_PROGRESS.md` remains the product task inventory.
