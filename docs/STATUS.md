# Tetherless development status

Evidence checkpoint: **2026-10-05 10:28 UTC**. Published `develop` is
**c5f5547fc481a8243ba5b511fbac6315f57796e6**. Native verification work is on
**verify/native-gates-c5f5547**, at
**d5668911cb60564f4b217093deb5da4e83862b67**. Both unsigned native builds and
packages now pass, with independent artifact checks. These branch changes are
not yet integrated into `develop` at this checkpoint. Both packages remain
`candidate-incomplete`; this is continued development, not release readiness.

The [original 16-task matrix](PLAN_PROGRESS.md) separates implemented/scoped
proof from feasible non-device, paused, external-evidence and physical gaps.
The scoped native build/package gate is met on the verification branch; the
original 16-task plan as a whole remains open.

## This integration candidate

This increment brings the three independently reviewed native-verification fixes above into the development candidate, retains the inspected d566 evidence, and adds the approved timing-only first-picker discriminator plus an exact-artifact C/Swift compile-and-link observation. The original product UI actions and deadlines remain unchanged. The historical SPDX candidate also has a reproducible pinned-schema structural check with zero errors; this is not final SBOM or licensing clearance.

New native/UI evidence for this candidate remains pending until its exact commit's jobs and artifacts are inspected. Prior d566 build/package success does not validate the added Swift timing emitter or compile/link probe. See [the one-run UI decision](simulator-ci/product-import-decision.md#next-diagnostic-decision-distinguish-first-picker-readiness-on-ios-262), [pairing observations](PAIRING_CAPABILITIES.md), [the link probe](PAIRING_LINK_PROBE.md) and [SPDX check](delivery/spdx-validation/README.md). No product gate is removed, and the paused/external/physical gaps below remain.

## What is verified now

