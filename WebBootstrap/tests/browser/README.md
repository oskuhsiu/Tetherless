# Static browser QA candidate

This isolated browser suite tests the static frontend with synthetic signing
material and both synthetic and owned unsigned native app inputs. It
does not enable Apple authentication, deploy Pages, publish a release or establish
Safari/iPhone installation acceptance. Production dependency pins are unchanged.

## Toolchain and execution

- Node **24.19.0**; Playwright **1.58.2** from the unchanged package-lock.json
- Playwright-managed Chromium/headless-shell **145.0.7632.6**, revision **1208**
- No system browser path or channel override; no custom `--no-sandbox` argument
- Playwright's standard launch defaults remain in effect; this is not a claim
  that Chromium's process sandbox is enabled
- One worker, no retries, 90-second tests, 8-minute suite, 20-minute CI job
- `actions/checkout`, `actions/setup-node` and `actions/upload-artifact` use full
  commit SHAs, with `contents: read` and checkout credential persistence disabled

On an authorized environment that supports localhost and browser IPC:

```sh
cd WebBootstrap
npm ci --ignore-scripts --no-audit --no-fund
npm test
npm run build
node --test tests/browser/harness.test.mjs
node node_modules/playwright/cli.js install --with-deps chromium
npm run test:browser
```

`npm run test:browser -- --list --reporter=list` discovers the 32 cases without opening a browser
or starting the server. `harness.test.mjs` also does not listen on a socket: it
checks the static response function directly using temporary synthetic files.
The `playwright.config.js` webServer starts the static server only for actual
browser execution. Do not attempt browser/localhost execution in an environment
where it is denied.

The CI setup steps may acquire official Node/npm/Playwright and operating-system
browser dependencies. Runtime tests use synthetic certificates and profiles, the
existing synthetic Mach-O fixture, and the pinned owned unsigned UIKit fixture. They never start `WebBootstrapService`, send real Apple credentials or real
provisioning requests, or contact an Apple service. The guided fixture accepts
only fixed synthetic values on exact localhost API routes.

Each static test's automatic context fixture allows only GET/HEAD within its exact
localhost origin and active project path. Same-origin Blob URLs remain allowed.
Unexpected requests fail the test and are aborted; WebSockets never connect;
service workers are blocked. This is an application-request guard, not a firewall
for the entire CI host or browser process. The Node preview server has no outbound
code, proxy, SPA fallback, or account API. `/health` really returns 404; no service
success is simulated. The cancellation test delays a real worker script response,
then falls through to the same guard without substituting bytes or signing output.

## Coverage and retained evidence

The original six cases run twice, once at `/` and once at `/Tetherless/`. They
cover closed Apple credential entry on static hosting, rights consent, wrong P12
password with recovery, real WASM signing and embedded-profile equality, immediate
inspection cancellation with recovery, and a 390 by 844 mobile layout screenshot of the compact default journey.
The mobile case checks that technical/manual/sign/install panels are initially
hidden, both missing prerequisites are visible, and manual/back controls work.

Three additional cases per path cover:

1. Actual built JS/CSS, binary-plist worker, signing worker and WASM loading at
   the active path, with binary Info.plist input and a real signed download
2. Cancellation during a delayed real worker load followed by a fresh successful
   signing attempt, without stale output
3. Repeated clicks producing one worker, clear revoking the old Blob URL and
   clearing inputs/consent, a second signing, and Back from the license page
   leaving output/password/consent cleared

Subpath tests reject root-level asset/worker requests, so root mounting cannot
silently hide a project-path regression. Both paths use identical build bytes;
no production base-path edit or mock signing implementation is involved.

CI retains an HTML report, JUnit XML, per-test request audits, failure traces and
screenshots, two mobile screenshots when those cases run, the actual checked-out
commit SHA, Node/npm identity, lock hashes and Chromium lock metadata for 14 days.
The screenshots and traces contain synthetic test inputs only. A failed setup or
earlier test may prevent screenshots from existing; artifact presence is not a
passing browser result. CI runner images and OS packages are not content-pinned.

## Separate synthetic guided-account cases

`guided-test.mjs` leaves the static request policy unchanged. Its own guard allows
only exact localhost/project-path health/config/login/session/2FA/team/device-list/provision
routes and methods, answered entirely in process by `guided-service.mjs`. Only
fixed `.invalid` login values and a fixed synthetic code/device/Team/App are
accepted. Unknown API paths, external requests and WebSockets are denied. Static
assets and real dedicated workers still come from the same bounded preview
server. Service workers remain blocked. The guard is not a host-level firewall.

Six guided cases run at both `/` and `/Tetherless/`:

