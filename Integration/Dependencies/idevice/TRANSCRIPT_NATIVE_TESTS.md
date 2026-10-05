# Synthetic composite transcript runner

This is a separate opt-in host verification profile for the three reviewed
`staged_acquisition::composite_transcript::` tests. It executes the actual staged
composite with controlled in-memory peer streams. It is not an app, artifact,
Apple compatibility or device acceptance profile.

The peer source was independently reviewed at manifest
`d3d85a874879e29021635ba4753121413b36749951d6cc4450b80cac050a8d04`.
The retained review receipt states the remaining native limitations. The fixture
feature is `tetherless-synthetic-peer`; it must stay out of production artifacts.

## Source composition

The current production acquisition/combined profiles and their overlay files stay
byte-identical. Four fixture sources live under `transcript-overlay/` and are
selected only by `candidate-profiles/transcript-only.json`. The staging helper
permits an alternate source only when the profile kind is the exact transcript
kind and its path is exactly `transcript-overlay/` plus the destination path.
Existing profiles continue using their original `overlay/` bytes.

The fixture's full upstream-based Cargo manifests are not copied over the
assembled source. The FFI edit composes its one new feature with the existing
plist unstable-stream feature. The idevice edit adds only its new feature. Both
dependency tables, both default arrays and the complete Cargo.lock are preserved
apart from the already-reviewed production plist declaration. No package/version
or dependency edge is added.

Verified local staging produces 491 transcript files. The unchanged production
acquisition and combined profiles still produce 489 and 490 files respectively.
These are source-staging checks, not compilation results.

## Exact invocation

Run `run_pairing_transcript_tests.py` with the existing required arguments:

- `--source`: pristine pinned idevice tree
- `--crate-cache`: checksum-authenticated locked crate archive directory
- `--provider-inputs`: exact captured provider tree
- `--work-dir` and `--output`: distinct fresh owned directories
- `--toolchain-lock` and `--toolchain-lock-sha256`: exact observed toolchain receipt

There is no profile selector or filter override. The runner selects idevice-ffi,
the exact three-test prefix and `openssl,tetherless-synthetic-peer`, preserving
default features. It uses the frozen/offline lock and the reviewed derived-vendor
cbindgen adapter. The production 74/94 runner is not modified.

The provider uses the already-reviewed host static archives. Header checking is
syntax-only. Commands use the existing bounded supervisor; SDK/compiler inputs,
feature graph and selected openssl-sys output are retained. Process failure,
timeout, log quota, wrong test count or input mutation prevents output publication.
Original vendor, derived vendor, workspace and provider audits run independently
in the failure path as well as on success.

Retain `completed/*.txt`, matching `*.txt.status.json`, `source-manifest.json`,
`vendor-layout.json`, `provider-input-receipt.json`, all four `*-input-audit.json`
receipts, the bounded selected OpenSSL output files and, on complete success,
`test-evidence.json`, `transcript-profile.json`, toolchain receipt and SHA256SUMS.
The fixture source/profile and provider identities must accompany any native result.

## Current evidence

Twelve controlled Python tests cover source composition, feature isolation, exact
test selection, success/failure wiring, timeout/quota rejection, provider output
selection and post-success mutation. Their successful summaries are deliberately
synthetic orchestration fixtures. The exact full-suite result for this successor is retained in its source-registration receipt.

Rust compilation and all three actual transcript fixtures remain unrun. Even a
native synthetic success would establish this controlled full path only; it would
not establish Apple/device compatibility or permit product activation.

## Stack-storage successor

This successor composes source-reviewed acquisition SHA256
`3057cc162efc267d3e8e3dee323141822adf789f226fed17292b4098ac1c5d89`
with the unchanged gated composite-test declaration. The peer and three actual
transcript fixtures are byte-identical to the reviewed original packet. Separate
repair and independent-review receipts preserve the original source and failed
native observations. This does not claim measured stack use or successful native
execution; the repaired acquisition and synthetic transcript suites still require
their own default-stack native results.
