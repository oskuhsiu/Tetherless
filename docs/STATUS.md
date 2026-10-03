# Current checkpoint — verified Anisette library generations

Updated 2026-10-03. Latest product implementation: **5a7b5ab8c138e5fe27ef955348388b8d2169c4d8**. **834f599988a0f77ea5428eb1f7b26aae11ef4f6e** corrects only a Swift Testing expression; product files are unchanged. A later documentation checkpoint does not change either implementation. Work remains on `develop`; `main` is not promoted. This is not a release candidate or physical-device handoff.

## Baseline now confirmed

The previous product `ae9fd0a` whole-App run **37124879007** completed successfully, including actual setup/recovery navigation, cold relaunch and diagnostic retention. The earlier pending status is historical. It does not substitute for this increment's UI result.

## Connected cache behavior

`AnisetteLibraryCache` records a versioned, bounded receipt linking a generation UUID, archive SHA-256, required library names and the complete extracted file/directory inventory. Every file is hashed and checked again before a provider is constructed. A loose legacy folder or an orphaned generation is never selected by file presence, timestamp or directory scan. An unreadable, corrupt or unsupported receipt is an error, not a cache miss.

Updates are extracted with the real bounded SafeArchive into a separate private generation. Required files, entry types, sizes and SHA-256 are checked; files/directories are flushed before publishing. The immutable generation is moved into place before atomic receipt replacement and readback. Failure before publication leaves the prior receipt; interruption after publication selects only the complete recorded new generation. Existing completed versions are not overwritten or deleted while a client might hold their URL.

The actual native local/remote ODA provider paths no longer load through presence-only checks or a retained provider reference. The manager transform validates input blob `d83b936e437177ba16b9664007f6a99ce7b86a2b` before modifying it, and copies the identical core cache/PrivateFileStore sources into SideSign.

This is **local integrity, not publisher authentication**. The initial digest still comes from mutable metadata. Independent binary provenance and redistribution review remain open. Local-directory mode requires a managed receipt rather than arbitrary loose libraries. Four completed/staged generations bound repeated updates until safe quiescent cleanup is implemented; this is a temporary explicit capacity limit, not finished cache garbage collection. Daily profile renewal reuses a valid generation and does not consume one generation per day. See ANISETTE_LIBRARY_CACHE.md.

## Verification

| Check | Observed result |
| --- | --- |
| Local Linux core Debug / Release | 235 existing tests passed each on completed invocations; Darwin-only cache tests do not execute here |
| Local Python integration | 149 passed with no skips against the exact retained input sources |
| Initial 5a7b5ab Darwin test compilation | Failed: a throwing call inside `#require` lacked an inner `try`; no runtime cache-test pass claimed for that run |
| Corrected 834f599 macOS core | Debug/Release and complete job passed, run **37126992225**; no exact macOS count inferred |
| Corrected 834f599 iOS Simulator core | **257 individually observed test passes and one explicit hardware Data Protection skip**, run **37126992210** |
| Twelve new cache cases on iOS Simulator | All twelve have individual passing records in the downloaded log |
| Product 5a7b5ab native iOS Debug / Release | Both compiled, linked, packaged and uploaded, run **37126826449** |
| Product 5a7b5ab whole-App Simulator | Run **37126826524** passed compilation, actual signature inspection, installation and launch; full UI execution was still in progress at this checkpoint, not accepted yet |

The compiler failure was in the test expression, not hidden by disabling tests. 834f599 evaluates the throwing read/JSON decode before the requirement macro and retains all twelve cases and assertions. Earlier local Release command timeouts are not counted as passes. Syntax parsing and source-contract checks are not substitutes for native execution.

The twelve Darwin cache tests use real filesystem IO and CryptoKit SHA-256 with an explicitly synthetic extractor. They cover repeated/reopened generations, same-size content changes, hidden extras, missing required libraries, symbolic/hard links and FIFO, bad checksums before mutation, extraction failure, interruption before/after publication, orphan/legacy rejection, corrupted/future receipts, failed receipt writes and capacity exhaustion. This is not downloaded-library execution, live CDN verification or independent publisher provenance. The native callback separately compiles against the real SafeArchive.

## Inspected artifacts

- Corrected source artifact **11275137435**: outer SHA-256 `3d558589b08d64138d2c39bf987e3413f50e12a24fa8e363ac35a076bb59cc5a`, inner TAR `8285ff8f64d3bce8d34aa08110df7e3e5b8c24fac1b1798f75ed1cdef8aa0b4f`, recorded commit 834f599. All seven changed code/test/doc files matched the local checkpoint byte-for-byte before this final documentation update. Archive contains 157 regular files.
- Simulator artifact **11274887680**: SHA-256 `dc45add537acb6640bf2d073e31c7fa26b95e2bdfc6e59d7c088de4fcc2174b1`. Its log contains each of the twelve new passing cases, 257 unique individual passes, one hardware-protection skip and TEST SUCCEEDED. The aggregate test summary includes the skipped case; it is not counted as a hardware pass.
- Native Release artifact **11275373542**: outer SHA-256 `a5b1f7b2cb8f13c5d27fec0fa9f16fc675838db75e48a04730aeb05c05b11132`. Actual IPA SHA-256 `2de3a4f1d15c25401316460033ff32969333969d0b5120027294450030bf0a28` matches the manifest. Actual main Info.plist is org.tetherless.Tetherless, version 0.1.0/build 0100. Prepared AnisetteDataManager and the two copied cache/file-store sources exactly match the tested transformation/core bytes. Native log reports BUILD SUCCEEDED. Filename inspection found no .p12/.p8/.key/.mobileprovision resources; this is not an exhaustive secret scan. Manifest still requires user signing and reports physical/unattended validation false.

## Resume next

1. Inspect completion of **37126826524** at product 5a7b5ab. Preserve any actual UI failure rather than inheriting the previous product's successful run. The 834f599 test-only commit does not trigger a new product build/UI through the existing path filters.
2. Complete safe quiescent cleanup of obsolete generations/crash-abandoned stages without deleting any client-held version, then independently review/pin actual library provenance. The present four-generation cap is not the final user experience.
3. Finish remaining native logging, pairing/maintenance callback lifetimes, metadata structure/aggregate RAM/disk limits, and remaining first-sign/self-update/configuration coverage.
4. Complete branding and binary/dependency distribution checks before one consolidated physical acceptance.

No real Apple provisioning, downloaded-library execution, physical signing/profile installation, hardware protection, locked-screen unattended renewal or expiry crossing has been verified here. Coherent code, actual failures and next actions are saved; no uncommitted feature batch is needed to resume.
