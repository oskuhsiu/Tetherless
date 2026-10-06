# Static browser QA candidate

This is a test-only change. It does not enable Apple authentication, deploy Pages,
change the app/service, or establish Safari/iPhone installation acceptance. The
existing README's `/usr/bin/chromium`/`CHROMIUM_PATH` instruction is superseded by
the portable bundled-browser steps below. No production dependency changes are
required.

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

`npm run test:browser -- --list --reporter=list` discovers the 18 cases without opening a browser
or starting the server. `harness.test.mjs` also does not listen on a socket: it
checks the static response function directly using temporary synthetic files.
The `playwright.config.js` webServer starts the static server only for actual
browser execution. Do not attempt browser/localhost execution in an environment
where it is denied.

The CI setup steps may acquire official Node/npm/Playwright and operating-system
browser dependencies. Runtime tests use synthetic certificates, profiles and the
existing synthetic Mach-O fixture. They never start `WebBootstrapService`, send
Apple credentials or provisioning requests, or contact an Apple service.

Every test's automatic context fixture allows only GET/HEAD within its exact
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
inspection cancellation with recovery, and a 390 by 844 mobile layout screenshot.

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

## Evidence limits and workflow interactions

The proposed workflow has not been published or dispatched by this candidate.
Browser tests have not run in the preparation environment because localhost and
browser IPC were denied. Offline syntax/config/discovery/harness/unit/build checks
are separate evidence. Browser screenshots, request interception and cancellation
behavior still require execution in a supported authorized environment.

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
