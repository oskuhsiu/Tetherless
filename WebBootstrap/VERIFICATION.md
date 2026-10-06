# Web bootstrap verification

Candidate verification: 2026-10-06 UTC, Node 24.19.0, npm 11.9.0.

## Progressive UI / pinned Release candidate

- `npm test`: 87 passed, 0 failed, including actual pinned WASM synthetic signing
- `npm run build`: passed, including pinned runtime/adapter hashes
- `node --test tests/browser/harness.test.mjs`: 5 passed, 0 failed
- `npm run test:browser -- --list --reporter=list`: discovers 30 cases at root
  and `/Tetherless/`; discovery is not browser execution
- No dependency, runtime, native, service, deployment or workflow change
- No real Apple credentials, device data, certificates or production release used

The registered-device follow-on is based on the frozen redirect-hardened UI
ZIP c5037ae58d48fdae1b1ba47f26d13b0dc0c7d1cba9999cf37425d5201b7581de.
It does not modify that first-publication source or any backend/native file.

New synthetic/DOM coverage includes progressive views, unavailable/configured
services, pre-login device return, single/multiple Teams, explicit login and
provision consent, consent revocation during package acquisition, automatic
provision-to-sign progression, original-CSR retry with frozen IPA/selection,
fresh-document and bfcache recovery of only a valid previously-started enrollment,
manual-mode/back file preservation, cancellation and stale password/output
protection. Service cookies are same-origin only and service/enrollment fetches reject redirects; exact inspected App IDs/App
Group are shown before consent and remain pinned to the session IPA. The Release
cap is the existing parser input budget (150 MiB), not proof the future App fits. Release tests check the complete pin, URL/size/digest, bounded streams,
cancellation, CORS errors and exact-file manual fallback. These mock account /
network / DOM tests are not browser or Apple acceptance.

The 12 guided-browser cases (six per project path) use a separately
restricted localhost-only synthetic service. They validate synthetic login/2FA,
exact mutation preview/consent, active registered-device selection, list error/
empty/cancel/stale-Team handling, explicit new-device registration, original-CSR
retry and real browser
WASM signing. They have been discovered but not executed here. The helper's
CSR-matching cert/profile passed offline admission and actual WASM signing.

The prior implementation passed actual Chromium CI **37420583887, 18/18**, with
real WASM synthetic signing, verified downloads and mobile screenshots. That run
is historical evidence for the pre-simplification implementation. The updated
candidate still needs the same isolated 30-case browser CI on its exact published SHA,
followed by inspection of the new screenshots. No local browser/IPC restriction
workaround is attempted. Browser/runtime tests use self-signed synthetic material,
not Apple-issued profiles or an installable Tetherless App.

## Remaining acceptance gates

- Exact-delta actual Chromium execution and mobile screenshot review
- A genuine current unsigned Tetherless App and reviewed GitHub Release manifest
- Approved deployed account service; actual Apple login/2FA/provisioning
- Safari/iPhone profile prompts, device-return behavior and trusted device identity
- Free Personal Team clean-phone installation, launch and native identity handoff
- Data/Keychain continuity and later unattended renewal

Signing/downloading an IPA is not installation. The default direct-install action
is disabled; only the explicit existing paid Ad Hoc HTTPS-manifest helper can
hand off to iOS, and even that does not verify installation. No OTA-hosting
backend extension is enabled. BOOT-01 remains open.

`npm audit --omit=dev` previously reported one unpatched high node-forge signature
verification advisory; the dependency is unchanged. No clean audit or full Apple
CMS trust, revocation, Mach-O entitlement or production security audit is claimed.
See `THIRD_PARTY_NOTICES.md` and `runtime-audit.json`.
