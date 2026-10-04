# Single-item checkpoint — instrument actual pairing selection and dismissal

2026-10-04. Implementation: **20faee940c802acb1cd2efc18e921ea3c4598636**. This last update changes documentation only. The implementation removes the disproven preview-image test target and adds fixed lifecycle diagnostics to the real picker/wizard. Renewal, parsing, storage and authorization behavior remain unchanged. Work stays on develop; main is unpromoted. AUTO-02 / PAIR-01 invalid-document acceptance is still OPEN.

## Next standalone verification

Full-App run **37195486462**, job **111416356929**, started 2026-10-04T10:28:47Z for 20faee9. At the single status check it was **in_progress**, conclusion null. No native/UI pass is claimed for this new instrumentation. Read its actual result in the next verification turn rather than repeatedly waiting or adding another large item. The entire uploaded Integration subtree `f6981086cb9b96f9f59ef1a5299ab3785e35195d` matched the locally tested tree exactly before publishing the implementation.

## Result inspected this turn

Full-App run **37191398887**, job **111404163196**, at c4b3f90 is FAILED. Installation, launch, fixture seed and both real system cancellations succeeded. The test reached the correct document cell, then failed at **TetherlessUITests.swift:171** because its Image child was **not hittable**. The preview tap was never executed. This is a disproven test-target hypothesis, not an observed parser rejection or dismissal failure. Original-file verification was skipped and is not accepted.

Downloaded artifact **11299044027** matched SHA-256 `62a665282418c864c5e9d66f642543c40ec9babe0f74016ec6336fdcdac22f39`. The actual native-ui.log, issue description D4FFA467-296D-4BBB-84E6-88C691AAB52C.txt, system-service logs and a late screen-recording frame were inspected. The frame shows the Files picker with the fixture visible. File-provider service logs include container lookup/preparation errors, but these do not establish a causal explanation for this test failure. Do not claim the new invalid-document route is accepted.

## Narrow change

Use the existing exact document Cell again, retaining enabled/hittable checks and one tap. Do not target decorative descendants, double-tap, increase deadlines, change content types or add a fallback. Both cancellations, the original ten-second outcome deadline, actual picker dismissal, explicit error, unchanged incomplete pairing/consent, recovery and cold-relaunch assertions remain.

The real native picker/wizard now emit only a fixed enum marker at request start, creation, plist-type policy classification, selection/cancellation callbacks, result delivery, invalidation, accepted/ignored resolution, cover dismissal, request-bound dismissal, and import start/success/failure. No event API accepts a filename, URL, raw error, request/account/device identifier or arbitrary string. Logging observes the same control flow; the original error is rethrown and state guards are unchanged.

The diagnostic manifest retains these exact whole-line markers from the ORIGINAL exported stdout, even if the existing head/tail excerpts omit the middle. Its scan is bounded to 32 MiB per selected stdout and at most 256 retained events, with scanned bytes/completeness and event truncation recorded. Unknown names, trailing payloads, partial lines and suffixes of oversized lines are ignored; no UI result is inferred. Existing full xcresult and raw excerpt bounds are unchanged. An empty/incomplete trace is not proof that a callback never ran.

## Local verification

**22 focused tests passed:** six lifecycle/export tests, five existing native-picker contracts, six fixture/activation contracts and five diagnostic-retention regressions. The real fixed-message Swift logger was compiled and executed in both -Onone and -O with Swift 6; output exactly matched the permitted enum events. Export tests used real temporary files, including events in the omitted middle, synthetic secret-bearing lines, oversized lines and explicit scan/event caps. Source contracts preserve delegate clearing, dismissal-before-import and the original throw. Native picker/onboarding and changed XCTest sources also passed frontend syntax parsing.

One initial new source-contract regex wrongly consumed a later line; it was replaced with explicit extraction of record-call arguments and the full focused set reran successfully. No claim of UIKit typechecking or XCUITest execution follows from these local tests. Unchanged core and the full integration suite were not rerun in this single-item turn. The next native/full-App run is required.

The source baseline artifact **11299321500** matched outer SHA-256 `4339049ee69a96387520f9eb2cde474441a8ada49b270d7e724e0b9639091b5f`, inner TAR `e052419eb76dbc1a92a43a10446fe850243ca29e2f4c80e508d5c94644c538b4` and recorded c4b3f90. Its parent-to-current b08eaca follow-up is documentation-only.

## Acceptance and diagnosis

Require the unchanged invalid-file rejection and original-file-preservation checks. Inspect `native-ui-diagnostics/manifest.json` / `pairingLifecycle` alongside the actual XCTest log:

- No selection marker after a confirmed single cell tap: inspect native picker activation/type/provider behavior; do not rotate tap guesses.
- Selection/result delivery but no accepted resolution: inspect coordinator/request lifetime.
- Accepted resolution without bound dismissal: inspect the real presentation completion/request capture.
- Import start without completion: inspect coordinated file access; importFailed with a dismissed picker must still satisfy the UI error and original-file checks.

Markers alone cannot pass acceptance. The original sixteen-task inventory remains PLAN_PROGRESS.md; no other task is claimed complete. No live Apple account, valid pairing record, physical profile install, locked-screen scheduling or expiry crossing was exercised.
