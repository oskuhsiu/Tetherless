# Bounded web-signing test service

This packages the existing browser signer and unchanged real Rust account
service into one Linux container. It adds no signed-IPA hosting, OTA-install
endpoint, native signing/parser/admission change, or production mock backend.
A successful build or local smoke test is not live Apple or iPhone acceptance.

## Exact source and license offer

`SOURCE_COMMIT` is a required Docker build argument containing the full lowercase
40-hex commit of the exact source being built. Missing, malformed or `unrecorded`
values fail the image build. The image retains it in `/app/build-info/source-commit.txt`
and in its revision label. CI verifies both against its checked-out commit.
Before login, the gate links directly to that commit's public source tree and
LICENSE in the fixed `https://github.com/oskuhsiu/Tetherless` repository. There is
no configurable repository URL and no `main`/`latest` source reference. A closed
test window still offers those links while refusing account access. The image
also includes the repository LICENSE under `/app/licenses/AGPL-3.0.txt`.

The production supervisor reads the immutable build-generated identity; runtime
`SOURCE_COMMIT` does not replace it. Local tests use a clearly synthetic identity
file; their link fixture is not a published deployment. The test-only identity
file override is ignored in the production image. This source-availability and
integrity mechanism is not a legal-clearance claim or permission to omit any
applicable dependency license/source obligation.

## Deployment contract

- Exactly one replica, with the browser and `/v1/...` on one approved HTTPS origin.
- The Node proxy listens on `0.0.0.0:$PORT` (default 10000); Rust stays on
  `127.0.0.1:8787`. The original public Host and Origin reach the Rust guards.
- The hosting edge must terminate TLS and redirect plaintext requests to HTTPS.
  Never expose this HTTP container directly to the internet or publish port 8787.
- Required variables, configured only after the operator approves the deployment:
  - `FRONTEND_ORIGIN`: canonical actual `https://<approved-host>` (no trailing `/`)
  - `TETHERLESS_PUBLIC_HOST`: exactly that origin's host, including a nondefault port
  - `TETHERLESS_FRONTEND_DIR`: `/app/frontend` in the image
  - `TETHERLESS_TEST_EXPIRES_AT`: an absolute UTC timestamp, `YYYY-MM-DDTHH:MM:SSZ`,
    in the future and at most 24 hours from process startup
  - `TETHERLESS_TEST_ACCESS_SHA256`: lowercase SHA256 of a separate test code
- Generate the test code with a cryptographically secure generator on an approved
  operator-controlled system: 32 random bytes encoded as 43 unpadded base64url
  characters. The visible gate rejects other lengths/alphabets; a digest cannot
  prove randomness, so do not use repeated characters, memorable phrases or an
  Apple password. Never put the code in chat, source, build arguments or logs.
  This package does not generate or configure a real operator credential.
- Store only its digest as runtime configuration, never the actual code. A
  short-lived test gate is access control, not a substitute for approved HTTPS,
  account data-recipient consent or action-time certificate confirmation.
- Do not attach a persistent disk, store signing keys, or enable autoscaling.
  Turn off automatic deploys for the approved test window. Do not redeploy or
  restart during account work. No process supervisor restart/retry is implemented.
- Set the HTTP health check to `/health`. Keep exactly the configured public
  hostname; adding another custom hostname changes Render's health-check Host
  behavior and requires deliberate origin/configuration review.

The gate has an accessible password-type form suitable for secure browser
handoff. Its code is separate from an Apple Account password. Successful access
creates a random in-memory `__Host-tetherless-test` cookie with Secure, HttpOnly,
SameSite=Lax, Path=/, at most 30 minutes and never beyond the fixed test window.
At most four gate sessions exist. This cookie grants no Apple-session authority;
the unchanged Rust API still needs its separate bearer and exact Origin.
Same-origin frontend API/config/health requests must use credentials:same-origin.
Cross-origin GitHub Release acquisition must continue to omit credentials.
The proxy strips its gate cookie and all forwarded-address/authority headers
before sending to Rust, preserving only the existing enrollment cookie.

Except for exact `GET /health` and no-Origin `POST` to the existing UUIDv4
`/v1/device-enrollments/<id>/callback`, requests need the test cookie. That
callback still has the unchanged bounded CMS/challenge/nonce/expiry/replay checks;
it cannot create an enrollment or Apple session. The test window also closes the
callback. Invalid Host, query-bearing paths, unsupported methods and HTTP upgrade
requests are rejected. There are no access tokens in URL query strings.

Global token-bucket limits are intentionally independent of untrusted forwarded
IP addresses: 240 general requests/minute, 6 gate attempts/
minute, 3 Apple-session starts/minute, 30 mutations/minute and 10 enrollment callbacks/
minute. Initial bursts equal these limits. Health checks have separate transport
capacity and no public rate bucket that can be exhausted to force a hosting
restart. At most 16 ordinary proxy requests and 64 total client connections are
active. Header limit 16 KiB, mutation body limit 32 KiB, gate body limit 256 bytes,
input timeout 15 seconds, headers 10 seconds; forwarded upstream
operations allow 130 seconds and response inactivity 135 seconds. Static/WASM
responses stream with backpressure. These conservative single-user test limits
are not an internet-scale DDoS defense or authorization for multi-user operation.

## State, expiry and sensitive data

The fixed deadline and cookie lifetime are checked again after request-body input,
before forwarding. New requests after expiry fail closed; `/health` remains public
and healthy while the account adapter is reachable. An already-forwarded account
operation can finish after the window closes. Expiry/cancellation/restart does
not roll back an Apple device/App ID/certificate mutation. A lost response can be
uncertain. Keep the original browser key/CSR, inspect the account state, and do
not automatically repeat provisioning or create another signing key/certificate.
A restart invalidates all gate cookies and every in-memory Apple session.

