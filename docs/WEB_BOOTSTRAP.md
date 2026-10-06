# Web bootstrap implementation and acceptance gates

Evidence checkpoint — 2026-10-06 23:22 UTC: current reviewed source is `cfafe7635b74ed509511796ccc7ecef0bbf557f3`. [Docker run 37518746038](https://github.com/oskuhsiu/Tetherless/actions/runs/37518746038) passes 26 packaging, 29 Rust and 91 frontend tests, plus actual isolated production-entrypoint smoke, healthcheck, graceful exit and cleanup. All eight build receipts are verified. Image SHA-256: `bfc63bec1c91676c0aacb52886e5028ab3d38a24d86694be3dfda590ab23a1b7`. Core on the same source passes 345 Swift Testing + 40 XCTest cases per Debug/Release configuration.

The full web subtree is unchanged from `f4d208ce8d991e84b5836c5c5d9bc1573f7d2bdc`, whose [browser run 37517431324](https://github.com/oskuhsiu/Tetherless/actions/runs/37517431324) passes all 32 Chromium cases with no failures, skips or retries. The original 30 cases remain, and the genuine 14,853-byte owned UIKit test IPA passes the visible custom-IPA/consent/device flow and real WASM output/resource-envelope checks at both mount paths. Generated synthetic outputs were checked inside CI and deleted; retained evidence contains hashes, sizes and assertions. The original `f4d208ce` Docker failure (89 frontend passes, two missing-fixture errors) is preserved; only the exact public fixture was subsequently allowed into the builder. Runtime fixture exclusion is supported by the exact-copy contract and unchanged build graph, without a separate final-filesystem scan.

No hosted login URL, deployment, live Apple authentication/provisioning, Safari, installation or native launch is established by these results. The official full Tetherless Release asset remains unbound. The owned fixture proves only its custom-IPA path, and the 150 MiB cap is not yet measured against a full Tetherless IPA. Earlier dated checkpoints below retain their historical evidence.

Publication addendum — 2026-10-06 18:08 UTC: the exact 14,853-byte owned UIKit fixture from run `37503567286` subsequently passed the pinned WASM signer with fresh synthetic matching material. Input and embedded-profile checks passed; the 22,169-byte output has a changed executable, verified CodeResources hashes and the exact synthetic CMS profile. Original IPA, Info.plist and BuildIdentity stayed unchanged. No private key or P12 was retained in the proof. The detailed 17:30 checkpoint below predates this replay; no live Apple, installation/launch or full Tetherless acceptance follows.

Evidence checkpoint: 2026-10-06 17:30 UTC. Scope: BOOT-01 from `ORIGINAL_PLAN.md`.
Verified implementation: [`757b45216adf0061542441e23b941985a6bdd04f`](https://github.com/oskuhsiu/Tetherless/commit/757b45216adf0061542441e23b941985a6bdd04f)
on `verify/staged-pairing-native`.

## Status

This is a functional **development prototype**, not a completed clean-phone
bootstrap or production signing service. It preserves the original free Personal
Team goal. A paid Ad Hoc helper is separate and does not count as that goal.
No deployment, Pages configuration, release, real Apple account action, certificate
creation/revocation, real device enrollment or iPhone installation was performed.

The web paths are isolated from native integration:

- [WebBootstrap](../WebBootstrap/README.md): relative-base static frontend, local signer, metadata checks,
  tests and pinned licensed runtime
- [Tools/WebBootstrapService](../Tools/WebBootstrapService/README.md): genuine transient Apple account/provisioning and
  UDID Profile Service adapter
- [Bounded deployment package](../Tools/WebBootstrapService/deployment/README.md):
  same-origin frontend/service container and short-lived test access gate
- This document

The web changes do not modify App/native CI or signing-admission paths.

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

The published frontend and backend implement the read-only route
`GET /v1/sessions/{id}/teams/{teamId}/devices`, authenticated with the
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
`officialRelease`. Both are `null` in the published source. A deployment owner must
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
manually downloaded and selected for the same hash check. The official-asset
contract adds no proxy, endpoint selection, release publication or signed-IPA
hosting. Public deployment remains a separate decision.

Custom IPA selection is a first-class path and does not require an official
Tetherless asset. A separate minimal owned signing-test app is published at
[`cfd8c6e`](https://github.com/oskuhsiu/Tetherless/commit/cfd8c6ede2c85970344e9e9c0f19cc672a95df71).
Its 24 portable tests/review pass, and authenticated [native run 37503567286](https://github.com/oskuhsiu/Tetherless/actions/runs/37503567286),
attempt 1, successfully produced an unsigned IPA:

- Size: 14,853 bytes
- Bundle ID: `org.tetherless.signingtest.r37503567286`
- SHA-256: `fda8c913af9d6f39f8a4351bd94d7953bb99b2b25506e67a3e7d943dafaf8111`
- Native content: arm64 iOS `MH_EXECUTE` UIKit app, without a code signature

This owned signing-test app is not Tetherless and does not close the full App
build or size gate. Synthetic WASM replay of this actual IPA, real Apple signing,
installation and launch remain unrun. The web results below remain bound to
`757b452`; they do not validate this later fixture artifact.

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
- Apple password/2FA/session: transient service memory for Apple authentication;
  bearer kept in JS memory, never URL, browser storage or deliberate logs
- Data recipients: the configured account service handles the entered password
  and Apple authentication; the pinned remote anisette provider
  `https://ani.stikstore.app` receives identifier/ADI provisioning data, not the
  password, in the pinned source path. The login consent names both recipients.
  This is a source-level boundary, not live traffic or production-security proof
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

### Historical prototype evidence

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

### Current exact-source evidence

The progressive login-first/existing-device UI has now run at `757b452`, tree
`899f58ad3c3ad2970bba3c17dfa20234d2108464`. These are executed results, not test
discovery or a transfer of credit from the preceding implementation:

| Run, attempt 1 | Passed evidence | Boundary |
|---|---|---|
| [Browser 37501163075](https://github.com/oskuhsiu/Tetherless/actions/runs/37501163075) | 30 executed Chromium cases: 12 guided synthetic account/device + 18 static/manual cases across root and project-subpath routes; 87 UI + five harness tests; production build and pinned runtime checks | Zero failures/errors/skips/retries. Guided Apple/service responses are synthetic; signing runs the actual browser WASM |
| [Container 37501163055](https://github.com/oskuhsiu/Tetherless/actions/runs/37501163055) | 24 packaging/proxy/supervisor/exporter + 29 Rust + 87 UI tests; actual Linux amd64 production image built; production-entrypoint smoke passed | Zero failed/skipped/ignored tests. Local CI container has network `none`, read-only root and user `node`; no Apple account call or public deployment |
| [Core 37501163284](https://github.com/oskuhsiu/Tetherless/actions/runs/37501163284) | Debug and Release each pass 345 Swift Testing + 40 XCTest cases | Zero failures; no skipped-test entries observed. This does not build or accept the native App |

Browser JUnit, report, source/lock identities and request audits reconcile. The new
390-by-2267 mobile Chromium screenshot was visually inspected: it shows explicit
synthetic existing-device selection and distinct mutation consent, including the
warning that an account record does not identify the current phone. Device-list
failure/empty state, cancellation, Team changes, stale responses and the separate
new-device route are covered. The signed-output screenshot still shows direct
installation blocked. A mobile viewport is not Safari or an iPhone.

The container image is
`sha256:1157651beafc3e3cfdd46763b3739268a532c3de9a890bb8b4d99547110f7237`.
Image, container, revision label and source receipt all match the implementation.
Actual health/static/WASM, access-gate, Host/Origin and synthetic local enrollment
checks pass. The healthcheck passes, graceful stop exits 0, the lifecycle log is
the fixed readiness line, and the owned container is removed. All eight bounded
build receipts (18,146 bytes total) were independently decoded and their byte
lengths and SHA-256 values verified, including the exact source-commit receipt.
Pinned base images and retained package inventories do not establish a
reproducible-image build; the prebuilt WASM was hash-verified, not independently rebuilt.

Retained artifact identities:

| Evidence | Artifact ID | SHA-256 |
|---|---|---|
| Browser ZIP, downloaded and verified | `11430036056` | `2aa52527e48e4afc1affa2a71b42c6799dc5fd12e0a5da4f6998d4532e9f2c49` |
| Container ZIP, downloaded and verified | `11429543078` | `41b2588f38825c4fb1193decebe4166fbfc0f05d0d1db5f8b1d77f87e77de6c8` |
| Core source artifact, GitHub-reported digest; not downloaded in this review | `11429114769` | `d3685b24c1f6178ff70f8a0750f1ca058a657d67663c863024ed3149c24d7a91` |

The preceding `8058762` [container run 37498141911](https://github.com/oskuhsiu/Tetherless/actions/runs/37498141911)
remains a failure: image build passed, but `docker cp` could not export a read-only
evidence directory, so smoke was skipped. The current bounded export repair and
successful smoke do not change that historical result.

No Safari/iPhone, real profile installation, live 2FA, real Apple certificate/
profile, free-Team installation or native self-update acceptance is claimed.

`npm audit --omit=dev` reports one unpatched high-severity node-forge signature
verification advisory, GHSA-86w9-cpqp-85rv. The application does not use that
verification API, but the dependency risk remains tracked in
`WebBootstrap/THIRD_PARTY_NOTICES.md` and `runtime-audit.json`. There is no clean-audit
claim. Runtime hashes establish the retrieved pin, not a reproducible WASM rebuild.

## Required next decisions and acceptance

1. Choose and authorize a separately hosted HTTPS service origin. Account-password
   transactions do not belong on GitHub Pages. Follow the approved host/origin,
   short-lived access-gate and fixed test-window contract before exposing the
   container. No public service is deployed, and code publication alone authorizes
   no provider, spending, sharing or deployment.
2. Preserve the current 30-case Chromium and container receipts above. Safari and
   actual HTTPS-host behavior remain separate acceptance checks; do not rerun
   unchanged source merely because the older prototype had fewer cases.
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
