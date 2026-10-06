# One-run decision: C source namespace isolation

- Current Tetherless source: 6af17537bcebfa797bf3c2659f749edd4c9d53eb
- Failed native producer: run 37446415281, attempt 1
- Verified failure report SHA-256: 1116949801b80dba4c05f371fa0cfff57ba836a6d69e936de4381dde7c3be423
- Earliest boundary: device mixed-provider C force-load link, after successful complete 382-name Rust scan and Rust/C disjointness
- Failure fingerprint: duplicate _sha512, _sha512_init, _sha512_update, _sha512_final in two members of the unchanged C provider archive
- Evidence: apple-producer-work/aarch64-apple-ios/completed/05-link-mixed_provider-c.txt and matching status JSON; pinned source declarations reveal incompatible context sizes

Hypothesis: isolating only bundled Ed25519's private SHA function identifiers removes the internal C collision while preserving both implementations, public C ABI and the complete original acceptance gates.

Discriminating change: exact 30-token/six-file source transform, authenticated full source rebuild, strict full archive export uniqueness and distinct live link-map member ownership. The new isolated producer builds only the C dependency; it does not rerun the existing Rust producer or the app.

Expected observation: all host synthetic and ASan checks succeed; both Apple C slices build with byte-identical public headers; complete C symbol sets equal the old set plus exactly four namespaced Ed25519 functions; all new global definitions are unique; actual C/Swift force-load links and live ownership maps pass in both slices; XCFramework packaging preserves tested bytes.

Unchanged assertions: no filtering/removal of duplicates, no lazy-link substitute, no mutation of the old archive, no crypto algorithm/layout change, no Rust export contract weakening, no second OpenSSL provider, no runtime activation, no device binary execution and no device acceptance claim. Subsequent Rust verification must still force-load both providers and scan the complete symbol sets.

First-run preconditions: independent candidate review; parent verifies exact branch head and publishes the isolated delta; no other current C run; existing Apple fingerprint and preinstalled Autotools match the observed contract. Missing tools stop without installation. Non-Apple tool versions are first-observed candidate evidence, not a claim of old release reproducibility.

One planned native run is justified only after this review. If the same link boundary fails, or tools/header/configuration differ, stop the full-run loop and preserve the earliest actual failure. Do not blindly retry, upgrade tools, drop dependencies, change context layouts or relax assertions. Run/job/artifact IDs and digest must be checked after completion before any C→Rust handoff. No native run has yet been requested or executed for this candidate.
