# Tetherless development status

Updated 2026-10-05. Current remote baseline checked: **3dd8641e84698b97f96d53a6c53ed8c6ca4675bd**. This is continued development, not a release candidate. The complete task inventory is [PLAN_PROGRESS.md](PLAN_PROGRESS.md). Work remains on the document-provider boundary, first-sign/self-update integration, lifecycle/resource controls, and supply-chain/delivery gates. Physical-device acceptance remains a single later phase.

## Standalone diagnostic checkpoint

The reviewed experiment was published at **985832fa741275b27236349fdb91f631a9e80d39**. [Run 37271883947](https://github.com/oskuhsiu/Tetherless/actions/runs/37271883947) failed before device allocation/build: complete simulator inventory exceeded bounded capture, so preflight refused truncated JSON. Neither iOS 26.2 nor iOS 18.6 was tested. The verified artifact and the independently reviewed narrow query-scope correction are recorded in [next-run decision](simulator-ci/next-run-decision.md). Twenty-one portable diagnostic tests passed; native execution remains pending. Core Debug/Release passed on 985832f. Normal full-product code and acceptance assertions are unchanged by the diagnostic commits.

## Latest verified full-product result

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

The next diagnostic is a separately reviewed, same-host, build-once cross-container UIKit experiment using exact iOS 26.2 and 18.6 runtimes and the same SE device type. It must preserve fixture bytes, open-in-place semantics, actual cancellation/selection, the ten-second outcome limit, source-file preservation and complete per-case evidence. Both cases use the same signed artifact hashes. Normal full-product coverage and acceptance assertions remain intact. The implementation and its local tests require independent review before a develop push starts that experiment.

A diagnostic callback is not pairing parsing, storage, installation or product acceptance. Missing runtimes/toolchain, build failure, missing logs or changed artifact hashes invalidate the intended comparison. No permission changes, selector rotation, timeout extension or blind rerun is justified by current evidence.

## Remaining delivery boundary

The original 16 tasks remain authoritative. In particular: complete the actual first-sign/self-update route and interrupted identity/data recovery; close maintenance/callback mutation races and aggregate install resource limits; review Mach-O/entitlements/nested signing; finish dependency/license/provenance and branding obligations; then verify the **same candidate SHA** through core, transformations, native artifacts and full UI.

Only after feasible implementation and non-device gates are satisfied should the owner be asked for the consolidated real-iPhone pass: Apple login/2FA and first-time permissions, pairing, true profile application/readback, next-day locked-screen proactive renewal, expiry crossing and longer observation. No unattended-renewal or permanent iOS-background guarantee is claimed. Clean-phone, computer-free bootstrap remains separate research. Develop only; main and releases are not authorized.

## Historical failures retained

Run 37242839315 at 8c25ff3 failed at the unchanged 120-second install bound; product/control UI never ran. The diagnostic improvement at 89c157d did not prove that timeout's cause. Earlier snapshots and decision records remain in Git history; the current UI failure must not be rewritten as the older install failure.
