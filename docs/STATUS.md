# Current checkpoint — explicit pairing picker and dismissal-bound import

Updated 2026-10-04 (Asia/Taipei). Product implementation: **6397897e7a3ee1196a058d428852f834e48eb80f**, which corrects the initial **6cee0e3619a4fb3335b6ccab686439b3b6462595** submission. A later documentation checkpoint changes no code or tests. Starting integration head was e704ed29598f206948a4b674f6bd114da4f7fc84 (product 7045e13). Development remains on develop; main is not promoted. No device or credentials requested. This is not a release candidate.

## Confirmed previous outcome

7045e13 native Debug and Release both passed run 37143684846. Its whole-App run 37143684889 FAILED the document-picker Cancel assertion at TetherlessUITests.swift:30. The current downloaded UI artifact 11281747494 matches SHA-256 4e5701887b587ccb191d0002404ffd56927e4b361f7eaac1af02ee2e5edceaa1. Actual test log and app stdout were inspected: database startup succeeded, while the presented picker container had no Cancel control during the wait. This is the continuing picker symptom, not an inferred App Group or metadata-parser regression. Earlier UI failures remain failures.

The verified 7045e13 source archive matched outer SHA-256 55309b6a0a36b344e75e3fdba58818696886e68d8b1df1d78fb510eebe1d49c0 and inner TAR f40fd91b8c24f1cf7ad8e48fd6b1d66b2cea9f8001301bc635a54d80ee88f1c1. The additional e704ed2 truncation test was read from GitHub and matched blob a67d9720d69aad2ae92bd6e7e3b03b131d2e2f86. No previous uncommitted edits were required.

## Connected change

Replace the Form-bound Boolean fileImporter with a concrete UIKit picker owned by a stable request and presented from the root NavigationStack via fullScreenCover. Delegate callbacks are single-shot and invalidated on teardown. The core PairingImportFlow requires matching request identity and actual dismissal before an import can start. Repeated selection, cancellation, dismissal and late completion are rejected; another request is not admitted while importing. Normal account, protected-pairing validation/storage and unattended-consent rules are retained.

Open-mode selection uses security-scoped, coordinated, bounded reading instead of creating a raw copy in a public Inbox. Coordination failure is not a successful read; cancellation never calls import. The system picker itself still supplies the real Cancel control. The UI test now requires two consecutive real presentations/cancellations with the same ten-second wait, then all prior setup/recovery/cold-launch assertions. No warm-up, fake picker, fake account, auto-granted permission or disabled assertion was added.

See PAIRING_IMPORT.md. This is a concrete presentation/lifetime repair, not a proven diagnosis of an Apple framework defect. It still requires actual UI results to know whether the observed blank sheet is resolved.

## Verification and corrected submission

| Check | Observed result |
| --- | --- |
| Local Linux core Debug / Release | 286 tests in 37 suites passed each |
| Local Python integration | 160 passed, no skips with exact retained native inputs; rerun after source verification |
| Corrected 6397897 macOS core | Both Debug/Release steps and full job passed, run **37150571819** |
| Core-only iOS Simulator | **310 unique individual passing records**, plus one explicit hardware Data Protection skip, run **37150340016** at 6cee0e3 |
| New picker-request core cases | All nine have actual passing records in that Simulator log |
| Corrected 6397897 native Debug | Compiled, linked, packaged and uploaded, run **37150571848**, job **111283499730** |
| Corrected 6397897 native Release | Compiled, linked, packaged and uploaded, same run **37150571848**, job **111283499616** |
| Corrected whole-App/UI | Run **37150571770** was compiling the actual Simulator app at the latest inspection; both system Cancel operations are NOT yet accepted |

The Simulator core sources/tests are byte-identical between 6cee0e3 and 6397897; the correction changed only the native PairingFileManager override. Core success cannot validate that native override or the actual document picker. The explicit actualIOSProtectionAndBackupExclusion skip is not a passing record. Native CI's Python prechecks skip five unavailable prepared-fixture cases; the complete no-skip 160 result above is the local invocation using verified retained inputs, not a claim that every native precheck ran all cases.

**A submission error occurred and was fixed.** The locally tested manager used the correct lockdown/rppairing comparison, but the initial uploaded file accidentally compared PairingProtocol to `.remote` (a case of a different enum). 6cee0e3 native Debug failed at PairingFileManager.swift:108 with “PairingProtocol has no member remote.” The original failure log remains in run 37150340052; it is not relabelled as passing. Commit 6397897 restores the exact locally tested branch; its returned blob `b504556851023359d8f0ecbbb0b61449a1006719` matches the local file. The complete corrected source artifact was then compared against the local workspace, rather than assuming local tests covered the submitted bytes.

The initial local state-test macro compilation failure was separately corrected by evaluating mutating calls before Swift Testing assertions; all cases remain. Syntax parsing is not substituted for native Xcode compilation. No production or UI assertion was removed to hide either failure.

## Independently inspected artifacts

- Initial 6cee0e3 source archive: SHA-256 `6180316a243b19d687d5caab550dbdaa3e394c174da0d462a22e931e9d1bfddc`, inner TAR `fa7d5d04fe1d86feeff80a4865d07359807438435a6ea024024fd1106d7c1427`. A full comparison identified exactly the native enum transcription error plus expected documentation differences. Other code matched.
- Corrected source artifact **11283652696**: outer SHA-256 `cb4148f8c47f9b057112d3aa23e6de6f171a383f1f114995b3e3ba8608b8310e`, inner TAR `46aee97cdaff5b3e26cac582904696cf93785b410089d8744161265e5373bb2a`, recorded commit 6397897. All **176 files** matched the local source checkpoint byte-for-byte before this documentation update.
- Simulator core artifact **11284375471**: SHA-256 `d94faa73923d78bf78d148329246333967da0686b69177554ff2945e1de16627`. The actual log was counted, including each of the nine new request-lifetime cases and the separate hardware-protection skip; it reports TEST SUCCEEDED.
- Corrected native Debug artifact **11283742686**: outer SHA-256 `e500ac32d71c181729d66fe72348173ddb37f6f350cdb07c4fd21d7953c64cdb`; actual IPA SHA-256 `0e823c8f2e3c466b8a285870092f2e9981d030070c7c2f1525134c6703cdb450` matches manifest/sourceCommit. Prepared PairingDocumentPicker, PairingImportFlow, OnboardingView and PairingFileManager match the tested sources byte-for-byte. The native log records BUILD SUCCEEDED.
- Actual unsigned Debug identity remains `org.tetherless.Tetherless.XYZ0123456`, version 0.1.0/build 0100. No .p12/.p8/.key/.mobileprovision resource filenames were found; this is not an exhaustive secret scan. The manifest still requires user signing and keeps physical/unattended acceptance false.

## Next

1. Inspect completion of actual UI **37150571770** at 6397897, especially BOTH system Cancel operations, cancellation status, released request and unchanged pairing/consent gates. Preserve any real failure and inspect current logs rather than rerunning until green.
2. Complete native selected-file/callback and broader logging/lifecycle checks. UI cancellation alone does not validate a real pairing import, file-provider access or account operation.
3. Independently verify/pin library provenance and distribution rights; complete remaining install-wide budgets, first-sign/self-update/configuration coverage and branding before consolidated physical acceptance.

No real Apple login, selected cloud pairing file, physical pairing, actual profile installation, hardware protection, locked-screen renewal or expiry crossing was verified. Code and continuation state are saved together.
