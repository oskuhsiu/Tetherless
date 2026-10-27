# Additive host-transcript source-review receipt

Reviewed 2026-10-05. No blocking fixture defect was found in the frozen candidate. This is source approval for separate native validation, not successful execution evidence. This receipt is outside the frozen candidate and does not amend its manifest or source files.

## Frozen identity and provenance

Candidate: `/workspace/scratch/30ad10c9f5dc/tetherless-host-transcript-fixtures`

- Candidate `source_manifest.json` SHA-256: `7b0a80e073c106cfde25003343642de9d92b65a17368d7f5f1dd456a76b30f13`
- Candidate `host-transcript.patch` SHA-256: `4c2b1e224c2f0696924493ea0627c9c00a3ed225a684093641916b392a8458c1`
- Host baseline `tetherless-host-generation/source_manifest.json` SHA-256: `6ea4370a0ec3c9470ff2c6690c576bc93b063cf010be9d14df5928e82949818a`
- Declared upstream commit: `3e55c8486b2057e40c1f74aaaa1155c82341cf76`
- Pinned Cargo.lock SHA-256: `3c1a7710f0cd02f9100e91b97c9f8abc6546f115f7f3255551c990628aea0e16`

The portable verifier passed, including whitespace-clean six-file patch application to a private temporary tree and exact reconstruction of the candidate bytes. Independent checks verified every candidate manifest file's recorded size/hash and every recorded input hash. Existing production source prefixes, dependencies, defaults and lock remain unchanged. The retained idevice-srp 0.6.0 source hashes match its review manifest and locked archive checksum `d84c9637ebbdfa523f352b62c8cf791288b3fbf59f6eac6c57c7c9949f5924b2`.

The supplied pinned source tree has no Git metadata; the declared upstream commit is provenance supplied by the packet, while the relevant recorded source bytes and lock were checked directly. Seven Rust tests are present, with no additional test or production file changes.

## Source findings

- The success fixture calls actual `tetherless_pairing_host_prepare` and `tetherless_pairing_host_accept_fd`, uses the callback's six PIN bytes for genuine SRP, authenticates M5/M6 with the derived key, independently verifies the accessory signature, and compares the returned record against the prepared identity/keypair, peer altIRK and advertised identity. Cancellation and final free also use the actual FFI functions.
- Four frames per direction are explicitly asserted on success. Wrong-PIN and tampered-M5 cases require the actual native protocol failure and cleared output. Capacity rejection is followed by a genuine successful transcript on the same token.
- The descendant helper's private-method access, transport trait implementation, Send/Sync requirements, scoped captures and buffer borrows appear compatible with the pinned APIs. This is a source assessment, not compiler acceptance.
- The valid false greeting avoids the unsupported pair-verify request without relaxing the responder. The bounded M5 decorator preserves controller identifier/public key/signature and adds the synthetic UDID using the real SRP-derived setup key. Independent source arithmetic confirms original/adapted M5 Info sizes of 192/232 bytes and M6 Info of 204 bytes.
- Callback work is bounded and non-unwinding. Token/context remain alive through native return, explicit thread join and all cancellation work. The native call runs on a scoped blocking OS worker outside Tokio.
- Caller-wait expiry requests cancellation and awaits actual native completion; it does not abandon a JoinHandle. The fixture guard failure still reaches the unconditional scoped join. Scope unwinding also joins before shared ownership expires.
- The original FD stays open and untouched during native execution. Its flags/options are checked after return, then closure and peer EOF check for surviving native duplicates. Native, peer and cancellation work finish before final free.
- Frame, wire, JSON/OPACK, polling, deadline, drain and output limits are present. Logging-sensitive execution is covered by NoSubscriber, and assertions do not print PIN, key or record contents.

## Required composition and registration handling

1. Append the `host_test_phone` declaration onto the current acquisition-enabled `idevice/src/remote_pairing/mod.rs`; do not overwrite that file with the candidate's pristine-based full-file overlay. Retain existing production/acquisition functions and declarations.
2. Preserve the current FFI plist `unstable-stream` feature when composing Cargo edits. Add the identical synthetic feature declarations only once, without changing existing dependencies/defaults/lock.
3. Retain the reviewed production host opack/responder overlays and the existing host-module lib declaration.
4. Enable the separate FFI `remote_pairing` feature. The synthetic forwarding feature enables idevice's feature, not the separate FFI host-module gate.
5. Explicitly select `tetherless-synthetic-peer` only for the fixture. Keep it excluded from production artifacts.
6. Register a distinct native case using the exact filter `bounded_pairing_host::host_transcript::` and require exactly seven tests. A zero-test green command is not evidence.
7. Registration/publication and CI remain parent-owned. Existing evidence must not be relabelled by this additive source receipt.

## Claim boundaries and execution status

The frozen production host verifies the SRP proof and M5 AEAD authentication but does **not** verify the controller's M5 Ed25519 signature. The fixture neither changes that behavior nor claims otherwise. The phone independently verifies the host's M6 accessory signature and identity.

Rust compilation and all seven native tests are unrun; rustc, cargo and swift were unavailable in the review environment. No native-success, Apple-build, physical-device compatibility, or full end-to-end product result is claimed. Native validation may expose compiler or runtime issues that source review cannot establish.

No frozen candidate or production source files were edited. Publication and CI were not started. No external writes, account/device/credential actions, Mach-O/CMS/signing admission, manager/startup/data-access integration, or aggregate INSTALL-resource inspection/edit/re-review were performed. Only this separate receipt was written after the source review was completed and saving it was requested.
