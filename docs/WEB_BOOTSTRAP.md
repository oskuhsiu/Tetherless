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

## Progressive default journey

The default view now shows the Apple-account journey, three compact progress
steps and the official-release availability. P12, profile, custom IPA and paid
Ad Hoc hosting controls are explicit advanced choices rather than four expanded
forms. An empty service configuration remains visibly unavailable; the page
cannot collect credentials or pretend to complete a login on static hosting.

1. Use the **official Tetherless GitHub Release** by default. The shipped
   `officialRelease` value is `null`: no genuine current unsigned App asset exists
   yet, so there is no fallback to an old release. A user may explicitly choose
   a custom IPA or the existing manual certificate route instead.
2. The default device route logs in first, then reads the selected Team's
   registered devices. Only active/selectable records can be explicitly chosen;
   even a sole record is not selected automatically. This identifies an Apple
   account record, not the current iPhone. A separate new-device route is an
   explicit choice: collect/enter its UDID before login when profile collection
   is needed. The Settings round trip clears Apple sessions and may require a
   new login. Only enrollment ID/expiry persist, never Apple secrets. A fresh
   document restores the new-device route only for a valid, unexpired existing
   enrollment ID; it never starts a new collection or registers a device.
3. Approve the named service/anisette data transmission and log in. Required
   trusted-device/SMS 2FA is shown only when requested. A pinned official package
   is acquired and hash checked before credentials are posted; cancellation or
   consent revocation prevents that post. A missing/unreadable package blocks
   the official route without silently switching sources.
4. The actual IPA bundle IDs and derived App Group are inspected and displayed
   before mutation consent, and the session stays bound to that exact IPA. A
   single Team is selected and named automatically; multiple Teams remain an
   explicit choice. Confirm the device, rights to the IPA, and device/App ID/
   certificate/App Group mutations. One approval starts CSR/key generation,
   provisioning, P12 assembly, bounded inspection and local WASM signing. There
   is no separate P12 upload, profile upload or second Sign click in this route.
5. Uncertain provisioning keeps the original private key, exact request, IPA and
   selection. Retry queries that same request, with inputs frozen; it does not
   issue another key/certificate. Cancellation/expiry discards it and warns that
   committed Apple actions are not undone.
6. Signed output opens **installation guidance, not an installed state**. Direct
   free Personal Team installation remains visibly disabled. The existing manual
   paid Ad Hoc helper can expose an explicit `itms-services` handoff only after
   local signing with eligible profiles, device binding and the user's HTTPS
   manifest. It neither uploads files nor verifies remote content or installation.

The browser's private key remains local. Exact bundle IDs and recognized
Tetherless App Groups are preserved. System profile/installation, trust and
Developer Mode confirmations must be completed by the user; they are not
represented as automatable.

### Existing registered-device contract

The follow-on frontend requires the corresponding separately reviewed backend
route: `GET /v1/sessions/{id}/teams/{teamId}/devices`, authenticated with the
in-memory Bearer token and same-origin gate cookie, with redirects rejected.
The response is `{teamId, devices:[{udid,name,status,selectable}]}`. Team IDs are
1–64 ASCII alphanumerics. Responses are capped at 512 KiB and 1000 records; names
must be nonempty, control-free and at most 128 UTF-8 bytes. Wrong-Team, malformed,
duplicate, oversized or failed responses cannot enable provisioning. Missing or
unknown status is not eligibility; only `active` plus `selectable:true` is usable.

Changing Team, rereading the list, or cancellation clears selection and consent;
old responses are aborted and generation-checked. Multiple Teams require an
explicit choice. After selection, the full name/UDID and the exact mutation plan
are visible. The device selector cannot change after provisioning begins.

The existing-only request sets `device.existingOnly:true` and exactly one of:

- `use-existing-device-register-app-ids-and-issue-certificate`
- `use-existing-device-register-app-ids-app-group-and-issue-certificate`