| Source and evidence | Actual result | Limit |
|---|---|---|
| d566891 [Renewal core 37294413223](https://github.com/oskuhsiu/Tetherless/actions/runs/37294413223) | Debug and Release: 345 Swift Testing tests passed each | Exact native-branch core evidence; separate from physical acceptance |
| c5f5547 [Renewal core 37286010454](https://github.com/oskuhsiu/Tetherless/actions/runs/37286010454) | Debug and Release: 342 tests passed each | Core execution, not native/device acceptance |
| c5f5547 [iOS core 37286010392](https://github.com/oskuhsiu/Tetherless/actions/runs/37286010392) | 336 tests passed | iOS Simulator core, not a physical-device result |
| c5f5547 [full product 37286010497](https://github.com/oskuhsiu/Tetherless/actions/runs/37286010497), iOS 18.6 job 111684962352 | Complete original UI assertions passed: two actual system-picker cancellations; one selected file delivered to the real pairing parser; typed invalid-content rejection; protected-store absence; wizard/resumption/relaunch/navigation and signed-out recovery checks | Invalid-input and signed-out product flow only. Valid pairing, existing-valid-record retention, Apple authentication, installation and renewal remain unverified |
| Same c5 product run, iOS 26.2 job 111684962133 | Failed at the first picker presentation: Cancel unavailable within the original ten-second readiness bound. Build/signature/boot/install/launch/source preparation passed; later picker UI appeared | No cancellation, selection or import occurred. This lane did not exercise the selected-result repair; no unique product/service/host cause is established |
| c1482e0 [iOS core 37291091619](https://github.com/oskuhsiu/Tetherless/actions/runs/37291091619) | Passed | Prior branch revision; no d566-specific iOS core run was triggered |
| c1482e0 [native 37291091604](https://github.com/oskuhsiu/Tetherless/actions/runs/37291091604) | Both configurations collected 352 pre-preparation tests with six unavailable-preimage skips and no failures, then all 13 strict post-preparation contracts with zero skips | The next prebuild source snapshot failed on the legitimate missing `build/SideBackup.ipa` target. Native compilation and complete packaging were not reached |
| d566891 [native 37294413252](https://github.com/oskuhsiu/Tetherless/actions/runs/37294413252), Debug 111712141173 / Release 111712141436 | **Both succeeded:** 359 pre-preparation tests collected, six intentional unavailable-preimage skips, no failures; all 13 strict prepared contracts pass without skips; snapshot, unsigned compile and package pass | Candidate integrity verified below; no signing/device, complete-source, legal or release clearance |

[Exact c5 product and branch checkpoint](checkpoints/2026-10-05-c5f5547.md)
retains artifact identities, the unchanged UI contract and evidence limits.

## Scope of the current correction sequence

The published c5 product repair makes delegate result and completed dismissal
rendezvous in either order and consume the result once. The passing iOS 18.6
full-product run supplies real product-path evidence for that repair. The earlier
0dfceb5 cancellation-before-result failure is historical, not the current 26.2
failure classification.

The native verification branch additionally contains:

1. [8db1e68](https://github.com/oskuhsiu/Tetherless/commit/8db1e68c0760c8b34bb78c672e90c26ca8191457): Swift 6 backup-ownership fixture isolation correction; production acceptance assertions remain intact
2. [c1482e0](https://github.com/oskuhsiu/Tetherless/commit/c1482e0e615f56bfa37fa9437c43aa1669550cec): validated metadata-reference dot-segment normalization, followed by passing strict prepared contracts
3. [d566891](https://github.com/oskuhsiu/Tetherless/commit/d5668911cb60564f4b217093deb5da4e83862b67): safe source-link inventory handling for the verified prebuild SideBackup link; exact target bytes are retained with missing/excluded metadata, without reading generated target contents

The third change has 44 focused delivery/package checks and independent review;
its actual Debug and Release native execution and packaging now pass. See
[the source-link diagnosis](delivery/PREPARED_SOURCE_LINKS.md) and
[candidate packaging scope](DELIVERY_CANDIDATE.md). These three branch commits are
not yet credited as integrated `develop` evidence at this checkpoint.

## Remaining work, by boundary

### Verified packages and remaining non-device work

- Both d566 candidate artifacts pass independent ZIP/TAR/plist and byte checks:
  all eight checksum-list entries per package; all manifest companions; 3,979
  source entries, including 3,146 recorded Git blobs/modes; 90 notice entries;
  nine lockfiles with 47 observed pin occurrences; all 40 historical review
  hashes and the GPL supplement. The same 833 prepared-file identities are
  retained before/after build, apart from truthful link-target availability
- Debug and Release source/notice tarballs are byte-identical. Actual output
  includes the main app, AltWidget extension, OpenSSL framework and nested
  SideBackup IPA. The final ZIP inventories match all 156 outer and 14 nested
  file entries. Five storyboard Info.plists are also listed as null-ID app
  metadata; exclude those duplicates from bundle counts. This file inventory
  does not determine the final static linked-component graph
- Preserve and integrate the exact candidate evidence. Complete producer source,
  linked notices, relinking materials and durable distribution remain open. The
  5,065 recorded binary-input entries are hashed but their expanded bytes are not
  included in the available-source bundle. Empty `missingEvidence` means the
  configured input roots were present, not complete corresponding source
- Finish cancellable functional wireless pairing and current-phone identity
  binding. Both actual slice headers contain the accept/cancel declarations,
  but Apple LLVM 17 nm failed to read Rust LLVM 22 members. Exports/ABI remain
  inconclusive; the report's `missing_exports` lists are not absence evidence
  after a tool failure. Wireless generation remains gated; stored/import routes
  are preserved
- Continue remaining temporary-file ingress versus cleanup ownership work. A
  source audit confirms public-certificate caching and local-profile
  import/delete/assignment/stale cleanup still cross startup/Core Data callback
  boundaries. Their closure depends on paused ownership integration; no isolated
  UI guard or blind synchronous reacquisition establishes it. The audit made no
  implementation change or native/device test claim
- Resolve the iOS 26.2 first-picker readiness boundary using a discriminating
  presenter/service/accessibility timeline. Preserve the original deadline and
  actual cancellation/selection/parser assertions; later UI appearance alone
  does not justify a timeout or selector change
- Complete remaining source/notice and exact-candidate consistency checks while
  keeping historical review evidence intact

### Paused local work, not published or credited

Signing-admission boundaries, manager-replacement integration and aggregate
install RAM/disk-budget work are paused and unpublished. Their presence in a
local work area does not establish review, tests or integration. This checkpoint
neither resumes that group nor counts it toward completion. Remaining local
certificate/profile mutation work is also dependent on its paused startup and
callback ownership boundary; an awaiting parent does not prove a callback can
borrow its task-local lease.

### External evidence still required

Essential ADI origin/authentication/admission and acquisition/use basis, exact
Unicorn combined-license compatibility, retained prebuilt-framework provenance,
complete corresponding source/relinking material and complete linked-component
notices remain unresolved. The historical inventory and supplemental GPLv3
reference text do not close those gates. Matching publisher digests are not
independent trust evidence.

### One physical acceptance phase, later

Finish feasible implementation and non-device checks before requesting the
owner's phone. Then use [DEVICE_ACCEPTANCE.md](DEVICE_ACCEPTANCE.md) for a single
consolidated pass: authorized login/2FA and permissions; valid pairing and
recovery; trusted install/launch; real profile application/readback and effective
expiry; locked-screen next-day proactive renewal without foreground manager or
computer; original-expiry crossing and longer real-time observation.

No real login, valid live pairing, profile apply/readback, locked-screen renewal
or expiry soak is claimed here. `appliedUnverified`, a UI countdown, manual
refresh or a permission switch is not successful unattended renewal. BOOT-01's
clean-phone computer-free first install remains separate research.

## Historical evidence retained

- **0dfceb5**, [product run 37277414175](https://github.com/oskuhsiu/Tetherless/actions/runs/37277414175): both runtimes reached selected-file delivery, but dismissal had already cancelled the request; no import began. [Preserved checkpoint](checkpoints/2026-10-05-0dfceb5.md). Its native run stopped earlier in a Swift test harness, not native compilation
- **9a49417**, [same-artifact UIKit comparison 37273262340](https://github.com/oskuhsiu/Tetherless/actions/runs/37273262340): selected-file delivery on 18.6; bookmark-resolution failure before the delegate on 26.2. This separate diagnostic had collector limits and did not prove product parser/storage acceptance. [Comparison and limits](simulator-ci/runtime-comparison-37273262340.md)
- **985832f**, [diagnostic 37271883947](https://github.com/oskuhsiu/Tetherless/actions/runs/37271883947): bounded broad-inventory failure before device allocation/build; [decision history](simulator-ci/next-run-decision.md)
- **89c157d**, [product run 37247923030](https://github.com/oskuhsiu/Tetherless/actions/runs/37247923030): both real cancellations passed, then document-provider bookmark preparation failed before a selection callback. The original 241-byte source was preserved. Neither disappearance nor boot failure explains that run
- **8c25ff3**, run 37242839315: failed at the unchanged 120-second install bound, before product/control UI. It is not the explanation for the later UI boundaries
- Takeover **3dd8641**: 212 ordinary source files matched their GitHub blobs. [Core run 37248028123](https://github.com/oskuhsiu/Tetherless/actions/runs/37248028123) and the earlier [native implementation run 37247923028](https://github.com/oskuhsiu/Tetherless/actions/runs/37247923028) remain historical, not validation of later edits

Keep old failures and diagnostics tied to their own versions. Record new run
outcomes here only after inspecting the exact commit/job/artifact evidence.
Development work does not authorize `main` promotion or a stable release.
