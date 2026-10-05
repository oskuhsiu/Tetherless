# Original 16-task closure matrix

Evidence checkpoint: 2026-10-05 10:28 UTC. The [original plan](ORIGINAL_PLAN.md)
remains unchanged (SHA-256
`49d049cea36c0872224e888e20074d08d313031a72d6ed9a128ef320370fe3a6`).
The 16 IDs below preserve its task scope. Closure is tied to the named SHA and
acceptance condition; no overall completion claim follows from a test count,
temporary capability gate or partial implementation.

## Current position

- Published `develop`: `c5f5547fc481a8243ba5b511fbac6315f57796e6`
- Native verification branch: `verify/native-gates-c5f5547`, at
  `d5668911cb60564f4b217093deb5da4e83862b67`; unsigned Debug and Release builds,
  strict contracts, source snapshots and packaging now pass
- The complete original product UI assertions **passed on iOS 18.6 at c5f5547**.
  This includes two real picker cancellations, selected-file delivery to the real
  pairing parser, typed invalid-content rejection, protected-store absence and
  later wizard/relaunch/navigation checks
- The same run **failed on iOS 26.2 before the first cancellation or selection**:
  the system Cancel control was unavailable within the unchanged ten-second
  readiness bound. Later picker UI appeared. That lane did not exercise the
  selected-result repair and does not pass product acceptance
- Core Debug/Release at c5f5547 passed 342 tests each; iOS core passed 336 tests.
  Those results are separate from native unsigned builds, UI and device evidence
- Native d566891 collected 359 pre-preparation tests with six intentional
  unavailable-preimage skips, then passed all 13 strict prepared contracts with
  **zero skips**, source snapshot, unsigned compilation and packaging in both
  configurations. Its core Debug and Release runs also pass 345 tests each
- Independent byte checks verify both IPAs, all manifest/checksum entries, 3,979
  available-source entries and 90 notice entries per configuration. The source
  and notice archives are identical across Debug/Release. Both manifests remain
  `candidate-incomplete`; complete producer source, linked notices, rights and
  device acceptance are not established by packaging success

[Current status](STATUS.md) and the [exact evidence checkpoint](checkpoints/2026-10-05-c5f5547.md)
identify commits, runs, artifacts and limits.

The candidate containing this matrix integrates those verified branch fixes and adds a separately reviewed timing-only UI discriminator, a compile/link-only pairing capability probe, and the historical SPDX structural report. Exact new-SHA CI remains pending; none of these observations implements the gated wireless host, resolves current-phone identity, or resumes the paused group.

## Gap types

- **Non-device:** implementation or verification that can proceed without the
  owner's phone, credentials or physical acceptance
- **Paused:** local unpublished signing-admission, manager-replacement-integration
  and aggregate-install-budget work. It is not included in the published result
  and receives no completed/reviewed/tested credit here
- **External evidence:** authenticated upstream/binary evidence or a documented
  rights/compatibility basis; tests or matching publisher hashes cannot create it
- **Physical:** one consolidated, authorized iPhone acceptance phase, after
  feasible work and non-device gates. No early device request is implied
- **Separate research:** BOOT-01, outside the proof of ordinary mobile-only renewal

## Closure matrix