1. Custom IPA independent of a missing official Release; explicit active
   registered-device selection, login and
   mutation consent, synthetic 2FA, exact bundle preview, local CSR generation,
   matching synthetic certificate/profile, then real browser WASM signing and
   embedded-profile/download verification
2. A held synthetic login response is cancelled, a new login progresses, and
   the old response cannot change the new view
3. Uncertain provisioning retries the identical CSR/request and signs once;
   a later held provisioning response cancelled before completion cannot restore
   output or begin another signing worker
4. An explicitly chosen new-device path retains its separate registration consent
   and signs with the real browser WASM runtime
5. Failed/empty device lists block provisioning without fallback; a cancelled
   delayed list cannot revive the dismissed form
6. Team changes clear selection/consent; a delayed old-Team list cannot replace
   the currently selected registered device

The fixture has no real Apple data or endpoint. `guided-fixture.test.mjs` also
checks its allowlist, synthetic-only login, CSR/cert identity and actual WASM
signing offline. Those checks are not browser execution. The full-path case
retains synthetic mutation-preview and signed-but-install-blocked screenshots.

## Owned unsigned UIKit custom-IPA regression

One additional case runs at both existing paths, bringing discovery to **32**
(18 static, 12 synthetic guided, 2 owned-native-input guided). The original 30
cases are unchanged. `owned-ipa.spec.js` reuses `guided-test.mjs`; its closed
`guidedApp` option selects only the pinned second fixture identity. Routes,
credentials, Team/device checks, consent, CSR rules and request guards stay the
same. Unknown app selectors and arbitrary mutation plans fail closed.

The case uses the exact 14,853-byte owned unsigned UIKit IPA from native build
[37503567286, attempt 1](https://github.com/oskuhsiu/Tetherless/actions/runs/37503567286/attempts/1).
Its source, LICENSE, identity and provenance are retained beside the fixture.
See [`fixtures/owned-signing-test/README.md`](../fixtures/owned-signing-test/README.md).
Through visible controls, the test selects the custom IPA, verifies login and
provisioning consent gates and explicit existing-device selection, then signs
using the actual browser worker and pinned WASM. It verifies the downloaded ZIP:
changed executable, unchanged Info.plist/BuildIdentity, exact synthetic profile,
expected member set, and SHA-1/SHA-256 CodeResources digests. Installation stays
blocked and the UI must say installation and launch are unverified. It then
clears the output and consent. The downloaded synthetic IPA is deleted rather
than retained as a deliverable; keys/P12s remain in memory.

`owned-ipa.test.mjs` provides four portable checks, including an offline genuine
input WASM replay and negative controls for the output verifier and the closed
fixture selector. These are separate from actual Chromium execution. The new
browser case attaches a digest-only output proof plus mutation-preview and
install-blocked screenshots only when actual browser execution reaches those
steps. Preparation/discovery does not produce or claim screenshots.

## Evidence limits and workflow interactions

The unchanged baseline passed actual Chromium execution in
[run 37501163075](https://github.com/oskuhsiu/Tetherless/actions/runs/37501163075):
18 static/manual cases and 12 synthetic guided-account/device cases. The two
owned-native-input cases require a new run on the exact published source SHA.
Browser tests are not run in this preparation environment because
localhost/browser IPC are restricted; syntax/config/discovery/harness/unit/build
checks are separate evidence. Prior green execution does not validate the new
cases or create their screenshots.

Even a green result establishes only Chromium execution with a synthetic signing
identity. It does not validate Apple CMS trust, real Apple provisioning, Safari,
iOS installation, real-device launch or unattended renewal. BOOT-01 remains open.
The existing runtime security advisory remains unresolved by this test-only work.

This workflow filters its own pushes to `develop` and the approved
`verify/staged-pairing-native` verification branch plus relevant web paths, and
its PRs to `develop` plus those paths. The repository default branch is `main`;
this push route tests the new workflow without changing the default/release
branch or depending on a default-branch manual-dispatch registration. It does not change other workflows. Existing
`core.yml` runs on every push/PR; `native.yml` runs on every PR to `develop`, even
if only web files change. Publishing a web-only branch/PR therefore cannot be
promised to trigger only this workflow.

## Primary pin references

- [Node 24.19.0 release checksums](https://nodejs.org/download/release/v24.19.0/SHASUMS256.txt)
- [Playwright 1.58.2 release and Chromium version](https://github.com/microsoft/playwright/releases/tag/v1.58.2)
- [checkout pinned commit](https://github.com/actions/checkout/commit/11d5960a326750d5838078e36cf38b85af677262)
- [setup-node v6.3.0 pinned commit](https://github.com/actions/setup-node/commit/53b83947a5a98c8d113130e565377fae1a50d02f)
- [upload-artifact pinned commit](https://github.com/actions/upload-artifact/commit/ea165f8d65b6e75b540449e92b4886f43607fa02)
