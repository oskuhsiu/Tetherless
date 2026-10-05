# Native pairing and verification checkpoint

Observed **2026-10-05 22:19 UTC**. Native source 1ed3b9c reports success in all
five Rust lanes; its full acquisition transcript (three tests) is independently
reconciled. Apple device release Rust compilation passes, then artifact selection
fails before Simulator/probes/XCFramework. The ec7e229 exact-event diagnostic ends
inconclusively and that path stops. No app, real-device, release or original-16-task
completion is established.

## Repository and scope

- develop: 3d97ef75a224a76f84ba6741da8d9a6b89f99217, unchanged
- Active branch: verify/staged-pairing-native
- Published diagnostic source: ec7e229cc3b6d7bbf715225dc545481c213f81dd
- Diagnostic tree: 5a70ead2300f3b161ea42fa13d53c18149662041; 544 leaves
- Native proof source: 1ed3b9c96810fa78c387da15ecbee8a544a1b68c
- Native tree: 76ad67dc62e7a24d1716154f6f78df5ceca78a39; 540 leaves
- ec7e229 adds only four diagnostic files after 1ed3b9c; native results remain
  attributed to the exact 1ed3b9c run
- Next selector-repair candidate: under review; exact commit and CI identities pending
- Previous native verification: 5a40878c56d5a458021c29df9e7b2cb471e5e0dd
- Earlier composition commit: ad9b33f4c00764bd738e1912389cbe08cedd2c7e
- Earlier native app branch: verify/native-gates-c5f5547 at
  1fc8968f1d37b59717cd655b9b8f7fc8ccc7f566
- Original plan SHA-256:
  49d049cea36c0872224e888e20074d08d313031a72d6ed9a128ef320370fe3a6

The owner authorized the temporary component branch. It remains distinct from
develop, main and release. Its narrow app-job exclusion does not establish a
current full app build. New product pairing gates remain off.

Source 3ae371e includes the M5 successor, synthetic transcript fixtures, Apple
producer recipes and proof workflow, and the bounded historical archive query.
Its failures below remain historical. The subsequent 1ed3b9c run verifies the
typing and version-stream repairs and reaches the new artifact-selection boundary.
Record that selector repair separately; no future SHA or successful rerun is assumed.

## Current native proof: 1ed3b9c

