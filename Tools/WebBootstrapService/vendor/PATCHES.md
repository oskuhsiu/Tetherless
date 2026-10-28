# Vendored isideload provenance and transport patch

Repository: https://github.com/nab138/isideload
Revision: `8ca39b6203263e539408986e546c42e7c1cc3699` (2026-10-14)
License: original MIT, copied to `isideload/LICENSE`; root license retained.
`README.md` is the upstream root README required by the crate's relative readme path.
`UPSTREAM-SHA256.json` records SHA-256 for the extracted original files before edits.

Only these original files are changed:
- `isideload/src/anisette/remote_v3/mod.rs`
- `isideload/src/anisette/remote_v3/websocket.rs`

Native service transport changes:
- HTTP redirects disabled. Standard certificate validation retained. HTTP connect timeout 10 seconds and overall request timeout 30 seconds.
- Decoded JSON responses bounded at 16 KiB (`client_info`) and 64 KiB (`get_headers`), including responses without Content-Length; reject non-success HTTP status before JSON parsing.
- Client info/user agent must be nonempty, at most 1024 bytes, contain no control characters, and be valid header values. No metadata body is logged by added code.
- WebSocket frame and message limits 64 KiB; connect/send/receive deadlines 30 seconds, close 5 seconds, whole provisioning deadline 120 seconds. Existing rustls/webpki TLS defaults retained and no redirect helper introduced.
- Closed provisioning stream fails rather than spinning indefinitely.
- Loopback-only tests cover HTTP POST redirect confinement, JSON bounds/malformed/synthetic success, metadata validation, WebSocket redirect rejection and oversize messages, WSS refusing plaintext, and the actual provider resync JSON key/value contract plus `-45061` response mapping. The resync test uses only synthetic identifiers/tokens and does not exercise full Apple hsc434 login or automatic reprovisioning.

No edits to upstream cryptography, SRP, Apple-account login, or signing implementation. This revision itself includes earlier upstream signing changes relative to the previously pinned dd44258; those remain unmodified.

Scope: these timeout/redirect and WebSocket frame controls target the native Render service, not browser/WASM deployments. Existing upstream proxy APIs and WASM transport paths are not security-hardened by this patch; the service must continue supplying no proxy and using the approved fixed HTTPS provider.

The code does not establish provider availability or real Apple authentication success. No credentials or live provider/auth requests are used by the tests.

Validation limits: deadlines and provisioning EOF termination were source-reviewed, not exercised with timed timeout/EOF tests. The WSS loopback test proves no plaintext fallback, not rejection of an untrusted certificate. HTTP test runtimes explicitly initialize the ring crypto provider so results do not depend on WebSocket test ordering.
