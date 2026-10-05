# Original 16-task closure matrix

Evidence checkpoint: **2026-10-05 23:25 UTC**. The [original plan](ORIGINAL_PLAN.md)
is unchanged, SHA-256
49d049cea36c0872224e888e20074d08d313031a72d6ed9a128ef320370fe3a6.
All 16 IDs retain their original scope. No overall completion claim follows from
the new component, Swift/Core or unsigned-build evidence.

## Current position

- develop remains 3d97ef75a224a76f84ba6741da8d9a6b89f99217
- Published source is bf077f8ee433524422efc0ae6c2a8720c8cd6d4e, tree
  6e8e2532794dc6cef7fd5206d3afa989bba177eb, 552 leaves. Its reviewed 11-file
  typed promotion/harness slice leaves the native recipe unchanged
- Latest native source is bdb4d45c717a2a661d5a8814b6b6d18d5f88e0a3, tree
  2aa598314ff123c608494a513ea5334fb8399d9f, 546 leaves. Run 37384014669 reports
  success for all five Rust lanes. Current Rust artifacts are not independently
  reconciled here; verified 3ae component/host transcript and 1ed acquisition
  transcript (three tests) evidence retains its exact historical scope
- At bdb4d45, Apple device release Rust compilation passes in 177.527 seconds,
  exact Cargo artifact selection succeeds and the C host probe links. Swift host
  import then fails on the duplicate enum/UInt32 result-type name. The analogous
  validation-result collision is source-reviewed; its probe was not reached.
  Repair remains pending; no Simulator slice or XCFramework is established
- At bf077f8, Swift run 37386817674 independently verifies eight actual-manager
  cases in each Debug/optimized configuration and 41 composition cases in each
  Debug/Release mode, with source hashes and all joined commands. Manager parser,
  app state and process-lease acquisition are synthetic seams; composition uses
  a C ownership spy. Host Core 37386817620 independently verifies 345 Swift Testing
  + 33 XCTest cases per mode, including eight new promotion-boundary cases.
  iOS Core 37386817629 is terminal failure: all 33 XCTest cases and a separate
  20-case Swift Testing target pass, but the 339-case Core target fails three
  unchanged 60-second limits. The adjacent post-await trace gap is 101.862882459
  seconds, with no intervening await/lease operation; cause remains unknown.
  Automatic retry is forbidden and no rerun is planned. App run 37386817575 is skipped
- Historical 3ae Swift composition run 37375339728 verifies 41 cases in each
  Debug/Release mode and all 24 source hashes. Host Core run 37375339731 verifies
  345 Swift Testing + 25 XCTest cases in each mode. No iOS Core run was triggered
  at 3ae; ad9 and newer bf077 evidence remain separate. Separate Swift-19 and
  helper jobs report success, but their artifacts are not separately reconciled
- The four-file ODA cleanup candidate has no blocking independent source-review
  findings, with 23 portable passes and five Swift skips. It is unpublished and
  has no actual Swift composition execution. Header repair and gated UI remain
  in review without native-success credit
- Actual Rust helper/RSD 43 and host 20 fixtures pass at their recorded source
  revisions. Configuration, metadata and README alias build blockers are resolved
  within this host path
