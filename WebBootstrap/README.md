# Tetherless web bootstrap prototype

A Pages-compatible, phone-oriented frontend plus a separate optional Apple
provisioning service. **BOOT-01 remains open.** The free Personal Team,
clean-phone first installation goal has not been demonstrated.

## Run locally

```sh
cd WebBootstrap
npm ci --ignore-scripts
npm test
npm run build
npm run dev
```

Node 24 is the verified local toolchain. The runtime hash check is part of the
build. `dist/` is a relocatable static site; Vite uses a relative asset base so a
GitHub Pages project subpath works. No deployment workflow or Pages setting is
changed by this implementation. Publish only after the deployment is separately
authorized and tested.

`npm run test:browser` runs the Playwright suite, using `CHROMIUM_PATH` or
`/usr/bin/chromium`. `npm run check` requires those browser tests in addition to
unit tests/build and must not be described as passing while browser access is
blocked. See `../docs/WEB_BOOTSTRAP.md` for current evidence and gates.

## Two distinct routes

1. **Existing certificate/profile:** choose your IPA, P12 and all bundle profiles;
   inspect basic bounds and consistency; sign with the real local WASM engine;
   download output. It does not produce a new Apple identity or install the app.
2. **Apple Account (service required):** serve this built frontend from the same
   separate HTTPS origin as `Tools/WebBootstrapService`. Its `/health` must
   advertise protocol 1 and account availability before a password form appears.
   The browser creates the private key/CSR. The service performs real SRP/2FA and
   provisioning API calls; no mock provider is used in production.

On GitHub Pages, set `public/config.json`'s `accountServiceUrl` only to the approved
separate service origin before rebuilding. The Pages site provides an outbound
link; it does not collect Apple passwords. Normal Sign in with Apple is not a
Developer Portal credential and is not used here.

The service route requires explicit on-page data/transmission consent and a
separate provisioning consent before device/App ID/certificate actions. It never
revokes a certificate automatically. No real account was used during development.

## Data and scope

IPA, P12, private key, profiles and P12 password stay in the current tab/worker.
There is no analytics, remote certificate catalog, automatic IPA upload, browser
key cache or signing-history persistence. Only a nonsecret UDID-enrollment ID and
expiry use sessionStorage for the Settings round trip; the enrollment-only capability
uses a short-lived HttpOnly cookie. Apple secrets never enter browser storage. Cancel/clear terminates the worker and
revokes output Blob URLs. JavaScript garbage collection cannot promise immediate
zeroization; close the tab to release its execution context.

The profile checks match RSA key/certificate, expiry, embedded certificate, Team,
bundle IDs and an optional UDID. They do **not** validate Apple CMS chain trust,
revocation, Mach-O entitlements or installation eligibility. Only registered-device
profiles are admitted; shared enterprise profiles are rejected. No extension
stripping, arbitrary bundle-ID rewriting, injection, entitlement bypass or `-a`
hash-only signing is exposed. Extension bundle IDs are preserved and need one exact profile each. Wildcards,
extra profiles and suffix-ambiguous IDs are rejected; embedded output profiles are
compared byte-for-byte with their intended inputs. Recognized Tetherless defaults
also require the artifact-derived shared App Group in every profile. Source and binary/license pins are in `THIRD_PARTY_NOTICES.md`.

The optional OTA helper generates a manifest and `itms-services` URL for separately
prepared registered-device Ad Hoc output and user-owned HTTPS hosting. It does not
upload or probe a URL, and never presents free development output as a proved
Safari first-install route. A Blob URL is a download, not an iOS installer.
