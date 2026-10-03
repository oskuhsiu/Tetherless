# Current checkpoint — database readiness and explicit App Group diagnostics

Updated 2026-10-03. Development integration, approximately 80% toward feature-complete implementation plus feasible non-device verification. Not a release candidate or a request for a phone. Work stays on `develop`; `main` remains unpromoted.

## Implemented startup boundary

`6ed95b0` introduced LaunchReadiness. Every transition to the main interface requires both a successful database startup and wizard dismissal, in either completion order, and happens only once. Completing the wizard no longer bypasses a failed database start. No account or renewal permission is inferred from navigation. It also introduced reading the main Simulator executable's linked iOS entitlements rather than its distinct macOS host signature. Device and other-bundle parsing remain unchanged.

`6dac8e7` is documentation-only: CERTIFICATE_STORAGE now describes the previously implemented durable CSR/key transaction. It explicitly warns that `allowNew: false` can still submit an existing prepared request; it is not a check-only API. Dedicated recovery controls and persistently uncertain-request decisions remain unfinished.

## Actual complete-app result at 6ed95b0

Run **37080604148** passed boot/screen readiness, whole-app compilation, actual signature/linked-identity inspection, installation and initial launch. Its real UI test **failed** at `TetherlessUITests.swift:63`, when the wizard could not enter the main interface. It did not complete final cold-relaunch acceptance.

Inspection of the full log, not only its last assertion, shows **App Group Container Inaccessible** during both initial and resumed setup. XCTest's default interruption handler pressed Retry three times and hid that alert before the final hierarchy was captured. The new startup gate then correctly refused to enter the main interface. This is not a scrolling failure, not a passing UI flow and not proof that group access was repaired.

Downloaded UI artifact SHA-256 matched `9800dd68b140ffb3a396c79b41919e892f785182122ec7f6f2575d3cf288a92a`. Its log, signing evidence and failure hierarchy `8B7DF74D-7CC8-46EC-99F0-9C99FCF183D7.txt` were read. The build log contains the expected group in the simulated entitlement payload, but that is not proof that the running app resolved it or obtained its container. The exact runtime failure stage was not exposed by this revision.

## Narrow follow-up in this checkpoint

The Simulator reader no longer assumes loaded-image index zero is the app. It matches the actual canonical main executable URL in a bounded image table, checks its executable header and reads that image's linked entitlement section. The immutable result includes only a predefined stage. It does not scan untrusted IPA files, invent a group, repair a signature or select a private database directory.

The existing missing-App-Group error now adds an allowlisted category: executable not found, invalid/missing linked payload, absent groups, no matching group, or matching group with unavailable container. No path, group identifier, account, key or token is added. This separates the next diagnosis rather than claiming the previous cause is proven.

The actual UI test explicitly rejects the startup error before the first action, after resuming setup and before finishing the wizard. XCTest may not silently turn a fatal startup error into Retry interactions and later apparent navigation progress. Existing navigation, consent and final relaunch assertions remain intact.

All three native transformation inputs are hash-locked and validated before any write. The current transforms were executed on exact retained source, and Swift frontend syntax checks passed. Runtime entitlement reading still requires the new native/UI run.

## Verification scope

| Check | Observed result |
| --- | --- |
| Current local Linux core Debug / Release | 186 tests passed each; no core code changed after 6ed95b0 |
| Current Python integration contracts | 112 passed, including image selection, safe stage reporting and early UI alert assertions |
| 6ed95b0 macOS core | Passed, run 37080604108; exact test count not inferred |
| 6ed95b0 Simulator core | 195 individual passes and one explicit hardware Data Protection skip, run 37080604233 |
| 6ed95b0 native Debug / Release | Both compiled, linked, packaged and uploaded, run 37080604217 |
| 6ed95b0 full UI | Failed as detailed above; not accepted |
| Follow-up native and real UI | Requires fresh CI for this checkpoint; prior builds do not validate the new reader or alert diagnostics |

Four LaunchReadiness tests exercise both completion orders, failure/retry, prior dismissal and duplicate callbacks. Local syntax/contract tests are not Xcode typechecking or iOS execution. A first local test macro failure was corrected before the recorded final Debug/Release results; no assertions were removed.

## Artifact identity already verified at 6ed95b0

The CI source archive's recorded commit, outer digest `2bf120bbe76fa60cb9af005ebae6723da065d59fa9a7ea34af73c48437d0daec` and inner TAR digest `66a57b1b6e68952c9312766f7fd73f7d6dcba8aacb6354145232e1f925d6f6ca` matched. All 120 files matched the implementation before the later follow-up edits.

Simulator core artifact digest: `9860971360d7fffb68b753e6cadcf017ef4bc16cfb9c468bde4da77824330acd`. Its 195 passing records were inspected separately from the one skipped test.

Release outer digest: `8e0a0150e4d333889213a47f0fa7119793ef6728e63cef15b4dbe3aca7a40969`. Actual IPA digest `18f2c690e1d568c4c0a3a3ea638ebbc784a730d60f10c14e432d9484997ba237` matched the manifest. Bundle ID org.tetherless.Tetherless, version 0.1.0/build 0100. No .p12/.p8/.key/.mobileprovision filenames were present. Prepared launch, Bundle extension and LaunchReadiness bytes matched. An existing unnecessary-await warning remains in NativeManagerUpdateControls; no warning-free claim.

## Next actions

1. Read the new native and full UI result for this follow-up commit. On failure, inspect the early startup alert's `[group/<category>]` and actual artifact, not just the last tab assertion. Do not weaken the shared-database gate or allow a sandbox fallback.
2. Complete the full setup/resume/reopen/consent/cold-relaunch flow. A launch smoke, missing-account check or successful compilation alone is insufficient.
3. Finish certificate uncertain-state recovery controls, Anisette/pairing/log lifecycle, aggregate resource reservation and abandoned staging cleanup, then remaining first-sign/self-update and supported-configuration coverage.
4. Finish branding and dependency/distribution review before one consolidated physical acceptance.

No live Apple authentication, real profile installation, physical pairing, locked-screen unattended renewal or expiry crossing was tested. Earlier failures remain failures in Git history. No uncommitted feature batch is needed to resume.
