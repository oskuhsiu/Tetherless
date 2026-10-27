# Composite pairing transcript source review

## Decision

No blocking source finding in the frozen six-file pairing fixture packet. It is suitable for a separately reviewed fixture-only registration and native test run, subject to the Cargo composition requirement below.

This is an independent source and portable-check receipt. Rust compilation, the three authored Rust tests, native TLS execution, Apple-target builds, and physical-device compatibility were not run or established by this review. No Rust, Cargo, Swift, or Xcode execution was available locally. The source packet remains unchanged.

Reviewed on 2026-10-05 by `review_composite_pairing_transcript`.

## Registration requirement

The fixture's full `ffi/Cargo.toml` is raw pinned upstream plus the new feature. The current helper registration already applies a separate change to the `plist` dependency:

```toml
plist = { version = "1.7.1", features = ["enable_unstable_features_that_may_break_with_minor_version_bumps"] }
```

Retain that existing change when adding `tetherless-synthetic-peer`. Replacing the assembled Cargo manifest with the fixture's whole copied manifest would remove the feature required by the production `plist::stream` imports. Add the fixture feature as a narrow source edit instead.

The parent acknowledged this requirement and stated that registration will compose additive edits onto the reviewed acquisition profile, preserving the existing plist feature. That future registration has not been reviewed here. It must also:

- Retain helper SHA256 `e827e5a464782009f4be7ab5557fecc449fe266836a3851bd1cbc97fa5637933`; do not restore the acquisition manifest's historical helper version
- Select the existing complete FFI acquisition feature set as well as `tetherless-synthetic-peer`; forwarding only the fixture feature to idevice does not by itself enable all FFI module gates
- Discover and execute exactly the three `staged_acquisition::composite_transcript` tests, failing a zero-test or wrong-count run
- Leave the existing 72/92 acquisition/combined profiles and Apple production profiles unchanged
- Verify that the actual resolved Apple artifact build feature graph excludes `tetherless-synthetic-peer`; its absence from default arrays alone is not that verification

## Frozen packet identity

Root: `tetherless-composite-transcript-fixtures`

- `source_manifest.json`: `d3d85a874879e29021635ba4753121413b36749951d6cc4450b80cac050a8d04`
- `verify_fixture_scope.py`: `b2c8e9649f94e2b02233d8282e68d5487b0155171d5820868215608add4c5d10`
- `CHECKPOINT.md`: `490c07346558b492d067502d75eb8e23c1f05eb18a77f7b655f2dcbcb6652638`
- Pinned source commit: `3e55c8486b2057e40c1f74aaaa1155c82341cf76`
- Unchanged `Cargo.lock`: `3c1a7710f0cd02f9100e91b97c9f8abc6546f115f7f3255551c990628aea0e16`

All paths below are relative to `Integration/Dependencies/idevice/overlay`:

| File | Bytes | SHA256 |
| --- | ---: | --- |
| `ffi/Cargo.toml` | 4516 | `c52071e53645cd9ea9dfaa88fde648c0c932ed8e9fdc54625d69121dfa03ef7d` |
| `ffi/src/staged_acquisition/composite_transcript.rs` | 11111 | `f0f976465a13be68b31e559d1917d353c0a73b21e9c03c6e66370befae4b613d` |
| `ffi/src/staged_acquisition.rs` | 28592 | `492f50eb732062ba1fa5b004255ef5b65a85a591268cb587d2a20220cc11b3a2` |
| `idevice/Cargo.toml` | 9348 | `7b829f3c80398b605e46797eea286380dc786c733d92c484527d1f49e2d2e62e` |
| `idevice/src/remote_pairing/mod.rs` | 41924 | `21a19a81099bd385a538523dff73ab3f11942aafe8d05761adf2ccb2953aee73` |
| `idevice/src/remote_pairing/staged_test_peer.rs` | 25850 | `d57d1e044bb86f2493b7dafe3ff0621c796a034ad3fca1c6e481d9fbea3863c3` |

