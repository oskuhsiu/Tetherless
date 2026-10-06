# Web bootstrap implementation and acceptance gates

Date: 2026-10-06. Scope: BOOT-01 from `ORIGINAL_PLAN.md`.

## Status

This is a functional **development prototype**, not a completed clean-phone
bootstrap or production signing service. It preserves the original free Personal
Team goal. A paid Ad Hoc helper is separate and does not count as that goal.
No deployment, Pages configuration, release, real Apple account action, certificate
creation/revocation, device enrollment or iPhone installation was performed.

The new paths are isolated from native integration:

- `WebBootstrap/`: relative-base static frontend, local signer, metadata checks,
  tests and pinned licensed runtime
- `Tools/WebBootstrapService/`: genuine transient Apple account/provisioning and
  UDID Profile Service adapter
- This document

Existing App/native CI/signing-admission paths are unchanged.

## Implemented route

1. Select a trusted IPA. No unverified Tetherless download is hardcoded.
2. On a separately hosted service origin, optionally obtain a device UDID with a
   ten-minute, challenge-bound Profile Service exchange. This requests UDID,
   product and OS version only, not serial/IMEI, MDM enrollment or a trust root.
3. Explicitly approve transmitting credentials to that service and anisette
   identity data to the named anisette provider; perform SRP/GrandSlam and
   trusted-device or SMS 2FA through actual pinned isideload APIs.
4. Choose the Team and confirm device/App ID/certificate mutations. Browser
   generates RSA2048/SHA256 CSR and retains the private key. The service receives
   only the CSR, registers the selected resources and issues/reuses a matching
   development certificate. It never silently revokes another certificate.
5. For recognized Tetherless input IDs, also request exactly the artifact-derived
   shared App Group and assign it to every supplied app/extension. Check each
   returned profile's CMS signature integrity and metadata. Apple signer-chain
   trust is not independently established.
6. Assemble P12 in browser memory, check key/certificate/profile/Team/bundle/device
   consistency, sign with the real zsign WASM engine in a disposable worker, and
   check that each output bundle embeds exactly its intended profile.
7. Download the signed IPA. **This is not installation.** The free Personal Team
   Safari first-install transport remains unproved. The paid Ad Hoc-only helper
   can generate a manifest and install URL for separately authorized user-owned
   HTTPS hosting; it does not upload anything.

A second, already-materialized P12/profile route supports the same local signer.
It is a distinct partial route, not a claim that account-only onboarding is done.

## Tetherless identity and handoff

Pinned source metadata from SideStore `0dd743f75afc358b0ba4a002feb5f19474492371`,
after Tetherless's build patch, has these defaults:

- Release main: `org.tetherless.Tetherless`
- AltWidget: `<main>.AltWidget`
- SideBackup: `<main>.SideBackup`
- Debug: main already appends `.<DEVELOPMENT_TEAM>` before extension suffixes
- Default/free shared group: `group.<main>`, required by all three templates

The web route reads actual IPA bundle IDs, recognizes only these known forms,
and preserves them. It neither assumes all extensions are present nor silently
appends another Team suffix. An unavailable App ID/group causes a real failure;
there is no automatic rename. Alternate paid push/kernel entitlement templates
are not requested. The final built artifact and signed profiles remain authoritative.
`org.tetherless.profile-renewal` is a separate background-task identifier and is
not changed by this implementation.

The browser private key is never embedded as `ALTCertificate.p12` or transferred
into the installed app. The native app must establish a device-local Keychain
identity on first authorized login. Same Team alone does not make profile-only
renewal possible with a different certificate. Source contains an explicit
foreground full self-reinstall path, conditional on an available certificate slot,
working installation transport and user confirmation; integration/data/Keychain
continuity is unverified. This web work does not close or modify that native gate.
Never recommend uninstalling first as the normal update procedure.

## Data and cancellation

- Apple password/2FA/session: transient service memory; bearer kept in JS memory,
  never URL, browser storage or deliberate logs
- RSA private key/P12/profile/IPA/output: current browser memory only; cancel/clear
  terminates the signing worker and revokes Blob output URLs
- UDID round trip: enrollment ID and expiry only in tab-scoped sessionStorage;
  capability in an enrollment-only Secure/HttpOnly/SameSite=Lax cookie
- The collected UDID is explicitly untrusted device metadata until the user reviews
  and separately approves registration. CMS integrity is not Apple-device identity
- Idempotent provisioning: original key/CSR/request retained in memory across
  uncertain HTTP responses; identical retry retrieves cached status/result without
  another issuance. Changed request is rejected. There is no durable crash journal
