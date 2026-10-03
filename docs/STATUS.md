# Current checkpoint — reject ambiguous catalog imports without crashing

Updated 2026-10-03. Development on `develop` only, approximately 80% toward feature-complete implementation and feasible non-device verification. No phone requested and no release promotion.

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

## Checks before commit

- Python integration checks: 117 passed after the complete change, including diagnostic-export workflow syntax checks.
- Linux core Debug: 194 tests passed.
- Linux core Release: 194 tests passed on a completed rerun. The first build/test invocation hit the local command timeout and is not counted as passing.
- Added a Darwin-only real SQLite/child-context test using the production preflight: three conflicting records reject, rollback leaves the saved catalog intact, and a following valid import can save and be independently read back. It requires macOS/iOS CI, not Linux.
- Current native and real UI results require fresh CI for this implementation. Earlier green builds do not validate this repair.

The verified source archive for 2eea8d1 matched outer SHA-256 `ed82b7386b6a76caf22eec1db4461ea090cc1d400b66c6936ac10567a0561529` and inner TAR SHA-256 `438f1054cccef94b1d3bda3bc2bbd6938ac671bdbc0ce05fda2a3130f59ea02e`; it is the local code baseline. There were no previous uncommitted edits in this working copy.

## Next actions

1. Inspect this repair's native builds, real SQLite test, and complete UI flow through final cold relaunch. Check app stdout if a screen disappears. Preserve real failures; do not merely rerun until green.
2. Finish certificate uncertain-state recovery controls, Anisette/pairing/log lifecycle, resource reservation and abandoned staging cleanup.
3. Finish first-signing/self-update integration, supported-configuration coverage and distribution/branding before consolidated physical acceptance.

No physical pairing, real signing/profile install, locked-screen unattended renewal or original-expiry crossing has been verified. Historical architecture/evidence remain in Git history.
