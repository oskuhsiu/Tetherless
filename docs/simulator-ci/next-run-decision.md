# One-run decision: isolate the real file-provider source

- Plan item: AUTO-02 / PAIR-01 invalid-document import. No other long item this turn.
- Starting branch/SHA: develop, `8b7b02bf8011bc3854c49cb1b9072e3ddab78fe2`.
- Observed run: `37195486462`, attempt 1, job `111416356929`, product instrumentation `20faee940c802acb1cd2efc18e921ea3c4598636`.
- Read-only classifier executed locally with the checked run/job projection and downloaded smoke artifact: firstFailureStage=ui, failureFingerprint=`78ee90c7035f5d63724529ad2afee4152e02db2a06122986b2dc2bf2829306f3`, reportSHA256=`7b0a0b244549650fa2dc5f1dbc986c2dad3845de7ec9d2a32279e8985cb23992`. No boot, install or launch failure; no automatic retry permission.

## Newly inspected evidence, not another tap hypothesis

UI artifact 11300687557 matches SHA-256 `24d2445d0453ea7876d931098a47437deefa0b8dd6f08af697180e082c3baecd`. At 10:40:36, immediately after the recorded single document-cell tap, `native-ui-diagnostics/00-stdout-1.txt` contains DocumentManager's bookmark resolution failure: NSFileProviderErrorDomain -1005, underlying NSFileProviderResolverErrorDomain -1012. It then reports an empty document-URL array because the selected item could not be prepared/materialized. No selectionReceived/importStarted event appears in the complete trace. The actual screenshot shows a loaded picker and the 241-byte fixture, not a blank Simulator.

The workflow currently writes the fixture from host Python into the target app's container before `xcodebuild test`. In the same artifact, installd subsequently patches/re-registers that target, and the test launches it again. The earlier fixture manifest has no post-install materialization evidence; its postcheck was skipped after UI failure. Seeing the cell/thumbnail did not prove a usable provider bookmark.

**Confirmed observation:** document-provider URL materialization failed before delivery to our delegate. **Unconfirmed hypothesis:** using a host-seeded file inside the target being reinstalled/re-registered is an invalid or unstable fixture source. It is not proved that app reinstall is the sole cause, or that every user document has this problem.

## One discriminating change

Use a tiny independent Simulator-only app as an ordinary external document source. It publishes the exact same invalid public plist from inside its own container with NSFileCoordinator, after the test runner is active; XCTest first requires its real ready UI and then terminates that source app. It owns no account/Keychain/App Group and is not bundled into Tetherless. The target app is no longer seeded. This is a minimal producer/consumer isolation, not a custom file provider extension, fake import/delegate result or additional user-facing requirement.

The product, content types, asCopy=false, picker presentation/delegate, parser/storage, one semantic file-cell tap, ten-second outcome deadline, both cancellations, explicit rejection, consent-off and cold-launch assertions stay unchanged. Only the source folder is the distinct fixture app. The unchanged 241-byte payload digest remains `8adc01ad4d6304deb1daf74335f9acc7891ed5ed442dd85c5a50a7e30b58b96b`. Post-run source verification now runs even after an unsuccessful UI test when the fixture app installed, and does not infer UI success.

## Expected evidence and stop condition

Require actual helper compile/sign/install, source-app ready UI, selectionReceived -> accepted resolution -> bound dismissal -> importStarted -> importFailed, the original UI refusal and complete existing assertions, and independent original-byte verification. The helper manifest's creationObserved=false is not rewritten to true by installation; creation evidence is the actual XCTest ready assertion. A successful postcheck alone cannot pass a failed UI run.

If the same resolver error remains with the independent coordinated source, this fixture hypothesis is not accepted. Inspect the specific provider/runtime failure or a minimal UIKit consumer; do not change tap targets, add retries, enlarge waits or weaken parser expectations. If selection now arrives but dismissal loses it, the trace separates that product bug. Do not relabel the original own-container fixture path as passed.

## Environment and fast checks

Existing Xcode/runtime selection, owned SE/iOS26.2 policy, concrete destination, product entitlements and dependency pins are unchanged. The tiny producer is compiled with the selected Simulator SDK and current runner architecture, with its own identity and no shared secret groups. Native compilation/execution of this new producer has NOT been observed locally.

Local checks: 8 new producer contracts/real bundle-file tests, 6 existing document activation/fixture tests and 6 lifecycle/export tests passed; 16 skill classifier tests passed. Actual helper and XCTest frontend syntax parsed, and workflow YAML parsed. Mocked command planning/host temporary-file checks are not UIKit or file-provider validation. Unchanged core and complete native integration suite were not rerun for this test-only increment.

A single new full-App workflow will follow the commit. Record its ID once and leave its completion as the next standalone item. No existing run is being reset or replayed. Read the exact new SHA's result; there is no after-turn work promise.

## Primary API basis

Apple documents coordinated access and security-scoped URLs for document-picker open operations, and local sharing via UIFileSharingEnabled plus LSSupportsOpeningDocumentsInPlace. These support the ordinary external-source test design, not a proven explanation of the observed -1012 error:
- https://developer.apple.com/documentation/uikit/uidocumentpickerviewcontroller
- https://developer.apple.com/library/archive/documentation/General/Reference/InfoPlistKeyReference/Articles/LaunchServicesKeys.html
