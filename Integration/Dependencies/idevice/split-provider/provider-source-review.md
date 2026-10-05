# Exact registry source review receipt

Date: 2026-10-05 UTC

## Decision and scope

The current bridge and owned-write source evidence is cleared for the reviewed staged acquisition route. No new blocking source defect was found. This is a bounded source-review conclusion, not native execution, target-provider approval, product activation or Apple-device acceptance.

The review covered authenticated selected source from OpenSSL Rust bindings, tokio-openssl and jktcp, together with the already-reviewed contributory acquisition candidate. It did not inspect or operate binaries, Mach-O/CMS/signing admission, manager/startup/data-access integration or INSTALL resources. It made no CI, external-service or ambient/global configuration changes. This receipt is the only new deliverable; frozen acquisition sources and manifests remain unchanged.

## Exact input identities

Paths below are relative to `/workspace/scratch/30ad10c9f5dc/`.

- Candidate manifest: `tetherless-contributory-acquisition/source_manifest.json`
  - SHA-256: `8eabd1496f2944178ed7897e25f4ef11640b049229b3e20dfe03580df8e93e07`
  - All five overlay files match their manifest hashes
- Retained registry-source manifest: `tetherless-component-verification/37323350367/retained/review-sources/review-source-manifest.json`
  - SHA-256: `2de722f10a2af94ffef4bb80a3257dd954ed534281efec7be72829e69607c408`
  - Provenance: parent-controlled CI run `37323350367`
  - Parent-reported verified transport ZIP SHA-256: `9daff12bf36d07ce905eea3885981a23872bc4c61268a2409849e7b37cbc28aa`; the ZIP was not independently reopened in this review
- Pinned source Cargo.lock: `tetherless-idevice-pinned-source/Cargo.lock`
  - SHA-256: `3c1a7710f0cd02f9100e91b97c9f8abc6546f115f7f3255551c990628aea0e16`
  - Matches the retained source manifest's lock hash

Four archive identities were checked against that Cargo.lock:

- `openssl 0.10.76`: `951c002c75e16ea2c65b8c7e4d3d51d5530d8dfa7d060b4776828c88cfb18ecf`
- `openssl-sys 0.9.112`: `57d55af3b3e226502be1526dfdba67ab0e9c96fc293004e79576b2b9edb0dbdb`
- `tokio-openssl 0.6.5`: `59df6849caa43bb7567f9a36f863c447d95a11d5903c9cc334ba32576a27eadd`
- `jktcp 0.1.7`: `4d3b9e59938be47d261173086c65a9352fe048951bc502109e7595b70b60cd98`

All four per-package review-checksums documents match the aggregate manifest. All 25 listed source/license files independently match their SHA-256 entries, totaling 395,979 retained file bytes. These are selected files, not a claim to have independently rehashed or reviewed every file in each crate archive. Authentication of the extracted source relies on the parent-controlled extraction provenance plus the checked lock/archive identities and retained hashes.

The retained jktcp `src/adapter.rs`, `src/stream.rs` and `src/handle.rs` are byte-identical to the earlier reviewed files under `tetherless-cancellable-host-evidence/`. Previous adapter ownership conclusions therefore apply to these exact registry bytes.

## Source findings

Registry-relative paths below resolve under the retained `review-sources/` directory.

### Polling, context and synchronous ownership

- `tokio-openssl-0.6.5/src/lib.rs:20-78,223-231`: the transport wrapper installs the current task context only around a synchronous OpenSSL call and resets it on normal return. Its underlying async Pending becomes an I/O WouldBlock result. No task is spawned. This normal-return reset is not a panic-recovery guarantee.
- `tokio-openssl-0.6.5/src/lib.rs:82-98,113-124,235-268`: handshake WANT_READ/WANT_WRITE and ordinary I/O WouldBlock become Pending. The bridge directly drives the owned stream.
- `openssl-0.10.76/src/ssl/bio.rs:33-49,85-127,175-185`: BIO state owns the underlying Rust stream; retryable I/O errors become BIO retry flags. Destruction drops that state synchronously.
- `openssl-0.10.76/src/ssl/mod.rs:3500-3548`: the SSL object owns the BIO; destruction frees SSL before its BIO method. No asynchronous shutdown or detached cleanup is introduced.

The candidate's `idevice/src/remote_pairing/tunnel/staged_packet_io.rs:51-76,100-117` retains a fixed, heap-owned pending plaintext buffer and accepts new packets only after the previous packet drains. Pending does not change the retained address, bytes or remaining length. Acceptance returns Ready without subsequently starting inner I/O. Errors become sticky. The mutex is held only during synchronous polls.

The candidate's `ffi/src/staged_acquisition.rs:194-225` retains both local owners within the controlled operation, drops the borrowed stream/adapter, completes final drainage and drops the remaining owner before success. Cancellation destroys the operation and its owners before the fixed outcome is finalized. Exact registry bridge source is consistent with this design.

### Write, flush, error and shutdown semantics

