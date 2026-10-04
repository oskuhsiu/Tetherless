# Single-item checkpoint — document-source signature verification

Implementation: **2ae7ebdc9a143505f8664ef5b85a61fac9347f0d**. This last commit updates documentation only. The implementation changes the test-document source's build/signature checks and retained diagnostics, not Tetherless's product Swift, the source app's Swift/payload or any XCTest assertion. Development remains on develop; main is unpromoted. No iPhone or credentials requested. AUTO-02 / PAIR-01 invalid-document acceptance remains OPEN.

## Next standalone run

Full-App run **37220011794**, job **111488264234**, for 2ae7ebd started **2026-10-04T17:18:44Z**. At the single status check it was **in_progress**, conclusion null. No new native/UI pass is claimed. Read its final result in the next standalone verification turn; do not cancel, dispatch another, repeatedly poll or mix it with another large item.

First require the producer's actual signature inspection, successful launch and visible `fixture.documentReady`. Then require both existing cancellations, one semantic document-cell selection, real selection callback and dismissal, explicit invalid-file rejection, byte-identical source, incomplete pairing, consent-off and cold-relaunch/recovery checks. Intermediate static verification cannot close this acceptance.

## Actual prior failure and correction

Run **37207927236**, attempt 1, job **111452931419**, at 2ec7213 FAILED. Tetherless compiled, passed signature checks, booted, installed and launched. The producer compiled, passed ordinary codesign verification and installed, but XCTest failed at `TetherlessUITests.swift:13` in `documents.launch()` after 6.874 seconds. It never reached documentReady or the product picker assertions. The subsequent missing-file check does not prove product deletion: no document was created.

Original UI artifact **11305708426** matched SHA-256 `1af4797c77483280058ad1e47112111100cf0f05b93c429a139565507725babd`. The original xcresult contains the producer crash omitted by the older app-only retainer: **SIGKILL (Code Signature Invalid), CODESIGNING / 1 / Taskgated Invalid Signature**, parent launchd_sim. Decoded crash SHA-256 `fe150437df1f48436fd15ad32fc7cac9c0610ffe0b69e67690b703bc1f1ef9f8`. Full extraction identity and evidence are preserved in STATUS.md at 2ae7ebd and docs/simulator-ci/next-run-decision.md.

The helper applied the same iOS entitlements to the linked simulated section and host ad-hoc signature. The working Xcode-built product in this exact run instead used an empty host dictionary and separate simulated entitlements. 2ae7ebd follows that observed separation: retain simulated identity/get-task-allow in __TEXT, sign using a distinct empty host plist, preserve strict verification, and inspect both actual representations before installing. No product privileges or acceptance checks are disabled. Static evidence explicitly records runtimeLaunchObserved=false. The original signature rejection is confirmed; successful corrected launch still requires this new run.

The bounded retainer now also selects only the source-app crash names and its exact stdout prefix as separate fixture categories. Size limits and product callback tracing remain. An empty old retained manifest was not proof there was no crash. The read-only classifier/report still preserves the first UI-stage failure with symptom fixture-signature-denied, not a simulator boot failure; report SHA-256 `428cf183950960d63d22e9127b2c4e57abfe02e21b59375f1e97d8a8adfe0d2b`.

## Completed local evidence

- **42 focused integration tests passed**, including seven new signing/diagnostic cases, eight producer cases, actual Mach-O reader checks, document/preservation contracts and lifecycle/retention regressions.
- **16 Simulator skill tests passed**. The actual read-only classifier processed live-checked projections and downloaded smoke evidence.
- Real files and the existing production Mach-O reader were exercised; codesign responses were scripted, not actual macOS signatures or runtime acceptance. Workflow YAML, the unchanged producer's syntax check and git diff --check passed.
- One initial command referenced a nonexistent test module and failed; the correctly named combined 42-test run passed afterward. No failed invocation is counted as success. Product core and full integration suites were not rerun for this test-build-only item.
- Uploaded Integration tree **3494d9ce7dbcf8a8db6c5c8adea0b0fd0b98fa4b**, workflow tree **ac438973501d26d320a86d4c3870540b2900b1f5** and initial docs tree **8857912493823440a76f8000d4ef7f9bed50406e** exactly matched the locally tested/staged subtrees before publishing 2ae7ebd. Only this STATUS checkpoint changes afterward.

If the producer still fails, inspect its new actual signed-bundle evidence and retained crash, without resetting the simulator or retrying blindly. If it starts but provider resolution fails, the prior independent-source hypothesis remains refuted/unresolved. If selection arrives but dismissal/import fails, investigate that observed product boundary. No live Apple login, valid pairing, physical installation, locked-screen renewal or expiry crossing is claimed. Broader scope remains PLAN_PROGRESS.md; no other item was mixed into this turn.
