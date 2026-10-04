# Verified checkpoint — complete setup UI and authoritative IPA input

Updated 2026-10-04. Product implementation: **6ca17af2956ff1b493600904fcfec734076bd60f**. This later checkpoint changes documentation only. Work remains on develop; main stays unpromoted. No phone or credentials requested. Not yet a release candidate or physical acceptance.

## Plan conditions closed in this increment

**AUTO-02 / PAIR-01:** the full-App workflow **37179423364** completed successfully, including actual Simulator compilation/signature, owned-device boot, installation, launch, the complete setup/recovery/cold-relaunch XCTest, diagnostic retention, artifact upload and owned-device shutdown. Both actual system document-picker presentations exposed their existing Cancel control and returned to the wizard with the correct cancelled status. No UI wait/assertion was weakened, no fake pairing was supplied and no retry-until-green loop was added.

The inspected native-ui.log reports one end-to-end test, zero failures, **164.832 seconds**, and TEST SUCCEEDED. The first two system-picker Cancel taps are recorded at t=33.98s and 41.87s. The original cancellation, resumed wizard, account/pairing prerequisites, settings/My Apps navigation, consent-off, signed-out recovery controls and final relaunch assertions all remain. The two actual picker screenshots and the relaunched Auto Renewal screenshot were inspected; the system picker is loaded and consent is off. This is one complete iPhone SE (3rd generation), iOS 26.2 Simulator run, not every OS/configuration, real pairing generation or live login.

**INSTALL-01 / QA-02:** DownloadAppOperation first creates one bounded private App.ipa snapshot and uses that same file for extraction and context.ipaURL. The prior method extracted the external source and then copied that source again, permitting changed original bytes between validation and cached-input creation. NativeIPAInput coordinates external reads only for the copy, holds/relinquishes security-scoped access where provided, and leaves extraction/signing outside the file-provider accessor. Fixed errors, regular-file/size/change checks, cancellation and descriptor-bound partial cleanup preserve the original and existing/replaced output. See IPA_INPUT.md. Full iCloud/third-party-provider execution and installation resource admission are still separate unfinished conditions.

## Historical failure retained, not relabelled

The previous product 6397897 run 37150571770 timed out at simctl install before UI. The isolated-environment commit decaef1 then created its owned device but introduced a different failure: its generic Simulator destination attempted unsupported x86_64 idevice linkage. The actual log contains missing _adapter_free/_afc_client_connect symbols for x86_64. Artifact 11294585641 matched SHA-256 bb929b2a687e8e78e8d0d1ed511330392f1edb3e1ecd49756c3e24cdab52c1c2. Both failures remain failures.

6ca17af restores the selected-device destination while retaining fresh owned devices, explicit boot after compilation and bounded service diagnostics. The new successful run proves the setup path works under that controlled configuration; it does not retrospectively establish the exact root cause of every earlier Simulator timeout or prove universal repeatability.

## Verification for 6ca17af

| Check | Observed result |
| --- | --- |
| Local Linux core Debug / Release | **296 tests in 38 suites passed each**, including ten new snapshot cases |
| Local Python integration | **171 passed, no skips** against restored exact native preimages |
| macOS core Debug / Release | Both steps and complete run **37179423325** passed; exact count not inferred |
| iOS Simulator core | **320 unique individual passing records**, one explicit hardware Data Protection skip; run **37179423330** |
| New snapshot cases on Simulator | All ten have individual passing records |
| Native iOS Debug / Release | Both compiled, linked, packaged and uploaded in **37179423323** |
| Complete App and setup/recovery UI | Entire run **37179423364** succeeded; one real XCTest, zero failures |

An earlier local Release driver timeout is not counted; the later complete invocation exited zero. Initial test type-inference errors were corrected before the recorded complete runs. Earlier 12/3 prepared-source skips were resolved by recovering exact inputs; the final local Python invocation has no skips. The metadata preimage reconstructed from the reviewed manager and the already-pinned cache transform matches df58f374bd41fc901ee5ed265429f765d33fee09. Native workflow preparation separately executed the complete real transform chain.

## Independently inspected artifacts

- Source **11295036502**: outer SHA-256 `33911a6d2dc206e6689f0df83e781f5f9280de86e1fec95b99e8e4ce874f0122`; inner TAR `3889a0cfb9e9a748c1208edb2cc3dbf7a1683b634a8e11f9aec453b0cee82292`; recorded commit 6ca17af; 185 regular files. All eight new/changed code, test and workflow inputs matched the locally tested files byte-for-byte.
- Simulator core **11294752270**: SHA-256 `35865f2ab65d3f1a2731f94ede8720e1db5ef925a5929754ad23799869ea5728`. Its actual log contains all ten snapshot case passes, 320 unique passing records and a separate actualIOSProtectionAndBackupExclusion skip. No hardware-protection pass is inferred.
- Native Debug **11294677496**: outer SHA-256 `d99f28aa0e018d06345bdaed2bcb10a47a5f703699383278f500aabf4d32713c`; IPA `26ea20bc19e56a0f55a1e16fad8a550ebe105258fad8c17f8e094e31c56bb0e7`, matching manifest/sourceCommit. Actual transformed DownloadAppOperation and copied IPAInputSnapshot/NativeIPAInput match the tested bytes. Identity is unsigned org.tetherless.Tetherless.XYZ0123456, version 0.1.0/build 0100. No .p12/.p8/.key/.mobileprovision resource filenames found; not an exhaustive secret scan. Release success was checked separately, not claimed as a downloaded artifact inspection.
- Whole-App/UI **11294543123**: SHA-256 `4346a26223b62be481388aff1f85fa1ea707205e2c162c26cdec6e959637d275`. Actual UI log, ten screenshot entries, picker and cold-relaunch images inspected. Owner record matches a fresh SE/iOS26.2 device. The separate native-launch-evidence.json is deliberately smoke-only: installed/launched/smokePassed true, uiFlowsTested false; actual UI success comes from the later XCTest log/xcresult, not by rewriting that earlier smoke record.

## Next exact work

1. Continue from a passing full-App setup baseline. Do not keep diagnosing the old install/Cancel failure as current absent new evidence. Extend AUTO-02/PAIR-01 to actual selected-file outcomes and native pairing callbacks; retain the successful two-cancellation and cold-launch checks.
2. Close the remaining existing INSTALL-01/02, AUTO-03, AUTH-01 and QA-02 conditions: installation-wide RAM/disk admission, complete foreground/maintenance/logging lifetime inventory, and first-sign/self-update integration coverage. The input snapshot closes one concrete condition, not every installer risk.
3. Complete BASE-02 binary provenance/SBOM/license/distribution decisions and final branding/configuration documentation. A package checksum or successful build alone is not independent publisher authentication.
4. Only then provide one coherent candidate and consolidated DEVICE_ACCEPTANCE.md procedure. No real Apple login, physical pairing/profile installation, hardware protection, locked-screen scheduled renewal or expiry crossing was verified this turn.

PLAN_PROGRESS.md is updated against the original sixteen tasks. No background work is promised; all source changes and this accepted checkpoint are committed independently.
