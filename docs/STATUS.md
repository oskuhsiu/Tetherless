# Tetherless development status

Evidence checkpoint: **2026-10-05 22:19 UTC**. All five Rust lanes at 1ed3b9c
report success; the full acquisition transcript's three tests are independently
reconciled. Apple iOS-arm64 release Rust compilation succeeds, then artifact
selection fails before any Simulator slice or C/Swift probes. A selector repair
is under review. The exact historical UI-event query ends inconclusively and that
diagnostic path stops. The original 16-task plan remains open; no app, release or
consolidated phone readiness is claimed.

- develop: **3d97ef75a224a76f84ba6741da8d9a6b89f99217**, unchanged
- Published diagnostic source on **verify/staged-pairing-native**:
  **ec7e229cc3b6d7bbf715225dc545481c213f81dd**; tree
  5a70ead2300f3b161ea42fa13d53c18149662041, 544 leaves
- Native proof source: **1ed3b9c96810fa78c387da15ecbee8a544a1b68c**; tree
  76ad67dc62e7a24d1716154f6f78df5ceca78a39, 540 leaves. ec7e229 adds only four
  diagnostic files; native results stay attributed to 1ed3b9c
- Next repair candidate: exact commit and CI identities pending; no new execution
  is inferred from the completed results below
- Earlier native app verification branch verify/native-gates-c5f5547 remains at
  **1fc8968f1d37b59717cd655b9b8f7fc8ccc7f566**. Its Debug/Core/iOS Core results do
  not validate the later app composition or newer native artifacts

The [16-task matrix](PLAN_PROGRESS.md) separates feasible active work, external
evidence, paused dependencies and physical acceptance. The [checkpoint](checkpoints/2026-10-05-native-pairing-progress.md)
records exact runs, artifacts, failures and verification limits.

## Current evidence

| Source and run | Established result | Limit |
|---|---|---|
| 1ed3b9c, [native proof 37378994528](https://github.com/oskuhsiu/Tetherless/actions/runs/37378994528) | All five Rust lanes succeed by API status. Acquisition transcript: three native success/cancellation/deadline fixtures independently verify, with source/provider audits, hashes and joins | Current host 26, acquisition 74, combined 100 and host transcript 10 artifacts are not yet separately reconciled. Their earlier 3ae artifacts remain verified; neither result is physical compatibility |
| Same 1ed3b9c run, Apple producer | Actual iOS-arm64 release Rust build succeeds in 197.595 seconds, with provider-header and feature-graph checks | Artifact selector rejects a legitimate same-manifest custom-build/bin record before the staticlib. No Simulator slice, C/Swift probes or XCFramework; selector repair under review |
| ec7e229, [exact-event query 37381049415](https://github.com/oskuhsiu/Tetherless/actions/runs/37381049415) | Bounded export/query/cleanup pass; one exact hash/time/activity record matches | Static template is “assertion failure: <value>”; no operation/error is recovered, and four unsupported lines prevent complete identification. Stop this diagnostic path without rerun or widening |
| 3ae371e, [native proof 37375339856](https://github.com/oskuhsiu/Tetherless/actions/runs/37375339856) | Verified host 26 including six M5 tests, acquisition 74, combined 100 and ten complete synthetic host transcript tests pass; source/provider audits, hashes and command joins verify | Acquisition transcript's three tests stop at Rust E0277 compilation of synthetic peer Properties: {}; Apple producer stops before compilation on a Swift version-stream comparison. No Apple artifact, app or device acceptance |
| 3ae371e, [Swift composition 37375339728](https://github.com/oskuhsiu/Tetherless/actions/runs/37375339728) | 41 cases pass in each Debug/Release mode; all 24 source hashes and command joins verify | Synthetic C ownership spy; no actual Rust ABI or UIKit compilation |
| 3ae371e, [host Core 37375339731](https://github.com/oskuhsiu/Tetherless/actions/runs/37375339731) | Raw job log verifies 345 Swift Testing + 25 XCTest cases in each Debug/Release configuration | No new iOS Core run was triggered; its reviewed evidence remains at ad9b33f |
| 3ae371e analysis of historical 3d97 UI, [37375339797](https://github.com/oskuhsiu/Tetherless/actions/runs/37375339797) | Archive export/query and cleanup succeed; sanitizer records 803 events from 807 nonblank lines | Four unparsed/out-of-scope records leave gaps. Enumeration precedes root activation; warning/timeout mentions establish no actionable cause or product fix |
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

The verified stack repair changes staged-acquisition future placement, not thread stack
limits, timeouts or original assertions. Its source SHA-256 begins 3057cc16.
Both repaired profiles now pass, including the previously failing cancellation
fixture and the new storage regressions. Keep the original stack-overflow artifacts
and do not expand this result into whole-protocol, Apple-platform or app acceptance.

The 21-file gated app composition plus its wrapper/workflow is published at
ad9b33f. Core and source/spy evidence are scoped above; the product pairing gate
remains off. Stored/import/reset routes remain available. Full synthetic acquisition
transcript success now has native evidence at 1ed3b9c. The Apple artifact and real
C/Swift probes, diagnostic iOS consumer and actual UIKit composition remain open.

The earlier synthetic-peer typing and version-stream blockers are resolved at
1ed3b9c. The current Apple boundary is artifact selection after successful device
compilation. Pairing promotion entry remains separate active development, with
no activation claim. These paths are separate from paused app-signing work.
A same-container challenge is not hardware attestation and cannot exclude an
active relay or compromised OS.

Read-only review of the existing 3d97 UI evidence refines the 26.2 failure: Browse
Locations remains visible with On My iPhone selected; the local root did not open.
Fixture installation and LaunchServices registration succeeded, document creation
was observed by XCTest, and the original file is intact. The installer manifest's
unupdated flag is not proof that creation failed. The bounded query of the existing
owned archive has run, but gaps remain. Enumeration mentions predate root activation;
all 19 unlisted-domain messages hash-match an iconServices warning. The late timeout
mention does not identify an operation. The subsequent exact-event query recovers
only the static assertion template, with four unsupported lines. It remains
inconclusive and this diagnostic path stops. No UI rerun, resolved cause or product
fix is claimed.

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
| Feasible active, non-device | Review and verify the Apple artifact selector; then obtain the Simulator slice, C/Swift probes and XCFramework before diagnostic-consumer/actual UIKit evidence. Continue the separate pairing promotion entry with gates off. Stop the exhausted exact-event path; any different UI work needs a new evidence-backed decision. Integrate one candidate without weakened assertions |
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
