# Tetherless development status

Evidence checkpoint: **2026-10-05 20:59 UTC**. At 5a40878, the repaired native
acquisition profile passes 74 fixtures and the combined profile passes 94,
including all 20 host fixtures. The earlier stack-overflow failure is retained as
historical evidence. Whole transcripts, the M5 successor and Apple/app integration
remain open. The original 16-task plan is not complete; the app is not ready for
release or the consolidated phone phase.

This candidate adds source-reviewed M5 and whole-transcript work, Apple producer
recipes and the new proof workflow, plus the prepared historical archive query.
These additions are unexecuted; exact-commit CI is pending. Completed results
below remain tied to their recorded revisions, not to this candidate.

- develop: **3d97ef75a224a76f84ba6741da8d9a6b89f99217**, unchanged
- Candidate branch: **verify/staged-pairing-native**; this candidate's commit and
  run identities will be recorded after publication and verification
- Last completed native verification:
  **5a40878c56d5a458021c29df9e7b2cb471e5e0dd**; tree
  e0b7aa426a483a2d891925c75844c7143d62926b, 502 leaves verified
- Earlier native app verification branch verify/native-gates-c5f5547 remains at
  **1fc8968f1d37b59717cd655b9b8f7fc8ccc7f566**. Its Debug/Core/iOS Core results do
  not validate the later app composition or newer native artifacts

The [16-task matrix](PLAN_PROGRESS.md) separates feasible active work, external
evidence, paused dependencies and physical acceptance. The [checkpoint](checkpoints/2026-10-05-native-pairing-progress.md)
records exact runs, artifacts, failures and verification limits.

## Current evidence

