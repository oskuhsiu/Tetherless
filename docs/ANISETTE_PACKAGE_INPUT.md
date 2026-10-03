# Anisette library input boundary

This increment secures the four ODA metadata/archive transfer paths and the beginning of `downloadAndCacheLibs`. It does **not** close the whole executable supply-chain or existing-cache trust review. Those remain pre-handoff blockers.

A package now requires exactly 64 ASCII hexadecimal SHA-256 characters. Missing or malformed checksums are rejected before resolving an archive. The existing Crypto SHA-256 computation is compared with that value, and mismatch throws before creating/changing the library destination or extracting anything. This replaces the former log-and-continue behavior. A checksum retrieved from the same mutable source is integrity metadata, **not** independently reviewed publisher provenance.

Concurrent calls to the same manager's download method no longer poll an unchecked Boolean and return success after an unrelated failure. A synchronized, generation-bound lease rejects overlap with an explicit busy error. Deferred/deinit release permits a later retry; repeated release cannot free a newer owner. This is an in-process download-admission guard, not proof that all provider/cache methods are race-free. Native mutations still require their process-wide lease.

Metadata, metadata-indirection and archive URLs use a namespaced copy of the existing tested `BoundedHTTPDownload`; the only source change is `HTTPDownload` → `ODAHTTPDownload`. It uses ephemeral requests, no shared cookie/credential cache, ordinary TLS verification, HTTPS-only redirects, declared and received-byte limits, cancellation, and private one-shot temporary files. A completed body is separately bounded when read. Normal completion/error/cancellation removes that transfer's directory; crash-abandoned cleanup is still pending. The complete preparation output is compiled separately by native CI.

Current limits: archive 64 MiB, Base64 transport `((64 MiB + 2) / 3) * 4` bytes, metadata up to that transport size plus 1 MiB (metadata can embed the archive), extracted total 256 MiB, one extracted file 128 MiB, 4096 entries. These are explicit product limits, not measured limits of every upstream distribution. Oversized legitimate packages must be reviewed rather than silently accepted. Base64 permits only its alphabet plus ASCII MIME whitespace; unknown characters and simultaneous direct URL/inline payload inputs are rejected. Extraction uses the existing production `SafeArchive` with stricter ODA limits and no unsafe fallback.

## Verification scope

Core tests execute the identical digest-format/comparison, Base64 and admission code. Existing downloader tests exercise actual URLSession callbacks/files with scripted HTTP responses. Integration tests compile the actual namespaced downloader and wrapper, reject an unsafe URL without a workspace leak, enforce copied-source equality, and run the complete transformation on hash-checked input. The transformation contracts verify checksum comparison precedes destination writes/extraction. These are not live CDN/TLS, Apple authentication, native library loading or independent digest-provenance tests.

## Subsequent cache and identity work

The inherited presence-only reuse and direct in-place update descriptions are now historical. Product `5a7b5ab` resolves managed receipts, revalidates the complete file inventory before client construction and publishes immutable generations without overwriting the active version. Untracked loose local libraries are refused. See ANISETTE_LIBRARY_CACHE.md and STATUS.md for the actual Darwin/native verification and the temporary four-generation limit. Product `97903f0` adds provider-owned usage pins and exclusive automatic reclamation of obsolete managed generations/stages; see CACHE_RECLAMATION.md. The four-generation bound still protects active clients but no longer permanently exhausts under unpinned updates. Independent publisher provenance and the separate HTTP-transfer staging cleanup remain unfinished.

Coherent checked identifier/adi.pb storage is separately connected at `ae9fd0a`; see ANISETTE_IDENTITY.md. Passing download/cache tests do not validate physical Keychain protection or a real Apple provisioning transaction.

## Still open

The SHA supplied by mutable remote metadata is not an independent trust root. Reviewing/pinning actual library distribution identity, binary rights and release inventory remains required. The metadata parser's depth/structure budget, all remote Anisette-server validation paths, aggregate RAM/disk reservation and complete crash-abandoned staging cleanup remain separate work. Do not treat an unsigned build as acceptance of these boundaries.
