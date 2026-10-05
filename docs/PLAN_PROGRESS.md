# Original 16-task closure matrix

Evidence checkpoint: **2026-10-05 22:19 UTC**. The [original plan](ORIGINAL_PLAN.md)
is unchanged, SHA-256
49d049cea36c0872224e888e20074d08d313031a72d6ed9a128ef320370fe3a6.
All 16 IDs retain their original scope. No overall completion claim follows from
the new component, Swift/Core or unsigned-build evidence.

## Current position

- develop remains 3d97ef75a224a76f84ba6741da8d9a6b89f99217
- Published diagnostic source is ec7e229cc3b6d7bbf715225dc545481c213f81dd, tree
  5a70ead2300f3b161ea42fa13d53c18149662041, 544 leaves. Native source is
  1ed3b9c96810fa78c387da15ecbee8a544a1b68c, tree
  76ad67dc62e7a24d1716154f6f78df5ceca78a39, 540 leaves; ec7 adds only four diagnostic files
- Native run 37378994528 is terminal. All five Rust lanes report success; full
  acquisition transcript (three tests) has independent artifact reconciliation.
  The current 26/74/100/10 lane artifacts are not separately reconciled yet;
  their verified 3ae artifacts remain historical evidence
- Apple iOS-arm64 release Rust compilation passes in 197.595 seconds, as do
  provider-header and feature-graph checks. The selector then rejects a legitimate
  same-manifest custom-build/bin record before reaching the staticlib. Repair is
  under review; no Simulator slice, C/Swift probes or XCFramework exists yet
