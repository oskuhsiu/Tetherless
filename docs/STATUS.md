# Current checkpoint — provider-pinned cache reclamation

Updated 2026-10-03. Product implementation: **97903f0c13bf943042644f9345b80e41511896d7**. A later documentation checkpoint changes no product or tests. This increment adds automatic cache cleanup and actual provider lifetime ownership. Work stays on develop; main is not promoted. No device or live credentials requested. Not a release candidate.

## Prior UI result is a real failure

Product 5a7b5ab whole-App run **37126826524** completed with failure in `TetherlessUITests.swift:30`: the system document picker never exposed the expected Cancel button after Choose pairing file. The test reached welcome and pairing, and the retained app stdout confirms Started DatabaseManager. Its failure hierarchy contains a blank presented container. It does not establish that cache code caused the picker issue, or that the entire flow passed. The previous App Group/catalog faults are not diagnosed again. No test assertion or product requirement is removed here.

The downloaded result ZIP matches SHA-256 `f63e9a45599a89f8d258a00a98724d55321cb271c9424f60ee0f82a825fb6a7c`. The actual native-ui.log, stdout and failure hierarchy `23708258-8AFE-4F05-A6AD-FE46AF524D63.txt` were inspected. A frame extracted at 29 seconds from the retained screen recording was also viewed: the pairing page is visible with a blank sheet beginning to present. The still-open picker presentation/cancellation behavior requires follow-up if reproduced. New CI for this changed implementation must be read independently.

## Connected increment

Stable per-slot shared/exclusive usage locks protect all returned managed Anisette clients and in-progress installs. Cleanup can only run exclusively; it verifies the active receipt and removes canonical obsolete generations/abandoned stages, never the active generation, receipt, lock or arbitrary unknown files. All candidates undergo bounded no-follow preflight before removal. Partial obsolete-tree deletion can be retried. Bad current data aborts rather than triggering destructive repair.

The native local and managed remote ODA paths now return a protocol-conforming wrapper retaining both the upstream client and PinnedGeneration throughout async operations. Upstream db8b410 AnisetteClient does NOT retain the resolver closure; a pin captured solely by that callback would have expired too early. The wrapper avoids that bug and changes no actual provisioning/wire data. Normal provider entry and installation attempt safe cleanup; repeated unpinned updates no longer exhaust the four-generation cap. Busy providers defer cleanup and keep the cap effective.

See CACHE_RECLAMATION.md. Independent binary provenance, other HTTP/staging cleanup, aggregate budgets and remaining logging/lifecycle/configuration coverage are separate unfinished gates. This change does not imply publisher trust.

## Verification for 97903f0

| Check | Observed result |
| --- | --- |
| Local Linux core Debug / Release | **244 tests passed each** on completed runs |
| Local Python integration | **149 passed, no skips**, using exact retained native inputs |
| macOS core Debug / Release | Both steps and the complete job passed, run **37129832912**; exact count not inferred |
| iOS Simulator core | **270 unique individual passing records** and **one explicit hardware Data Protection skip**, run **37129832865** |
| Cache generation tests on Simulator | All **16** individual cases passed, including four new reclamation integration cases |
| Portable maintenance tests on Simulator | All eight iOS-available cases passed; the independent-process case is macOS/Linux-only |
| Native iOS Debug / Release | Both compiled, linked, packaged and uploaded successfully, run **37129832897** |
| Current complete App / UI | Run **37129832976** was still in progress at the last inspection; no full UI acceptance claimed |

Nine new portable lifetime/cleanup tests executed locally, including an independent process respecting the actual stable lock. The four new Darwin cases cover repeated unpinned updates, retaining an old provider, refusing cleanup/replacement when current content is corrupt, and cleanup deferral during installation followed by abandoned-stage removal. The test extractor is synthetic; the native path separately compiles the real SafeArchive integration. These tests do not execute downloaded libraries or authenticate their publisher.

The downloaded Simulator log was inspected rather than inferring its count from the suite total. Two passing records had invisible leading characters, which were included in the individual-record count. No passing record exists for the skipped hardware-protection test. Earlier local Release timeouts are not passes. No tests or UI assertions were weakened in this increment.

## Independently inspected source and native output

- Current source artifact **11276840616**: outer SHA-256 `a9c55aac0f5b0e114ce7fc7d7219e7d9ebeeb7e8ad0dc74d36a0def4ad630ed1`, inner TAR `dbe6be2df67dfc7d18a58106337ba8e85cb1aa28f75e069facb4e27a0277dca3`, recorded commit 97903f0. All **ten changed files** matched the local tested files byte-for-byte before this documentation update. The source archive has 161 regular files.
- Simulator artifact **11276751102**: SHA-256 `c03b35a60cce8dedea9efbfc4673c477dae3ac38398eff1b60b3b9eb1f99130c`. Its actual log contains all 16 generation-cache cases and eight maintenance cases with successful records, plus TEST SUCCEEDED.
- Native Debug artifact **11276746273**: outer SHA-256 `ea3a35b93edc231a8b00e3376d534f786254370755ce78eeb5e32efd79c9a3f8`; actual IPA SHA-256 `05369d0693ea644c0d5e19c03af09634312c229e5ddea14adaec0fcc362b0334` matches its manifest and sourceCommit. The actual transformed AnisetteDataManager, copied AnisetteLibraryCache/PrivateFileStore/LibraryCacheMaintenance and LibraryPinnedAnisetteClient wrapper all matched the tested sources byte-for-byte. Native log records BUILD SUCCEEDED and includes compilation of the wrapper and maintenance helper.
- Debug product is unsigned `org.tetherless.Tetherless.XYZ0123456`, version 0.1.0/build 0100. Filename inspection found no .p12/.p8/.key/.mobileprovision resources; this is not an exhaustive secret scan. Manifest still requires user signing and reports device/unattended acceptance false. Release build success was read independently; its artifact was not separately downloaded this turn.

The initial 834f599 source baseline and retained ae9fd0a/dd0b09c native inputs were hash-checked; those older archives are preparation inputs, not proof that the newer product works.

## Resume

1. Inspect completion of full-App run **37129832976** at 97903f0. Core and native build results above are accepted within their stated scope; do not substitute them for UI, provisioning or device execution. Preserve any actual picker/UI failure.
2. Resolve a reproduced system pairing-picker presentation failure using actual hierarchy/stdout, not by skipping cancellation or retrying blindly until green.
3. Independently review/pin library provenance; finish separate download/staging cleanup, native logging and callback lifetimes, aggregate limits, supported-configuration/first-sign/self-update coverage and distribution/branding.

No real Apple login, downloaded library execution, physical pairing, actual profile install, hardware Data Protection, locked-screen renewal or expiry crossing has been verified. Source and checkpoint are saved together before further work.