- `openssl-0.10.76/src/ssl/mod.rs:3774-3790,3960-3977`: writes use SSL_write_ex on the selected modern OpenSSL branch. Flush only delegates to the underlying transport; it does not complete an abandoned SSL_write. Consequently the owned shim's poll_drain-before-flush ordering remains essential.
- `openssl-0.10.76/src/ssl/mod.rs:3886-3908` retrieves SSL/BIO errors. The candidate maps handshake failures to a fixed staged rejection and strips adapter errors to fixed error kinds/messages; no new permissive fallback was found.
- `openssl-0.10.76/src/ssl/mod.rs:3848-3863` and `tokio-openssl-0.6.5/src/lib.rs:271-285`: explicit shutdown can finish after sending TLS close_notify, then delegates transport shutdown. It does not necessarily wait for the peer's close_notify.
- The composite performs final packet drainage and local destruction, not a demonstrated two-way TLS shutdown. It must not claim remote FIN acknowledgment or close_notify receipt.

### PSK and configuration boundary

- `openssl-0.10.76/src/ssl/mod.rs:1339-1356`: the PSK API requires a null-terminated identity and owns a Send+Sync+'static callback in context ex-data. The candidate supplies a complete 32-byte key or fails, without truncation, and offers only its two specified TLS 1.2 PSK suites.
- Certificate VerifyMode::NONE does not introduce a certificate fallback for this pure-PSK cipher selection. The independent container challenge remains required; neither PSK success nor the contributory check establishes a named hardware identity.
- `openssl-0.10.76/src/ssl/mod.rs:722-727` calls standard library initialization. `openssl-sys-0.9.112/src/lib.rs:173-184` invokes OPENSSL_init_ssl with LOAD_SSL_STRINGS and, on the selected version branch, NO_ATEXIT. It does not add NO_LOAD_CONFIG.
- Correct wording is **no custom global initialization override**. The route does trigger standard global initialization; absence of ambient configuration effects is not established. No change to that initialization or process environment was authorized or made.

## Proposed separate link profiles

These are source-backed design options requiring owner review and native verification. They are not implemented, activated or approved target inputs by this receipt.

### Host fixture profile

Use the exact verified macOS header tree and matching static archives, with target-prefixed explicit OPENSSL_INCLUDE_DIR, OPENSSL_LIB_DIR, OPENSSL_STATIC=1 and OPENSSL_NO_VENDOR=1. Select OPENSSL_LIBS=ssl:crypto explicitly. Keep this standalone host fixture profile separate from the consumer's final framework linkage.

### Apple consumer profile

Retain the existing selected OpenSSL.framework as the sole OpenSSL ABI provider at final native link. Build the Rust staticlib against exact verified headers matching that selected framework, with target-prefixed OPENSSL_LIBS set to an explicitly empty string, not omitted. Retain explicit isolated include/library-directory inputs and disable vendored discovery. The final native linker, rather than Rust's archive bundling, resolves OpenSSL symbols from that single framework.

Source basis:

- `openssl-sys-0.9.112/build/main.rs:41-44`: target-prefixed environment values take precedence
- `openssl-sys-0.9.112/build/find_normal.rs:7-12`: providing both library and include directories bypasses automatic discovery
- `openssl-sys-0.9.112/build/main.rs:47-56`: NO_VENDOR prevents a vendored branch when that feature is present
- `openssl-sys-0.9.112/build/main.rs:219-239`: an explicitly empty OPENSSL_LIBS yields an empty library list and no OpenSSL rustc-link-lib emissions; omission instead defaults to ssl and crypto
- `openssl-sys-0.9.112/build/main.rs:497-503`: explicit STATIC selects the link kind, but does not add libraries to an empty list

The existing static-input contract must not silently be treated as this different link-only profile. Keeping its default ssl/crypto bundling while also linking the existing framework risks duplicate OpenSSL ownership. An empty library list also does not itself verify the selected provider, its symbol availability or correct final linkage.

Preserve Cargo.lock and the established AWS-LC/rustls defaults. The pinned idevice Cargo.toml:120-124 routes its aws-lc feature to rustls, not openssl/aws-lc; native verification must still confirm the resolved feature graph and selected openssl-sys provider branch. Do not substitute AWS-LC/BoringSSL for the intended OpenSSL API provider.

## Remaining evidence and stopping boundary

Two relevant implementation files were not retained and have not been authenticated/reviewed here:

- `openssl-0.10.76/src/ssl/callbacks.rs`, including the raw PSK callback trampoline and context callback cleanup
- `openssl-0.10.76/src/ssl/error.rs`, including final SSL-to-I/O error conversion

The exact tokio bridge source gap is closed. These selected-source leaf gaps remain explicitly open; no complete binding audit is claimed.

Required native/provider evidence remains outstanding: exact target static archive and complete header bytes; selected framework/header correspondence; final C/Swift/Rust single-provider linking; actual provider/version/configuration and intended PSK suite behavior; no unintended native key logging; component and combined OpenSSL/borrowed-adapter runtime fixtures. Matching versions, package resolution or standalone host tests do not establish static/framework equivalence or Apple compatibility.

Per the parent's run report, the available Cargo run failed before fixtures in nested workspace setup. No Rust fixture, native target or provider runtime success is claimed by this receipt. No additional run was requested or performed for this documentation step.
