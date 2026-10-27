# Tetherless web bootstrap account service

Independent account/provisioning adapter for the web bootstrap candidate. It does
not edit or replace Tetherless's native authentication, signing admission,
certificate parser, pairing or renewal paths.

## What is real

The production implementation calls `isideload` at exact source revision
[`dd442588370060b8776b1276a1acd717b6668b26`](https://github.com/nab138/isideload/tree/dd442588370060b8776b1276a1acd717b6668b26).
The upstream MIT license is in that repository; retain dependency notices when
distributing. This service's source is AGPL-3.0-only, matching Tetherless.

- Apple SRP/GrandSlam: `AppleAccount::builder(...).login(...)`
- Trusted-device and SMS 2FA: `TwoFactorCallbackParams/Response`
- Developer session: `DeveloperSession::from_account(...)`
- Teams: `TeamsApi::list_teams`
- Certificates: `CertificatesApi::list_ios_certs/submit_development_csr`
- Device registration: `DevicesApi::list_devices/add_device`
- App IDs and profiles: `AppIdsApi::list_app_ids/add_app_id/update_app_id/download_team_provisioning_profile`
- Shared App Groups: `AppGroupsApi::list_app_groups/add_app_group/assign_app_group`

There is no production mock backend and no invented success response. Tests do
not submit Apple credentials, send a real 2FA challenge, register a device, issue
a certificate, or call an Apple service.

## Trust and deployment boundary

The browser creates RSA2048 key material and a CSR. Only the CSR goes to this
service; its request schema has no private-key field. The public certificate and
profiles come back for browser-side signing. Bundle IDs remain exactly the
explicit input IDs; the service does not substitute another developer's team.

The service receives the entered Apple password and 2FA code in memory. Its
password owner is zeroized after authentication and on cancellation; this is not
a claim that every copy in the HTTP runtime/upstream library is securely erased.
Apple tokens and anisette state are held in memory for at most ten minutes.
Restarting loses the session. No password, token, anisette identity or private key
is deliberately written to disk. Do not enable request-body, authorization-header,
debug, upstream-error, proxy or process-dump logging. No tracing subscriber is
installed. Upstream error descriptions are not sent to the browser.

The fixed remote anisette provider is `https://ani.stikstore.app`; it receives
anisette provisioning/identity data. The account service sends authentication and
developer requests to Apple. This is not a direct-browser-to-Apple-only system.
Using an existing remote anisette provider avoids distributing Apple's ADI
binaries; the operator still needs to assess that provider's availability and
privacy terms. There is no arbitrary request proxy, destination URL or user
selected anisette server endpoint.

Run behind an HTTPS reverse proxy on a host you control. The process deliberately
binds only a loopback address. Serve `WebBootstrap/dist` at the same origin as
`/health` and `/v1/...`. GitHub Pages may link to this separate HTTPS origin; it
must not collect the Apple password. A native login and the web bootstrap are
separate authentication sessions: the service does not transfer passwords,
tokens or signing private keys into the installed IPA.

### Build and run

Use the committed `Cargo.lock` and a recent stable Rust (verified toolchain is
recorded in `VERIFICATION.md`). The upstream edition is Rust 2024. A C compiler
and `pkg-config` are needed by cryptography dependencies; Linux additionally
needs OpenSSL development libraries when selected by the resolved graph.

```sh
cargo test --locked --all-targets
cargo build --locked --release
FRONTEND_ORIGIN=https://bootstrap.example.com \
TETHERLESS_PUBLIC_HOST=bootstrap.example.com \
TETHERLESS_FRONTEND_DIR=/absolute/path/to/WebBootstrap/dist \
./target/release/tetherless-web-bootstrap-service
```

The reverse proxy must preserve the public `Host` header, terminate TLS, disable
access/body/authorization logging for account routes, and send traffic only to
`127.0.0.1:8787`. Prevent direct access to the unencrypted upstream. Do not expose
the service by port-forwarding its HTTP listener. Configure external request
rate limits and a private/authenticated deployment before multi-user use; the
in-process capacity cap is not a comprehensive abuse-defense system.

Local development defaults to `http://127.0.0.1:8787` for both static files and
API. HTTP is accepted only for literal loopback/localhost frontend origins.
`TETHERLESS_BIND` can change the loopback port; set matching `FRONTEND_ORIGIN`
and `TETHERLESS_PUBLIC_HOST`. No wildcard origins or credentials-in-URL are
accepted. Mutations require an exact Origin header. API responses are no-store.

## Protocol 1

Account request/response bodies are JSON, maximum request body 32 KiB. Protected
account endpoints require `Authorization: Bearer <sessionToken>`. Never put the token,
password or 2FA code in a URL. Session IDs alone confer no access.

1. `GET /health` returns `protocol:1`, `appleAuthAvailable:true` and
   `liveAppleAcceptance:false`. `profileServiceAvailable` is true only with a
   configured HTTPS origin. Available means the real adapter is compiled;
   it is not evidence of a successful Apple login or an installable IPA.
2. `POST /v1/sessions` with `{appleId,password}` returns HTTP 202 and
   `{sessionId,sessionToken,state:"starting",expiresInSeconds:600}`. The user
   must explicitly initiate this after reviewing the data recipients.
3. `GET /v1/sessions/{id}` returns `{state,challenge,error}`. State is
   `starting`, `awaitingTwoFactor`, `authenticated` or `failed`. A challenge is
   `{sms,unknown,retry,numbers:[{id,lastTwoDigits}],selectedNumberId}`. No full
   trusted-phone-number or raw upstream error is disclosed.
4. `POST /v1/sessions/{id}/2fa` accepts one of:
   - `{action:"submitCode",code:"123456"}`
   - `{action:"sendSms",numberId:1}` using a returned phone choice
   - `{action:"sendToDevices"}`
   - `{action:"resendCode"}`
5. `GET /v1/sessions/{id}/teams` returns `{teams:[{id,name,type,status}]}`.
6. After the user chooses a team and explicitly approves the listed mutations,
   `POST /v1/sessions/{id}/provision` accepts:

```json
{
  "consent": "register-device-app-ids-and-issue-certificate",
  "teamId": "EXAMPLE123",
  "device": {"udid":"0000000000000000000000000000000000000000","name":"My iPhone"},
  "csrPem":"-----BEGIN CERTIFICATE REQUEST-----\n...\n-----END CERTIFICATE REQUEST-----",
  "machineName":"Tetherless Web Bootstrap",
  "apps":[{"bundleId":"org.example.Tetherless","name":"Tetherless"}]
}
```

The example is synthetic, not a request to send it to Apple. The response is
`{teamId,certificateDerBase64,certificateSerial,certificateReused,
appGroupIdentifier,profiles:[{bundleId,profileBase64,profileId}],
verification:"cmsSignatureAndMetadataOnly"}`.
The service reuses an existing selected-team certificate when its public key
matches the CSR, otherwise submits exactly one development CSR. Returned
certificate public key and validity are checked with the existing `x509-cert`
library. Optional `appGroup:{identifier,name}` requires the separate consent
`register-device-app-ids-app-group-and-issue-certificate`. It lists/creates that
exact group, enables App Groups (`APG3427HIY=true`), and assigns Apple's returned
group resource ID to every explicitly supplied App ID before profile download.
IDs are never rewritten. For a Tetherless IPA use the actual artifact's main,
AltWidget and SideBackup IDs and the shared group required by that artifact;
do not infer suffixes or paid capabilities from a filename.

OpenSSL verifies each returned profile's CMS signature integrity without signer
chain verification; plist checks exact Team, bundle, supplied UDID, unexpired
lease, returned leaf certificate and requested group membership. The response
label reflects that limited evidence. These checks do not modify or replace
native signing admission/parsers and do not establish Apple chain trust or
physical launch acceptance.

An identical repeat returns the same stored result or `busy`. A changed request
in that session is rejected. HTTP disconnect does not restart the mutation.
No certificate is automatically revoked. Capacity yields `certificateLimit`.
Timeout/cancellation can leave an Apple mutation committed: treat
`provisioningUncertain` as requiring inspection, not permission to issue again.
There is no durable crash-recovery journal for this transient service. Keep the
browser's original key/CSR until the user resolves an uncertain result.

7. `DELETE /v1/sessions/{id}` cancels work and removes the session. Cancellation
   does not undo a mutation already committed by Apple. Expiry likewise does not
   revoke certificates or delete registered devices/App IDs.

## Optional device-ID Profile Service

This uses Apple's documented Profile Service exchange. It does not install an
MDM/SCEP payload or trust root. Production requires a reachable HTTPS origin;
HTTP loopback is for API tests only and refuses profile creation.

- `POST /v1/device-enrollments` with `{consent:"collect-device-udid"}` returns
  `{enrollmentId,profileUrl,expiresInSeconds:600,verification:"untrustedDeviceMetadata"}`
  and an enrollment-only Secure/HttpOnly/SameSite=Lax cookie scoped to that ID.
  No Apple-session cookie is created. The browser may retain only the ID/expiry
  across navigation; it must not persist an Apple bearer, password or private key.
- Navigate to `profileUrl` on the intended phone. This is a random, expiring
  download capability. It contains no Apple password/token, but should still be
  excluded from logs. The unsigned `.mobileconfig` asks the user in Settings to
  send only UDID, product and OS version to the configured service.
- The callback accepts bounded CMS DER on a single nonce-bound URL. OpenSSL
  verifies the embedded signer's signature, with chain verification disabled.
  It therefore does **not** establish Apple-issued signer identity or that the
  metadata belongs to the phone currently showing the browser. It never uses a
  substring search to pull XML out of CMS. A wrong challenge, malformed/unsigned
  message, replay, expired/cancelled record or sixth attempt is rejected.
- Successful receipt returns a fixed 301 to `/#device-collected`; no UDID or
  bearer is put in the return URL. `GET /v1/device-enrollments/{id}` uses the
  HttpOnly cookie and returns `{state:"awaitingDevice"|"received",device:null|
  {udid,product,version},verification:"untrustedDeviceMetadata"}`.
- Display those details for explicit review. Collection itself never registers
  anything with Apple. Registration requires the separate provision consent.
- `DELETE /v1/device-enrollments/{id}` cancels the record and expires its cookie.
  Records otherwise expire in ten minutes. No profile installation or callback
  from a real iPhone has been tested; current iOS unsigned-profile prompts and
  Settings/Safari return behavior remain acceptance gates.

The two-slot CMS parsing permit is owned by each actual blocking parser until
it exits, including after HTTP disconnect. Tests hold parsing work, cancel the
waiting caller and verify that the occupied capacity is not prematurely freed.

## Explicit gaps

- No live Apple login, 2FA, certificate, profile, profile installation or device
  acceptance has run. Synthetic CMS fixtures are self-signed and not from Apple.
- Browser WASM signing and iOS installation are separate from this service.
  Personal/free-team profile issuance does not prove a clean-phone Safari OTA
  installation route. A successful signature is not an installation result.
- Required App Group API operations are connected, but real portal capability
  behavior and each final main/widget/backup profile remain unverified. Extra
  capabilities of alternate paid entitlement templates are not auto-requested.
- The browser-held key is not transferred into the native app. Read-only native
  source inspection identifies a possible same-Team takeover: first login
  creates its own Keychain key/certificate and asks for foreground full
  self-reinstallation while preserving exact bundle ID, Team and shared App
  Group. That needs a free certificate slot, working transport, explicit user
  confirmation and real-device verification. No-revocation success is not
  guaranteed when quota is exhausted. Profile-only renewal cannot silently
  switch the running binary to a different signing certificate.
- CMS signature integrity and metadata consistency are not independent Apple
  signer-chain validation, revocation checks or kernel launch acceptance.
- No automatic certificate revocation, credential export, paid/distribution
  certificate issuance, account repair/terms acceptance or arbitrary proxy.
- Password-based auth on a hosted backend creates a stronger trust dependency
  than local native auth. isideload also has WASM support, but a browser build
  needs a separate wasm-bindgen API plus a tightly controlled relay for Apple
  requests. Such a relay still sees session tokens/2FA/portal data. It does not
  make the backend zero-trust or solve first installation.

## Source feasibility references

- [isideload API source](https://github.com/nab138/isideload/tree/dd442588370060b8776b1276a1acd717b6668b26/isideload/src)
- [isideload WASM feature and native dependencies](https://github.com/nab138/isideload/blob/dd442588370060b8776b1276a1acd717b6668b26/isideload/Cargo.toml)
- [SideSign current pin](https://github.com/SideStore/SideSign/tree/6b68651697f99791ef85404b7aea1891a26a285d)
- [SideSign dependency pins](https://github.com/SideStore/SideSign/blob/6b68651697f99791ef85404b7aea1891a26a285d/Package.resolved)

SideSign's README declares GPL-3.0 and its dependencies include Linux support:
AnisetteKit links system Unicorn off Darwin, while CodeSignKit/GSACryptoKit use
Swift cryptography packages. It is not categorically Apple-only. It does not
provide a ready browser-WASM/HTTP account service. Reusing it would require a
Swift runtime plus those libraries and ADI provenance/license review. isideload
is the narrower new-service dependency here; it does not replace the already
pinned/hardened native SideSign implementation.

Profile Service source references:
- [Apple profile-server example and challenge exchange](https://developer.apple.com/library/archive/documentation/NetworkingInternet/Conceptual/iPhoneOTAConfiguration/profile-service/profile-service.html)
- [Apple example request and device-response keys](https://developer.apple.com/library/archive/documentation/NetworkingInternet/Conceptual/iPhoneOTAConfiguration/ConfigurationProfileExamples/ConfigurationProfileExamples.html)
- [Source example documenting the 301 Safari return pattern](https://github.com/shaojiankui/iOS-UDID-Safari/blob/master/README.md)

The archived Apple example includes an obsolete CA. This service deliberately
does not import it or claim modern Apple-device attestation. It reports only
untrusted metadata until the user reviews and explicitly elects to register it.