| ID | Established, scoped evidence | Remaining closure condition and gap type |
|---|---|---|
| BASE-01 | Pinned preparation, strict contracts, unsigned Debug/Release builds and real packaging pass at d566891; exact artifacts and source/notice bytes verified. d566 core passes 345 tests per configuration | **Non-device:** integrate the verified branch into `develop` and maintain one final candidate identity across required evidence. Product UI evidence remains c5; iOS core has a prior c148 pass, not a new d566 run. A successful candidate package is not a release |
| BASE-02 | Historical 32-component inventory and full GPLv3 supplement preserved; actual d566 packages contain 3,979 available-source entries and 90 notices, with verified hashes | **Non-device + external evidence:** complete producer/corresponding source, applicable relinking material and actual linked notices; independently establish binary provenance, ADI origin/admission/use basis and exact Unicorn combined-license compatibility. 5,065 binary-input hash records are not retained producer source or release clearance |
| AUTH-01 | Account/key/session and typed authentication boundaries exist; identified logging/history paths have scoped changes and tests. A source audit identifies remaining public-certificate cache mutations | **Non-device, dependent:** public-certificate/profile closure requires startup/callback ownership work that is paused; a UI-only guard or blanket synchronous gate is insufficient. Finish other log/history coverage without claiming retroactive disk sanitization. **Physical:** real login, 2FA, session expiry and repair |
| LEASE-01 | Ordinary profile-only renewal is separated from necessary full signing/install; core behavior is tested | **Non-device:** preserve this separation through remaining integration. **Physical:** prove both real routes; normal renewal must not become routine app or manager reinstallation |
| LEASE-02 | Profile selection, earliest effective expiry, readback and journal/database reconciliation are wired | **Physical:** demonstrate real profile application, compatible readback, forward effective expiry and launch. UI dates, mock success and `appliedUnverified` cannot close this row |
| AUTO-01 | Headless App Intent and background entrypoints are wired; policy tests are available | **Non-device:** finish candidate integration and honest trigger/permission diagnostics. **Physical:** authorized scheduled execution while locked, without opening the manager or connecting a computer |
| AUTO-02 | At c5, the complete iOS 18.6 original UI contract passes, including cancellation, selected invalid pairing input, resumption, consent-off and signed-out recovery/navigation checks | **Non-device:** classify and correct iOS 26.2 first-picker readiness without weakening the original assertions; complete self-check and permission/error coverage. **Physical:** genuine authorized non-foreground self-check and configured automation, not merely a toggle or manual invocation |
| AUTO-03 | Core serialization/cancellation/backoff and scoped cache/backup/ODA workspace ownership have tests; native verification now passes the backup harness correction | **Non-device:** remaining temporary-file ingress versus cleanup ownership. **Dependent on paused ownership:** certificate startup and local profile import/delete/assignment/stale-cleanup routes cross detached/Core Data callbacks; audit only, no fix or acceptance. **Paused:** aggregate install RAM/disk budgets remain uncredited |
| SAFE-01 | Manager profile receives renewal priority; ordinary renewal does not require manager replacement | **Physical:** next-day renewal and continued executable manager operation across its original expiry. Manual refresh or a longer paid-account profile does not establish the free-account objective |
| SAFE-02 | Write-ahead journal, partial-success preservation and recovery/readback behavior exist; scoped deletion lifetime tests do not release ownership before work returns | **Non-device:** complete remaining native interruption, commit/persistence-failure and cleanup-race coverage. **Paused:** replacement-specific integration is not credited. **Physical:** real interruption/recovery outcomes without dropping pending evidence |
| INSTALL-01 | Input snapshot, download and archive protections exist. The c5 pairing-file UI pass establishes that specific import path, not successful IPA signing/installation | **Non-device:** complete provider/data-retention coverage and candidate integration. **Paused:** signing/Mach-O/entitlement/nested-signature admission and aggregate install-resource work remain unpublished. **Physical:** trusted IPA install/launch and data preservation |
| INSTALL-02 | Certificate issuance/recovery and manager-replacement receipt primitives exist | **Paused:** complete first-sign to manager-replacement integration, identity/data-access continuity and interruption recovery; no local unpublished implementation is counted. **Non-device:** verify the eventual integrated candidate. **Physical:** prove authorized first signing/replacement and data recovery |
| PAIR-01 | Stored/import/reset routes are preserved; c5 iOS 18.6 proves invalid-file rejection and store absence. Actual IDevice device and Simulator headers contain accept/cancellation declarations | **Non-device:** functional cancellable same-phone host/PIN/current-phone identity integration remains gated. Apple LLVM 17 nm failed on Rust LLVM 22 members: exports/ABI are inconclusive, not absent. Obtain compatible symbol/link evidence and test cancellation/re-pairing. **Physical:** valid import/retention and live peer behavior |
| QA-01 | Acceptance procedure is defined; device/soak testing has not been performed | **Physical, last:** first prove next-day proactive locked-screen renewal, then crossing the original expiry and longer real-time observation. Do not wait seven days to iterate; never advance the device clock or count manual refresh as unattended evidence |
| QA-02 | Scoped safety/fault tests, c5 product UI on 18.6, prior iOS core and d566 core/native/package checks pass within their stated scope | **Non-device + external evidence:** remaining temporary ownership, 26.2 readiness, supply chain and final integrated-candidate checks. **Dependent/paused:** local mutator startup/callback ownership and install-wide signing/replacement/budgets. **Physical:** traffic, performance, power, hardware protection and aggregate faults |
| BOOT-01 | Clean-phone first-install approaches remain documented research | **Separate research:** establish a trusted completely computer-free initial delivery/install route. Neither importing a pairing file nor generating one proves first installation; do not silently broaden the ordinary-renewal milestone |

## Order for the remaining work

1. Preserve the verified d566 build/package evidence and integrate the reviewed
   branch into `develop`. Keep artifact identities and candidate limitations with
   the integration; temporary CI retention is not durable delivery
2. Continue genuinely independent gaps: temporary-ingress/cleanup analysis,
   compatible pairing API evidence, iOS 26.2 readiness classification and
   source/notice/provenance preparation. Hold local certificate/profile mutation
   fixes at their paused startup/callback dependency; do not add blind gate wrappers
3. Keep the paused signing, replacement-integration and aggregate-budget group
   distinct until it is resumed and reviewed; no completion claim may rely on it
4. Resolve required external authenticity/rights evidence and produce a coherent
   candidate whose core, transformations, native artifacts and UI results are all
   tied to its exact SHA
5. Only then make one consolidated device request following
   [DEVICE_ACCEPTANCE.md](DEVICE_ACCEPTANCE.md): login/2FA, pairing and permissions,
   install/launch, profile apply/readback, next-day locked-screen renewal, original
   expiry crossing and longer observation

A development merge is not release authorization. `main`, stable publication and
an unconditional unattended-iOS guarantee remain outside this checkpoint.
