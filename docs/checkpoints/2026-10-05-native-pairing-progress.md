# Native pairing and verification checkpoint

Observed **2026-10-05 20:59 UTC**. At 5a40878, acquisition passes 74 native
fixtures and combined passes 94, including all 20 host fixtures. The repaired
composite cancellation fixture and both new regressions pass. The earlier 1366ace
stack-overflow failure remains preserved. M5 successor, full synthetic transcripts,
Apple producer, real ABI, UIKit and physical acceptance remain open.

## Repository and scope

- develop: 3d97ef75a224a76f84ba6741da8d9a6b89f99217, unchanged
- Active branch: verify/staged-pairing-native
- This candidate: source-reviewed additions; exact commit and CI identities pending
- Last completed native verification commit: 5a40878c56d5a458021c29df9e7b2cb471e5e0dd
- Its verified tree: e0b7aa426a483a2d891925c75844c7143d62926b; 502 leaves
- Earlier composition commit: ad9b33f4c00764bd738e1912389cbe08cedd2c7e
- Earlier native app branch: verify/native-gates-c5f5547 at
  1fc8968f1d37b59717cd655b9b8f7fc8ccc7f566
- Original plan SHA-256:
  49d049cea36c0872224e888e20074d08d313031a72d6ed9a128ef320370fe3a6

The owner authorized the temporary component branch. It remains distinct from
develop, main and release. Its narrow app-job exclusion does not establish a
current full app build. New product pairing gates remain off.

This candidate includes the source-reviewed M5 successor, full synthetic transcript
fixtures and Apple producer recipes, the new proof workflow, and the prepared
bounded query of the historical owned archive. These additions have no execution
result at this candidate's revision. Record exact publication/run identities and
their outcomes when established; do not inherit 5a or ad9 passes as candidate CI.

## Historical native progress

