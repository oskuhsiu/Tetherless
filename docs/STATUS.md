# Tetherless development status

Evidence checkpoint: **2026-10-06 11:37 UTC**. The Rust FFI namespace repair is
published, and the device archive's 382 expected names, absence of old aliases
and disjoint Rust/C export sets are verified. The next native link exposed a
separate collision inside the retained C archive. Its source-level repair is
published, but the Apple rebuild is blocked before compilation by unavailable
build tools. Installation approval for disposable CI is pending.

All 16 original tasks remain open with their established scoped passes preserved.
Product wireless-pairing gates stay off. No current full App package, device
acceptance or release readiness is established.

## Source and current result

- `develop`: **3d97ef75a224a76f84ba6741da8d9a6b89f99217**, unchanged
- Verification source: [80265213253940a904a0d1d0eae2bdbcd34066ce](https://github.com/oskuhsiu/Tetherless/commit/80265213253940a904a0d1d0eae2bdbcd34066ce)
  on `verify/staged-pairing-native`; tree
  `b37c6212eb9e0e9c74a558f6301fd6a58c9c42ff`
- Rust namespace/consumer isolation: [b477539](https://github.com/oskuhsiu/Tetherless/commit/b477539bcfd43a4350d98b2a5fc5775bb8818e37),
  all 35 reviewed files, including matched consumer metadata, are published
- Pinned symbol-reader repair: [6af17537](https://github.com/oskuhsiu/Tetherless/commit/6af17537bcebfa797bf3c2659f749edd4c9d53eb).
  [Run 37446415281](https://github.com/oskuhsiu/Tetherless/actions/runs/37446415281)
  is terminal **failure** at the mixed-provider C link, after the scoped passes below
- Current isolated C run: [37456626052](https://github.com/oskuhsiu/Tetherless/actions/runs/37456626052),
  attempt 1 at `80265213`, terminal **failure** during tool preflight
- The [App runtime context](../Integration/pairing-ios-diagnostic/runtime-producer.json)
  deliberately still names historical `9ee2ccc` / run `37400684000`. No failed
  Rust or C producer has been selected as an accepted App input

| Evidence | Established result | Limit |
|---|---|---|
| `80265213`, [Core run 37456625983](https://github.com/oskuhsiu/Tetherless/actions/runs/37456625983) | Raw logs verify 345 Swift Testing + 40 XCTest cases in each Debug/Release mode | Host Core evidence only; no full App build, UI, install or renewal acceptance |
| `6af17537`, native run `37446415281` | Complete zero-exit Rust/C archive scans; Rust symbol log 217,323 bytes. All 382 expected names, old-alias absence and disjoint provider export sets pass for the device archive. 31 joined commands and two native C/Swift links pass. Five independent Rust companion lanes pass 26/74/100/10/3 | The mixed-provider C force-link then fails on four internal C SHA512 duplicates. Simulator slice, remaining links, XCFramework packaging and final App provider ownership are not accepted |
| `80265213`, C run `37456626052` | 84 portable contracts + 16 host-contract tests; pinned input authentication and all measured Apple, SDK and Swift identities pass | Six required command entries are unavailable through approved lookup paths. No macOS-host crypto fixture, C cross-compilation or new C package ran in this or either earlier C job |
| `805e1b8`, [Swift fixture run 37443731193](https://github.com/oskuhsiu/Tetherless/actions/runs/37443731193) | Actual macOS generated-record promotion: eight original cases per mode; composition: 41 per mode. Source hashes and joined commands reconcile | Composition uses a C ownership spy; promotion has synthetic external seams. No actual IDevice FFI, real parser/OS-lock or live-backend acceptance follows |
| `fb0a95f4`, [bound unsigned App retention](https://github.com/oskuhsiu/Tetherless/commit/fb0a95f44e41fe49f8976d2c565c55b5ef81a853) | Published and reviewed retention implementation; 286 diagnostic tests including 28 new, plus seven existing package and 37 delivery tests pass | Designed to retain complete producer-bound Debug/Release IPAs. No new full App compile/package has run; fixture tests are not retained product binaries |

### C-provider repair and three rejected attempts

The failed mixed-provider link identifies `_sha512_init`, `_sha512_final`,
`_sha512_update` and `_sha512` in two members of the same C archive. The pinned
Ed25519 and glue contexts have incompatible layouts: 208 versus 216 bytes.
Export disjointness between Rust and C therefore does not settle this separate
internal C collision.

The [isolated C derivation](../Integration/Dependencies/libimobiledevice/README.md)
was published at [7d89a9f3](https://github.com/oskuhsiu/Tetherless/commit/7d89a9f35e105e0bc66df0fad66f9739e4816147).
It makes 30 identifier-only substitutions across six Ed25519 files, preserving
algorithms, layouts and public headers and retaining the authenticated OpenSSL
3.6.2 provider. Ordinary and ASan SHA512/RFC8032 fixtures pass on Linux. That is
source/host-fixture evidence, not a native Apple C build.

1. [Run 37452546963](https://github.com/oskuhsiu/Tetherless/actions/runs/37452546963)
   at `7d89a9f3` failed one portable alias-path fixture before acquisition.
   [673eb9c7](https://github.com/oskuhsiu/Tetherless/commit/673eb9c7039010355905b6c3c8823bed0a4eb699)
   corrected the fixture and retained early logs; the strict production guard stayed unchanged
2. [Run 37453986835](https://github.com/oskuhsiu/Tetherless/actions/runs/37453986835)
   at `673eb9c7` passed 66 portable + 16 host contracts and authenticated the
   inputs, then rejected the known Swift driver/stdout representation.
   `80265213` reuses the existing exact validator and owned Xcode packaging
   wrapper without relaxing identity or cleanup checks
3. [Run 37456626052](https://github.com/oskuhsiu/Tetherless/actions/runs/37456626052)
   at `80265213` passed the corrected Swift check and remaining Apple/SDK
   identities, then stopped because `autoconf`, `autoheader`, `automake`,
   `aclocal`, `glibtoolize` and GNU `m4` were unavailable through approved lookup
   paths. This does not prove absence from every filesystem location. The
   retained artifact is `11408684501`, SHA-256
   `7e12c270b78da907c26bbb561976fe4f105eedad9adaa24132d66bc98a051c52`

Approval to install **Autoconf, Automake, GNU Libtool and GNU m4 only on disposable
CI** is pending. Installation and dependent native work remain paused; preparation
and review of the setup do not authorize its publication or execution. Do not
rerun unchanged source or substitute a different crypto provider. A successful
future C build must still pass source/export/link-map/package checks before
separate Rust and App consumer admission.

## Historical evidence retained at its original scope

- `9ee2ccc`, [native run 37400684000](https://github.com/oskuhsiu/Tetherless/actions/runs/37400684000):
  both Apple slices, 12 C/Swift ABI probes, XCFramework and five Rust lanes
  (26/74/100/10/3) were accepted for the closed diagnostic consumer. These are
  historical input/build/link results, not validation of the current namespace repair
- `3f717ea`, [App run 37407474925](https://github.com/oskuhsiu/Tetherless/actions/runs/37407474925):
  Debug failed the `PLIST_OPT_COERCE`/`plist_write_options_t` declaration mismatch;
  unsigned Release compiled, but its binary was not retained. Normal tests,
  preparation and producer binding passed. The compile pass does not establish
  selected-provider ownership, execution or delivery
- The same `3f` Integration phase exercised the actual manager/store/ordinary
  cold reader in separate writer/reader processes, nine scenarios per mode. Its
  explicit synthetic app/preference/process-lock/receiver seams exclude the
  actual gateway, native handle, cached-protocol handoff and startup mutation
- `4838168`, [support run 37393328997](https://github.com/oskuhsiu/Tetherless/actions/runs/37393328997):
  ten actual ODA cleanup/EMProxy Debug/Release spy tests passed. Existing logs or
  subscriber state are not retroactively changed
- The `a12` host/iOS Core and Swift fixture passes, the unexplained historical
  `bf077` timing failures and the failed `3d97` full product UI remain in the
  [05:56 ledger](checkpoints/2026-10-06-retained-native-consumer-progress.md).
  The original picker diagnostic is stopped and inconclusive; no new UI retry is claimed

The published [native-9ee inventory](supply-chain/native-9ee2ccc-README.md) remains
explicitly historical: 359 registry + four workspace packages, target/host/source
distinctions, 666 notice files and 232 texts. Three compiled-package notice-text
treatment gaps and 13 additional source-only named-notice gaps remain. The
inventory is not the current linked graph, complete product SBOM or legal clearance.

## Remaining work before a phone request

1. Resolve the disposable-CI build-tool prerequisite within the approved scope.
   Then verify the isolated C producer, separately admit its exact retained output
   to the Rust producer, and prove mixed-provider links and map ownership before
   selecting any new accepted App runtime context
2. Build and retain both unsigned App configurations against the accepted producer;
   verify one integrated source, exact package contents and final provider ownership.
   The published packaging implementation alone does not satisfy this gate
3. Establish committed-record/intended-protocol handoff and caller/native-worker
   quiescence. Cold-reader and composition fixtures do not close the live-backend
   contract or permit per-renewal manual restart
4. Complete remaining unpaused UI, source/notice and delivery checks. Any new UI
   investigation needs a distinct evidence-backed decision under Simulator CI
   rules; do not rerun or widen the stopped picker diagnostic
5. Preserve the separate pause on native signing-admission/certificate/Mach-O
   parser work, manager-replacement integration, aggregate install budgets and
   dependent startup/callback ownership. Their drafts receive no new credit
6. Resolve ADI origin/admission/acquisition-use evidence, Unicorn compatibility
   and provider source/binary provenance. Compilation and inventory hashes do not establish rights

The [original 16-task matrix](PLAN_PROGRESS.md) keeps all closure conditions and
separates completed scoped work from product acceptance.

## Web bootstrap remains a development prototype

The original reviewed **70-file prototype is published at `01bf960`**. It has a
real zsign WASM signer, 47 passing frontend tests/build, and 19 offline Rust tests,
formatting, strict Clippy, release build and local HTTP checks. Synthetic IPA
signing is established. The reviewed nine-file browser-QA delta is published at
`00c1c93`: [run 37420583887](https://github.com/oskuhsiu/Tetherless/actions/runs/37420583887)
executes **18 real Chromium tests, all passed**, across root and project-subpath
routes in 16.118674 seconds. Source/lock identities, raw logs and JUnit reconcile;
actual Chromium mobile-viewport screenshots are retained. Coverage includes real
WASM synthetic-IPA signing, wrong-password recovery, cancellation/retry, repeated
clicks, clear/Back and mobile layout. This is Chromium with synthetic material;
real Apple, Safari, installation and deployment remain unverified.

The 18-file hosted-OTA extension is **unapproved and paused at review**. It is
separate from the published snapshot and receives no acceptance credit here.
No deployment or live Apple action is authorized or performed. The tracked
node-forge advisory remains; no clean dependency-audit claim is made.

In the published prototype, the ten-minute service TTL covers account sessions and
UDID enrollment. There is **no signed-IPA hosting endpoint**: output is a browser
Blob/download. The separate paid Ad Hoc helper requires externally authorized
HTTPS hosting. Free Personal Team clean-phone Safari installation remains
unproved, and paid evidence cannot substitute for it.

## Product acceptance remains unchanged

First authorized login/setup must lead to proactive, unattended mobile-only
renewal: no computer, opening the manager, refresh button or per-renewal restart.
Finish feasible development and non-device checks before one consolidated
[phone phase](DEVICE_ACCEPTANCE.md). Real login/2FA, live pairing, trusted install
and launch, actual profile application/readback, next-day locked-screen renewal,
original-expiry crossing and the separate 30-day observation remain unverified.
`appliedUnverified`, displayed expiry and manual refresh are not unattended success.

The [05:56 checkpoint](checkpoints/2026-10-06-retained-native-consumer-progress.md),
[23:25 status](STATUS-2026-10-05-2325.md),
[23:25 matrix](PLAN_PROGRESS-2026-10-05-2325.md) and
[earlier checkpoint](checkpoints/2026-10-05-native-pairing-progress.md) remain
historical evidence. `main`, release publication and web deployment are outside
this checkpoint's authorization.