The supervisor forwards SIGTERM as SIGINT to the Rust process so its existing
cancellation handler runs. If the backend exits, the whole service stops and
never automatically restarts the child. It logs only fixed lifecycle messages.
Child stdout/stderr is discarded, and only a minimal explicit environment reaches
it. There is no proxy request/access/body/cookie/authorization/error-detail log.
Do not enable hosting-edge request-body capture, debug tracing, process dumps,
session replay, analytics, or packet capture. The host's internal logging and
administrative access remain a hosting-provider trust dependency.

The browser's Apple password/2FA reach the approved HTTPS host and account-service
memory. Apple authentication and developer requests go to Apple. The pinned
Anisette provider `https://ani.stikstore.app` receives generated identifier/ADI
provisioning material; this is not a claim that it receives the Apple password.
The browser creates the signing key and sends only the CSR. The existing service
issues development signing material, including for paid teams; it does not issue
Ad Hoc/distribution certificates. Real login, 2FA, development certificate/profile
issuance, browser signing, installation and launch remain separate evidence gates.

## Build and verification

Build from the repository root, using only approved source:

```sh
docker build --platform linux/amd64 --progress=plain \
  --build-arg SOURCE_COMMIT="$(git rev-parse HEAD)" \
  -f Tools/WebBootstrapService/deployment/Dockerfile \
  -t tetherless-web-test:reviewed .
```

`Dockerfile.dockerignore` allowlists source and excludes caches, local environment
files, private-key containers and IPA uploads. The one allowed PEM is a checked-in
public synthetic CSR required by backend tests; no private key is included. No
runtime secret is referenced as a Docker build argument. The required nonsecret
`SOURCE_COMMIT` build argument identifies the reviewed source. The build runs locked npm frontend tests/
build and locked Cargo tests/release build. The runtime is non-root; application
files are read-only to that user. Its only copied content is the real binary,
frontend, proxy/supervisor and notices. Browser dependency/license notices remain
in the frontend; retain the repository's AGPL source/license and pinned upstream
MIT source/license notices when distributing the service.

Unit checks:

```sh
node --test --test-concurrency=1 \
  Tools/WebBootstrapService/deployment/tests/proxy.test.mjs \
  Tools/WebBootstrapService/deployment/tests/supervisor.test.mjs
```

Real backend integration, with an already compiled release and built frontend:

```sh
TETHERLESS_INTEGRATION_BINARY="$PWD/Tools/WebBootstrapService/target/release/tetherless-web-bootstrap-service" \
TETHERLESS_INTEGRATION_FRONTEND="$PWD/WebBootstrap/dist" \
node --test Tools/WebBootstrapService/deployment/tests/integration.test.mjs
```

The integration test starts the production supervisor, checks the real health
response/adapter pin, exact built HTML and WASM hash, Host/Origin rejection,
gate-cookie behavior, and the existing local enrollment/profile/CMS-rejection/
cancellation path. It never calls account-creation or Apple mutation endpoints. It restarts only its
synthetic test instance to prove stale gate cookies are rejected and checks that
only fixed lifecycle logs were emitted. It never submits valid Apple credentials
or starts Apple/network-dependent account work. Fixture codes are public test
data, deliberately unusable for deployment. An unset integration environment
produces a visible skipped test, not a passed live-service claim.

A true Docker build and offline-container integration must pass before deployment.
Local native release/HTTP tests alone do not prove that the image builds, all
runtime libraries are present, TLS works at the hosting edge, or a deployed
service is correctly configured. The scoped `web-bootstrap-deployment.yml` workflow
builds this image, starts its normal entrypoint with `--network none`, and runs
nonaccount loopback smoke using `docker exec`. It neither pushes nor deploys the
image. All base image manifest digests are pinned and recorded in `base-images.json`;
Debian packages are resolved during build and their exact versions retained.
Record the exact source commit, base-image
resolved digests, installed Debian versions, image ID and all test receipts.

## Render-specific preparation (no deployment performed here)

Use one Docker Web Service, repository root build context, Dockerfile path
`Tools/WebBootstrapService/deployment/Dockerfile`, `/health`, exactly one instance,
and automatic deploys disabled. Set the nonsecret Render environment/build
argument `SOURCE_COMMIT` to the complete exact reviewed commit being deployed.
Render exposes declared environment variables as Docker build arguments; verify
the build-info value and image revision match that commit before any test. Do
not use a branch name, abbreviated SHA or an earlier package commit. Leave
`TETHERLESS_SOURCE_COMMIT_FILE` unset; production ignores that local-test override.
Confirm the exact reviewed commit and approved
actual origin/environment before any credential entry. A free plan is for this
bounded test, not a production reliability claim. Render may restart free
services at any time and idles them after 15 minutes. Active polling is not a
guarantee of session continuity. All state is lost on restart; warn the tester.
Platform health checks may also trigger restarts. Do not intentionally keep an
idle free service alive indefinitely or claim this package prevents platform
restarts. No hosting signup, deployment, plan upgrade or security-setting change
is authorized merely by building this package.

Primary references checked 2026-10-06:
- [Render Docker builds](https://render.com/docs/docker)
- [Render ports and TLS](https://render.com/docs/web-services)
- [Render health checks](https://render.com/docs/health-checks)
- [Render free-plan limits](https://render.com/docs/free)
- [Render deploy and shutdown behavior](https://render.com/docs/deploys)
- [Render image platform requirements](https://render.com/docs/deploying-an-image)
