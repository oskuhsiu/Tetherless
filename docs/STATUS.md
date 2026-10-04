# Current checkpoint — reusable Simulator CI skill, no blind reruns

2026-10-04. Starting develop: **9101523a11b915223561933e41dac9fccd9cacee**. Latest production instrumentation remains **20faee940c802acb1cd2efc18e921ea3c4598636**; renewal core remains b67a362. This increment adds a repository-discoverable skill, read-only classifier/tests, exact stage map and observed evidence. It changes no production Swift, UI assertions, existing simulator scripts or existing iOS workflow.

## Read first

`.agents/skills/ios-simulator-ci/SKILL.md` now governs Simulator/CI diagnosis. `docs/SIMULATOR_CI.md` contains the Tetherless adapters and current evidence. AGENTS.md requires reading them before editing/rerunning Simulator work. One long item per turn remains mandatory. Main is not promoted. No iPhone or secrets requested.

## Latest result actually inspected

Run **37195486462**, attempt 1, job **111416356929**, at **20faee9** is FAILED, not pending. Build/signature/boot/install/launch passed. Step 11 failed in the actual XCTest: no import outcome, picker still visible. Original-file verification was skipped. All subsequent evidence and owned-device cleanup completed. This is a UI-path failure, not a Simulator boot failure.

Downloaded artifact **11300687557** SHA-256: `24d2445d0453ea7876d931098a47437deefa0b8dd6f08af697180e082c3baecd`. The smoke JSON, XCTest failure log and complete fixed-event trace were inspected. Third picker request records creation/plist acceptance, but no selection callback or import-start event in a complete 4,423,416-byte scan. No root cause inferred; no valid/invalid-file import acceptance claimed. The two cancellation traces have dismissal-before-delegate ordering, which is an observation to inspect, not proof that it caused the third selection failure.

## Skill implementation and verification

- Reusable skill separates environment, preparation, build, signature, boot, install/launch, fixture, UI, data postcheck, evidence and cleanup failures.
- Actual Python classifier consumes raw REST or connector-wrapped JSON, binds run/job/source identity, rejects mixed evidence, preserves first failure despite successful cleanup, distinguishes pending/cancelled, and flags repeated stage/symptom fingerprints across changed commits.
- It is read-only, has no network/simctl/GitHub mutation, never authorizes automatic retries and never equates report generation with test/product acceptance. Repository step names/incidents are not hard-coded into the generic skill.
- **16 helper tests passed locally**, including real CLI file output/no-overwrite checks. Current live job projection plus actual downloaded smoke JSON produces firstFailureStage=ui and automaticRetryAllowed=false. A lightweight Ubuntu skill-check workflow is added; its remote result is not inferred from local tests.
- No new Xcode/Simulator run was requested for this skill-only work. The failing product UI remains open. This does not claim to make GitHub infrastructure failure-free or install a ChatGPT-wide plugin.

## Exact next product item

Use the skill and its decision record to isolate actual document activation/delegate/provider behavior in the current version. Preserve two cancellations, single semantic cell tap, original outcome deadline, explicit refusal, original-file verification, pairing incomplete, consent off and cold-relaunch checks. Do not rotate tap targets, increase waits, reset simulators or change type restrictions without evidence. Save one change before one planned long verification; do not combine it with installer/supply-chain work.

Original remaining product scope stays in PLAN_PROGRESS.md. Prior checkpoint at 9101523 retains the previous test-target failure and detailed history; it is not the current run outcome. No whole-product, live Apple, physical installation, locked-screen renewal or expiry crossing acceptance is claimed here.
