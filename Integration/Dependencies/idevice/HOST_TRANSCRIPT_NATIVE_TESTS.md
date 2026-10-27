# Synthetic host-generation transcript runner

This separate opt-in profile selects exactly ten
`bounded_pairing_host::host_transcript::` tests. They exercise the actual caller-owned-FD
host FFI with a controlled peer, including genuine SRP/M5/M6 success, PIN and
identity failures, cancellation, deadlines, output handling and joined teardown.
Native execution remains pending. Python orchestration results do not establish
Rust, Apple or device compatibility.

## Source composition

The production base includes the source-reviewed acquisition stack repair and
bounded M5 controller-identity verification. Its shared helper, defaults,
dependencies, Cargo.lock, provider inputs and runtime limits remain unchanged.
The host fixture appends only gated declarations to the current production host
module and acquisition-enabled remote-pairing module. It does not replace that
module with the older pristine-based fixture copy.

Four isolated sources under `host-transcript-overlay/` provide those two module
variants and the peer/test bodies. The staging helper accepts that namespace only
for `registered-host-transcript-tests`, with each source path exactly matching its
destination path. Composite transcript sources use their separate namespace.

The profile composes the synthetic feature into the existing FFI manifest while
retaining the production plist streaming feature. Both dependency tables and
default-feature arrays remain unchanged. The exact selected features are
`openssl,remote_pairing,tetherless-synthetic-peer`; the explicit FFI
`remote_pairing` selection keeps the host module present. The synthetic feature
must stay excluded from built application artifacts.

The fixture sources originate in source manifest
`7b0a80e073c106cfde25003343642de9d92b65a17368d7f5f1dd456a76b30f13`.
The separate bounded M5 security successor is source manifest
`a4b8e30b2a83e2dca1122221021b3a44be8647dfe239cb1c139bc60437dcc3a9`.
Both original and superseding source/review receipts are retained. The eight
identity-negative scenarios use valid M5 AEAD and require native protocol failure,
cleared output and no bytes of M6, then the existing joined ownership checks.
These are authored assertions until real native execution succeeds.

## Invocation and evidence

Run `run_pairing_host_transcript_tests.py` with the same required source,
crate-cache, provider-inputs, work-dir, output, toolchain-lock and
toolchain-lock-sha256 arguments as the reviewed component runner. There is no
filter or profile override. The exact expected count is ten; zero-test success,
wrong counts, nonzero exits, timeout, log quota or changed inputs cannot publish
success evidence.

The runner retains the bounded native logs and status JSON, exact source profile,
feature graph, syntax-only header probe, SDK/compiler paths, selected OpenSSL
build output, and independently attempted original-vendor, derived-vendor,
workspace and provider audits. Work and output directories must be fresh.
The process supervisor and provider checks are the shared reviewed implementations.

This profile's ten cases are separate from the six bounded-controller signature
unit cases selected by the production host/combined runners. Do not add repeated
counts together as independent protocol coverage. Passing this synthetic path
would not prove physical-device identity, interoperability or full product
activation; those remain separate acceptance conditions.
