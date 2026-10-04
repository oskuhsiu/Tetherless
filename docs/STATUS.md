# Single-item checkpoint — repair the document-source Simulator signature

Starting develop: **2ec72137dd76d8d63b44961d561be39fff61fb83**. This increment changes only the test-document producer's build/signature checks and retained diagnostics. Product Swift, the producer's Swift/payload, and every existing XCTest assertion are unchanged. Work stays on develop, main unpromoted. AUTO-02 / PAIR-01 invalid-document acceptance remains OPEN. No iPhone or credentials requested.

## Actual result, not the previous selection failure

Run **37207927236**, attempt **1**, job **111452931419**, finished FAILED. Tetherless compilation, signing inspection, boot, installation and initial launch passed. The document-source app compiled, verified with codesign and installed. The XCTest then failed at **TetherlessUITests.swift:13**, on `documents.launch()`, after **6.874 seconds**. It never reached `fixture.documentReady` or the product's picker/cancellation/import assertions. The original-file check also failed because the source had not created its document; this is not evidence that Tetherless deleted a file.

The read-only skill classifier ran against live-checked run/job projections and actual smoke evidence: firstFailureStage=ui, symptom=fixture-signature-denied, automaticRetryAllowed=false, productAccepted=false. Report SHA-256: `428cf183950960d63d22e9127b2c4e57abfe02e21b59375f1e97d8a8adfe0d2b`. Current projections/report replace the previous incident's files in docs/simulator-ci; earlier records remain in Git history.

## New evidence and targeted correction

The downloaded UI artifact **11305708426** matched SHA-256 `1af4797c77483280058ad1e47112111100cf0f05b93c429a139565507725babd`. The actual XCTest failure, helper build command, system logs and original xcresult were inspected. The existing diagnostic filter excluded helper crashes; its empty retained manifest did not mean there was no crash.

A bounded zstd extraction of the original xcresult payload `data.0~A3fIgqb71vwDARRY3BVLHN9UFGGCCCzuCTqHRVZ2fEHD_urhAmjZJw0K2rU5mWDG5iiUpwU2I8XksYvzUssxrQ==` recovered DocumentFixture's crash report. Decoded bytes SHA-256: `fe150437df1f48436fd15ad32fc7cac9c0610ffe0b69e67690b703bc1f1ef9f8`. It records `SIGKILL (Code Signature Invalid)`, termination namespace **CODESIGNING**, code **1**, indicator **Taskgated Invalid Signature**, parent launchd_sim. That identifies the startup rejection; it is not a new file-provider or pairing-parser result. No raw crash identifiers or host paths are copied into this document.

The helper build incorrectly applied the same iOS entitlement plist to both the linked simulated section and the host ad-hoc signature. In this very run, the working Xcode-built Tetherless has an empty host entitlement dictionary (`native-simulator-build.log` lines 8736–8744) and separate simulated entitlements at link time. The correction matches that separation: preserve the helper's simulated identity/get-task-allow section, but sign with a distinct empty host entitlement file and the observed Xcode timestamp/DER options. No product entitlement, signing check, shared group, sandbox permission or UI condition is disabled.

Before installation, inspect the actual helper bundle: strict codesign verification, an empty host entitlement dictionary, an iOS Simulator Mach-O platform and exactly the expected linked simulated identity. Reuse the existing bounded Mach-O reader rather than adding a second parser. Save `native-document-fixture-signing.json`, explicitly runtimeLaunchObserved=false. Successful static verification still does not establish successful launch.

The existing bounded diagnostic retainer now includes only DocumentFixture crash names and that exact source-app stdout prefix as separate fixture categories. The original xcresult is still retained; existing size limits and product callback tracing stay unchanged. A new failure should no longer hide the helper crash behind an empty app-only summary.

## Fast checks actually completed

- **42 focused integration tests passed**, including 7 new host/simulated signing and fixture-diagnostic regressions, the 8 existing producer tests, existing Mach-O checks, document selection/preservation contracts and lifecycle/diagnostic checks.
- **16 Simulator skill tests passed**. The actual read-only classifier produced the current report above.
- Tests parsed generated on-disk Mach-O bytes using the production inspector and exercised real temporary-file retention. macOS codesign responses were scripted; these are not real native signatures or UIKit execution. Unchanged producer Swift passed its existing frontend syntax check. Workflow YAML and `git diff --check` passed.
- An initial adjacent-test invocation used a nonexistent module name and failed to load it; the correctly named combined 42-test invocation above subsequently passed. That failed invocation is not counted as success.
- The current source artifact **11305936118** matched ZIP SHA-256 `0df8f8fafeea6556ed7a0993194f1effcc805b0a35c6f0cb8a59a47a5ebf9d1f`, inner TAR `22932e7e25aaad551292d837da7ce1a70f046ccafd1f6ac8230ec9ebc727d79e` and recorded source commit 2ec7213 before editing. No old native/UI success is substituted for this correction.

## Next standalone verification

One full-App workflow may run for this saved correction, under the unchanged runner/Xcode/runtime selection and same concrete destination. First require the helper's actual signature inspection, launch and documentReady UI. Then require the existing two cancellations, real single file selection, callback/dismissal, visible rejection, byte-identical source, incomplete pairing, consent-off and cold-relaunch/recovery assertions. No retry, longer wait, new tap target or fake delegate response is introduced.

The earlier independent-source/materialization hypothesis has not yet been exercised, because the helper failed first. Even if this signature correction lets it run, do not declare that earlier issue fixed until the original full acceptance passes. Save the new run ID once; pending native/UI work is the next standalone item, not a reason to keep polling or add another feature this turn.
