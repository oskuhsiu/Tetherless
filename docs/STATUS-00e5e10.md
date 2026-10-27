# Current checkpoint — reject ambiguous catalog imports without crashing

Updated 2026-10-03. Latest implementation: **59203681c2ee8a4780fec88c85dff669b2ce3fe9**. This follow-up changes only diagnostic retention and its tests/workflow, not the production Swift code or UI assertions. Development on `develop` only; no physical-device handoff or release promotion. The prior approximately 80% estimate refers to implementation and feasible non-device verification, not reliability.

## Diagnosed actual failure at 2eea8d1

Run 37082841722 failed its first UI assertion because the **app terminated**, not because the App Group remained inaccessible. The downloaded result ZIP matches Actions SHA-256 `57fdd5a805f69209d42941a8de655969627869366f410061370a7bac7ebc12dc`. The result's actual app stdout and crash report were inspected, not just the final XCTest assertion:

- App stdout records the shared App Group payload cache being used and `Started DatabaseManager`.
- It then fetches the remote default source and hits `MergePolicy.swift:221` with three `AppVersion` records sharing `(sourceID, appBundleID, version, buildVersion)` and no database object.
- The `assertionFailure` becomes a SIGTRAP. Its stack goes through `MergePolicy.resolveWhenDatabaseObjectUnavailable`, Core Data save and `AppManager.fetchSources`.
- The screen recording shows SpringBoard after termination. The earlier launch smoke did pass but did not cover this subsequent catalog fetch.

Thus the new reader achieved container/database startup in this run, exposing another defect. Previous failed runs remain failures. This evidence is neither device App Group acceptance nor real Apple login.

## Current coherent repair

- Validate the **entire inserted AppVersion graph** before saving a decoded source to its parent. All release channels are included. Composite keys are typed tuples; nil and empty builds are the same stored key, while the literal `nil` string is distinct.
- Reject duplicate apps and ambiguous versions instead of silently selecting a payload or deleting an arbitrary duplicate. This intentionally rejects snapshots with cross-channel versions the current database schema cannot represent distinctly.
- Roll back a rejected child import. Keep the previously saved catalog and installed-app records.
- Unknown context-level merge conflicts now throw a fixed, serializable error instead of trapping in Debug or silently falling through in Release.
- A failed parent save rolls back and reports failure; it no longer returns an unsaved context as a success for callers to save again.
- Export the actual app-only stdout/crash diagnostics from xcresult in CI, in addition to screenshots and the untouched full result. Do not infer a missing control means the app is still running.

All three native input hashes are checked before writing any patched file. The transformation was applied to the actual retained prepared sources. No production UI assertions, App Group gate, native authentication or renewal behavior were bypassed.

## Verification for 5920368

| Check | Observed result |
| --- | --- |
| Local Linux core Debug / Release | 194 tests passed each on completed runs |
| Local Python integration checks | 117 passed; workflow shell blocks also passed syntax checks |
| macOS core Debug / Release | 207 tests passed each; run 37086781254, actual log inspected |
| iOS Simulator core | 204 actual passes and 1 explicit hardware Data Protection skip; run 37086781196, downloaded log counted |
| Real SQLite/child-context regression | Passed on macOS Debug/Release and on iOS Simulator |
| Native iOS Debug / Release | Both compiled, linked, packaged and uploaded successfully; run 37086781269 |
| Whole App signature / install / launch | Passed in run 37086781219 |
| Complete setup/resume/reopen/consent/cold-relaunch UI | Passed: 1 real end-to-end XCTest, 0 failures, 119.652 seconds; overall job failed later in diagnostic retention |

The SQLite test calls the same production preflight against real inserted objects in a real child context. Three conflicting rows are rejected, rollback leaves the saved catalog intact, and a later valid import commits and is independently read back. It uses a minimal model with the production uniqueness keys, not the complete upstream decoder/model or a real Apple service. The complete-app run supplies the separate production integration evidence.

The first local Release invocation timed out and is not counted as passing; a completed rerun passed. The unnecessary-try warning in the new Darwin test and an inherited unused-result warning remain. No warning-free claim. Data Protection remains explicitly unverified on hardware.

## Actual whole-app result and retention follow-up

The real UI test in run **37086781219** finished with **TEST SUCCEEDED**: welcome, cancelling the actual pairing picker, mid-wizard termination/relaunch, missing pairing/account gates, consent remaining off, incomplete review, navigation to Settings/My Apps, reopening setup, and final cold relaunch all passed. Startup errors are still asserted absent. This is one complete navigation test on an iPhone SE (3rd generation), iOS 26.2 Simulator with Xcode 26.3, not the entire product/OS matrix.

