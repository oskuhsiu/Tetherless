# Production gate browser regression tests

Run after `npm ci --ignore-scripts --no-audit --no-fund` and installation of the
Chromium revision bundled with the pinned Playwright 1.58.2 dependency:

```sh
node node_modules/playwright/cli.js install chromium
node node_modules/playwright/cli.js test --config playwright.gate.config.js
```

This suite imports the production `gate-page.mjs` through the actual
`createProxy` HTTP server. Chromium sees `https://bootstrap.example.com`; an
allowlisted Chromium Fetch interceptor bridges only GET `/`, GET `/_test/access`, and POST
`/_test/access` to an ephemeral `127.0.0.1` listener. The browser processes the
real response CSP, 303 redirects, Origin and secure HttpOnly cookie. The only
upstream is a local, script-free, public synthetic HTML fixture. All other
URLs, methods and account routes are blocked and fail the test. WebSockets are
blocked separately. Chromium Fetch interception covers every redirect hop; the
Playwright context.route API would bypass the handler after a redirect in the
locked version, so it is intentionally not used for HTTP in this harness.

An init script replaces `crypto.getRandomValues` before every page script with
fixed public bytes 0 through 31. The original RNG is never invoked. SHA-256
uses actual WebCrypto except the explicit missing/denied capability tests.
The isolated test process also replaces Node randomBytes with public counters
and synchronizes its ESM export, so proxy session cookies are deterministic too. No code or cookie from this suite is a deployment secret.
Never run the suite against a real service, configure its public fixture
verifier on a deployed service, or use real credentials as test input.

Coverage includes trusted versus scripted gestures, no automatic generation or
submission, password-only raw-code state, fixed expiry, forbidden persistence
and clipboard writes, unsuccessful Open and recovery after service restart,
real redirect/cookie/readback success, lost-session readback, unavailable
WebCrypto, duplicate actions and stale asynchronous completion. The expiry
and page lifecycle interruption tests use Playwright clock control and an
explicit synthetic pagehide event; they do not claim physical-device coverage.

Reports, failure screenshots and traces may contain the deterministic public
fixture code. CI saves them separately under `playwright-gate-report/` and
`test-results/gate-browser/`, alongside the exact source/toolchain evidence.
These tests establish synthetic browser/proxy behavior only. They do not prove
cloud Chrome handoff, production TLS, Render deployment, Apple Account access,
physical-device installation, or unattended renewal acceptance.
