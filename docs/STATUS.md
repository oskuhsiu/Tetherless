# Tetherless development status

Evidence checkpoint: **2026-10-06 05:56 UTC**. The retained native producer now
passes both Apple slices and all 12 C/Swift ABI link probes. Its diagnostic app
consumer passes unsigned **Release** compilation; **Debug fails** on a declaration
mismatch between `libimobiledevice` and `IDevice`. Further review found overlapping
Rust/C exports with incompatible ABIs. Release compilation does not prove correct
provider ownership. A header-only patch was rejected; full Rust FFI namespace
isolation and matched consumer changes now have a reviewed 35-file candidate.
The candidate remains unpublished; no new native commit or run is verified.
Product wireless-pairing gates stay off.
All 16 original tasks remain open; this is not a phone-ready or release candidate.

## Source and current result

- `develop`: **3d97ef75a224a76f84ba6741da8d9a6b89f99217**, unchanged
- Published branch head: [00c1c9397a01107b045d17b0ccba64431197d975](https://github.com/oskuhsiu/Tetherless/commit/00c1c9397a01107b045d17b0ccba64431197d975)
  on `verify/staged-pairing-native`; tree
  `6b535da4d6e85190a0474e56fbc046bef7c43993`, 699 leaves. It includes the
  original 70 web files and nine-file browser-QA delta; unrelated entries are unchanged
- Latest native consumer evidence remains at [3f717ea5441d2cacee13e1d078e5ba7f1484edc5](https://github.com/oskuhsiu/Tetherless/commit/3f717ea5441d2cacee13e1d078e5ba7f1484edc5);
  web source publication does not constitute a new native verification
- Accepted native producer: [9ee2ccc9bd3519053781087acde54d4b4ee43236](https://github.com/oskuhsiu/Tetherless/commit/9ee2ccc9bd3519053781087acde54d4b4ee43236),
  [run 37400684000](https://github.com/oskuhsiu/Tetherless/actions/runs/37400684000),
  attempt 1. Acceptance is limited to the closed diagnostic consumer
- Latest diagnostic consumer: [run 37407474925](https://github.com/oskuhsiu/Tetherless/actions/runs/37407474925),
  attempt 1 at `3f717ea`, terminal **failure** at 03:22 UTC. Normal tests,
  preparation and exact producer binding pass; Debug fails; Release passes

| Evidence | Established result | Limit |
|---|---|---|
| Current `3f717ea` diagnostic run | Core: 345 Swift Testing + 40 XCTest cases in each Debug/Release mode. Integration: 499 collected, 492 passed, seven skipped before preparation. Diagnostic: 231 passed. Prepared contracts: 13 passed without skips | Source, fixture and build evidence; no app execution or physical acceptance. The seven pre-preparation skips are not passes |
| Same run, unsigned app | Actual UIKit/composition compilation and linking pass in Release. Debug exits 65: `PLIST_OPT_COERCE` is in `libimobiledevice`'s `plist_write_options_t` but absent from the `IDevice` definition | Both static archives are linked and have conflicting exports/ABIs; no link map identifies the selected providers. No Debug success, correct provider ownership, product activation, install or launch is established |
| `9ee2ccc` native producer | Five Rust lanes pass and are reconciled: host 26, acquisition 74, combined 100, host transcript 10, acquisition transcript three. Both Apple slices, 12 ABI probes, 61 joined commands, 166 output hashes and 167 checksum entries verify; XCFramework packaging drains naturally without cleanup signals | Synthetic native fixtures and build/link evidence. No live peer/protocol, iOS runtime or product acceptance |
| Current cold-reader fixture | Normal macOS Integration executes the actual manager/store and ordinary parser in distinct writer/reader processes, in Debug/optimized modes, with nine scenarios each | Synthetic app/preferences/process-lock and receiver seams; no native gateway, cached-protocol switch, startup mutation or all-caller quiescence proof |
| `4838168`, [support run 37393328997](https://github.com/oskuhsiu/Tetherless/actions/runs/37393328997) | Actual ODA cleanup positive/negative controls and EMProxy Debug/Release callback spy: ten tests, no skips; 13 source inputs and three derived fixtures verify | Production-source fixtures with external seams. Does not erase prior logs, reconfigure an existing subscriber or prove complete app behavior |
| `a12b3ed`, [Core](https://github.com/oskuhsiu/Tetherless/actions/runs/37391449382), [iOS Core](https://github.com/oskuhsiu/Tetherless/actions/runs/37391449448), [Swift fixtures](https://github.com/oskuhsiu/Tetherless/actions/runs/37391449492) | Host 345 + 40 per mode; iOS Core 339 + 40. Composition 41 per mode; actual-manager promotion eight per mode, with source/command reconciliation | Composition uses a C ownership spy; promotion has synthetic external seams. The iOS pass does not explain or repair the historical `bf077f8` timing failure |

The namespace candidate passed independent source/portable review: 255 diagnostic,
45 namespace and 11 mixed-provider tests, plus C header-coexistence syntax checking.
The previously unavailable authentic C-provider download is now retained; its
actual device and Simulator slice inputs pass the unchanged `mixed_provider.py`
verifier. This verifies input acceptance, not Apple mixed-provider linking. New
Rust exports, disjoint provider ownership, mixed C/Swift links, linker maps and
new Debug/Release app builds remain pending. The namespace candidate is
unpublished; no new native commit or run is claimed.

Full identities, artifact hashes, intermediate failures and limits are in the
[new checkpoint](checkpoints/2026-10-06-retained-native-consumer-progress.md).
The [16-task matrix](PLAN_PROGRESS.md) records closure conditions.

## Remaining work before a phone request

1. Complete publication of the reviewed Rust FFI namespace/consumer candidate,
   then verify its exact native producer and app consumer with explicit
   provider-ownership evidence. The accepted Rust IDevice archive has 100 global `plist_*` exports; eight mutator
   return types differ from C libplist. Other overlapping device-service exports
   also have differing ABIs. A header-only fix is insufficient. Verify the new
   exact producer/consumer source before crediting a repair; preserve the current
   Release compile pass without treating it as ownership or runtime proof
2. Establish the committed-record/intended-protocol handoff and caller/native
   worker quiescence. Cold-reader persistence/selection is now tested, but the live
   backend contract remains open. Do not require a manual restart on each renewal
3. Complete remaining non-device UI, source/notice and delivery work. The last full
   product UI run still failed at `3d97ef7`; its exhausted archive investigation
   remains inconclusive and stopped. Any new UI run needs its own evidence-backed
   decision under the Simulator CI rules
4. Preserve the pause on native signing-admission/certificate/Mach-O parser work,
   manager-replacement integration, aggregate install budgets and dependent
   startup/callback ownership. Their drafts receive no new credit here
5. Resolve external ADI origin/admission/acquisition-use evidence, Unicorn
   compatibility and provider source/binary provenance. Compilation and inventory
   hashes do not establish rights

The accepted producer's source archive has 46,639 entries and 189 recipe files
verified. A separately reviewed, **unpublished** inventory adds 359 registry and
four workspace packages, target/host/source classifications, 666 notice files and
232 exact notice texts. Three target-package and 13 additional source-only named
notice gaps remain. It is not a complete product SBOM or license clearance.

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

At the same source, [Core run 37420583864](https://github.com/oskuhsiu/Tetherless/actions/runs/37420583864)
reports API success. Its raw test counts are not reconciled here; earlier exact
counts remain attributed to their recorded source commits.

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

The [23:25 status](STATUS-2026-10-05-2325.md),
[23:25 matrix](PLAN_PROGRESS-2026-10-05-2325.md) and
[earlier checkpoint](checkpoints/2026-10-05-native-pairing-progress.md) remain
historical evidence. `main`, release publication and web deployment are outside
this checkpoint's authorization.
