# Current checkpoint — verified native Anisette identity transaction

Updated 2026-10-03. Latest product implementation: **ae9fd0a0ae27f9c74abdd7976d10139f7ebae363**. A later documentation checkpoint does not change product code. Development only on develop; main is not promoted. No phone or credentials requested. This is not a release candidate or physical acceptance.

## Previous baseline confirmed

The b7b597f full-App run 37120735783 completed successfully, including setup, signed-out certificate recovery, cold relaunch and diagnostic retention. Earlier pending status is historical. Its prior native/core evidence is in the 733c9e2 checkpoint. Do not re-diagnose historical App Group or catalog crashes without new evidence.

9cba8dea4d60f693298e10fc43328420e26748af saved the identity core before native wiring. Its original local Debug/Release suites passed 231 tests. ae9fd0a connects it to both native providers and explicit reset paths, with additional lock-ownership regression tests.

## Current implementation

Identifier and adi.pb use a coherent versioned generation-bound record, checked Keychain replacement/readback and strict legacy migration. Invalid or inaccessible split data cannot cause automatic identity replacement. Fresh provider material must be saved before returning headers. Cancellation after a successful provider return preserves material first. Failed legacy cleanup retains the authoritative record; explicit reset writes a new generation or tombstone. Stale results cannot restore old state. All four native input hashes are validated before any transformed source is written.

A real integration conflict was found while wiring the new native guard: headless RenewalEngine owned a ProcessLease without conveying MutationScope ownership. Nested Anisette would have tried to relock it and failed busy. The engine now transfers the real descriptor to a task-local scope; there is no no-op acquire or lock bypass. Admitted children retain ownership and old handles cannot unlock transferred/reused descriptors. The two native repair preflights also use the shared scope. Existing policy, transaction, reconciliation and consent rules remain unchanged.

## Verification for ae9fd0a

| Check | Observed result |
| --- | --- |
| Local Linux Swift Debug / Release | 235 tests passed each on completed invocations |
| Local Python integration | 145 passed, no skips, with exact reviewed native inputs |
| macOS core Debug / Release | Both test steps and full job passed, run 37124879010; no exact count inferred |
| iOS Simulator core | 246 individually counted passing records and 1 explicit hardware Data Protection skip, run 37124879006 |
| Exact four native transformations | Executed locally and by native preparation; all input hashes checked |
| Native iOS Debug / Release | Both compiled, linked, packaged and uploaded successfully, run 37124879152 |
| Latest whole-App setup/recovery UI | Run 37124879007 is still in progress; latest observed stage is full-App Simulator compilation, NOT accepted yet |

The new tests include 17 real-file identity tests and four real-descriptor/scope tests. The latter run the actual renewal coordinator with a scripted backend entering the same nested lease pattern. A separate macOS-only Keychain test uses a unique temporary service and synthetic blob. Initial local test macro errors, a Sendable closure error and earlier Release command timeouts were corrected before the completed results; none is counted as success or hidden by disabling assertions/concurrency checking. Syntax parsing is not substituted for Xcode compilation.

The Simulator log explicitly passes actualRenewalEngineSnapshotCanEnterNativeStyleLease and failedFreshSaveNeverReturnsHeadersOrDeletesOldBlob. It skips hardware Data Protection; the skipped name has no passing record and was counted separately. The 246 passing records were unique. These are tests of production logic with synthetic providers, not real Apple login/provisioning or physical signing.

## Independently inspected artifacts

The current source ZIP matched outer SHA-256 `6d087c41189f5a082b92aa0626b56a8f38e57f2631be3e8e9d67c1e423598a61`, recorded ae9fd0a commit and inner TAR SHA-256 `c7b2e8a432c106798475b6c1a4b38150eb5be1cbd30d4ebc2095b4872f06a1e2`. All **11 changed code/test files** matched the local tested files byte-for-byte. The source archive contains 152 regular files.

The Simulator core archive matched SHA-256 `178ad0a8b9e04db0b2229ff9cfeb02bb9c2459240fe190af1df4fad917dd852b`; its actual test log was inspected.

The current Debug native artifact matched outer SHA-256 `546bb414371e527595b99214ac776924e334d30dd7330e311943103102739917`. The IPA SHA-256 `9080f946f4f7addb57c7e687f1b30cf29b00147b50742f9edb02afba21ac826e` matches its manifest and sourceCommit. Forty-seven copied core/native and transformed Swift inputs matched the tested sources byte-for-byte. The actual native log reports BUILD SUCCEEDED. No .p12/.p8/.key/.mobileprovision resource filenames were found; this is not an exhaustive secret scan. Product is unsigned Debug org.tetherless.Tetherless.XYZ0123456, version 0.1.0/build 0100, requiring user signing. Manifest device/unattended validation remains false.

## Resume next

1. Inspect complete run **37124879007** for ae9fd0a. Preserve any actual failure rather than inheriting b7b597f's UI success. Whole-App navigation does not exercise a real signed-in Anisette transaction.
2. Complete Anisette executable cache validation, promotion recovery and independently reviewed provenance. The earlier download checksum is not trust in mutable metadata or existing cache contents.
3. Finish native logging and pairing/maintenance callback lifetimes, aggregate metadata/RAM/disk limits and abandoned staging cleanup.
4. Finish remaining first-sign/self-update, supported-configuration UI, branding and dependency/distribution checks before consolidated physical acceptance.

See ANISETTE_IDENTITY.md for scope and limits. No live Apple provisioning, physical pairing, actual signing/profile installation, hardware protection, locked-screen unattended renewal or expiry crossing has been verified. Every coherent increment remains saved independently. No uncommitted feature batch is required to resume.