The backend independently rechecks active membership before certificate mutation
and never registers a missing device. The new-device route retains its original
explicit registration consent. There is no fallback between routes. Empty/error
lists remain blocked with read-only retry. A submitted request, including a cached
`deviceNotAvailable` preflight failure, retains its original key/CSR/selection:
choosing a different request requires cancel/restart. Nothing here establishes
actual Apple authorization, current-phone identity or installation acceptance.

### Official Release contract

`WebBootstrap/public/config.json` contains `accountServiceUrl` and
`officialRelease`. Both are `null` in this candidate. A deployment owner must
review the actual release/build evidence before filling in this manifest:

- `repository` (exactly `oskuhsiu/Tetherless`), `tag`, `assetId`, `assetName`, `assetUrl`
- `size` (integer bytes, at most 150 MiB), `sha256` (64 lowercase hex)
- `sourceCommit`, `buildHeadSha` (40 lowercase hex), `buildRunId`,
  `runAttempt` (positive integer)

Asset/run IDs are decimal strings. The asset URL must exactly match
`https://github.com/{repository}/releases/download/{encoded tag}/{encoded assetName}`.
The pinned configuration is the trust root, not an unauthenticated lookup of
`latest`. It records source/build identities for review; the browser does not
independently attest the build. Before adopting downloaded or locally selected
official bytes it checks exact size and SHA-256. Direct GitHub acquisition is
credential-free, no-referrer, CORS-only, limited to 120 seconds and 150 MiB, with
an incremental exact-size cap shared with the existing archive parser input
budget. The 150 MiB cap is unchanged; the not-yet-produced actual Tetherless App
has not demonstrated that it fits. A larger artifact fails early with a clear
size error and requires a separately measured/reviewed budget decision. Only GitHub and its release-assets redirect host
are allowed by the page CSP. Missing assets, CORS failures, digest mismatches and
cancellation leave the official path blocked. The same pinned asset may be
manually downloaded and selected for the same hash check. No proxy, endpoint
selection, release publication, backend hosting extension or deployment is added.

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

- Same-origin service/health/config/delete requests may carry the deployment
  gate cookie; route origins are enforced and service/enrollment redirects are
  rejected, including cleanup requests. GitHub acquisition omits credentials
  and referrers. There is no cross-origin credential API
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

The preceding frontend passed actual Chromium CI in
[run 37420583887](https://github.com/oskuhsiu/Tetherless/actions/runs/37420583887):
**18/18** root/project-subpath cases, including actual WASM signing of synthetic
IPAs, download inspection, binary plist worker loading, cancellation/retry,
Back/clear behavior and mobile screenshots. The screenshot used to design this
simplification is real Chromium output from that run, not a mockup.

That run does **not** validate this new progressive UI delta. This candidate's
Node/DOM tests, static build, request-guard harness and browser-test discovery
are separate checks. The updated 30-case actual-browser suite (18 static plus 12 separately guarded
synthetic account/device cases) must run on the
exact published delta, and its new mobile screenshots must be inspected. No
localhost/IPC restriction workaround was attempted in this environment.
No Safari/iPhone, real profile installation, live 2FA, real Apple certificate/
profile, free-Team installation or native self-update acceptance is claimed.

`npm audit --omit=dev` reports one unpatched high-severity node-forge signature
verification advisory, GHSA-86w9-cpqp-85rv. The application does not use that
verification API, but the dependency risk remains tracked in
`WebBootstrap/THIRD_PARTY_NOTICES.md` and `runtime-audit.json`. There is no clean-audit
claim. Runtime hashes establish the retrieved pin, not a reproducible WASM rebuild.

## Required next decisions and acceptance

1. Choose and authorize a separately hosted HTTPS service origin. Account-password
   transactions do not belong on GitHub Pages. No provider, spending, sharing or
   deployment has been authorized by this code change.
2. Re-run the updated browser suite on this exact UI delta and inspect its phone
   screenshots; prior run 37420583887 validates only the preceding implementation.
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
