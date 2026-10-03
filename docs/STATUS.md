# Current checkpoint — owned ODA transfers and abandoned-download reclamation

Updated 2026-10-04 (Asia/Taipei). Product implementation: **582953dac54b139fe4b3614a4f61865c29c7b51d**. A later documentation checkpoint does not change product code or tests. Starting develop head was 279c35c844877eefa26ed61767759d1d2a33df28 (product 97903f0). Work stays on develop; main is not promoted. No phone, account or signing credentials requested.

## Baseline confirmed

The previous complete-App/UI workflow **37129832976** at 97903f0 completed successfully in every step, including setup/recovery navigation, document-picker cancellation, diagnostic retention and upload. The earlier 5a7b5ab blank picker remains a historical failed run; a later pass is not a proven fix for every intermittent system-picker failure. No UI assertion is weakened in this increment.

## Connected change

The four public ODA data-transfer routes now use an owned TransferWorkspace pool, not independent random temporary folders. One real exclusive stable lock covers network callbacks, the final bounded no-follow read and cleanup. Another caller using the same pool fails busy before creating files. After process death, the next admission reclaims only recognized abandoned flat transfer directories under exclusive ownership. Unknown root entries and the lock inode are preserved; malformed/link/special-file stage contents fail the complete deletion preflight.

The existing download byte ceiling remains, with an additional workspace maximum of 128 MiB and one active transfer per pool. Normal success requires checked cleanup. Cancellation/error cleanup does not replace the original error. Both the main core and SideSign receive the identical tested helper source. No URL, metadata or account can select a cleanup path. See TRANSFER_WORKSPACES.md.

This does not yet collect legacy random folders or every IPA install stage, and does not claim aggregate in-memory JSON/Data budgeting or independent binary provenance. Those remain separate pre-handoff work. Unattended renewal policy, consent, pairing and signing behavior are unchanged.

## Local verification before commit

- Swift Debug and Release: **258 tests passed each** on completed invocations. The first compile-only filter had zero matching cases before new tests existed; that is not counted as test execution.
- Twelve new real-files workspace tests, plus two downloader/workspace test declarations (including parameterized success/error cases), cover live ownership, cancelled callbacks, success/error cleanup, a separate process respecting the lock, and process-death leftovers recovered by the actual production manager.
- Python integration tests use retained exact dd0b09c authentication and ae9fd0a cache-transformation inputs, validated by their pinned hashes. **150 checks passed with no skips**, including compiling the real namespaced downloader, workspace helpers and wrapper. Invalid URL and excessive limit tests made no network request or workspace. Native compile/UI results require this increment's own CI.
- The source baseline archive matched outer SHA-256 a9c55aac0f5b0e114ce7fc7d7219e7d9ebeeb7e8ad0dc74d36a0def4ad630ed1, inner TAR dbe6be2df67dfc7d18a58106337ba8e85cb1aa28f75e069facb4e27a0277dca3 and recorded 97903f0. The intervening 279c35c change is documentation-only.

## CI and artifact verification for 582953d

| Check | Observed result |
| --- | --- |
| macOS core | Debug/Release steps and complete job passed, run **37138805982**; no exact count inferred |
| iOS Simulator core | **282 unique individual passes**, one explicitly skipped hardware Data Protection test, run **37138806052** |
| New workspace cases on Simulator | All ten iOS-available workspace cases plus both composed downloader/workspace declarations passed; two independent-process cases are macOS/Linux only |
| Native iOS Debug | Compiled, linked, packaged and uploaded in run **37138806062** |
| Native iOS Release | Compiled, linked, packaged and uploaded successfully in **37138806062**; its artifact was not separately downloaded this turn |
| New full-App/UI | **37138806001** is still in full-App Simulator compilation; this increment's complete UI is not accepted yet |

The original source ZIP **11279746545** matched SHA-256 `89a7609c076fa681e21145e41caf252e5934bda81d4a9f2bc33c9fabafe243a4`, recorded product commit, and inner TAR `8abd2bba57c7c235fb7f444ba419289bf0e786c776cfb99072e2968068828041`. All nine changed files were byte-identical to the local tested checkpoint before this documentation update. The archive contained 164 regular files.

Simulator artifact **11279053789** matched SHA-256 `b6776255fbd135375ff7c2c91477537d45eb6eb6b85639fad58d135ea8f38cc1`. Its downloaded log was read and unique passing records counted separately from the explicit `actualIOSProtectionAndBackupExclusion` skip. It contains TEST SUCCEEDED. These are production-code tests with scripted HTTP, not real Apple/CDN or physical protection evidence.

Debug artifact **11279303445** matched SHA-256 `d848afa283f80538685ee1c997bb01891a6eab823e655accd60ae157bb790496`. Actual IPA hash `abedf513145c02d824e9b38b21bde9c62a0146c3383c83f7c87250a4050280e7` matched the manifest and sourceCommit. Four actual prepared helper/wrapper files matched their local tested sources: TransferWorkspace, AnisettePackageTransfer, PrivateFileStore and LibraryCacheMaintenance. Prepared AnisetteDataManager still has all four bounded transfer call sites. The build log shows BUILD SUCCEEDED and compilation of the new helper.

The main Info.plist was found by enumerating the IPA (Payload/Tetherless.app, not the internal Xcode product name). It reports unsigned Debug org.tetherless.Tetherless.XYZ0123456, version 0.1.0/build 0100. Filename inspection found no .p12/.p8/.key/.mobileprovision resources; that is not an exhaustive secret scan. The manifest retains requiresUserSigning=true and physical/unattended validation=false.

## Next

1. Inspect the complete new UI result **37138806001**. Core and native Debug/Release evidence above have been observed; do not substitute them for uncompleted UI or device checks.
2. Continue independent library provenance/redistribution review and remaining native logging/callback lifetimes. Finish metadata structural/RAM and install-wide disk limits, remaining first-sign/self-update/configuration coverage and branding.
3. Consolidate physical acceptance only after feasible implementation/integration gates. No live Apple, downloaded-library execution, physical installation, locked-screen renewal or expiry crossing is claimed here.
