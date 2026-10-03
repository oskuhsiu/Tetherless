# Current checkpoint — bounded ODA metadata and non-silent fallback

Updated 2026-10-04 (Asia/Taipei). Product implementation: **7045e1387515af44208ace1251065f0a5141f039**. A later follow-up adds one truncation regression test and this evidence checkpoint, not production changes. Starting develop head was cb6bd38faf939ced28c1d83270183910cceb59bd (product 582953d). Work remains on develop, main unpromoted. No physical-device handoff or credentials requested.

## Baseline and actual outstanding UI failure

The previously saved transfer-workspace implementation was recovered from the exact CI source archive (11279746545): ZIP SHA-256 89a7609c076fa681e21145e41caf252e5934bda81d4a9f2bc33c9fabafe243a4, inner TAR 8abd2bba57c7c235fb7f444ba419289bf0e786c776cfb99072e2968068828041 and recorded commit 582953d matched. cb6bd38 is documentation-only. Prior core/native passes remain scoped to that version.

Complete-App run **37138806001** at 582953d finished with failure, not pending: TetherlessUITests.swift:30 timed out waiting for the actual document-picker Cancel control. Setup reached the pairing page, and app stdout records Started DatabaseManager. This matches the earlier intermittent blank system-picker symptom, not proof of another App Group failure or of a cache regression. The downloaded artifact 11279718861 matched SHA-256 71c03352974cf2719b06ef6371d4991f9789a20d3dcec579d8ce18436c5bb44f. Actual test log, app stdout and diagnostic attachments were inspected. No UI assertion was removed or weakened in this increment; picker lifecycle/root-cause work remains open.

## Connected change

All three metadata routes call the same checked adapter. A raw buffer preflight validates grammar/Unicode and bounds depth, tokens, array entries, key and string lengths before Foundation builds its graph. Escaped-equivalent duplicate keys, multiple non-null package aliases, wrong field types and mixed envelopes fail explicitly. Recognized layouts and individual legacy aliases are preserved. Invalid data or unsafe references no longer silently turn into an absent ODA entry and activate fallback. One synchronous parse per process is admitted without queueing.

The adapter is compiled locally together with actual SideSign model declarations, not fake replacements. It demonstrates legitimate explicit fallback when the validated catalog lacks ODA, rejection of malformed/unsafe references without fallback, and relative-reference resolution. The native transformation requires prepared input blob df58f374bd41fc901ee5ed265429f765d33fee09 and runs after the existing cache transform. All destinations are checked before writing. See ODA_METADATA.md for deliberate compatibility and resource limits.

This does not authenticate mutable metadata, downloaded binaries or their distribution rights. The per-parse structural/string budget is not an install-wide RAM/RSS budget. Real Apple/Anisette and locked-screen behavior are not exercised.

## Verification for product 7045e13

| Check | Observed result |
| --- | --- |
| Local Linux core Debug / Release | 276 tests passed each on completed invocations, including all 18 new metadata tests |
| Local Python integration | 155 passed with no skips using exact retained native inputs |
| macOS core Debug / Release | Both steps and the complete job passed, run **37143684834**; exact macOS count not inferred |
| iOS Simulator core | **300 unique individual passing records**, plus one explicit hardware Data Protection skip, run **37143684828** |
| New metadata cases on Simulator | All 18 new case names have passing records in the downloaded log |
| Native iOS Debug | Compiled, linked, packaged and uploaded, run **37143684846**, job **111263172935** |
| Native iOS Release | Job **111263173144** was still compiling at the latest inspection; not accepted yet |
| Current whole-App/UI | Run **37143684889** was still compiling the full Simulator app; this product's UI result is not accepted yet |

The iOS log contains TEST SUCCEEDED. Its explicit actualIOSProtectionAndBackupExclusion skip is not counted as a hardware-protection pass. The five new Python contracts include compiled actual SideSign-model/adapter execution without networking. Earlier local Release driver timeouts are not passes; a completed invocation exited zero. A compile-only filter before the new tests existed matched zero cases and is not counted as test execution.

## Permanent truncation regression added after the product commit

A separate optimized harness exercised the production preflight on 500 Foundation-generated valid JSON objects and every incomplete prefix: **40,190 truncated inputs were rejected** on this Linux Foundation version. This is a structured truncation test, not exhaustive fuzzing or a memory-safety proof.

The follow-up saves this as ODAMetadataTruncationTests.generatedObjectsAndEveryIncompletePrefix. It calls the actual scanner without mocking its results, preserves unexpected errors as failures, and requires at least 30,000 tested prefixes while allowing Foundation's escaping lengths to differ across OS versions. The production parser, native adapter and UI assertions are unchanged.

Completed local Debug and Release after that test addition each passed **277 tests in 36 suites**, including the new truncation case. Local integration contracts remain 155 passing with no skips. The new test itself has not yet been observed on macOS or iOS CI; those remote results above concern the original 18-case product commit. Native product evidence remains tied to 7045e13.

## Independently inspected source and native output

- Product source artifact **11280967611**: outer SHA-256 `55309b6a0a36b344e75e3fdba58818696886e68d8b1df1d78fb510eebe1d49c0`, inner TAR `f40fd91b8c24f1cf7ad8e48fd6b1d66b2cea9f8001301bc635a54d80ee88f1c1`, recorded commit 7045e13. All **eight changed files** matched the locally tested files byte-for-byte before the final test/documentation follow-up. The archive contains 170 regular files.
- Simulator artifact **11281441968**: SHA-256 `1ffc3f8e70bfe8cd5aae8a5ac81e3c7f048b20b5a65c4e3e17aaf82c4efed7f0`. Its actual log was inspected; 300 unique passes and the explicit protection skip were counted separately.
- Native Debug artifact **11281102684**: outer SHA-256 `39020ff0d2f2c9aa3f4399dda52babbd0ad077cda451b73ea4c352a18c35321c`. Actual IPA SHA-256 `b2316e0376b0e506fbf7a7add3f20c2fccd21dc2232b99eca63db04dd98a8f5f` matches its manifest and sourceCommit. Prepared AnisetteDataManager, TetherlessODAMetadata and ValidatedODAMetadata match the exact tested transformation and helper bytes. All three adapter call sites are present, and the actual native log reports BUILD SUCCEEDED.
- Actual IPA main Info.plist is Payload/Tetherless.app/Info.plist: unsigned Debug `org.tetherless.Tetherless.XYZ0123456`, version 0.1.0/build 0100. No .p12/.p8/.key/.mobileprovision resource filenames were found; this is not an exhaustive secret scan. The manifest still requires user signing and reports physical/unattended validation false.
- Prepared 582953d Debug artifact 11279303445 matched SHA-256 d848afa283f80538685ee1c997bb01891a6eab823e655accd60ae157bb790496 before its source was used as transformation input. It is not evidence for newer product behavior.

## Next

1. Read completion of product native Release **37143684846** and full-App/UI **37143684889**, plus the follow-up core test runs. Preserve any actual compiler/test or picker failure rather than substituting older green results.
2. Resolve the repeated system pairing-picker presentation/cancellation failure without skipping that product path. Finish remaining native logging and callback lifetime checks.
3. Independently verify/pin library provenance and distribution rights; finish IPA/install-wide resource admission, remaining first-sign/self-update/supported-configuration tests and branding. Consolidate device acceptance only after feasible development gates.

No downloaded library execution, live Apple provisioning, real profile installation, physical protection, locked-screen unattended renewal or expiry crossing is claimed. Product and the additional regression are saved with their distinct evidence; no uncommitted feature batch is required to resume.
