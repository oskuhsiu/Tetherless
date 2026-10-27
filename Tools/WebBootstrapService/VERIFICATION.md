# Verification — 2026-10-06 UTC

The exact production adapter compiles against pinned isideload with Rust 1.99.0.
The machine uses system OpenSSL 3.5.7. Cargo.lock records the resolved graph.

Passed on the final source recorded in verification.json:
- cargo test --locked --all-targets: 19 passed, 0 failed
- cargo clippy --locked --all-targets -- -D warnings
- cargo fmt --all -- --check
- cargo build --locked --release
- Optimized-binary HTTP smoke: health/protocol/no-store, actual built frontend,
  hostile Host rejection, missing/hostile Origin rejection before account login,
  HTTPS-only Profile Service creation and oversized-body rejection

No test submitted a valid account-login request to the service. No Apple account,
2FA challenge, certificate issuance, App ID/group/device registration, device
profile installation or iPhone acceptance was performed. Runtime tests start and
stop the service and client in one process namespace; an earlier cross-command
loopback check was connection-refused because command namespaces are isolated.
That failed smoke was replaced by the successful same-namespace test, not counted
as success.

Tests use synthetic local authentication/provisioning state and ephemeral
self-signed CMS fixtures. They cover request/identifier/CSR constraints, fixed
errors, bearer/Origin/Host gates, cached uncertain provisioning (no retry), profile
metadata requirements, App Group-specific consent, enrollment privacy/cookies,
CMS signature integrity, nonce mismatch, corrupted/unsigned/oversized callbacks,
replay, cancellation/expiry and cancellation-safe blocking-parser capacity.
They do not simulate a successful Apple transport exchange or certify iOS trust.

The release binary is a build artifact, not a distributable release. Toolchain
and target directories are ignored and must not be committed or packaged. Public
synthetic fixture certificates/CSR contain no Apple/account data or private key.
See README.md for remaining end-to-end installation and native-takeover gates.
