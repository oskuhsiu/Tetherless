# Browser certificate lifecycle

This document describes the implementation and test boundaries, not Apple or iPhone acceptance.

## Data flow and explicit actions

1. After authenticated Team/device selection, the user either creates an RSA identity in this browser or imports an encrypted Tetherless recovery file / existing P12. P12 parsing runs in a cancellable, 15-second local Worker; no imported private key or password is sent to the service.
2. Before the first certificate request, the browser downloads an encrypted recovery file. The user must separately confirm that they actually saved the file and password. A download click is **not** proof of saving it. There is no localStorage, IndexedDB, backend or third-party private-key custody.
3. The recovery file encrypts private key, exact CSR, Team and optional public certificate using PBKDF2-SHA256 (310,000 iterations) and AES-256-GCM, random 16-byte salt / 12-byte IV. Only the public CSR, Team/device/app selection and explicit intent go to the service.
4. Only a newly-created identity with separate new-certificate consent requests `createOrReuse`. An imported recovery file or P12 always requests `reuseOnly`, even if its UI checkbox is manipulated. A missing certificate is **not** evidence that Apple has no pending request. No automatic create/revoke/reissue loop exists.
5. `/certificate` returns a matching public certificate before downstream profile work. Encrypted P12 and updated recovery export therefore remain available if `/provision` fails. Retry uses the exact retained CSR and selection. `/provision` cannot issue a certificate.
6. The user can download an AES-256 encrypted P12 (PBKDF2-HMAC-SHA256, 100,000 iterations) and each profile explicitly. P12 export is tested against the pinned real WASM signer. New P12 export passwords must be 12–1024 printable ASCII characters: Forge's Unicode PBES2 password encoding is not interoperable with the pinned WASM/OpenSSL and Apple importer. This restriction does not affect Unicode AES-GCM recovery passwords. Changing the export password does not change already-downloaded recovery files. Keeping a P12 does not extend certificate/profile expiry or guarantee iOS installation.
7. Cancellation, pagehide or original session expiry clears in-memory identity and passwords. JavaScript cannot guarantee immediate memory erasure. The saved encrypted file is the recovery path; users should import it rather than make another identity.

## Recovery limits

An imported recovery file downloaded **before any request was dispatched** is indistinguishable from the same file whose CSR was later dispatched and whose response was lost. Consequently imports remain readback-only; the UI does not infer permission to issue from a missing certificate. This is a deliberate safety limitation. A future “never submitted” recovery action needs a separate, explicit protocol and must not convert uncertain operations into issuance automatically. A `.cer` or IPA cannot recover a lost private key.

P12 admission checks one RSA key, key mathematics, matching certificate/public key, Team and validity dates. It does not establish Apple's issuer chain, portal revocation status, or installation eligibility. The guided route must read back the matching certificate from Apple via the authenticated service; the existing advanced local signing route retains its separate verification limits.

## Certificate list and revocation

The read-only list is an explicit user action; it is Apple's current response, not complete issuance history and not a pending-CSR list. Missing metadata stays missing. Machine name `Tetherless Web` is not proof of origin.

Revocation requires an exact selected certificate ID/serial, server snapshot confirmation token and fresh unchecked consent acknowledging that profiles become invalid and installed apps may stop launching. List/revoke/identity preparation and new provisioning cannot race while a management operation is active. A successful response must match Team and certificate ID and affirm `revoked: true`; any mismatch is uncertain and prompts a read-only refresh, never automatic resend. After confirmed revocation, the session is cleared; a replacement requires a separate login, backup and new-certificate authorization.

No developer test uses a real Apple account, issues/revokes a live certificate or sends credentials. Synthetic files explicitly identify themselves as NOT APPLE.

## Regression evidence

- `certificate-recovery.test.mjs`: encrypted round trip, password/tamper/cost/size/null rejection, exact CSR/key binding, damaged RSA private exponent, mismatched Team/certificate/dates, AES-P12 import/export, KDF work bounds.
- `ui-state.test.mjs`: pre-dispatch backup/ack gates, early P12 after profile failure, same-CSR retries, pagehide/reload recovery, cancellation of late replies, exact and uncertain revocation responses, held-revoke serialization, cancelable P12 import.
- `wasm.test.mjs`: actual pinned signer accepts the new AES-256 P12 output and signs a synthetic Mach-O IPA.
- `browser/certificate-lifecycle.spec.js`: production build over real loopback HTTP, real WebCrypto/downloads/WASM, profile failure/retry, expiry/two tabs/reload import, duplicate clicks, late cancellation and exact revocation. Wired to Chromium and WebKit; execution status must be reported from actual CI/runtime, not inferred from source or DOM tests.

The browser tests fence requests to their exact loopback origin. They are not evidence of real Apple authentication, iOS Settings callbacks, a free Personal Team's first installation, or replacing a running native app.

## Dependency advisory and CSR verification boundary

The older [GHSA-86w9-cpqp-85rv / CVE-2026-85393](https://github.com/advisories/GHSA-86w9-cpqp-85rv) page, updated 2026-10-01, still said no patched version when initially checked. The newer maintainer [GHSA-2g46-22mc-6gwp](https://github.com/digitalbazaar/forge/security/advisories/GHSA-2g46-22mc-6gwp), published 2026-10-27, identifies 1.4.1 as patched. This implementation pins official node-forge **1.4.2**, which includes that fix; the conflicting older database metadata is not treated as current release guidance. Vite is separately pinned to **8.1.6** for its published development-server fixes. See `docs/CERTIFICATE_DEPENDENCY_REVIEW.md` for source, integrity and final audit evidence.

Product CSR verification now uses platform WebCrypto `RSASSA-PKCS1-v1_5` with SHA-256, original CertificationRequestInfo DER bytes, and SPKI. The bounded DER framing checks are not an alternative signature verifier: DigestInfo and RSA padding validation belong to WebCrypto. No product entry point calls Forge's affected CSR/RSA verifier. Generated and imported identities retain RSA mathematical consistency and exact public-key binding checks. Missing platform support, unsupported algorithms or tampering fail closed, without a Forge fallback.

Regression tests construct a synthetic malformed nested DigestAlgorithm signature historically accepted by Forge 1.4.0; both pinned Forge 1.4.2 and the platform now reject it, including encrypted recovery import and browser UI. Additional tests replace Forge CSR verification with throwing traps, prove valid create/import still succeeds, and exercise missing platform API. The platform verifier remains defense in depth even after the package upgrade; a passing test or audit is not a claim that every possible vulnerability is absent.
