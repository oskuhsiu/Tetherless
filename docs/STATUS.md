# Current product verification — renewal recovery and real document selection

2026-10-04. Product Swift: b67a36264dd0baddf69fe65cd156b6f3ced42e58. UI/environment extension: 1b14f75a349d04fdebbd17f42187a3a83b13be91. This follow-up fixes only the observed UI selector and records completed evidence; product Swift is unchanged. Develop only; main remains 4cfcc185cd529e07c212c3b310c0ee5162c19b2f. No physical device or credentials requested, and no complete-product or release-readiness claim.

## Product fixes actually tested

The engine/runtime retain earlier durable renewal results when later work is cancelled or persistence fails. Per-invocation capture preserves verified expiries for summaries/alarms without counting uncommitted work or suppressing errors. Pending mutations still reconcile before another write. The native backend consumes the exact final batch readback rather than repeating a full profile-store dump; final readback and cancellation checks remain mandatory.

Six scenario tests run the real coordinator with actual journal files and process locks and a scripted device: next-day manager/two-app renewal, no duplicate same-day renewal, cancellation after manager success, second-commit failure followed by reconciliation without duplicate writes, write-ahead failure and applied-but-unverified results. Three transport tests verify the exact returned post-apply snapshot, missing-extension refusal and cancellation during final readback. These are not real Apple/physical-device results.

## Current verification

- Local current baseline Debug: 296 passes. Modified product Debug: 305 passes in 40 suites. Local Release invocations timed out; the remaining orphaned compiler from that command was stopped, not counted as a completed run.
- macOS product core run 37187683409 completed successfully with both Debug and Release steps. The follow-up source archive from core run 37188333824 was also retained and checked.
- iOS Simulator core run 37187683404: 329 unique individual passes counted in the downloaded log, plus one explicit hardware Data Protection skip. All nine added scenario/readback cases passed; TEST SUCCEEDED recorded.
- Native current integration 1b14f75 run 37188333754: Debug and Release both compiled, linked, packaged and uploaded successfully.
- Local integration after restoring exact reviewed source preimages: 178 tests passed, no skips. The initially recorded 13 missing-input skips were resolved by restoring and hash-checking the retained auth/cache/IPA inputs and reconstructing the metadata preimage with the current pinned cache transform. Final checks were rerun after the selector fix.

## Actual UI execution and narrow correction

Current full-App run 37188333737 successfully allocated/booted its owned Simulator, compiled and signature-checked the app, installed/launched it and seeded only one invalid public plist. The real test completed both system-picker cancellations and navigated to On My iPhone. It then FAILED at TetherlessUITests.swift:151: the broad Any/firstMatch selector selected the presenting wizard's hidden StaticText named Tetherless instead of the visible document Cell named `Tetherless, 1 item`. Actual hierarchy includes both elements and confirms the correct cell exists. This is a test-selection failure before the invalid file was selected, not evidence that its rejection succeeded or failed.

The downloaded UI artifact 11298198553 matched SHA-256 aba8a046e2324be9657138b687d67939ee3a6a2cf1cf2b53df487263f77d280f. Actual log and full failure hierarchy were inspected. The original-file verification step was skipped after test failure; no preservation success is inferred from a seeded file.

The follow-up scopes only file/folder targets to document Cells, retaining the working location navigation and all hittability, rejection, consent, resume/recovery/cold-launch assertions. No coordinate taps, success fixtures or production hooks are added. Its complete UI execution still requires the next CI result; syntax/contract checks are not a passing UI claim.

The first b67a362 UI attempt failed before compilation because initial simctl listing exceeded 30 seconds. Only fresh-service initialization was given 90 seconds in 1b14f75; ordinary diagnosis and UI/action bounds remain unchanged. No reset/retry loop was introduced. That earlier failed attempt remains a failure, not a product assertion.

## Inspected current artifacts

- b67a362 source 11297776949: ZIP SHA-256 35e13ec3cac552a600d29dfa9348f7d65177c31b2730115ad472c0e7978acf0e, TAR 40de96ab6c18dbf95070377a514e78a119f6ee89d8b1963d7ee14ccf31635726; nine changed files match tested bytes.
- b67a362 Simulator 11298246283: ZIP SHA-256 09a0662537b475dd3129df1bb3195431bd22862dd33fc54cdaed8b44536991dd; actual individual results counted separately from the protection skip.
- 1b14f75 source 11297647354: ZIP a661d34240e188b8d57abadd16bf2ac820b3460a68915f9a449f5d865898b46c, TAR c829e282293ada3bc47a5bc0c7944212c69d2bcfa673cb2174457851e6af3f46; all six test/environment/checkpoint files match before this follow-up.
- 1b14f75 native Debug 11297893333: ZIP e0603e7f4e2099518c85cae67e42015003339e16f6d553252b1020100c451f3a. IPA a4ada7b67a14261dc7121286635a661a959fef13172a889a0f6e561833890be8 matches manifest/sourceCommit. Prepared RenewalEngine, ProfileBatch, RenewalRunCapture, NativeRenewalRuntime and NativeRenewalBackend match the tested source. The unsigned product still requires user signing and reports physical/unattended acceptance false.

## Continue from current code

Read the corrected document-cell UI run before declaring selected-file coverage complete. Continue remaining actual installer/first-sign/self-update and distribution requirements, not previous percentage estimates. All product changes and test corrections are saved independently. No real Apple login/provisioning, physical pairing/profile install, locked-screen scheduling or expiry crossing has been verified in this work.