| Revision and run | Result | Evidence boundary |
|---|---|---|
| 6bf7b891ad59a5ae00fbf45e527b7412dfca597d, [37348967899](https://github.com/oskuhsiu/Tetherless/actions/runs/37348967899), job 111894672236 | 18 helper + 25 RSD Rust fixtures pass | Host fixture execution, not complete pairing, iOS ABI or device behavior |
| 1366ace57491dea1b05e9223489d14274d25a386, [37362664851](https://github.com/oskuhsiu/Tetherless/actions/runs/37362664851), host job 111940738761 | 20 host fixtures pass, grouped 8/5/3/4 | Bounded host source/fixtures, not a successful whole peer transcript |
| Same 1366ace run, acquisition job 111940739025 | Compiles with exact recorded OpenSSL inputs; preceding helper 18 and RSD 25 pass | The nine-test staged-acquisition suite aborts in its composite cancellation fixture |
| Same 1366ace run, combined job 111940739132 | Same compilation and preceding 18/25 passes | Same fixture, stack overflow and SIGABRT; combined profile fails |

The 6bf helper artifact independently verifies all 13 completed checksum entries,
22,799 logical vendor inputs, original/derived input audits, the README alias
identity, matching provider capture and child/process-group cleanup. The recorded
derived changes are confined to cbindgen's metadata source and its checksum record.

The earlier process/configuration/nested-metadata/README alias blockers are resolved
in this verified path. Historical attempts remain evidence, not current blockers:

- 7f0f400, [37320923359](https://github.com/oskuhsiu/Tetherless/actions/runs/37320923359):
  macOS EPERM in the process harness before Cargo
- bcff221, [37323350367](https://github.com/oskuhsiu/Tetherless/actions/runs/37323350367):
  71 portable tests pass; actual Cargo stops in plist_ffi/cbindgen nested-workspace
  metadata
- c012349, [37329375641](https://github.com/oskuhsiu/Tetherless/actions/runs/37329375641):
  89 portable tests pass; dialoguer packaged config rejected before Cargo
- c5e70c0, [37334149741](https://github.com/oskuhsiu/Tetherless/actions/runs/37334149741):
  111 portable tests pass; complete 359-package/four-config inventory exposes three
  additional packaged configs
- Subsequent owned-workspace discovery/derived-metadata and proved README alias
  handling reach real Rust compilation. b7f9a59,
  [37345923482](https://github.com/oskuhsiu/Tetherless/actions/runs/37345923482),
  stops at two fixture key-inference errors; reviewed explicit key typing at
  6bf7b89 then yields the actual 43-fixture pass

These repairs retain the pinned root dependency lock and authenticated archives.
They do not authorize ambient Cargo configuration or arbitrary dependency updates.

## Historical acquisition failure and verified repair

Both 1366ace profiles abort in:

staged_acquisition::ownership_fixtures::composite_acquisition_joins_rp_socket_on_cancel_and_timeout

The test process reports stack overflow and signal 6/SIGABRT; the Cargo command
fails with exit 101. This is an actual runtime fixture failure after compilation,
not another package preparation error. Preserve both artifacts and their original
logs. The preceding 18/25 passes do not make either full profile successful.

The reviewed repair changes the placement of the adapter and sequential phase
futures onto bounded heap-pinned storage. Production staged_acquisition.rs has
SHA-256 3057cc162efc267d3e8e3dee323141822adf789f226fed17292b4098ac1c5d89.
All nine original staged-acquisition tests and assertions remain unchanged; two
new regressions increase that suite to eleven. Thread stack settings, original
deadlines and acceptance assertions are not relaxed.

The repair is published in 5a40878. [Matrix 37369016726](https://github.com/oskuhsiu/Tetherless/actions/runs/37369016726)
now establishes actual, independently reconciled passes:

- Acquisition: **74 fixtures**, in groups 18/25/11/3/2/4/4/7
- Combined: **94 fixtures**, the same groups plus host groups 8/5/3/4,
  totaling **20 host fixtures**
- All source/provider audits pass. Log/status hashes verify and every command
  joins before cleanup. No source, provider or test result is inferred merely
  from the workflow's overall conclusion
- Both profiles retain the original nine staged-acquisition tests and execute
  the two new regressions. The previously overflowing composite cancellation
  fixture now passes under the recorded host toolchain
- Recorded future layouts are production 2,288 bytes, injected 2,160 bytes,
  controlled 4,592 bytes and joined 4,656 bytes

This closes the observed stack-overflow fixture failure at this source revision.
It does not establish a successful whole synthetic pairing transcript, the M5
controller-signature successor, real IDevice ABI, an Apple producer artifact or
product activation. Those next execution gates remain distinct.

## Native artifact identities

These retained ZIP digests were reconciled locally. Hashes establish artifact
identity, not independent source-to-binary provenance.

| Source/profile | Artifact | Bytes | SHA-256 |
|---|---|---:|---|
| 6bf7b89 helper/RSD | [11360969741](https://github.com/oskuhsiu/Tetherless/actions/runs/37348967899/artifacts/11360969741) | 16904673 | e092e87c9fc36c32e2627c8b3731b0e5fdb0537393bd7544bd96fb30360798fa |
| 1366ace host-only | [11366838605](https://github.com/oskuhsiu/Tetherless/actions/runs/37362664851/artifacts/11366838605) | 3159955 | eebe5c6a2f88bc9aaa50af8afd518231ad15543f57cbc1765c37c12594a40816 |
| 1366ace acquisition | [11367742807](https://github.com/oskuhsiu/Tetherless/actions/runs/37362664851/artifacts/11367742807) | 15975131 | 11a0607172253922998ff9346aad0c69027c325f9c8d7744450d9e3033d14601 |
| 1366ace combined | [11368365572](https://github.com/oskuhsiu/Tetherless/actions/runs/37362664851/artifacts/11368365572) | 15975116 | c32d6a4224dae976078822644987304ab382443614ab03e5d50239749967ca39 |

Current 5a40878 archives from run 37369016726, separately reconciled against
the retained source/provider audits and test evidence:

| Profile / retained archive | Bytes | SHA-256 |
|---|---:|---|
| Acquisition / acquisition-5a40878.zip | 16079981 | b9f6df1abd3033e5cf19354fbafefe7a6673d11e976fe1d340bf35122573c154 |
| Combined / combined-5a40878.zip | 16158251 | d7a5a6ea7734319a9a1f96ff187deea2a76a43a8560f23dbb3f5bd70986e873a |

These current successes do not overwrite the failed 1366ace artifacts above.

## Gated composition and genuine Swift/Core evidence

The 21-file app composition plus wrapper/workflow, 23 published files in total,
is at ad9b33f. Its registration and product gates remain unchanged/off.

- [Host Core 37365518439](https://github.com/oskuhsiu/Tetherless/actions/runs/37365518439),
  job 111949571410: **345 Swift Testing + 25 XCTest cases pass in each of Debug
  and Release**
- [iOS Core 37365518481](https://github.com/oskuhsiu/Tetherless/actions/runs/37365518481),
  job 111949572077: **339 Swift Testing + 25 XCTest cases pass**. Swift Testing
  reports 1.927 seconds. Artifact 11368851055 is 709,175 bytes, SHA-256
  3890ea1b5b54fcfecf6a06a59b0ec3e315fe1253404c5c0c62d890296d02f585
- [Standalone Swift/C-spy 37365518696](https://github.com/oskuhsiu/Tetherless/actions/runs/37365518696):
  original job 111949572665 reports runner ID 0, no steps, cancellation and no
  artifact. Terminal log retrieval returned BlobNotFound. Its roughly 15-minute
  interval is consistent with the job ceiling, but no exact cause is exposed
- One specifically approved retry of that job, attempt 2/job 111958936845, succeeds
  at 20:19 UTC. Eighteen wrapper checks pass. Artifact 11369355358 is 15,211 bytes,
  verified SHA-256 bff8e4cb8186a7e646b230691fe65f789ede75cbaa951b3091c57726d5c2ce66

Independent reconciliation verifies all 24 source input hashes and **41 unique
Swift/C-spy cases in each configuration**: Debug takes 29.480457959 seconds and
Release 20.878993667 seconds. All four command groups return zero with complete
bounded logs and verified joins; scratch is removed only afterward. This genuine
pass does not establish real IDevice/Rust ABI or compile UIKit Model/View/Onboarding.
Host Core, iOS Core, spies and full-product UI remain distinct evidence.

The earlier 3ace Swift run [37351051432](https://github.com/oskuhsiu/Tetherless/actions/runs/37351051432)
independently passed 19 unique Swift fixtures in each Debug/Release mode, with
joined commands and scratch cleanup. Artifact 11361829300 has SHA-256
df9b1e213ce057d240716531d5295aaab55b086a8299123ab8bbfba9a34ef71d.
It covers source, registration spies and local socket pairs, not the actual
IDevice bridge or the later 41-fixture composition.

## Core timing: preserve the differing observations

The earlier 3ace iOS Core run 37351051292 failed three original 60-second tests.
The later diagnostic at 1366ace, [37362665017](https://github.com/oskuhsiu/Tetherless/actions/runs/37362665017),
passes 339 Swift Testing and 12 XCTest cases. Its artifact 11367906473 is 690,477
bytes, SHA-256 efee44e463b9ca5d4a4e15492104639cf55f499c7d89e967da354d6c3fb7ac22.

Monotonic observations include:
- admitted signal to parent resumption: 54.652098208 seconds
- late child exit to awaiting body resumption: 54.650541042 seconds
- late await exit to expectation exit: 0.049719208 seconds
- admitted busy assertion body: 0.00008925 seconds
- real lease body/post-body: 0.000130916 / 0.000064667 seconds

At ad9b33f, the corresponding instrumented bodies are about 0.26 seconds, while
the whole Swift Testing run reports 1.927 seconds. Framework-reported test
durations and instrumented body spans remain different measures. The original
assertions and 60-second bounds are unchanged. Scheduling and tracing overhead
remain part of the observations; no unique cause or production lock fix is proved.

## Published privacy and held pairing work

The five-file EMProxy callback-privacy packet is published at 5a40878. Four
portable checks pass; the actual Swift spy was unavailable locally and remains
pending the normal native Integration phase. This is separate from the already
executed 1fc IDevice logger-Off spy. Neither change erases existing logs or promises
to reconfigure a previously initialized subscriber.

Source review has closed the selected OpenSSL PSK trampoline/lifetime and error
conversion questions. Exact recorded host OpenSSL inputs now compile and support
preceding fixture execution. That is progress beyond source review, but does not
prove the final Apple single-provider link, successful acquisition or physical
compatibility.

The remote-pairing M5 controller-signature check is independently source-reviewed
and included in this candidate but unrun. Its successor targets are 26 host and 100
combined fixtures; the verified 20/94 results do not execute that successor.
It is separate from paused app-signing admission. Three full synthetic acquisition
and ten host transcript fixtures, the Apple producer/rebuilt artifact and real
C/Swift probes, and a diagnostic iOS consumer remain pending execution. The
previous native repair prerequisite now passes, but does not itself close these
next gates. Actual UIKit composition and failure-atomic record promotion still
require integrated verification.

A same-container challenge has explicit active-relay and compromised-OS limits;
it is not hardware attestation. No new pairing product gate is enabled.

## Earlier app build, delivery and full UI remain scoped

At 1fc8968, [native app 37303840335](https://github.com/oskuhsiu/Tetherless/actions/runs/37303840335)
is terminal cancelled overall. Debug job 111742646518 succeeds; Release job
111742646421 is cancelled during compilation with unavailable BlobNotFound logs
and no Release artifact. No compiler error or completed Release build is inferred.

The exact Debug log shows 402 pre-preparation tests with six intentional skips,
13 strict prepared contracts with zero skips, actual IDevice logger spy checks
in Debug/Release compilation modes, build/package success and typed C/Swift
device/Simulator arm64 link probes. The probes do not launch executables or
establish runtime ABI, cancellation, handshake or current-phone identity.

Debug artifact 11342129657: 129,256,589 bytes, SHA-256
866221e61b4ba8f32f18f3b20b037fd88f21d079ff38bf66070acfb83577ffec.
Its unsigned IPA: 42,875,593 bytes, SHA-256
dbd74c0a5ee5de2e5575cc2da8c3d91aca72491390e9bedb6fe5abd0e8a81122.
Independent reconciliation covers 3,992 available-source entries, 3,159 Git
blobs/modes, 91 notices, eight package checksums, 40 historical review hashes,
nine lockfiles and 47 pin occurrences. Five storyboard Info.plists are excluded
from canonical bundle counts. candidate-incomplete/releaseReady=false remain.

Prior cb8e4dd [run 37299257442](https://github.com/oskuhsiu/Tetherless/actions/runs/37299257442)
is retained as the earlier two-configuration native pass. It does not validate
later composition.

The latest full product UI is still [37298228388](https://github.com/oskuhsiu/Tetherless/actions/runs/37298228388)
at develop 3d97ef7, attempt 1. No new full UI run has occurred:

- iOS 18.6/job 111724485325: build/signature/boot pass; install exceeds the original
  120-second bound. No launch, fixture or UI acceptance
- iOS 26.2/job 111724485744: build/signature/boot/install/launch/fixture pass and
  two actual picker cancellations pass. Third picker fails the original ten-second
  source-folder wait before selection. Read-only review shows Browse Locations
  still displayed with On My iPhone selected; the local root did not open.
  Fixture installation and LaunchServices registration succeeded. XCTest separately
  observed document creation; the installer manifest's never-updated flag does
  not negate that evidence. No parser/import/store/relaunch acceptance
- The original 26.2 document stays 241 bytes with SHA-256
  8adc01ad4d6304deb1daf74335f9acc7891ed5ed442dd85c5a50a7e30b58b96b
- The complete scan has 5,260,553 stdout bytes and 23 fixed events. Two suspended
  service rows exposed the old collector grammar gap; the 1fc repair does not
  retrospectively provide missing direct-PID/final-clock evidence or justify an
  unchanged full UI rerun

The bounded read-only query of the existing owned archive is authorized and
prepared in this candidate but unexecuted. It analyzes retained evidence, not a new Simulator/UI run.
The visible navigation boundary is more precise, but its underlying cause remains
unresolved; no selector, deadline or product behavior is changed by this review.

UI artifacts: 18.6 artifact 11339289989, 347,334 bytes, SHA-256
28aca5ecc62a437d9d6c69030d4cfa414fee93aa98cd197342c39130c5253e68;
26.2 artifact 11341735733, 76,465,711 bytes, SHA-256
ac79e699970ebf98f07277855ffd824529fb826b6aba01583da4538433b742e2.
Historical c5f5547 [run 37286010497](https://github.com/oskuhsiu/Tetherless/actions/runs/37286010497)
passed the original full contract on 18.6. It does
not validate current source, 26.2, valid pairing, authentication, install or renewal.

## Closure and authorization boundaries

Complete corresponding and producer source, actual linked-component notices,
applicable relinking materials and durable delivery remain open. Matching package
hashes, source inclusion, structural SPDX validation or host OpenSSL compilation
does not establish essential ADI authenticity/admission/use rights, exact Unicorn
combined-license compatibility or retained binary provenance.

Signing-admission, manager-replacement integration and aggregate install RAM/disk
budget work remain paused and unpublished. Their dependent startup/Core Data
callback ownership receives no new implementation, review or acceptance credit.
No pairing repair or M5 review bypasses that pause.

Next: preserve the verified 5a repair and reconciled Swift evidence; execute the
pending transcripts, M5 successor and Apple producer/ABI/provider/link tests,
then actual UIKit/consumer checks. Complete the authorized read-only UI analysis.
Integrate a reviewed final candidate and resolve current full UI. Request one
consolidated [phone acceptance phase](../DEVICE_ACCEPTANCE.md) only after feasible
development and non-device gates. No credentials, phone action, main promotion or
release is requested or claimed here. See [all 16 conditions](../PLAN_PROGRESS.md).
