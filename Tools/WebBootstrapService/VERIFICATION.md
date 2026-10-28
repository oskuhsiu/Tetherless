# Certificate lifecycle verification — 2026-10-28 UTC

Local candidate evidence is recorded by source hash in
`verification-certificate-lifecycle.json`; repository-wide/remote CI and the final
integration SHA are tracked separately in `docs/STATUS.md`.

- `cargo test --locked --offline --all-targets`: **62 passed, 0 failed**.
  Baseline: 40; new tests: 18 certificate lifecycle, 3 route/profile/deadline,
  1 safe request-default test. One old cached-failure test now verifies the
  profiles-only resumable behavior rather than permanently cached errors.
- `cargo build --locked --offline --release`: passed, Rust 1.99.0.
- Optimized binary, same-process-namespace loopback HTTP smoke
  (`python3 tests/http_certificate_smoke.py /path/to/release/binary`): **7 checks passed**
  (new capability + no-store, each of three certificate routes rejects unknown
  sessions and hostile Origins). No account session was started.
- `git diff --check`: passed. Newly changed Rust code was rustfmt-formatted.
  No claim of a current whole-project `cargo fmt --check` or clippy pass is made;
  clippy is not installed in this executor.

The new injected-adapter tests cover quota rejection → explicit exact revocation
→ separate creation; unknown-submit guards surviving unrelated revocation;
same-key readback; stale-directory concurrent sessions issuing once; cancel and
expiry; imported recovery remaining reuse-only after a process restart; duplicate
keys/IDs; wrong Team/session/confirmation and fresh-record changes; one-shot
uncertain revocation; bounded catalogs/guard capacity; and failed profile-stage
admission reopening without reaching CSR issuance.

Limitations: these tests do not simulate all real Apple profile operations or
prove Apple authentication, issuance, revocation, provisioning trust or device
installation. There were no live Apple requests, credentials or account changes.
Private keys stay in the browser/device; backend fixtures contain public
synthetic certificates and CSRs only. Process-memory guards do not survive a
restart and are not shared between server instances. Upstream DeveloperSession
response parsing retains its existing implementation; catalog/DER bounds here
are post-parse, not a claimed raw-network-body limit.

---

## Historical verification (not evidence for this candidate)

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