- Ten-minute session expiry, explicit cancellation or tab close discards pending
  key/CSR. If an Apple mutation may already have committed, inspect account state
  before any new request. Cancellation cannot undo committed Apple actions

JavaScript garbage collection and third-party runtime copies prevent a secure
immediate-zeroization claim. No analytics, external certificate catalog, remote IPA
proxy, enterprise certificate sharing or automatic uploading is included.

## Input/runtime restrictions

Ordinary ZIP limits: 150 MiB compressed, 384 MiB declared expanded size, 20,000
entries; no traversal, links/special files, duplicate/case-colliding names, split or
ZIP64 archives, encrypted entries, unsupported methods or inconsistent local names.
Binary plist metadata uses a pinned BSD-licensed parser with explicit input,
object, traversal, depth, cycle and materialization budgets, plus a cancellable
worker. This is a focused JS dependency change, not native parser work.

P12 must contain one RSA private key and matching certificate. Every app/extension
needs one exact profile with no extras. Wildcards and suffix-ambiguous bundle IDs
are rejected because the pinned runtime's multi-profile fallback can otherwise
choose the wrong profile. Output embedded profile bytes are compared per bundle.
No custom entitlement overrides, library injection, extension stripping, hash-only
`-a` signing or trust bypass is exposed. This is not a full Mach-O entitlement,
Apple chain/revocation or production security audit.

## Verification evidence

Frontend: Node unit tests, real pinned WASM certificate-backed synthetic signing,
metadata/profile consistency, DOM-emulated cancellation/2FA/UDID return-state
regressions, and a static production build. DOM service/worker tests use mocks;
WASM tests execute the actual runtime against self-signed synthetic material.
These fixtures are not Apple-issued and cannot establish iOS acceptance.

Backend: `Tools/WebBootstrapService/VERIFICATION.md` and `verification.json` record
19 offline Rust tests, formatting, strict clippy, optimized build, and actual local
release HTTP/static/Origin/Host/body-limit checks. Tests exercise synthetic CSR/CMS,
nonce/replay/expiry/cancellation, parser lifetime and idempotence. No live Apple
traffic was used.

Browser acceptance did **not** run: local Chromium launch was blocked by the
execution environment's IPC restriction, including an approved escalation, and
the cloud browser blocked localhost. No restriction workaround was attempted.
The Playwright suite remains available for a suitable authorized environment.
No Safari/iPhone, visual mobile-layout, real profile installation, live 2FA, real
Apple certificate/profile, OTA or native self-update acceptance is claimed.

`npm audit --omit=dev` reports one unpatched high-severity node-forge signature
verification advisory, GHSA-86w9-cpqp-85rv. The application does not use that
verification API, but the dependency risk remains tracked in
`WebBootstrap/THIRD_PARTY_NOTICES.md` and `runtime-audit.json`. There is no clean-audit
claim. Runtime hashes establish the retrieved pin, not a reproducible WASM rebuild.

## Required next decisions and acceptance

1. Choose and authorize a separately hosted HTTPS service origin. Account-password
   transactions do not belong on GitHub Pages. No provider, spending, sharing or
   deployment has been authorized by this code change.
2. Run the included browser suite and inspect phone layout in an authorized browser.
3. Bind a genuine unsigned Tetherless artifact using its source commit and SHA-256;
   verify all emitted IDs and default entitlements before offering a download.
4. With separately authorized account actions, validate free-Team login/2FA,
   certificate capacity, exact App Groups and every resulting profile.
5. On an explicitly approved clean iPhone, validate Profile Service prompts/return,
   Developer Mode/trust and the real free-Team installation transport. Keep paid
   Ad Hoc evidence separate. An install URL or successful download is not success.
6. Verify first native login, same-Team/certificate transition, complete foreground
   self-reinstall, data/Keychain preservation and later self-signing. Until then,
   BOOT-01 and account-only end-to-end bootstrap stay open.

## Primary references

- [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
- [Apple Profile Service exchange](https://developer.apple.com/library/archive/documentation/NetworkingInternet/Conceptual/iPhoneOTAConfiguration/profile-service/profile-service.html)
- [Pinned isideload source](https://github.com/nab138/isideload/tree/dd442588370060b8776b1276a1acd717b6668b26)
- [Pinned SylvaSigner runtime/source](https://github.com/AntonP29/SylvaSigner/tree/f7127d6857a6aaa919b7430ef73baa262fe28070)
