# Current checkpoint — installation timeout precedes the comparison

2026-10-05. Starting develop: **8c25ff3b984cd08401b4491aa0876ff0129161e6**. This increment changes only the existing Simulator failure-diagnostic helper, its tests and this evidence checkpoint. Product Swift, the independent UIKit control, fixture signing, the full-App workflow and every UI assertion are unchanged. Main is not promoted; no phone or credentials requested. AUTO-02 / PAIR-01 is still open.

## Actual latest result

Run **37242839315**, attempt 1, job **111554802378**, completed FAILED at step 8. Compilation, signature inspection, Simulator bootstatus and the home screenshot passed. **`xcrun simctl install` timed out at its existing 120-second limit.** Product launch, document-source installation and all product/control UI were skipped. The independent comparison has no result; do not attribute this run to FileProvider -1005/-1012 or infer control success/failure.

Artifact **11318286484** matched SHA-256 **dc10213d482dbc643681f7c698bb2ef1ab03fafbe711bc9930a512411fb13048**. Its actual install log contains the single command and TIMEOUT. The smoke record has simulatorReady=true, installed=false, launched=false, smokePassed=false and failureType=TimeoutExpired. These flags mean no successful command result was observed, not proof that installd never performed a partial or late install.

The preparation log reports terminal bootstatus after 80 seconds. Generic service output includes initial container/registration work, but no retained target-specific installation completion. The combined service log originally had **637,606 bytes**; only **262,144 bytes** were retained, omitting **375,462 middle bytes**. It included many containermanagerd messages and did not query lsd directly. Root cause remains unknown: no assertion of insufficient RAM, a broken app signature or a proven deadlock is supported by these excerpts.

The actual read-only skill classifier was run with the live-checked run/job projection, exact source SHA and verified smoke JSON. Result: failed / install_launch, automaticRetryAllowed=false, productAccepted=false. Report SHA-256 **4b10b0db99b2afbf39295b91bb2b5c13bd4fa65169f52dcf8d0b2062bb2fad0e**. The current projections/report are in docs/simulator-ci. Earlier provider failures remain historical evidence; the comparison in 8c25ff3 was not exercised here.

## Narrow diagnostic correction

After a recorded installation failure, the existing failure step now performs three separate **read-only** observations before generic logs: get the exact product's app container, query installd/lsd registration events, and query events naming that exact product. They use the existing bounded capture (15 seconds and 256 KiB retained per command), with explicit exit/timeout/truncation metadata. This avoids mixing targeted installation evidence into thousands of generic container events.

Saved evidence must match the current job SHA, live owned device UUID, owner record and expected product identifier before these commands are constructed. Malformed, oversized, mismatched or prior-success evidence is rejected. Rejection is recorded without suppressing existing generic diagnostics. No new query runs for a UI-only failure. The bundle allowlist prevents predicate injection.

A container returned after timeout is **not** converted into installation success. The original smoke record is never written by these observations, the failed job stays failed, and no install/launch/reset/retry is issued. A missing container or a second query timeout remains evidence, not a guessed cause. This increment repairs an evidence gap, not the underlying installation timeout. The existing failure-only UIKit comparison and invalid-document acceptance stay intact.

## Local checks completed

- **8 new installation-diagnostic tests passed**: read-only command selection, failed-state preservation even when observation commands report success, exact SHA/UUID binding, invalid input/identifier refusal, malformed evidence fallback and original deadlines/assertions.
- **23 existing Simulator environment/signature/smoke tests passed**, including actual subprocess timeout/output capture and existing boot ordering.
- **16 Simulator skill tests passed**; its actual classifier also processed this current failure.
- The actual new selector was executed against the downloaded owner/smoke/device records and produced the three expected observation commands. No macOS command was executed locally; simctl responses in tests are scripted. Product Swift/core and the full integration suite were not rerun for this diagnostic-only change. No fresh native or UI success is claimed.
- Source artifact **11317283922** matched ZIP SHA-256 **35bc701d8e0384aacbc2a96a48b2d1cd1872e7dd2c1bf850a5c9e6a737facecf**, inner TAR **41a7e1d9fe6b6a1fe453615b66d46a0756bfa3d7ee8541bf587db6e2dde6ab30**, and recorded 8c25ff3 before editing. git diff --check passed. A direct clone was unavailable in the local runtime; the connector's verified source artifact was used instead.

## Next single verification

At most one new full-App run is justified by the previously missing installation observations; see next-run-decision.md. Do not increase the installation timeout, reset services or loop until green. If installation fails again, inspect container readback and focused logs and preserve truncation/timeout limits before proposing another run. If installation succeeds, continue the already-written original product/control comparison and retain its actual outcome, rather than concluding that the timeout was fixed by logging.

No new product feature, selected-file acceptance, Apple authentication, physical profile installation, locked-screen scheduling or expiry-crossing acceptance was completed here. Broader product scope remains PLAN_PROGRESS.md.