- Historical 3ae Swift composition run 37375339728 verifies 41 cases in each
  Debug/Release mode and all 24 source hashes. Host Core run 37375339731 verifies
  345 Swift Testing + 25 XCTest cases in each mode. No new iOS Core run was
  triggered; reviewed iOS Core evidence remains at ad9b33f. Separate Swift-19 and
  helper jobs report success, but their artifacts are not separately reconciled
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
  now have verified native evidence at their respective sources. Apple artifact
  selection/Simulator/link probes, diagnostic iOS consumer and UIKit composition
  remain open. Pairing promotion entry is separate active development, not activation.
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
| BASE-01 | Prior app/Core/Swift and 3ae native evidence stay scoped. Current 1ed independently verifies full acquisition transcript (3); all five Rust lanes report success. Apple device release Rust compilation and provider-header/features pass | **Active, non-device:** repair artifact selection, then verify Simulator/ABI/XCFramework and app/UI paths at one final SHA. Current other-lane artifacts need separate reconciliation. Latest full UI failed, 1fc Release was cancelled, and current full app compilation is not established |
| BASE-02 | Historical 32-component inventory, GPLv3 supplement and structural SPDX checks remain. Exact 1fc delivery reconciles 3,992 source entries and 91 notices. Component vendor/configuration/source audits now support actual host fixture builds | **Active + external evidence:** complete corresponding and producer source, linked notices, applicable relinking materials and durable delivery. Establish ADI origin/admission/use basis, Unicorn combined-license compatibility and binary provenance. Host compilation and matching hashes do not clear these gates |
| AUTH-01 | Account/key/session and typed authentication boundaries exist. Actual 1fc IDevice logger-Off spy checks pass in Debug/Release modes. Five-file EMProxy callback privacy is published at 5a with four portable passes | **Active, non-device:** execute the EMProxy native Swift spy and remaining logging/lifetime checks. Changes do not erase old logs or reconfigure existing subscribers. **Dependent on paused work:** public-certificate/profile startup/callback ownership. **Physical:** real login, 2FA, session expiry and repair |
| LEASE-01 | Profile-only renewal is separated from necessary full signing/install; core behavior is tested | **Active, non-device:** preserve this separation through final integration. **Physical:** prove both real routes; ordinary renewal must not become routine app or manager reinstallation |
| LEASE-02 | Profile selection, earliest effective expiry, readback and journal/database reconciliation are wired | **Physical:** actual profile application, compatible readback, forward effective expiry and launch. UI dates, mocks and appliedUnverified cannot close this row |
| AUTO-01 | Headless App Intent and background entrypoints are wired; policy/core tests exist | **Active, non-device:** finish candidate integration and honest trigger/permission diagnostics. **Physical:** scheduled locked-screen execution without opening the manager or connecting a computer |
| AUTO-02 | Historical c5 UI and failed current 3d97 boundaries stay unchanged. Archive analysis has 803/807 records classified; exact-event analysis finds one matching record but only a static assertion template, with four unsupported lines and no operation/error | **Active, non-device:** stop this inconclusive diagnostic path without rerun or widening. Actual UIKit compilation and any different readiness investigation require their own evidence-backed next step. No product fix or cause is established. Latest 18.6 stopped during installation; 26.2 never selected a file. **Physical:** authorized non-foreground self-check and automation |
| AUTO-03 | Core serialization/cancellation/backoff and scoped cache/backup/ODA ownership have tests. Later iOS Core runs pass with original assertions/bounds; 1366 records long await-resumption gaps and ad9 much shorter bodies | **Active, non-device:** finish temporary ingress/cleanup ownership and candidate verification. No production lock fix or unique stall cause is proved. **Dependent/paused:** certificate startup, local profile mutations and aggregate install budgets remain uncredited |
| SAFE-01 | Manager profile has renewal priority; ordinary renewal does not require manager replacement | **Physical:** next-day renewal and manager execution across original expiry. Manual refresh or a longer paid-account profile does not establish the free-account objective |
| SAFE-02 | Write-ahead journal, partial-success preservation and recovery/readback exist; scoped deletion lifetime tests retain ownership until work returns | **Active, non-device:** complete native interruption, persistence-failure and cleanup-race coverage. **Paused:** replacement integration is uncredited. **Physical:** real interruption/recovery without dropping pending evidence |
| INSTALL-01 | Input snapshots, bounded downloads and archive protections exist. Pairing-file UI and Swift/Core evidence remain limited to their own routes | **Active, non-device:** finish provider/data-retention coverage and final integration. **Paused:** signing/Mach-O/entitlement/nested-signature admission and aggregate install budgets. **Physical:** trusted IPA installation/launch and data preservation |
| INSTALL-02 | Certificate issuance/recovery and manager-replacement receipt primitives exist | **Paused:** first-sign to manager-replacement integration, identity/data-access continuity and interruption recovery receive no new credit. **Active when resumed:** verify the integrated candidate. **Physical:** authorized first signing/replacement and data recovery |
| PAIR-01 | Stored/import/reset and earlier static/Swift proofs stay scoped. Verified 3ae host (26, including M5), acquisition (74), combined (100) and host transcript (10) are retained. At 1ed, full acquisition transcript (3) independently verifies success/cancellation/deadline behavior against a synthetic peer; other lanes report success without fresh artifact reconciliation | **Active, non-device:** verify the Apple selector repair, Simulator slice, real C/Swift probes and XCFramework, then consumer/UIKit integration. Continue the separate promotion entry with joined cancellation, PIN lifetime, same-container challenge and failure-atomic promotion. New gates stay off. **Physical:** valid import/retention, peer compatibility, cancellation and re-pairing |
| QA-01 | Consolidated acceptance procedure exists; no device or soak test has run | **Physical, last:** next-day proactive locked-screen renewal, original-expiry crossing and longer observation. Do not wait seven days to iterate, advance the device clock or count manual refresh as unattended evidence |
| QA-02 | Historical app/UI/Core/Swift evidence remains. Current full acquisition transcript passes independently; Apple device Rust compilation succeeds but artifact selection fails. Other Rust lanes have API success, with fresh artifact reconciliation pending. Exact-event diagnosis stops inconclusively | **Active + external evidence:** selector repair and Apple producer/provider/link, remaining artifact reconciliation, final app/UI evidence, source/rights/provenance and temporary ownership. **Dependent/paused:** signing/replacement/install budgets and startup/callback ownership. **Physical:** traffic, performance, power, hardware protection and aggregate faults |
| BOOT-01 | Clean-phone first-install approaches remain documented research | **Separate research:** trusted completely computer-free initial delivery/install. Importing or generating pairing data does not prove initial installation; do not broaden the daily-renewal milestone |

## Remaining order

1. Preserve verified 1ed acquisition-transcript and device-compilation evidence
   separately from current other-lane API success and verified historical artifacts.
   Review the selector repair; record its exact next candidate/run when known
2. Complete Apple artifact selection, Simulator build, typed probes and XCFramework,
   then diagnostic consumer and actual UIKit composition. Continue the separate
   pairing promotion entry without activation. Earlier passes do not replace these gates
3. Run the published EMProxy spy in the normal native phase. Integrate reviewed
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
