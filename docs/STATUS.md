# Single-item checkpoint — targeted installation observations

2026-10-05. Implementation: **89c157dbc6acd3c16eb31a32bdc6d73af6c40f57**. This final checkpoint is documentation only. The implementation changes the existing Simulator failure helper and adds eight focused tests; **product Swift, the independent UIKit control, the full-App workflow and every acceptance assertion are unchanged**. Develop only; main remains unpromoted. No iPhone or credentials requested.

## Next standalone verification

Read full-App run **37247923030**, job **111569414544**, for 89c157d. It started **2026-10-05T00:32:45Z** and was **in_progress**, conclusion null, at the single status check. Do not infer success, cancel it or dispatch another. Keep this long verification separate from additional features.

If installation fails, inspect native-simulator-health/manifest.json and the new install-container-readback.log, install-registration.log and install-product-events.log. Preserve each command's timeout/exit and truncation metadata. A returned container is not complete-install or launch acceptance, and these observations never overwrite smoke flags. If installation succeeds, inspect the original product and failure-only UIKit comparison. Neither logging nor an incidental successful installation proves the previous timeout's cause was fixed.

## Actual latest completed result

Run **37242839315**, attempt 1, job **111554802378**, at **8c25ff3** FAILED at step 8: **simctl install timed out at the unchanged 120-second bound**. Build, signature inspection, bootstatus and the home screenshot passed. Product launch, the document source, and all product/control UI were skipped. The independent comparison has no result. Do not call this another observed FileProvider rejection or a comparison failure.

The verified artifact **11318286484** has SHA-256 **dc10213d482dbc643681f7c698bb2ef1ab03fafbe711bc9930a512411fb13048**. Its install log contains one command and TIMEOUT; smoke records simulatorReady=true, installed=false, launched=false, smokePassed=false, failureType=TimeoutExpired. No successful install command result was observed; a partial/late daemon result was not checked in that version.

Generic service output mixed container initialization with installer events. Of 637,606 original bytes, only 262,144 head/tail bytes were retained, omitting 375,462 middle bytes. It did not query lsd directly. The retained log cannot establish a deadlock, memory shortage or product signature defect. Full details are preserved in STATUS.md at 89c157d and docs/simulator-ci/next-run-decision.md.

The actual skill classifier processed live-checked run/job projections and the verified smoke JSON: failed / install_launch, automaticRetryAllowed=false, productAccepted=false. Report SHA-256 **4b10b0db99b2afbf39295b91bb2b5c13bd4fa65169f52dcf8d0b2062bb2fad0e**. Current projections/report remain in docs/simulator-ci.

## What changed and what did not

Only after a recorded installation failure, the existing diagnostic step adds three read-only queries before generic logs: exact product app-container lookup, installd/lsd registration events, and exact-product events. Each uses the existing 15-second/256-KiB capture with explicit failure and omission metadata. Inputs must match the current job SHA, owned live device and allowed bundle identifier. Malformed/unbound evidence records a gap without suppressing generic diagnosis. No new query runs for a UI-only failure.

No install/launch/reset/retry is issued by diagnostics. The original failed smoke record remains byte-identical even when all observation commands return success. This is an evidence-gap correction, **not a verified fix for the installation timeout**. The unchanged control still runs only after a frozen product failure and cannot turn it green.

## Local evidence

**8 new diagnostic tests, 23 existing Simulator checks and 16 skill tests passed.** They include real temporary-file/subprocess behavior, scripted simctl responses, binding/input checks and immutable failure-state checks. The actual selector also consumed the downloaded owner/smoke/device records and produced the expected three queries without executing them remotely. No new native/UI pass, full integration count or product-core test run is claimed.

Current source artifact **11317283922** matched ZIP **35bc701d8e0384aacbc2a96a48b2d1cd1872e7dd2c1bf850a5c9e6a737facecf**, TAR **41a7e1d9fe6b6a1fe453615b66d46a0756bfa3d7ee8541bf587db6e2dde6ab30**, and recorded 8c25ff3. Uploaded Integration subtree **6ae2a46237b58d81a6799e6252948978c25006ef** matched the locally tested tree. git diff --check passed. Initial expected-SHA ref update was rejected by connector argument binding; the unchanged head was re-read before a successful non-force update.

AUTO-02 / PAIR-01 invalid-document acceptance is still open. No new product feature, live Apple login, valid pairing, physical profile install, locked-screen scheduled renewal or expiry-crossing acceptance was completed. Broader task scope remains PLAN_PROGRESS.md. End at this saved checkpoint, not another polling loop.
