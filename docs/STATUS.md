# Current verification — isolated document exists, provider resolution still fails

2026-10-05 (Asia/Taipei). Starting develop: **c6e2b27f7531622f91f78138870261ed0d73494d**. This increment adds a failure-only UIKit comparison inside the existing Simulator document-source app and its XCTest. **No Tetherless production Swift, picker delegate, content-type policy, parser, storage, signing, renewal or existing acceptance assertion changes.** Main stays unpromoted. AUTO-02 / PAIR-01 invalid-document acceptance remains open; no phone or credentials requested.

## Verified result for 2ae7ebd

Full-App run **37220011794**, attempt **1**, job **111488264234**, is completed/failed. Product build/signature/boot/install/launch and source-app signature/installation succeeded. XCTest then actually launched the source, observed `fixture.documentReady`, and ran both product picker cancellations. This confirms the previous source-app signature correction worked on this configuration; static signing evidence alone was not used to infer launch.

The test selected the external source's real plist but failed at **TetherlessUITests.swift:69**: no import outcome in the unchanged ten-second deadline, picker still visible. One test failed in **65.513 seconds**. The independent postcheck succeeded: the original **241-byte** document's SHA-256 remains **8adc01ad4d6304deb1daf74335f9acc7891ed5ed442dd85c5a50a7e30b58b96b**. That proves preservation of the invalid test file, not successful import or preservation of an already installed valid pairing.

Downloaded artifact **11310038625** matches SHA-256 **c9ef4da729c008f252d164e285e9b9b482c50d07ed06bf3a8c7650b57b44d039**. Actual XCTest log, original-file manifest, signature report, lifecycle manifest, service logs and the post-selection screenshot were inspected. The screenshot shows the actual external source folder and invalid plist, not a blank launch screen.

At **17:28:49 UTC** the target's stdout again reports FileProvider **-1005**, resolver **-1012**, then no materialized URL for delegate delivery. The complete 4,760,014-byte callback scan has 23 events, no truncation, and no selectionReceived/importStarted for the third request. The source demonstrably exists outside the target being reinstalled. Therefore the prior source-isolation change did **not** resolve the defect; do not keep attributing this result solely to a file missing after target reinstallation. Root cause below the resolver is still unknown. No Simulator reset, selector rotation or type-policy relaxation is justified by this result.

The skill classifier executed on live-checked run/job projections and the verified smoke JSON: first failure `ui`, automaticRetryAllowed=false, productAccepted=false; report SHA-256 **8bd9c3a882c559c398886c913dc0c086704dc78be481c93d5091b58027b66753**. Projections/report are updated in docs/simulator-ci; previous attempts remain in Git history.

## One discriminating comparison, only after an already failed product attempt

The source app adds an independent **UIKit UIViewController / UIDocumentPickerDelegate** control. It uses system open-in-place selection (`asCopy: false`), property-list/XML types, an ordinary full-screen UIKit presentation, and its own retained delegate. It imports no product code and invokes no simulated delegate, parser or backend. The only reported result is a fixed callback category and whether a file URL was received; it does not claim pairing validity or read the selected contents.

XCTest first runs the original Tetherless path without warming the control. Only after the unchanged outcome deadline fails (or its picker remains visible) does it freeze that outcome, capture the product failure and launch the control in the separate source app. It performs one semantic file selection with bounded checks and retains an `independent-picker-control-result` attachment and screenshot. The original `XCTAssertTrue(outcomeAppeared)` / dismissal assertions still run against their **immutable pre-control values** and still fail. A successful control cannot make the product pass. The product is never relaunched or retried during this comparison.

This comparison separates a plain UIKit recipient from the full product's presentation/identity. It is NOT an exact identity-matched substitute: the control is in the source app and opens its own visible file, while Tetherless is a different recipient. Both failing strengthens a common provider/runtime hypothesis; control success only narrows recipient/presentation/cross-container differences. Neither alone proves a universal Simulator bug or closes product acceptance. The existing original-file postcheck still runs.

## Local checks for this increment

- **33 focused checks passed**, including **6 new comparison contracts**, existing source-app signing/Mach-O checks, real fixture IO, diagnostic retention, and production callback contracts.
- **16 Simulator skill tests passed**; the real CLI generated the current read-only report.
- Both changed Swift files passed frontend parsing. UIKit/XCTest typechecking and actual comparison execution require the next macOS CI; no such result is claimed.
- Product core and the full integration suite were not rerun because no production/core code changed. Do not advertise old counts as fresh executions.
- Current source artifact **11309682134** matched ZIP **ecdfc98135931ec1833c558663f2ae85189c81e980c94dd100aa6eecdbb7c76d**, inner TAR **0243abefc108e1ad9d561829e209616ae8b3899020e786da23f62b0edf064f14**, and the recorded c6e2b27 commit before editing.

## Next standalone verification

Inspect the single workflow for the commit containing this change. The original product acceptance must remain red if it fails, independently of control outcome. Read the comparison attachment, helper stdout and actual resolver errors before changing production presentation, permissions or runtime. If the product unexpectedly passes without invoking the comparison, require every original assertion and byte-preservation step before accepting that one route. If the comparison cannot run, report that diagnostic gap rather than infer the underlying cause.

Do not run another identical full workflow after a same-layer failure. This change's only justification is the new independent control observation; it is not another guessed tap or a claim to repair the provider. Broader plan items remain in PLAN_PROGRESS.md. No live Apple login, valid pairing, physical profile install, locked-screen renewal or expiry crossing acceptance is claimed.