The overlay contains exactly these six regular files and no symlinks. Both copied Rust production files are byte-identical to their production baselines followed only by the stated module declarations. Removing the new feature entries from the Cargo TOML data leaves the pinned upstream package, dependency, default-feature, and existing-feature data unchanged. Text comparisons also confirm the one-entry/comment insertions.

The idevice peer must be feature-gated rather than merely `cfg(test)` because the FFI tests consume idevice as a dependency. The FFI fixture module requires both `test` and the explicit feature. No existing default or `full` feature enables the new feature. No new dependency, lockfile replacement, C ABI, connector route, or production protocol implementation is included.

## Checks performed

1. Read `CHECKPOINT.md`, the portable verifier, the manifest, and all six scoped files. Ran `python3 tetherless-composite-transcript-fixtures/verify_fixture_scope.py`: PASS.
2. Independently checked the exact six-file set, unique manifest paths, recorded sizes, symlink absence, every SHA256, both copied production-base hashes, and the production manifest hash: PASS. This adds coverage beyond the supplied verifier, which iterates manifest entries but does not itself reject extra unlisted overlay files or check recorded sizes.
3. Verified the retained source-tree digest against its source-lock record and checked ten relevant pinned upstream files against their Git blob identities: lockfile, both Cargo manifests, idevice library and TCP module, RP TLV and pairing record, XPC macro/format, and HTTP/2 framing: PASS.
4. Verified every retained file listed by the jktcp 0.1.7, tokio-openssl 0.6.5, and openssl 0.10.76 review-checksum records. Their archive hashes occur in the unchanged lockfile: PASS. These are retained local sources; no new remote retrieval or binary review was performed.
5. Inspected the new fixture's types, visibility, feature requirements, API calls, protocol ordering, future ownership, cancellation paths, and success assertions against those sources and the current helper/RSD implementations. No definite compile/type/API error or source-visible happy-path deadlock was found. That statement is not a compiler or runtime result.

## Protocol and ownership findings

- `acquire_with_connector` and `staged_pairing::run_controlled` are actually called. The two connector invocations are constrained to the numeric endpoint and advertised listener port. Only the physical sockets are replaced by two fixed-capacity Tokio duplex pairs.
- RP uses real randomized X25519 agreement, a contributory check, HKDF/ChaCha authentication, and host Ed25519 signature verification. The peer decrypts the actual listener request, checks its TCP transport and PSK against the agreed secret, and encrypts the listener reply. It does not return a mocked acquisition success.
- TLS uses the existing OpenSSL APIs, bounded to TLS 1.2 and `PSK-AES256-CBC-SHA384`, with an empty identity and the negotiated key. The CDTunnel request is read and checked before a bounded reply selects the IPv6 endpoints, MTU, and RSD port. This review checked the peer contract, not the separately reviewed provider adapter or linked binaries.
- The bounded TCP responder uses jktcp's public `Ipv6Packet::from_reader`, `TcpPacket::parse`, and packet constructors. IPv6 input is completely acquired and bounded before calling the public reader. It checks addresses, ports, ordered sequence/acknowledgment progress, SYN/ACK establishment, and FIN observation. It is deliberately not a general TCP listener.
- The RSD exchange crosses real TCP and encoded/decoded XPC. The server sends an empty non-ACK SETTINGS preface before the SETTINGS ACK. Its two DATA frames require the actual client SETTINGS ACK and all four WINDOW_UPDATE frames. The responder retains ordered client application bytes received while waiting for TCP ACKs, avoiding loss of those control replies.
- The actual client consumes both check-in replies, then issues VendContainer, read-only AFC open, a 33-byte-bounded challenge read, a one-byte EOF probe, and file close. The fixture validates the four AFC operation numbers and bodies, and success requires both RSD and service FINs through TLS.
- The final-drain cancellation case waits for the stalled underlying flush and an independently observed service FIN. This prevents an earlier incidental flush from falsely satisfying the final-drain assertion. It does not prove the peer acknowledged the FIN; the peer intentionally does not provide that acknowledgment, and the production close does not require it.
- Client, peer, and cancellation futures are joined without spawning. The cancellation result path selects away and drops the same peer future. All twelve cancellation checkpoints stall deterministically at their selected boundary; the deadline case requires reaching AFC read before returning timeout.
- The token guard is declared before the joined futures. Normal completion drops those futures before freeing the handle, and unwinding preserves that ownership ordering. The unused raw duplex endpoints are dropped explicitly. Connected client sockets must be dropped before result publication; both tracked peer endpoints must be dropped after the overall join. Post-join read/write/flush poll counters must remain unchanged after a yield.
- Bounds include 16 KiB duplex capacity per transport, 16 KiB RP/read allocations, 64 KiB cumulative client application data, 1,024 peer packet events, 32 RSD handshake frames, and 100,000 counted read/write/flush polls per side. Each transcript has an outer ten-second guard and a shorter whole-operation deadline. No shutdown polling is used by the transcript; `TrackedIo::poll_shutdown` is not counted by the fixture counters.
- Success requires completed peer evidence, verified stage flags, the exact AFC operation sequence, two observed FINs, exactly two dials, unchanged staged record bytes, and a bounded nonzero application-byte count. The normal and choppy cases execute the same production composite. The choppy transport deliberately fragments reads/writes and injects Pending.

