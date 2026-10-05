# Tetherless development status

Updated 2026-10-05. Takeover baseline: **3dd8641e84698b97f96d53a6c53ed8c6ca4675bd**. Latest inspected product source: **0dfceb58710543b2272d6d4613fa0205db9ec62e**. This is continued development, not a release candidate. The complete task inventory is [PLAN_PROGRESS.md](PLAN_PROGRESS.md). Work remains on the document-provider boundary, first-sign/self-update integration, lifecycle/resource controls, and supply-chain/delivery gates. Physical-device acceptance remains a single later phase.

## Independent privacy and cache-maintenance increment

This development increment adds reviewed cache-maintenance lease/coordination fixes, source-compatible app-local logging suppression and removal of identified lower-layer PIN logs. Wireless generation is explicitly gated before unsafe native work; imported pairing and normal renewal remain available. PAIR-01 remains incomplete. The initial cache/log/PIN increment compiled in full-product Debug at 0dfceb5; its unsigned native workflow was blocked by the separate test harness. The next reviewed persisted-error, backup-lifetime and delivery increments still require their own exact-SHA native evidence. Broader signing/resource/manager-recovery changes are not included in this increment and must not be inferred from local work-in-progress. See [the original 16-task inventory](PLAN_PROGRESS.md).

## Next reviewed correction

