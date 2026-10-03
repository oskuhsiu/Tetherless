# Current checkpoint — staged Anisette library generations

Updated 2026-10-03. Development stays on develop; main is unpromoted. No device or credentials requested. This is an integration increment, not a release candidate.

## Baseline

Starting head: 267068b972ac88107fbf2f6892377cd769f71f22; previous product ae9fd0a. The initial lookup of ae9fd0a full-App run 37124879007 showed real UI execution in progress, not yet accepted. Earlier b7b597f UI is historical evidence, not validation of this change. The mounted ae9fd0a source and native Debug artifacts were checksum-verified before reuse.

## Current increment

AnisetteLibraryCache binds a bounded versioned receipt to a complete SHA-256 inventory of an immutable library generation. SafeArchive builds a separate private generation; required-file checks, hashing and flushing happen before atomic receipt publication. A failed update does not erase the former version. Relaunch reads exactly the recorded generation, never an abandoned directory chosen by a scan.

The native local/remote cache and provider paths no longer authorize loading based on file presence, and no cached provider bypasses fresh verification. Missing legacy receipts are not trusted. Corrupt/inaccessible receipts fail rather than silently becoming cache misses. The cache/PrivateFileStore sources copied into SideSign are identical to the core files; the new transformation requires input blob d83b936e437177ba16b9664007f6a99ce7b86a2b after the prior package transform.

This is local integrity, NOT independent publisher provenance. The required binary release/rights review remains open. Completed generations are retained for possible existing clients; four generations/stages bound updates until quiescent cleanup is implemented. ASCII names/depth/count/byte limits are deliberate compatibility limits. See ANISETTE_LIBRARY_CACHE.md.

## Local checks before publication

- Linux Debug: 235 existing tests passed. Completed Release rerun: 235 passed. Two earlier Release command timeouts are not passes.
- Python: 149 passed with no skips using the exact retained pre-privacy/identity inputs plus the ae9fd0a cache input. The four new contracts execute the actual transformation and check copied-source equality, all loading routes and fail-closed pin/destination checks.
- Swift frontend parsed the transformed native source; this is not Xcode typechecking.
- Twelve new cache tests are defined for Darwin: real files, CryptoKit SHA-256, corrupted/same-size/extra/missing files, links/FIFO, old-versus-new publication recovery, broken pointer writes, unknown receipt versions and retention limits. They use a synthetic extractor and do NOT execute on Linux. Fresh macOS/iOS and native results are required; none is inferred from earlier green builds.

## Resume next

1. Inspect fresh core/native/UI checks for this commit. Fix concrete compiler/test failures before expanding scope. Confirm all 12 Darwin cache tests ran.
2. Finish safe quiescent cleanup of abandoned stages/obsolete generations and independent library provenance. Do not authenticate mutable metadata by merely calling its digest trusted.
3. Complete remaining logging, callback lifetimes, aggregate resource budgets and first-sign/self-update/configuration coverage, then branding/distribution review before consolidated physical acceptance.

No real Apple provisioning, downloaded-library execution, device signing, hardware protection, locked-screen renewal or expiry crossing was tested in this increment. Coherent source and the next verification boundary are saved together.
