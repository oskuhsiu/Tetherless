# Recovery checkpoint — plan-aligned inventory and actual install timeout

Updated 2026-10-04 (Asia/Taipei). Product implementation remains **6397897e7a3ee1196a058d428852f834e48eb80f**. Recovery started from develop **b393cacd9a012127aa4f26cf2ca76f8fff63b7cc**. This update is documentation only; no product code, tests or workflows changed. Main remains at **4cfcc185cd529e07c212c3b310c0ee5162c19b2f** and is not promoted. No phone or live credentials requested.

## Read first

**PLAN_PROGRESS.md** maps the original v1.0 plan's G0–G5 gates and all 16 task IDs to current implementation, verification gaps and concrete closeout conditions. It incorporates the later owner-required device-last order from IMPLEMENTATION_PLAN.md without weakening unattended-renewal acceptance. The old rough 80% is not a weighted acceptance score and must not be inferred from test counts.

## Recovered saved work

The prior turn preserved three checkpoints: 6cee0e3 (explicit document picker, request/dismissal-bound import), 6397897 (correct the uploaded PairingProtocol enum comparison to the locally tested version), and b393cac (documentation). The complete detailed prior evidence remains in STATUS.md at b393cac. Do not repeat the original feature work or claim a new product implementation for this recovery.

Recovered source artifact **11283652696** matched outer SHA-256 `cb4148f8c47f9b057112d3aa23e6de6f171a383f1f114995b3e3ba8608b8310e`, inner TAR `46aee97cdaff5b3e26cac582904696cf93785b410089d8744161265e5373bb2a` and recorded commit 6397897. A fresh local source tree was extracted for inspection. No prior uncommitted Git working tree was present in the current runtime; recovery confirms committed/retained source, not every hypothetical uncommitted edit.

The original delivered plan was recovered from the actual mounted `ios-mobile-sideload-autorenew-plan-v1.0.md`, SHA-256 `49d049cea36c0872224e888e20074d08d313031a72d6ed9a128ef320370fe3a6`. PLAN_PROGRESS.md uses its original task IDs, not replacement task names invented from the latest implementation.

## Current CI, rechecked during recovery

| Product / check | Observed final result |
| --- | --- |
| 6397897 macOS core, run **37150571819** | Both Debug/Release test steps and the complete job succeeded |
| 6397897 native builds, run **37150571848** | Debug job 111283499730 and Release job 111283499616 compiled, linked, packaged and uploaded successfully |
| 6397897 whole-App run **37150571770**, job 111283651651 | FAILED during actual simulator installation, before UI execution |

The whole-App run passed source preparation, actual Simulator compilation and signature/Keychain-identity inspection. The step `Install and launch the complete app in a fresh simulator` then failed; adding the UI test target and exercising the UI were skipped. Subsequent diagnostic/artifact steps succeeded. None of this proves the changed document-picker behavior succeeded or failed.

UI artifact **11284436124** was downloaded and its outer SHA-256 independently checked against Actions: `5d07870e4ceb0b18d0a9dc91b15b86ee46641bfde7338cec34a8620a3d80bd65`. The actual `native-launch-evidence.json` reports:

- sourceCommit: 6397897e7a3ee1196a058d428852f834e48eb80f
- installed=false, launched=false, uiFlowsTested=false, smokePassed=false
- lastCommand: xcrun simctl install
- failedStage: native-simulator-install.log
- failure: timeout; failureType: TimeoutExpired

The corresponding install log contains the real simctl install command and TIMEOUT. It provides no deeper root-cause explanation. Do not call this another observed Cancel-button assertion failure: the two Cancel operations never ran for this corrected product. Earlier blank-picker UI failures remain separate historical failures. Do not substitute an earlier green UI build or simply retry until green.

The previous checkpoint's local 286-test/160-integration-check and core-only Simulator 310-pass/one-hardware-skip records were not rerun in this documentation recovery. They remain scoped to the executions already recorded at b393cac; no fresh execution count is claimed. No production acceptance is inferred from source inspection.

## Exact continuation

1. Address the actual simulator-install timeout with appropriate installation/service diagnostics, then obtain the corrected product's complete real UI result, including both system picker cancellations and existing setup/recovery/cold-relaunch assertions. Keep failure history and assertions intact.
2. Use PLAN_PROGRESS.md to close existing AUTO-02, PAIR-01, AUTH-01, AUTO-03, INSTALL-01/02 and QA-02 gaps: selected-file and callback lifecycle, remaining logging/maintenance ownership, install-wide resource admission and full first-sign/self-update integration. Do not grow unrelated features in place of closing these criteria.
3. Finish BASE-02 dependency/binary provenance, complete license/SBOM/distribution decisions, branding and supported-configuration evidence. Current checksum/cache integrity is not independent publisher authentication.
4. Prepare one coherent, non-device-verified candidate and the existing consolidated DEVICE_ACCEPTANCE.md procedure before requesting the owner's iPhone. Next-day proactive renewal is the initial device test; longer observation is separate. G5 clean-phone bootstrap remains an independent research objective, not a hidden prerequisite for routine mobile-only renewal.

No real Apple login/2FA, physical pairing, profile installation, locked-screen scheduled renewal, hardware Data Protection or expiry-crossing acceptance is claimed. This recovery saved the current failure and a plan-aligned checklist; it did not fix simctl installation or validate the picker. No ongoing/background work or unreported test execution is promised.