## Supporting source hashes

- Acquisition `source_manifest.json`: `8eabd1496f2944178ed7897e25f4ef11640b049229b3e20dfe03580df8e93e07`
- Acquisition base `ffi/src/staged_acquisition.rs`: `f52cc40cf75a28a6fa48238d9decdb20d822b3bed8e83f553b9a186f5387730d`
- Acquisition base `idevice/src/remote_pairing/mod.rs`: `738436e19a5a3e7d422ddf609404aa36d14df62c8a92a169f9bfa74df07a2c3f`
- Current helper `ffi/src/staged_pairing.rs`: `e827e5a464782009f4be7ab5557fecc449fe266836a3851bd1cbc97fa5637933`
- Current RSD HTTP/2 pump: `02f97206bef9a00d4cde14845443c23d9c0aba1d4c190588eced8b43da1100d8`
- Current RSD service parser: `016838732e04cd3cf920c4c0401fd42a8c3fc510470a9d6841de2659d65d51f4`
- Current XPC client: `133875a825e20ff09dfacd4653d81977c03718fb6802d1d2dffdb365375acb16`
- Retained source-lock: `9352c4601afa296fdd4b40c36a68a98d612b7a5d9bd8cdf86abe72270de830cd`
- Retained source-tree: `c38e6280cb3b564ba57682337cf4c536af9460c4f3b5fb5889b1a053e8ce1fa5`
- jktcp archive: `4d3b9e59938be47d261173086c65a9352fe048951bc502109e7595b70b60cd98`
- jktcp `src/packets.rs`: `f9eea859110e5c364800a22c2aeb06cade460227ee4da00d2433db01c351100a`
- jktcp `src/adapter.rs`: `12399d17b16b349ee6aae88afdf2877e64df58e8b5a63328522e5030f2c37197`

## Remaining limits and excluded scope

The three Rust tests are still uncompiled and unrun. Source review cannot establish Tokio scheduling behavior, OpenSSL provider availability, native linkage, test timing, or successful execution of the joined transcript. Native execution must retain exact source and resolved feature evidence. A passing synthetic transcript would establish the tested synthetic integration behavior; it would not establish Apple/device compatibility or complete protocol conformance.

No edits or review were made to Mach-O/CMS/signing admission, manager replacement/startup/data-access integration, or aggregate INSTALL resources. No account, device, credential, network, publication, CI-start, or other external write action was performed. The only new deliverable is this separate additive review receipt.
