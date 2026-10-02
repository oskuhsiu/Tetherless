# Current checkpoint — setup read verified; compact-screen UI traversal

Development integration only, approximately 80% toward complete implementation and feasible non-device verification. No physical-device handoff yet. Current product code is **7dbaac4a3360e351ed65aca2cfc199f0a6ed73a1**. This follow-up changes only UI-test traversal, its source-contract check and this checkpoint; it does not alter production code or weaken setup/consent assertions.

## Actual UI result, no longer pending

Whole-app run **37031170226** at `7dbaac4` passed Simulator boot/screen readiness, compilation, strict signature and linked simulated entitlement inspection, installation and initial launch. The real UI test then passed its earlier steps: first-launch welcome, cancelling the real pairing picker, termination/relaunch into the pairing step, missing-pairing and missing-account gates, off-by-default consent, the actual incomplete-review assertion, back navigation and entering the real Auto Renewal tab.

The old review-page `Setup status could not be read` error did not recur in this execution. The viewed review screenshot explicitly shows `Setup is not finished` with pairing/account/signing key missing. This is evidence for this fresh Simulator run, not an isolated proof of the previous error's cause or live Apple sign-in.

The workflow still **failed**, later at `TetherlessUITests.swift:66`: the test waited for `renewal.openSetup` without scrolling. Its retained accessibility hierarchy shows Auto Renewal selected, the Form at 0% of five scroll pages, and Continue setup starting at y=624.5 on the 375x667 SE display; the requested next row was not materialized. This is not another signing or readiness failure.

The downloaded UI artifact SHA-256 matched `939287f9246d7deed787347d1230a2b0bd15ac48a79c57c93a67acac1ad17831`. The log, exported screenshot and full failure hierarchy were inspected. The complete test is not counted as passing because its early assertions passed.

## Narrow traversal correction

Auto Renewal test actions now reveal their exact element by bounded swipes inside the actual Form collection view before requiring it to exist and be hittable. Both scroll directions are bounded for tab-return positions. The helper first verifies the selected tab/navigation screen; failure captures a screenshot and fails the original assertion. No coordinate taps, fake backend/account state, removed assertion or product signing changes.

Local Python integration checks: **103 passed**. `swiftc -frontend -parse` accepted the updated UI test's syntax; this is NOT an XCUITest typecheck or execution. The corrected traversal needs its new real UI run.

## Verified product baseline, unchanged by traversal correction

| Check | Observed result at 7dbaac4 |
| --- | --- |
| Local Linux Swift Debug / Release | 182 tests passed each |
| macOS core | Passed, run 37031170064; exact count not inferred |
| iOS Simulator core | 191 actual passing records plus 1 explicit hardware Data Protection skip, run 37031170023 |
| Native iOS Debug / Release | Both compiled, linked, packaged and uploaded, run 37031170188 |
| Whole-app smoke/signature | Passed, run 37031170226 |
| Complete UI navigation | Failed at the offscreen-control lookup described above |

The exact source artifact (116 files), current Release IPA/manifest hashes and prepared source matches were inspected and recorded in the previous `48bdb222c2480b9f60aa61c05b8759eb853f18bc` checkpoint. The unsigned IPA still requires user signing and contains no live account, signing key or pairing record. Builds and synthetic tests do not prove physical installation or locked-screen renewal.

## Resume next

1. Inspect the fresh run for this test-only correction. Require the remaining actual Settings/library routes, reopening the wizard, retained consent and final relaunch assertions. Do not treat the earlier passed review page as a complete suite pass.
2. Finish remaining certificate uncertain-state recovery decisions, Anisette/pairing/log lifecycle, aggregate resource reservation and crash-abandoned staging cleanup.
3. Finish remaining first-signing/self-update integration, supported-configuration UI coverage, branding and dependency/distribution checks before consolidated physical acceptance.

Evidence: https://github.com/oskuhsiu/Tetherless/actions/runs/37031170226 (real UI); https://github.com/oskuhsiu/Tetherless/actions/runs/37031170188 (native builds); https://github.com/oskuhsiu/Tetherless/actions/runs/37031170064 (macOS core); https://github.com/oskuhsiu/Tetherless/actions/runs/37031170023 (Simulator core).

All changes remain on develop. main remains unpromoted. No live Apple authentication, real profile installation, physical pairing, unattended locked-screen renewal or original-expiry crossing was tested.