[Run 37378994528](https://github.com/oskuhsiu/Tetherless/actions/runs/37378994528)
is terminal. All five Rust lanes have successful API conclusions. Current host 26,
acquisition 74, combined 100 and host transcript 10 artifacts are not yet separately
reconciled; their exact 3ae371e artifacts below remain the prior independent proof.
Do not substitute those older bytes for a current-run verification.

The full acquisition transcript is independently reconciled at 1ed3b9c, job
111995670082. All three actual native fixtures pass against a synthetic peer:

- Complete composite success authenticates, discovers, reads, closes and joins
- Cancellation joins at every tested protocol boundary
- The original overall deadline covers AFC after prior stages

All source/provider audits, log/status hashes and complete command joins verify.
The profile SHA-256 is
dbf445f10ca106d656c15ff5df84ab4bdcc38d4ecfe9d4010b6780e062a241ee.
[Artifact 11373355772](https://github.com/oskuhsiu/Tetherless/actions/runs/37378994528/artifacts/11373355772)
is 2,037,959 bytes, SHA-256
48f29e74c20766efc4cd4463cbf482833ff7153be58c9d063fb15f273b582df8.
This is the real native composite with a synthetic peer, not Apple-platform or
physical-device compatibility.

The Apple producer now passes actual iOS-arm64 release Rust compilation in
197.595237709 seconds with exit zero, complete bounded output and no truncation.
Provider-header compilation and the selected feature graph also pass. The next
selector rejects a legitimate same-manifest custom-build/bin compiler record
before reaching the correct staticlib record. Its failure is
“selected FFI compiler artifact is not the staticlib target”. This is after
successful device compilation, not the earlier version-stream or compiler failure.

[Artifact 11372648085](https://github.com/oskuhsiu/Tetherless/actions/runs/37378994528/artifacts/11372648085)
is 2,043,035 bytes, verified SHA-256
9bcae1e5093d818e83fe397baf66f6b0c51d523ec3ed067468a0fd5523667446.
It is retained and extracted locally. No Simulator slice, C/Swift probes or
XCFramework is established. The narrow selector repair is under review; dependent
consumer work must use the exact verified producer artifacts when available.
Pairing promotion entry remains separate active development, without activation.

## Current exact-event stopping result: ec7e229

[Run 37381049415](https://github.com/oskuhsiu/Tetherless/actions/runs/37381049415),
attempt 1/job 112002825438, is terminal failure with an **inconclusive** diagnostic
result. Bounded owned-archive export, exact-second query and cleanup pass. One
parsed record matches the exact message hash, timestamp and activity hash, but
four unsupported nonblank lines prevent complete event identification.

The recovered static format is “assertion failure : <value>”. It identifies no
specific operation, technical error code or explicit timeout. No private dynamic
message value was exported. A matching record is not a unique identified event
or a root cause.

[Artifact 11374265213](https://github.com/oskuhsiu/Tetherless/actions/runs/37381049415/artifacts/11374265213)
is 1,756 bytes, SHA-256
ca2da7de7935a8e5bcb72e4c3d464df2378374d3bc79b96d9c6936029469d4c4;
report SHA-256 is
bdf3df9b333e8a33e61baf96b817190157ce9d8ee72bad42d5f2cb0fd40ba12f.
This path stops without rerun or widening. No new UI run, product acceptance,
operation failure attribution or product fix follows. The historical product
source remains 3d97ef7/run 37298228388.

## Historical native proof: 3ae371e

[Run 37375339856](https://github.com/oskuhsiu/Tetherless/actions/runs/37375339856)
is terminal. Independent retained-artifact checks distinguish each lane:

| Lane / job | Actual outcome | Boundary |
|---|---|---|
| Host-only / 111982471894 | 26 pass, groups 8/5/3/4/6, including six M5 controller-identity tests | Host component behavior; not Apple or physical compatibility |
| Acquisition / 111982472206 | 74 pass, groups 18/25/11/3/2/4/4/7 | Does not substitute for the separate complete acquisition transcript |
| Combined / 111982473351 | 100 pass, acquisition groups plus host 8/5/3/4/6 | Synthetic host component execution; not real IDevice ABI or app activation |
| Host transcript / 111982471841 | All ten complete synthetic host transcript tests pass | A synthetic peer, not a phone; physical compatibility remains open |
| Acquisition transcript | Rust compilation reaches E0277 at synthetic peer Properties: {} | No transcript execution at 3ae. Later typing repair and three-fixture pass are recorded above at 1ed |
| Apple producer | Stops before compilation on merged Swift-driver output versus the stdout-only receipt | No compilation at 3ae. Later version-stream repair reaches device compilation and a distinct selector failure at 1ed |

The passing lanes have verified source/provider audits, log/status hashes and
complete command joins. The host-only record separately verifies its input/tooling
hashes. The six original artifact ZIPs match their published digests and sizes:

| Lane | Artifact | Bytes | SHA-256 |
|---|---|---:|---|
| Host-only | [11371177162](https://github.com/oskuhsiu/Tetherless/actions/runs/37375339856/artifacts/11371177162) | 3164815 | 9ed8a4f864e8601ba9867e884cb507c33ecc2af7b7dd3ed055c537a4e1490ce7 |
| Acquisition | [11371167807](https://github.com/oskuhsiu/Tetherless/actions/runs/37375339856/artifacts/11371167807) | 16081206 | f0006fe85dc190089807a6e4ed7306a6384918a11bda2e3195d4b5a66348ecb9 |
| Combined | [11371337835](https://github.com/oskuhsiu/Tetherless/actions/runs/37375339856/artifacts/11371337835) | 16178589 | 6c6a0296354fba71b6f1c0e3bc3705838a94888ecd043fe6e8bd7e6f5e6d6936 |
| Host transcript | [11372400317](https://github.com/oskuhsiu/Tetherless/actions/runs/37375339856/artifacts/11372400317) | 2038232 | 7a740ecc9d04915291c0d65e4832c9b2d7a58953e86335e87c60417512689b12 |
| Acquisition transcript, compile failure | [11372075978](https://github.com/oskuhsiu/Tetherless/actions/runs/37375339856/artifacts/11372075978) | 2024536 | 07b66e8dd7be4fc6a36acde1b7d3db231b6395e8454ea63123057c47ed7c7978 |
| Apple producer, pre-compilation failure | [11372195083](https://github.com/oskuhsiu/Tetherless/actions/runs/37375339856/artifacts/11372195083) | 21778 | ed7344fd7c6808fd4caf4593cd0b04f83c4ac4aa60742942ab96373ced3b77a7 |

These two historical failures are resolved at their original boundaries by the
subsequent 1ed3b9c run. The new selector failure remains open. The future consumer
must use the exact verified producer artifact, without substituting another binary.

## Earlier Swift and historical-archive analysis

At the same 3ae371e source, [Swift composition 37375339728](https://github.com/oskuhsiu/Tetherless/actions/runs/37375339728),
job 111982471628, verifies 41 passing cases in each Debug/Release mode, all 24
source hashes, and complete joined commands. Artifact 11371256288 has SHA-256
f3ed51006b71c2fd277a140bf9198070088d7ebe0d4380a70654823ebe956508.
This is synthetic C ownership-spy evidence, not real Rust ABI or UIKit compilation.
[Host Core 37375339731](https://github.com/oskuhsiu/Tetherless/actions/runs/37375339731),
job 111982470938, has reviewed raw-log evidence of 345 Swift Testing + 25 XCTest
cases passing in each Debug/Release configuration. No new iOS Core run was
triggered; its reviewed evidence remains at ad9b33f below. Separate Swift-19 and
helper jobs report success, but their artifacts have not been separately reconciled.

[Archive analysis 37375339797](https://github.com/oskuhsiu/Tetherless/actions/runs/37375339797),
job 111982471184, uses 3ae371e tooling against historical 3d97ef7/run 37298228388.
Export and the scoped query succeed, and temporary cleanup is confirmed. Artifact
11371641139 has SHA-256
0098c93c71adc4fb50a061d5aec256c33d5412833938bbd5b5574c5d5240c164;
sanitized report SHA-256 is
58151ec4f9b366c70cff7eeb3e5ed9274710813ce8420e16601e47d8f5b5e4e2.

The report retains 803 events from 807 nonblank lines and reports gaps for
unparsed/out-of-scope records. It has 716 DocumentManager and 87 FileProvider
events. Enumeration mentions all precede local-root activation. All 19
unlisted-domain messages hash-match an iconServices warning. The late lexical
navigation/error/timeout event has neither an identified operation nor a correlated
activity partner; no allowlisted error code is present. These observations do not
establish an actionable cause, justify another query/UI run by themselves or
constitute a product fix. Historical source preservation and failed UI assertions
are unchanged.

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

The M5 controller-signature and ten-test synthetic host transcript proof remains
independently established at 3ae371e. The current 1ed3b9c acquisition transcript
adds verified success/cancellation/deadline evidence, while other 1ed lane artifacts
await separate reconciliation. This is separate from paused app-signing admission.
Apple artifact selection, Simulator compilation, C/Swift probes, XCFramework and
diagnostic consumer remain open. Actual UIKit composition and the separate pairing
promotion entry still require integrated verification; no gate is activated.

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

The bounded read-only query and subsequent exact-event query analyze retained
evidence, not a new Simulator/UI run. Both remain inconclusive; the exact-event
path has reached its stopping result and must not be rerun or widened. No selector,
deadline or product behavior changes, and no cause is established.

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

Next: preserve current 1ed verification and separately labelled API successes,
alongside historical 3ae/5a evidence. Review and verify artifact selection, then
finish Simulator/ABI/XCFramework before actual UIKit/consumer work. Continue the
separate promotion entry without activation. Stop the exact-event diagnostic path;
any different UI work needs a new evidence-backed decision.
Integrate a reviewed final candidate and resolve current full UI. Request one
consolidated [phone acceptance phase](../DEVICE_ACCEPTANCE.md) only after feasible
development and non-device gates. No credentials, phone action, main promotion or
release is requested or claimed here. See [all 16 conditions](../PLAN_PROGRESS.md).