The specific product event-ordering repair is now staged: explicit delegate result and completed dismissal rendezvous in either order, with stable UIKit/physical-cover ownership and exactly-once consumption. Existing UI acceptance and both runtime lanes are unchanged. The [next decision](simulator-ci/product-import-decision.md#next-changed-source-decision-fix-actual-dismissalresult-ordering) records the expected observation and failure rules. Actual new Swift/UIKit execution remains pending. Closed persisted-error metadata, coordinated backup deletion and incomplete source/notice/IPA inventories are separately documented in [privacy](ERROR_HISTORY_PRIVACY.md), [backup lifetimes](BACKUP_LIFETIMES.md) and [delivery](DELIVERY_CANDIDATE.md).

## Latest product and native evidence at 0dfceb5

[Full-product run 37277414175](https://github.com/oskuhsiu/Tetherless/actions/runs/37277414175), attempt 1, failed at the actual UI assertion on **both** exact-runtime lanes. Compilation, signature inspection, Simulator boot, install/launch, external document creation and original-file preservation passed. The selected file callback arrived once on both runtimes, but the product had already treated cover dismissal as cancellation. Complete fixed-event scans show `coverDismissed → dismissalObserved → cancelFinished → selectionReceived → resultDelivered → resolutionIgnored`; no `importStarted` followed. This is a demonstrated product event-ordering bug. The earlier 26.2 pre-delegate provider failure remains historical evidence, not the explanation for this newer run.

The actual status was “Import cancelled. Existing pairing was retained.” The typed invalid-content assertion, post-rejection store checks, relaunch and later navigation were **not reached**. Screenshots show the picker dismissed, fresh pairing missing and Continue disabled; hierarchy and XCTest establish the cancellation text. [Exact checkpoint and artifact identities](checkpoints/2026-10-05-0dfceb5.md). No product acceptance is claimed.

[Native run 37277414343](https://github.com/oskuhsiu/Tetherless/actions/runs/37277414343) stopped before preparation/build in the Swift-backed maintenance test harness: blocking semaphore waits inside async detached tasks do not compile with Swift 6.2.4. Both configurations collected 273 tests: 266 passed, one failed, six prepared-input checks skipped. The actual logger, PIN-gate and typed parser/classifier tests passed. Package API observations correctly report unavailable input, not present or absent exports. A narrowly reviewed test-only GCD continuation bridge retains every lease/cancellation assertion; corrected native execution remains pending. The next CI gate also captures verified transient preimages so the six older prepared-source contracts must execute without skips.

[Core run 37277414263](https://github.com/oskuhsiu/Tetherless/actions/runs/37277414263) passed Debug and Release for this exact source. Full-product Debug compilation is separate evidence from the blocked unsigned Debug/Release workflow and from physical acceptance.

## Standalone diagnostic checkpoint

The corrected experiment at **9a49417dc6f6b707b94786882722ca907870fa9c**, [run 37273262340](https://github.com/oskuhsiu/Tetherless/actions/runs/37273262340), produced a discriminating result: the same signed build delivered one selected-file URL and dismissed on **iOS 18.6**, while **iOS 26.2** failed bookmark resolution before the recipient delegate. Both actual cancellations passed in both cases; both source files remained intact. All 47 uploaded bundle files, installed bundle maps, test configuration and required attachments were independently checked. This supports a runtime-associated difference under the observed host/artifacts, not a proven Apple defect or product parser/storage acceptance.

The overall diagnostic remains **failed**: 26.2 UI failed, and both cases retain collector gaps (help exit 64 and truncated broad recipient unified logs). Complete recipient stdout and focused provider logs were retained. No run is repeated merely to make collectors green. [Verified comparison and evidence limits](simulator-ci/runtime-comparison-37273262340.md). Core Debug/Release passed for the exact 9a49417 source. Normal full-product code and acceptance assertions were unchanged by the diagnostic commits.

The earlier experiment at **985832fa741275b27236349fdb91f631a9e80d39**, [run 37271883947](https://github.com/oskuhsiu/Tetherless/actions/runs/37271883947), failed before device allocation/build because broad simulator inventory exceeded bounded capture. The separately reviewed focused-query repair retained the original capture bound and assertions; all 21 portable diagnostic tests passed. Its history remains in [next-run decision](simulator-ci/next-run-decision.md).

## Earlier full-product result at 89c157d

**Native simulator launch 37247923030**, attempt 1, job **111569414544**, source **89c157dbc6acd3c16eb31a32bdc6d73af6c40f57**, is completed/failed at **step 11, XCTest document selection**. Compilation, signature checks, boot, installation, launch and the separate public-document source passed. The prior pending entry was a historical checkpoint, not the current result. Do not rerun it merely to recover state.

The product completed two actual system-picker cancellations. Its subsequent single file activation reached DocumentManager, but bookmark/URL preparation failed with FileProvider -1005 and underlying resolver -1012. The complete retained lifecycle scan has picker creation/type acceptance and no selectionReceived or importStarted. The original ten-second assertion failed. Later wizard/relaunch assertions were not executed.

The failure-only independent UIKit control also stayed in the picker without a delivered selection. It removes Tetherless's SwiftUI/import state machine, but shares the fixture/provider/runtime and selects its own container's file; it is not identical to the product's cross-container case. Its raw stdout was not retained. Do not attribute the product's exact error codes to the control.

Original-document verification passed: **241 bytes**, SHA-256 **8adc01ad4d6304deb1daf74335f9acc7891ed5ed442dd85c5a50a7e30b58b96b**. Neither file disappearance nor Simulator boot failure explains this run.

## Evidence rechecked during takeover

- [UI run 37247923030](https://github.com/oskuhsiu/Tetherless/actions/runs/37247923030), artifact **11319844035**, 99,156,455 bytes, SHA-256 **7edc964fe50816aac025f1a4cd6d43a3f2c644339ed35ba4902fab4553165f81**. The complete artifact was downloaded and its digest independently verified; logs, process/service evidence, hierarchy and actual screenshot pixels were inspected.
- The broad provider-service capture produced 2,067,057 bytes but retained 262,144. Its retained halves omit the product's selection time, and 1,424 of 1,605 retained lines are APS connection noise. The predicate did not include the observed ResolverService or LocalStorageFileProvider executables. This is a diagnostic evidence gap, not a proved product correction.
- Surviving control-period filecoordinationd logs report provider-preparation failures. Container class-2 misses immediately fall back to class-4 successfully; those misses do not prove corrupt containers.
- [Core run 37248028123](https://github.com/oskuhsiu/Tetherless/actions/runs/37248028123) passed for baseline 3dd8641. [Native integration run 37247923028](https://github.com/oskuhsiu/Tetherless/actions/runs/37247923028) passed for implementation 89c157d. These do not validate any subsequent edit.
- All **212 ordinary baseline source files** in the recovered handoff were verified against current GitHub blob SHAs. The standalone handoff matched the archive document. No Git history or submodule checkout was present locally; native/preimage verification remains a separate CI obligation.
- The current classifier input and report are in [simulator-ci](simulator-ci/): failed / ui, automaticRetryAllowed=false, productAccepted=false. The report classifies the earliest failed boundary; it does not infer the cause.

## Decision before further Simulator work

The recovered runtime patch is **not adopted unchanged**. It replaces the normal push-triggered UI runtime with iOS 18.6, does not pin the tested architecture, rebuilds/re-signs across runtime destinations, and accepts host-image drift while calling the toolchain matched. An older-runtime green job would not close iOS 26.2 or establish a pure runtime comparison.

The separately reviewed, same-host, build-once cross-container UIKit experiment has now run. It preserved fixture bytes, open-in-place semantics, actual cancellation/selection, the ten-second outcome limit and source-file preservation. Both cases used the same signed artifact hashes. The next product-specific question is whether selected bytes reach the real pairing parser and protected storage on the demonstrated working delivery environment. Any additional 18.6 product coverage must remain separate from the unresolved 26.2 acceptance condition; it cannot replace or green that condition.

A diagnostic callback is not pairing parsing, storage, installation or product acceptance. Missing runtimes/toolchain, build failure, missing logs or changed artifact hashes invalidate the intended comparison. No permission changes, selector rotation, timeout extension or blind rerun is justified by current evidence.

## Remaining delivery boundary

The original 16 tasks remain authoritative. In particular: complete the actual first-sign/self-update route and interrupted identity/data recovery; close maintenance/callback mutation races and aggregate install resource limits; review Mach-O/entitlements/nested signing; finish dependency/license/provenance and branding obligations; then verify the **same candidate SHA** through core, transformations, native artifacts and full UI.

Only after feasible implementation and non-device gates are satisfied should the owner be asked for the consolidated real-iPhone pass: Apple login/2FA and first-time permissions, pairing, true profile application/readback, next-day locked-screen proactive renewal, expiry crossing and longer observation. No unattended-renewal or permanent iOS-background guarantee is claimed. Clean-phone, computer-free bootstrap remains separate research. Develop only; main and releases are not authorized.

## Historical failures retained

Run 37242839315 at 8c25ff3 failed at the unchanged 120-second install bound; product/control UI never ran. The diagnostic improvement at 89c157d did not prove that timeout's cause. Earlier snapshots and decision records remain in Git history; the current UI failure must not be rewritten as the older install failure.
