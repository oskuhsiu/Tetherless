# Original 16-task closure matrix

Evidence checkpoint: **2026-10-06 11:37 UTC**. All 16 original IDs retain their
scope and remain open. The [original plan](ORIGINAL_PLAN.md) is unchanged:
SHA-256 `49d049cea36c0872224e888e20074d08d313031a72d6ed9a128ef320370fe3a6`.

## Current position and evidence boundaries

`develop` remains `3d97ef75a224a76f84ba6741da8d9a6b89f99217`. Verification
source is [80265213253940a904a0d1d0eae2bdbcd34066ce](https://github.com/oskuhsiu/Tetherless/commit/80265213253940a904a0d1d0eae2bdbcd34066ce)
on `verify/staged-pairing-native`. The 35-file Rust FFI namespace/consumer repair
is published at `b477539`, including matched consumer metadata. With the
`6af17537` reader repair, [run 37446415281](https://github.com/oskuhsiu/Tetherless/actions/runs/37446415281)
verifies complete Rust/C scans, 382 expected device-archive names, no old aliases,
disjoint export sets, 31 joined commands and two native links. Its five Rust
companion lanes pass 26/74/100/10/3. The run then fails on four internal C SHA512
collisions; Simulator/package and final App ownership remain unaccepted.

The isolated C source derivation at `7d89a9f3` makes 30 identifier substitutions
across six Ed25519 files without changing algorithms, layouts, public headers or
the authenticated OpenSSL 3.6.2 provider. Linux ordinary/ASan fixtures pass.
After the alias-path and Swift-format corrections, current [C run 37456626052](https://github.com/oskuhsiu/Tetherless/actions/runs/37456626052)
passes 84 portable + 16 host contracts and authenticated Apple/SDK/Swift inputs,
then stops before macOS-host crypto or C compilation: six tool commands are
unavailable through approved lookup paths. Approval for Autoconf, Automake, GNU
Libtool and GNU m4 installation on disposable CI is pending; installation and
dependent native work are paused. The two earlier failed C attempts remain rejected.

Current [Core run 37456625983](https://github.com/oskuhsiu/Tetherless/actions/runs/37456625983)
at `80265213` passes 345 Swift Testing + 40 XCTest cases in each Debug/Release
mode, with raw logs verified. Actual macOS [fixtures at `805e1b8`](https://github.com/oskuhsiu/Tetherless/actions/runs/37443731193)
pass eight generated-record promotion and 41 composition cases per mode within
their synthetic seams. Producer-bound unsigned App retention is published at
`fb0a95f4` with scoped tests, but no new full App build/package has run. The App
runtime context still names historical `9ee`; the historical `3f` Release compile
did not retain a binary and its Debug build failed. Neither validates current source.

The 70-file web prototype and nine-file browser-QA delta are published. [Browser
run 37420583887](https://github.com/oskuhsiu/Tetherless/actions/runs/37420583887)
passes 18 Chromium cases including real WASM signing of a synthetic IPA. No
Safari, real Apple login, service deployment or clean-phone installation follows.
Product wireless gates remain off. See [current status](STATUS.md) for exact
source/run boundaries; scoped passes below do not close the overall tasks.

- **Active:** feasible implementation or verification without the owner's phone
  or credentials. Reviewed source, queued work and skipped tests are not passes
- **External:** missing rights, authenticity or source/binary provenance evidence
- **Paused:** native signing-admission/certificate/Mach-O parser work,
  manager-replacement integration, aggregate install RAM/disk budgets and dependent
  startup/callback ownership. No inspection, implementation or review credit is
  assigned to their paused drafts
- **Physical, later:** one consolidated authorized phone phase after feasible
  development/non-device gates; real-time observation remains separate
- **Bootstrap:** clean-phone first installation is independently unproved and
  cannot be inferred from pairing, signed-output generation or daily renewal

## Closure matrix

| ID | Established, scoped evidence | Remaining closure condition and gap type |
|---|---|---|
| BASE-01 | Namespace repair published at `b477539`; `6af17537` device scans verify 382 names/no old aliases, Rust/C disjointness, two native links and five Rust lanes (26/74/100/10/3). Current `80265213` Core passes 345 + 40 per Debug/Release mode. Historical `9ee` two-slice/XCFramework and `3f` Release compile evidence remain scoped to those commits | **Approval-dependent + active:** complete the isolated C rebuild after the disposable-CI tool prerequisite is authorized; then admit its exact output to the Rust producer, prove mixed-provider links/map ownership and build/package both App modes. Current C preflight passed 84 + 16 contracts and Apple identities but never reached host crypto or C compilation. No current integrated App/UI pass; latest full product UI remains failed |
| BASE-02 | Historical product inventory/delivery retained. Exact `9ee` source archive: 46,639 entries and 189 recipe files verified. Reviewed [published supplement](supply-chain/native-9ee2ccc-README.md): 359 registry + four workspace packages, target/host/source distinctions, 666 notice files and 232 texts. Exact producer-bound unsigned App retention is published at `fb0a95f4` with 286 diagnostic, seven package and 37 delivery test passes | **Active + external:** produce and inspect actual current App packages; integrate the historical supplement into exact delivery and complete source/notices/relinking/durable distribution. Resolve three target notice-text treatment and 13 additional source-only named-notice gaps. ADI origin/admission/acquisition-use basis, Unicorn compatibility and provider source/binary equivalence remain open. Inventory and packaging fixtures are not rights clearance or delivered product evidence |
| AUTH-01 | Native authentication/secret boundaries and historical IDevice logger-Off fixtures exist. Actual EMProxy initializer/callback spy passes Debug/Release within ten support tests at `4838168`; historical `3f` normal Integration passes that route | **Active:** finish remaining unpaused logging/lifetime and final integration checks. **Paused dependency:** public-certificate/profile startup/callback ownership. **Physical:** real login, 2FA, session expiry/repair and secret-access conditions. Existing subscriber state and prior logs are not retroactively changed |
| LEASE-01 | Profile-only renewal is separated from necessary full signing/install; core policy tests pass at the current source | **Active:** preserve the separation through coherent integration. **Physical:** prove both real routes; normal renewal must not require routine app/manager reinstallation |
| LEASE-02 | Profile selection, effective expiry, readback and journal/database reconciliation are wired and fixture-tested | **Physical:** actual application, compatible system readback, forward effective expiry and launch. UI dates, synthetic results and `appliedUnverified` cannot close this row; paused admission work receives no new credit |
| AUTO-01 | Headless App Intent/background entrypoints and coordinator policies exist; current Core tests pass | **Active:** complete final integration and honest trigger/permission diagnostics within unpaused scope. **Physical:** authorized locked-screen execution without opening the manager or connecting a computer; no guaranteed OS timer claim |
| AUTO-02 | Guided setup/self-check source exists. Historical `c5` invalid-input/signed-out UI passed; latest `3d97` full UI failed. Retained archive/exact-event diagnostics are inconclusive | **Active:** final UI integration and a distinct evidence-backed readiness investigation under Simulator CI rules; do not rerun/widen the exhausted diagnostic path or claim a cause. **Physical:** initial authorization and a real non-foreground self-check without an Open App step |
| AUTO-03 | Core serialization, cancellation, backoff and scoped ownership tests pass. Published ODA pool/lock preservation is exercised by actual Swift positive/negative controls at `4838168`; historical `3f` Integration passes | **Active:** final integrated non-device verification. Historical `bf077` three 60-second failures remain unexplained despite later `a12` iOS Core success. **Paused dependency:** startup/profile-mutation ownership and aggregate install budgets. **Physical:** competing real entrypoints and cancellation without unsafe mutation |
| SAFE-01 | Manager profile renewal has priority; ordinary renewal is distinct from manager replacement | **Physical:** proactive next-day renewal and continued manager execution across original expiry. Manual refresh/restart or a longer paid-account profile cannot establish the free-account objective |
| SAFE-02 | Portable journal/lock tests cover write-ahead/commit failure, partial success, cancellation and reconciliation before retry. Published ODA ownership repair now has actual positive/negative Swift evidence | **Active:** verify recovery in the final integrated candidate. **Paused:** replacement/startup-dependent recovery receives no new credit. **Physical:** interruption/readback recovery without duplicate resources or loss of pending evidence |
| INSTALL-01 | Input snapshots, bounded downloads and archive protections have scoped tests. Historical `3f` unsigned Release compiled; published `fb0a95f4` retention has scoped package tests | **Active:** remaining unpaused provider/data-retention coverage, actual App packages and final integration. **Paused:** signing/Mach-O/entitlement/nested-signature admission and aggregate install budgets. **Physical:** trusted IPA installation/launch and data preservation; a compiled app, packaging fixture or synthetic web-signed IPA is insufficient |
| INSTALL-02 | Previously documented certificate/replacement receipt primitives remain historical evidence | **Paused:** first-sign to manager-replacement integration, certificate/admission, identity/data-access continuity and interruption recovery are uncredited. **After authorized resumption:** integrated verification. **Physical:** authorized identity transition/replacement and recovery; web bootstrap does not close this dependency |
| PAIR-01 | Historical `9ee` native fixtures/two slices/ABI probes and `3f` Release UIKit/composition compile. Published namespace repair has `6af17537` device export and two-link evidence. At `805e1b8`, actual macOS promotion eight and composition 41 per mode pass. Historical `3f` cold reader exercises actual manager/store/ordinary parser in separate processes, nine scenarios per mode | **Approval-dependent + active:** complete C producer and subsequent Rust mixed-provider/App verification with map ownership, then safe committed-record/intended-protocol handoff with caller/native-worker quiescence. Cold/composition fixtures exclude actual gateway/native handle/live peer/startup. Cached-protocol and live-backend proof remain open; no per-renewal manual restart. Gates stay off. **Physical:** valid import/retention, peer compatibility, cancellation and phone-side re-pairing |
| QA-01 | Consolidated acceptance procedure exists; no device or soak execution has occurred | **Physical, last:** next-day unattended locked-screen renewal, original-expiry crossing and the original 30-day observation under declared conditions. Do not advance the clock, wait seven days for each development iteration or count manual refresh/debugger activity as unattended evidence |
| QA-02 | Current `80265213` Core 345 + 40 per mode; exact native export/two-link progress at `6af17537`; `805e1b8` promotion/composition fixtures; C portable/preflight and Linux crypto fixture passes. Historical App/native/support/cold-reader evidence remains at its original commits. Real Chromium QA passes 18 synthetic-input cases at `00c1c93`. Failure artifacts preserved | **Approval-dependent + active + external:** finish C native build, mixed-provider ownership, both App packages and final UI/live-backend closure; remaining notice/provenance/rights and unpaused security checks. **Paused dependencies:** signing/replacement/install budgets and startup/callback ownership; stopped picker diagnostic receives no retry credit. **Physical:** traffic, power, performance, hardware protection and real fault matrix. No general production-safety claim |
| BOOT-01 | Original reviewed 70-file prototype published at `01bf960`: real zsign WASM synthetic IPA signing, 47 frontend tests/build; 19 offline Rust tests, format/Clippy/release/HTTP checks. Temporary account/UDID service and browser-only signed output are implemented. Nine-file browser-QA delta published at `00c1c93`; all 18 real Chromium tests pass across root/project-subpath, including real WASM synthetic signing, cancellation/retry, stale-output prevention and mobile layout | **Active + authorization + physical:** genuine artifact binding, Safari checks and separately authorized Apple operations; Chromium synthetic-material results do not establish those gates. The 18-file hosted-OTA extension is unapproved and paused at review; no deployment is authorized. Still needed: free Personal Team clean-phone installation, first native login and identity continuity. No signed-IPA host endpoint; ten-minute TTL covers account/enrollment sessions only. Paid Ad Hoc needs external HTTPS hosting and cannot replace free-Team proof; tracked dependency risk remains |

## Remaining order

1. Resolve the disposable-CI tool prerequisite, then verify the isolated C
   producer and separately admit its exact retained output into the Rust producer.
   Prove mixed-provider links/map ownership before selecting a new App context;
   preserve the already verified namespace/export results and all rejected attempts
2. Build and retain both unsigned App configurations against accepted inputs.
   Close unpaused pairing handoff and remaining integration/UI work without
   manual per-renewal restart or weakened assertions; keep gates off and the
   original picker diagnostic stopped
3. Integrate historical source/notices into actual exact delivery, preserving
   scoped evidence and unresolved rights/provenance. Respect the separately
   paused signing/replacement/install-budget/startup and hosted-OTA scopes;
   deployment and live Apple actions need their own authorization
4. Request one consolidated [phone phase](DEVICE_ACCEPTANCE.md) only after feasible
   development gates. Keep clean-phone bootstrap, normal unattended renewal and
   the 30-day observation as distinct acceptance outcomes

See [current status](STATUS.md) and the
[historical 05:56 checkpoint](checkpoints/2026-10-06-retained-native-consumer-progress.md).
The [previous matrix](PLAN_PROGRESS-2026-10-05-2325.md) is preserved as history.
No all-task completion, release, `main` promotion or phone readiness is claimed.