- Historical acquisition/combined profiles at 1366ace abort in the same composite
  cancellation fixture after preceding 18/25 passes. The repaired 5a40878
  [matrix 37369016726](https://github.com/oskuhsiu/Tetherless/actions/runs/37369016726)
  now passes acquisition 74 and combined 94, including 20 host fixtures. Original
  staged-acquisition tests, both new regressions, source/provider audits, hashes
  and command joins verify. This closes the observed fixture failure, not whole pairing
- Gated app composition at ad9b33f passes host Core with 345 Swift Testing + 25
  XCTest cases in each Debug/Release configuration, and iOS Core with 339 + 25.
  The standalone Swift/C-spy retry and artifact reconciliation establish 41 unique
  cases in each Debug/Release mode and all 24 input hashes. Neither route establishes
  real IDevice/Rust ABI or UIKit compilation
- Earlier 1fc native Debug/Core/iOS Core evidence remains scoped; its Release app
  job was cancelled. Latest full UI is still failed at 3d97ef7. Historical c5
  iOS 18.6 acceptance does not validate newer revisions
- New pairing routes remain gated off. Synthetic host and acquisition transcripts
  now have verified native evidence at their respective sources. Apple Swift import,
  remaining probes/Simulator/XCFramework, diagnostic iOS consumer and UIKit
  composition remain open. Typed promotion’s actual-manager harness passes with
  synthetic external seams; its live backend handoff remains unverified.
  Existing reload retains the cached protocol and does not prove all-caller/native
  adapter quiescence; saved bytes are not active-backend proof. Gates stay off.
  Published EMProxy privacy still needs its real native Swift spy
- Existing UI evidence shows Browse Locations with On My iPhone selected, without
  opening the local root. Fixture installation/LaunchServices and document creation
  succeeded; the original remains intact. Archive run 37375339797 exports/queries
  successfully but classifies 803 of 807 nonblank records and remains inconclusive.
  Enumeration predates root activation; 19 unlisted-domain records match an
  iconServices warning; a late timeout has no identified operation. Exact-event run
  37381049415 at ec7 observes one exact match but only “assertion failure: <value>”,
  without operation/error details and with four unsupported lines. This inconclusive
  diagnostic path stops; no rerun, widening, resolved cause or product fix is claimed

[STATUS.md](STATUS.md) gives the summary. The [checkpoint](checkpoints/2026-10-05-native-pairing-progress.md)
records exact source identities, artifacts and the boundary of each result.

## Gap types

- **Active, non-device:** feasible implementation or verification without the
  owner's phone or credentials. A queued run or reviewed source is not a pass
- **External evidence:** authenticated binary evidence or a documented rights/
  compatibility basis. Passing tests cannot create rights
- **Paused:** signing-admission, manager-replacement integration and aggregate
  install RAM/disk budget work, including dependent startup/callback boundaries.
  Their unpublished drafts receive no implementation, review or acceptance credit
- **Physical, later:** one consolidated authorized phone phase after feasible
  development and non-device gates
- **Separate research:** BOOT-01, outside ordinary mobile-only renewal proof

## Closure matrix

| ID | Established, scoped evidence | Remaining closure condition and gap type |
|---|---|---|
| BASE-01 | Prior app/Core/Swift and 3ae/1ed native artifacts stay scoped. At bdb, all five Rust lanes report success; Apple device Rust compilation, exact Cargo selection and C host linking pass. At bf077f8, manager 8 and composition 41 pass per configuration; host Core passes 345 + 33 per mode, while iOS Core passes all 33 XCTest cases but fails three unchanged Swift Testing limits | **Active, non-device:** repair Swift result-type import and respect the repeated iOS Core failure’s no-retry decision; verify remaining probes/Simulator/ABI/XCFramework and app/UI at one final SHA. Current Rust artifacts need separate reconciliation. Latest full UI failed, 1fc Release was cancelled, and current full app compilation is not established |
| BASE-02 | Historical 32-component inventory, GPLv3 supplement and structural SPDX checks remain. Exact 1fc delivery reconciles 3,992 source entries and 91 notices. Component vendor/configuration/source audits now support actual host fixture builds | **Active + external evidence:** complete corresponding and producer source, linked notices, applicable relinking materials and durable delivery. Establish ADI origin/admission/use basis, Unicorn combined-license compatibility and binary provenance. Host compilation and matching hashes do not clear these gates |
| AUTH-01 | Account/key/session and typed authentication boundaries exist. Actual 1fc IDevice logger-Off spy checks pass in Debug/Release modes. Five-file EMProxy callback privacy is published at 5a with four portable passes | **Active, non-device:** execute the EMProxy native Swift spy and remaining logging/lifetime checks. Changes do not erase old logs or reconfigure existing subscribers. **Dependent on paused work:** public-certificate/profile startup/callback ownership. **Physical:** real login, 2FA, session expiry and repair |
| LEASE-01 | Profile-only renewal is separated from necessary full signing/install; core behavior is tested | **Active, non-device:** preserve this separation through final integration. **Physical:** prove both real routes; ordinary renewal must not become routine app or manager reinstallation |
| LEASE-02 | Profile selection, earliest effective expiry, readback and journal/database reconciliation are wired | **Physical:** actual profile application, compatible readback, forward effective expiry and launch. UI dates, mocks and appliedUnverified cannot close this row |
| AUTO-01 | Headless App Intent and background entrypoints are wired; policy/core tests exist | **Active, non-device:** finish candidate integration and honest trigger/permission diagnostics. **Physical:** scheduled locked-screen execution without opening the manager or connecting a computer |
| AUTO-02 | Historical c5 UI and failed current 3d97 boundaries stay unchanged. Archive analysis has 803/807 records classified; exact-event analysis finds one matching record but only a static assertion template, with four unsupported lines and no operation/error | **Active, non-device:** stop this inconclusive diagnostic path without rerun or widening. Actual UIKit compilation and any different readiness investigation require their own evidence-backed next step. No product fix or cause is established. Latest 18.6 stopped during installation; 26.2 never selected a file. **Physical:** authorized non-foreground self-check and automation |
| AUTO-03 | Core serialization/cancellation/backoff and scoped cache/backup/ODA ownership have tests. Earlier iOS Core runs pass with original bounds; bf077 repeats three 60-second failures with an adjacent post-await trace gap. The unpublished four-file ODA cleanup candidate has source review and 23 portable passes, with five Swift skips | **Active, non-device:** execute the reviewed cross-cleaner repair’s Swift composition checks, preserving the ODA live stage and stable usage.lock inode and leaving reclamation to TransferWorkspace; then verify the final native candidate. Current published cleanup remains vulnerable to deleting that pool. No production lock fix or unique stall cause is proved. **Dependent/paused:** certificate startup, local profile mutations and aggregate install budgets remain uncredited |
| SAFE-01 | Manager profile has renewal priority; ordinary renewal does not require manager replacement | **Physical:** next-day renewal and manager execution across original expiry. Manual refresh or a longer paid-account profile does not establish the free-account objective |
| SAFE-02 | Portable journal/lock tests cover write-ahead and commit failures, partial success, cancellation and reconciliation without duplicate mutation; scoped deletion harnesses preserve ownership | **Active, non-device:** verify these routes in the final native candidate and execute/integrate the reviewed, unpublished ODA pool/lock cleanup repair. **Paused:** replacement and startup-dependent cases remain uncredited. **Physical:** real interruption/recovery without dropping pending evidence |
| INSTALL-01 | Input snapshots, bounded downloads and archive protections exist. Pairing-file UI and Swift/Core evidence remain limited to their own routes | **Active, non-device:** finish provider/data-retention coverage and final integration. **Paused:** signing/Mach-O/entitlement/nested-signature admission and aggregate install budgets. **Physical:** trusted IPA installation/launch and data preservation |
| INSTALL-02 | Certificate issuance/recovery and manager-replacement receipt primitives exist | **Paused:** first-sign to manager-replacement integration, identity/data-access continuity and interruption recovery receive no new credit. **Active when resumed:** verify the integrated candidate. **Physical:** authorized first signing/replacement and data recovery |
| PAIR-01 | Stored/import/reset and earlier static/Swift proofs stay scoped. Verified 3ae host (26, including M5), acquisition (74), combined (100), host transcript (10) and 1ed full acquisition transcript (3) are retained. All five bdb Rust lanes report success. Typed promotion’s actual-manager harness passes eight cases per configuration at bf077f8 with synthetic external seams | **Active, non-device:** resolve Apple Swift import and remaining probes/Simulator/XCFramework, then consumer/UIKit integration. Verify real parser/lock integration and a quiescent handoff of the committed record and intended protocol; existing reload uses cached protocol and lacks all-caller/adapter join proof. Preserve cancellation, PIN lifetime, same-container challenge and failure-atomic promotion. Gates stay off. **Physical:** valid import/retention, peer compatibility, cancellation and re-pairing |
| QA-01 | Consolidated acceptance procedure exists; no device or soak test has run | **Physical, last:** next-day proactive locked-screen renewal, original-expiry crossing and longer observation. Do not wait seven days to iterate, advance the device clock or count manual refresh as unattended evidence |
| QA-02 | Historical app/UI/Core/Swift and reconciled native transcripts remain scoped. At bdb, all Rust lanes have API success; Apple device compilation, Cargo selection and C host link pass, then Swift import fails. Promotion manager 8 and composition 41 pass per mode; host Core passes 345 + 33 per mode. iOS Core passes 33 XCTest cases but repeats three unchanged Swift Testing limits; no automatic retry or rerun is planned. Exact-event diagnosis remains inconclusive and stopped | **Active + external evidence:** Swift import repair and remaining Apple producer/provider/link proofs, promotion/backend handoff, current artifact reconciliation, final app/UI evidence, source/rights/provenance and ODA pool/lock protection during generic cleanup. **Dependent/paused:** signing/replacement/install budgets and startup/callback ownership. **Physical:** traffic, performance, power, hardware protection and aggregate faults |
| BOOT-01 | Clean-phone first-install approaches remain documented research | **Separate research:** trusted completely computer-free initial delivery/install. Importing or generating pairing data does not prove initial installation; do not broaden the daily-renewal milestone |

## Remaining order

1. Retain scoped bf077f8 host Core/manager/composition passes and the terminal iOS
   Core failure. Respect the classifier’s no-retry decision; cause remains unknown.
   Preserve bdb device
   compilation, exact selection and C host link evidence separately from its Rust
   API successes and the reconciled historical artifacts
2. Repair and verify Apple Swift result-type import, remaining probes, Simulator
   build and XCFramework, then diagnostic consumer and actual UIKit composition.
   Establish a quiescent handoff of the committed record and intended protocol;
   persistence alone does not prove backend readiness. Keep pairing gates off
3. Execute the reviewed, unpublished ODA pool/lock cleanup candidate’s Swift
   composition checks, then integrate only with the required evidence.
   Run the published EMProxy spy in the normal native phase. Integrate reviewed
   changes into one app candidate. Stop the inconclusive exact-event path without
   rerun or widening; any different UI work needs new discriminating evidence and
   original assertions. No cause or product fix follows from the retained diagnostics
4. Complete source/notice/delivery and external authenticity/rights gates. Keep
   paused signing/replacement/budget scope and its dependencies separate
5. Request one consolidated [phone phase](DEVICE_ACCEPTANCE.md) only after feasible
   development: authorized login/2FA and permissions, pairing/recovery, install/launch,
   profile application/readback, next-day locked-screen renewal and expiry crossing

Development authorization excludes main promotion and release. BOOT-01 remains
separate; iOS background execution is not guaranteed under every condition.
