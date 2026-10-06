# Original 16-task closure matrix

Evidence checkpoint: **2026-10-06 05:56 UTC**. All 16 original IDs retain their
scope and remain open. The [original plan](ORIGINAL_PLAN.md) is unchanged:
SHA-256 `49d049cea36c0872224e888e20074d08d313031a72d6ed9a128ef320370fe3a6`.

## Current position and evidence boundaries

`develop` remains `3d97ef75a224a76f84ba6741da8d9a6b89f99217`. Published branch
head is `00c1c9397a01107b045d17b0ccba64431197d975`, tree
`6b535da4d6e85190a0474e56fbc046bef7c43993`, 699 leaves: the original 70 web
files plus the reviewed nine-file browser-QA delta, with unrelated entries
unchanged. Native consumer evidence remains tied to
`3f717ea5441d2cacee13e1d078e5ba7f1484edc5`. The accepted native producer is
`9ee2ccc9bd3519053781087acde54d4b4ee43236`,
[run 37400684000](https://github.com/oskuhsiu/Tetherless/actions/runs/37400684000).
Both Apple slices, all 12 C/Swift ABI link probes, the XCFramework and all five
Rust lanes now have reconciled evidence.

At `3f717ea`, [diagnostic run 37407474925](https://github.com/oskuhsiu/Tetherless/actions/runs/37407474925)
passes normal tests, preparation, producer binding and unsigned Release app
compilation. Debug fails on the `PLIST_OPT_COERCE`/`plist_write_options_t`
declaration mismatch. Review also found overlapping Rust/C exports with differing
ABIs in the two directly linked static archives; no link map proves the selected
providers. A header-only patch was rejected. Full Rust FFI namespace isolation
and matched consumer changes have a reviewed 35-file candidate; the candidate remains
unpublished, with no new native commit or run. Both real C-provider slice inputs
now pass the unchanged verifier; new Apple mixed-provider linking and final
provider ownership remain unverified.
The run remains terminal failure. Product wireless gates remain off. The new
native and source-fixture evidence closes specific earlier blockers, not the
overall tasks below.

At `00c1c93`, [browser run 37420583887](https://github.com/oskuhsiu/Tetherless/actions/runs/37420583887)
passes all 18 real Chromium cases at root/project-subpath, with source/lock and
JUnit reconciliation. Its synthetic signing material does not establish Apple,
Safari or install acceptance. [Core run 37420583864](https://github.com/oskuhsiu/Tetherless/actions/runs/37420583864)
also reports API success; raw test counts are not reconciled here.

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
| BASE-01 | Exact published source/locks; accepted `9ee` producer with five Rust lanes (26/74/100/10/3), both Apple slices, 12 ABI probes and retained XCFramework. At `3f`, host Core 345 + 40 per Debug/Release mode, 492 Integration passes plus seven skips, 231 diagnostic and 13 prepared-contract passes; unsigned Release app compiles | **Active:** publish and natively verify the reviewed 35-file namespace/consumer candidate, prove provider ownership and verify one integrated final SHA and applicable app/UI gates. Actual C-provider device/Simulator inputs now pass the unchanged verifier; this is not mixed-provider link success. Release directly links both archives; its compile pass proves neither selected-provider ownership nor execution; latest full product UI remains failed |
| BASE-02 | Historical product inventory/delivery retained. Exact `9ee` source archive: 46,639 entries and 189 recipe files verified. Reviewed unpublished supplement: 359 registry + four workspace packages, compiler-target/host/source distinctions, 666 notice files and 232 texts | **Active + external:** publish/integrate the scoped supplement and complete product source/notices/relinking/durable delivery; resolve three target and 13 additional source-only named-notice gaps. ADI origin/admission/acquisition-use basis, Unicorn compatibility and provider source/binary equivalence remain open. Inventory is not rights clearance or a final linked graph |
| AUTH-01 | Native authentication/secret boundaries and historical IDevice logger-Off fixtures exist. Actual EMProxy initializer/callback spy passes Debug/Release within ten support tests at `4838168`; current normal Integration passes that route | **Active:** finish remaining unpaused logging/lifetime and final integration checks. **Paused dependency:** public-certificate/profile startup/callback ownership. **Physical:** real login, 2FA, session expiry/repair and secret-access conditions. Existing subscriber state and prior logs are not retroactively changed |
| LEASE-01 | Profile-only renewal is separated from necessary full signing/install; core policy tests pass at the current source | **Active:** preserve the separation through coherent integration. **Physical:** prove both real routes; normal renewal must not require routine app/manager reinstallation |
| LEASE-02 | Profile selection, effective expiry, readback and journal/database reconciliation are wired and fixture-tested | **Physical:** actual application, compatible system readback, forward effective expiry and launch. UI dates, synthetic results and `appliedUnverified` cannot close this row; paused admission work receives no new credit |
| AUTO-01 | Headless App Intent/background entrypoints and coordinator policies exist; current Core tests pass | **Active:** complete final integration and honest trigger/permission diagnostics within unpaused scope. **Physical:** authorized locked-screen execution without opening the manager or connecting a computer; no guaranteed OS timer claim |
| AUTO-02 | Guided setup/self-check source exists. Historical `c5` invalid-input/signed-out UI passed; latest `3d97` full UI failed. Retained archive/exact-event diagnostics are inconclusive | **Active:** final UI integration and a distinct evidence-backed readiness investigation under Simulator CI rules; do not rerun/widen the exhausted diagnostic path or claim a cause. **Physical:** initial authorization and a real non-foreground self-check without an Open App step |
| AUTO-03 | Core serialization, cancellation, backoff and scoped ownership tests pass. Published ODA pool/lock preservation is exercised by actual Swift positive/negative controls at `4838168`; current Integration passes | **Active:** final integrated non-device verification. Historical `bf077` three 60-second failures remain unexplained despite later `a12` iOS Core success. **Paused dependency:** startup/profile-mutation ownership and aggregate install budgets. **Physical:** competing real entrypoints and cancellation without unsafe mutation |
| SAFE-01 | Manager profile renewal has priority; ordinary renewal is distinct from manager replacement | **Physical:** proactive next-day renewal and continued manager execution across original expiry. Manual refresh/restart or a longer paid-account profile cannot establish the free-account objective |
| SAFE-02 | Portable journal/lock tests cover write-ahead/commit failure, partial success, cancellation and reconciliation before retry. Published ODA ownership repair now has actual positive/negative Swift evidence | **Active:** verify recovery in the final integrated candidate. **Paused:** replacement/startup-dependent recovery receives no new credit. **Physical:** interruption/readback recovery without duplicate resources or loss of pending evidence |
| INSTALL-01 | Input snapshots, bounded downloads and archive protections have scoped tests. Current unsigned Release diagnostic builds | **Active:** remaining unpaused provider/data-retention coverage and final integration. **Paused:** signing/Mach-O/entitlement/nested-signature admission and aggregate install budgets. **Physical:** trusted IPA installation/launch and data preservation; a compiled app or synthetic web-signed IPA is insufficient |
| INSTALL-02 | Previously documented certificate/replacement receipt primitives remain historical evidence | **Paused:** first-sign to manager-replacement integration, certificate/admission, identity/data-access continuity and interruption recovery are uncredited. **After authorized resumption:** integrated verification. **Physical:** authorized identity transition/replacement and recovery; web bootstrap does not close this dependency |
| PAIR-01 | Accepted `9ee` native fixtures, transcripts, both slices and ABI probes; current Release UIKit/composition compile. `a12` promotion eight and composition 41 per mode. Current cold reader runs actual manager/store/ordinary parser across separate writer/reader processes, nine scenarios per mode | **Active:** publish/natively verify reviewed FFI namespace/consumer isolation with provider-ownership evidence, final integration and safe committed-record/intended-protocol handoff with caller/native-worker quiescence. Cold fixtures exclude actual gateway/native handle/live peer/startup. Cached-protocol and live-backend proof remain open; no per-renewal manual restart. Gates stay off. **Physical:** valid import/retention, peer compatibility, cancellation and phone-side re-pairing |
| QA-01 | Consolidated acceptance procedure exists; no device or soak execution has occurred | **Physical, last:** next-day unattended locked-screen renewal, original-expiry crossing and the original 30-day observation under declared conditions. Do not advance the clock, wait seven days for each development iteration or count manual refresh/debugger activity as unattended evidence |
| QA-02 | Current Core/Integration/diagnostic/prepared-contract passes and Release compile; accepted native/source evidence; actual ODA/EMProxy and cold-reader fixtures. Real Chromium bootstrap QA passes 18 cases at `00c1c93`, with synthetic input. Historical failure artifacts preserved | **Active + external:** FFI namespace and provider-ownership proof, Debug/final-app/UI closure, live-backend contract, remaining source/notice/provenance/rights checks and unpaused security tests. **Paused dependencies:** signing/replacement/install budgets and startup/callback ownership. **Physical:** traffic, power, performance, hardware protection and real fault matrix. No general production-safety claim |
| BOOT-01 | Original reviewed 70-file prototype published at `01bf960`: real zsign WASM synthetic IPA signing, 47 frontend tests/build; 19 offline Rust tests, format/Clippy/release/HTTP checks. Temporary account/UDID service and browser-only signed output are implemented. Nine-file browser-QA delta published at `00c1c93`; all 18 real Chromium tests pass across root/project-subpath, including real WASM synthetic signing, cancellation/retry, stale-output prevention and mobile layout | **Active + authorization + physical:** genuine artifact binding, Safari checks and separately authorized Apple operations; Chromium synthetic-material results do not establish those gates. The 18-file hosted-OTA extension is unapproved and paused at review; no deployment is authorized. Still needed: free Personal Team clean-phone installation, first native login and identity continuity. No signed-IPA host endpoint; ten-minute TTL covers account/enrollment sessions only. Paid Ad Hoc needs external HTTPS hosting and cannot replace free-Team proof; tracked dependency risk remains |

## Remaining order

1. Complete publication of the reviewed namespace/consumer candidate, then verify
   the exact new producer and app consumer, including provider ownership and
   retained linker maps. The actual C inputs are now verified; Apple mixed-provider
   execution has not run. A header-only patch is insufficient
2. Close the unpaused pairing handoff and remaining app/UI/integration work without
   manual per-renewal restart or weakened acceptance assertions; keep gates off
3. Integrate the reviewed source/notice work with its stated limits; the original
   70 web files and browser-QA delta are published, and Chromium tests pass.
   Resolve external
   rights/provenance; respect paused native and hosted-OTA scope, plus separate
   deployment/account permissions
4. Request one consolidated [phone phase](DEVICE_ACCEPTANCE.md) only after feasible
   development gates. Keep clean-phone bootstrap, normal unattended renewal and
   the 30-day observation as distinct acceptance outcomes

See [current status](STATUS.md) and the
[dated checkpoint](checkpoints/2026-10-06-retained-native-consumer-progress.md).
The [previous matrix](PLAN_PROGRESS-2026-10-05-2325.md) is preserved as history.
No all-task completion, release, `main` promotion or phone readiness is claimed.
