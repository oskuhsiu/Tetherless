# Current checkpoint — native Anisette identity transaction and inherited process lease

Updated 2026-10-03. Development only on develop; main is not promoted. No phone or credentials requested. This checkpoint records implementation and local verification, not a release candidate or physical acceptance.

## Previous baseline confirmed

The b7b597f full-App run 37120735783 completed successfully, including setup, signed-out certificate recovery, cold relaunch and diagnostic retention. Earlier pending status is historical. Its prior native/core evidence is in the 733c9e2 checkpoint. Do not re-diagnose historical App Group or catalog crashes without new evidence.

9cba8dea4d60f693298e10fc43328420e26748af saved the identity core before native wiring. Its original local Debug/Release suites passed 231 tests. This following increment connects it to both native providers and explicit reset paths.

## Current implementation

Identifier and adi.pb use a coherent versioned generation-bound record, checked Keychain replacement/readback and strict legacy migration. Invalid or inaccessible split data cannot cause automatic identity replacement. Fresh provider material must be saved before returning headers. Cancellation after a successful provider return preserves material first. Failed legacy cleanup retains the authoritative record; explicit reset writes a new generation or tombstone. Stale results cannot restore old state. All four native input hashes are validated before any transformed source is written.

A real integration conflict was found while wiring the new native guard: headless RenewalEngine owned a ProcessLease without conveying MutationScope ownership. Nested Anisette would have tried to relock it and failed busy. The engine now transfers the real descriptor to a task-local scope; there is no no-op acquire or lock bypass. Admitted children retain ownership and old handles cannot unlock transferred/reused descriptors. The two native repair preflights also use the shared scope. Existing policy, transaction, reconciliation and consent rules remain unchanged.

## Executed local checks for this integration

| Check | Observed result |
| --- | --- |
| Linux Swift Debug | 235 tests passed |
| Linux Swift Release | 235 tests passed on a completed invocation |
| Python integration checks | 145 passed, no skips, with exact reviewed native inputs |
| Exact four native transformations | Executed; every resulting Swift source parsed |
| New native wrapper/runtime syntax | Parsed; not Xcode typechecking |
| Fresh macOS/native/whole-App CI | Not yet accepted for this integration |

The new tests include 17 real-file identity tests and four real-descriptor/scope tests. The latter run the actual renewal coordinator with a scripted backend that enters the same nested lease pattern. A separate macOS real Keychain test uses synthetic bytes and awaits CI. Initial local test macro errors, a Sendable closure error and earlier Release command timeouts were corrected before the completed results; none is counted as success or hidden by disabling assertions/concurrency checking.

## Resume next

1. Inspect this integration's macOS core, native Debug/Release and real setup/recovery UI checks. Resolve actual compiler/transform failures narrowly; previous green builds do not validate new native code. Verify committed files against the tested local source/artifact.
2. Complete Anisette executable cache validation, promotion recovery and independently reviewed provenance. The earlier download checksum is not trust in mutable metadata or existing cache contents.
3. Finish native logging and pairing/maintenance callback lifetimes, aggregate metadata/RAM/disk limits and abandoned staging cleanup.
4. Finish remaining first-sign/self-update, supported-configuration UI, branding and dependency/distribution checks before consolidated physical acceptance.

See ANISETTE_IDENTITY.md for scope and limits. No live Apple provisioning, physical pairing, actual signing/profile installation, hardware protection, locked-screen unattended renewal or expiry crossing has been verified. Every coherent increment remains saved independently.