The downloaded artifact outer SHA-256 matches `4d86ff5250ab369a469368339af690e5934252e083bb7e1ebad25b3ffd016812`. The actual test log and seven exported screenshot entries were inspected. The final `06-relaunch-database-ready` and `04-review-incomplete` images were viewed: the former shows Auto Renewal with consent off, the latter explicitly shows missing setup rather than fabricated success. The app stdout records three successful database startups. No live Apple login or successful signing was supplied by the test.

**The workflow itself remains failed**, because the subsequent diagnostic copy rejected the 5,454,641-byte stdout as larger than its 2 MiB limit. The export command worked, and the original xcresult, screenshots and passing UI test log were still uploaded. This is not a failed product assertion and must not be relabelled as a green workflow.

The narrow follow-up replaces the inline copier with `retain_ui_diagnostics.py`. Oversized files keep separate bounded head/tail parts with exact offsets, original/omitted lengths and `truncated: true` in a manifest; the original xcresult is unchanged. The limit is still 2 MiB retained per file and 20 files, with file-type/link/change checks. IO and structural errors still fail rather than being ignored, and the manifest never infers UI success. Local Python checks: **122 passed**. The helper was also run on the actual extracted 5,454,641-byte stdout: it retained 1,048,576-byte head and tail and explicitly recorded the 3,357,489 omitted bytes. Native execution of this follow-up export still requires its next CI run; it changes no product source.

## Inspected exact-source and packaged evidence

- Source artifact outer SHA-256: `1d5e2ecb8c8093198c7402bde428bd9bd6f3683cb574b82f093fdbbeb28ac545`; inner TAR: `25b2f7fb62c53edbc4c940b04d7b909a60d14eda968a5a41c7640a8b887fe6c5`. Recorded implementation SHA and all **124 files** matched the checked local implementation before this retention-only follow-up.
- Simulator core artifact: `0db1c5cf8f8a73af5f20e20a8313ebde4aa7ca0b87d853a3bbd4c1d1ddd0eb04`; its 204 passing records were counted separately from the skip.
- Release artifact outer SHA-256: `d605fe9fc83777594d226467492123c2e95d1abd36430e52a1e8d72c8d8e8c50`. Actual unsigned IPA SHA-256 `40578e402d824baa0e2bb775e9b9c450578b98d5709a64761bb53b533bd8bff1` matches the manifest.
- Actual Release Info.plist: `org.tetherless.Tetherless`, version `0.1.0`, build `0100`. No `.p12`, `.p8`, `.key` or `.mobileprovision` resources were found by filename inspection. This is not a claim of exhaustive secret detection.
- Prepared MergePolicy, FetchSourceOperation and AppManager exactly match the hash-checked native transformations. The copied CatalogImportSafety is byte-identical to the tested core file. The actual Release build log records BUILD SUCCEEDED; the manifest still requires user signing and reports physical/unattended validation false.

Exact runs: https://github.com/oskuhsiu/Tetherless/actions/runs/37086781254 (macOS core), https://github.com/oskuhsiu/Tetherless/actions/runs/37086781196 (Simulator core), https://github.com/oskuhsiu/Tetherless/actions/runs/37086781269 (native builds), https://github.com/oskuhsiu/Tetherless/actions/runs/37086781219 (actual app/UI).

## Next actions

1. Confirm the follow-up diagnostic step with CI. The complete navigation baseline at 5920368 is now passing; do not continue to diagnose the previously resolved App Group and catalog traps as current failures without new evidence.
2. Implement dedicated certificate recovery controls with a genuine check-only path. Existing `allowNew: false` can submit a saved prepared request, so it must not be used as a read-only check. Preserve uncertain keys, account/Team ownership and explicit recovery decisions.
3. Complete remaining Anisette, pairing callback and logging lifecycle review, aggregate input/resource reservations, and crash-abandoned staging cleanup. The catalog count check is not a complete memory/body-size budget; inherited verbose diagnostics remain a separate review item.
4. Complete remaining first-signing/self-update and supported-configuration coverage, branding and dependency/distribution review before consolidated physical acceptance.

No physical pairing, real signing/profile install, locked-screen unattended renewal or original-expiry crossing has been verified. Historical failures remain failures. No live credentials were used in CI. Main remains unpromoted.