| Source and run | Established result | Limit |
|---|---|---|
| 6bf7b89, [37348967899](https://github.com/oskuhsiu/Tetherless/actions/runs/37348967899) | Actual Rust helper/RSD suites pass 18 + 25 fixtures; retained checksums, vendor audits, README alias identity and process cleanup pass | Host fixtures only; no whole pairing transcript, iOS ABI or app activation |
| Historical 1366ace, [37362664851](https://github.com/oskuhsiu/Tetherless/actions/runs/37362664851) | Host-only profile passes 20 fixtures. Acquisition and combined profiles compile and pass preceding 18/25 suites | Both then abort in the same composite cancellation fixture with stack overflow/SIGABRT. Keep these failures tied to 1366ace |
| 5a40878, [37369016726](https://github.com/oskuhsiu/Tetherless/actions/runs/37369016726) | Acquisition passes 74; combined passes 94, including the 20 host fixtures. Source/provider audits, log/status hashes and all command joins verify. The original nine staged-acquisition tests plus two regressions pass | Host component evidence only. M5 successor, whole synthetic transcripts, Apple producer, real IDevice ABI and app activation are not established |
| ad9b33f, [host Core 37365518439](https://github.com/oskuhsiu/Tetherless/actions/runs/37365518439) and [iOS Core 37365518481](https://github.com/oskuhsiu/Tetherless/actions/runs/37365518481) | Each host Debug/Release configuration passes 345 Swift Testing + 25 XCTest cases; iOS Core passes 339 + 25 | Genuine core evidence; no real IDevice ABI or UIKit Model/View/Onboarding compilation |
| ad9b33f, [Swift/C-spy 37365518696](https://github.com/oskuhsiu/Tetherless/actions/runs/37365518696), attempt 2 | Approved job retry succeeds: 18 wrapper checks and 41 unique Swift/C-spy cases in each Debug/Release mode pass. All 24 source inputs and joined command logs are reconciled | Initial job never reported a runner or steps and was cancelled without an artifact. Successful spies do not establish real IDevice/Rust ABI or UIKit compilation |
| 1fc8968, [native app 37303840335](https://github.com/oskuhsiu/Tetherless/actions/runs/37303840335) | Debug passes 402 pre-preparation tests with six intentional skips, all 13 strict contracts without skips, unsigned build/package and C/Swift device/Simulator link probes | Release was cancelled during compilation, with unavailable logs and no artifact. No later full native app build is claimed |
| 3d97ef7, [full product UI 37298228388](https://github.com/oskuhsiu/Tetherless/actions/runs/37298228388) | iOS 26.2 installs/launches and passes two real picker cancellations; its 241-byte source remains intact | Both lanes fail: 18.6 at installation timeout, 26.2 at source-folder readiness before selection. No new full UI run or selected-file/parser/store/relaunch acceptance |

The older complete invalid-input/signed-out UI contract passed on iOS 18.6 at
historical c5f5547, [run 37286010497](https://github.com/oskuhsiu/Tetherless/actions/runs/37286010497).
That result does not validate later source, iOS 26.2, valid pairing, login, install
or renewal. Original UI selectors, deadlines and acceptance assertions remain intact.

## Pairing implementation and next gate

The old macOS process harness, packaged Cargo configuration, nested-workspace
metadata and README case-alias blockers are **resolved within the verified host
fixture path**. Actual native execution establishes that progress; these are no
longer current blockers.

The current repair changes staged-acquisition future placement, not thread stack
limits, timeouts or original assertions. Its source SHA-256 begins 3057cc16.
Both repaired profiles now pass, including the previously failing cancellation
fixture and the new storage regressions. Keep the original stack-overflow artifacts
and do not expand this result into whole-protocol, Apple-platform or app acceptance.

The 21-file gated app composition plus its wrapper/workflow is published at
ad9b33f. Core and source/spy evidence are scoped above; the product pairing gate
remains off. Stored/import/reset routes remain available. Successful synthetic
whole acquisition and host transcripts, Apple rebuilt artifacts and C/Swift probes,
the diagnostic iOS consumer and actual UIKit composition still need verification.

A separate remote-pairing M5 controller-signature check is included in this
candidate with source review but no execution; its host/combined targets are 26/100, not
passed counts. Three full acquisition and ten host transcript fixtures and the
Apple producer also remain pending execution. These are the next active pairing
requirements, separate from paused app-signing work. A same-container challenge is not
hardware attestation and cannot exclude an active relay or compromised OS.

Read-only review of the existing 3d97 UI evidence refines the 26.2 failure: Browse
Locations remains visible with On My iPhone selected; the local root did not open.
Fixture installation and LaunchServices registration succeeded, document creation
was observed by XCTest, and the original file is intact. The installer manifest's
unupdated flag is not proof that creation failed. The authorized bounded read-only
query of the existing owned archive is prepared in this candidate but unexecuted. No UI rerun or
resolved root cause is claimed.

The five-file EMProxy callback-privacy change is now published at 5a40878. Four
portable checks pass; its real Swift spy remains pending the normal native
Integration phase. Earlier 1fc IDevice logger-Off tests do not validate EMProxy,
erase prior logs or reconfigure an already initialized subscriber.

## Timing evidence is not a production lock fix

Three original 60-second tests failed in the earlier 3ace iOS Core run. At 1366ace,
diagnostic iOS Core passes while recording approximately 54.65-second await-resumption
gaps and small sampled assertion/body intervals. At ad9b33f, the corresponding
instrumented test bodies are about 0.26 seconds. These distinct runs preserve
their assertions and bounds. They establish neither a unique cause for the
earlier stalls nor a production locking repair.

## Remaining closure boundaries

| Type | Required closure |
|---|---|
| Feasible active, non-device | Complete whole synthetic transcripts, the source-reviewed M5 successor, exact Apple producer/build/link evidence, real ABI and UIKit/diagnostic-consumer compilation. Perform the authorized bounded read-only UI archive analysis. Integrate reviewed changes into one candidate and resolve current full-UI failures without weakened assertions |
| Delivery and external evidence | Complete corresponding/producer source, linked notices, applicable relinking materials and durable delivery. Establish essential ADI authenticity/admission and acquisition/use basis, exact Unicorn combined-license compatibility and retained binary provenance |
| Paused | Signing-admission, manager-replacement integration and aggregate install RAM/disk budget work remain unpublished and uncredited, including dependent startup/Core Data callback ownership. This pairing work neither reviews nor bypasses that pause |
| Physical, later | One consolidated authorized phone phase after feasible implementation and non-device gates: login/2FA, permissions, valid pairing/recovery, install/launch, profile application/readback, next-day locked-screen renewal and expiry crossing |

The exact 1fc Debug delivery artifact remains independently reconciled: 3,992
available-source entries, 3,159 Git blobs/modes, 91 notices, eight package checksums,
40 historical review hashes, nine lockfiles and 47 pin occurrences. It remains
candidate-incomplete and releaseReady=false. Neither that earlier package nor
structural SPDX validation establishes complete source, rights or the actual
linked-component graph for the newer verification branch.

No real login, live pairing, profile application, unattended renewal or expiry
soak is claimed. appliedUnverified, displayed expiry, a permission toggle or manual
refresh is not unattended success. Follow [DEVICE_ACCEPTANCE.md](DEVICE_ACCEPTANCE.md)
only after the development gates. BOOT-01's clean-phone first installation remains
separate research. main and release publication remain unchanged and outside
this authorization.
