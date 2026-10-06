# Retained native producer and app-consumer checkpoint

Evidence cutoff: **2026-10-06 05:56 UTC**. This supersedes the current-state claims
in the [2026-10-05 23:25 checkpoint](2026-10-05-native-pairing-progress.md), which
remains unchanged history. The [old status](../STATUS-2026-10-05-2325.md) and
[old matrix](../PLAN_PROGRESS-2026-10-05-2325.md) are also preserved.

## Recovery entry point

The accepted native producer now includes both Apple slices and a retained
XCFramework. The current app-consumer run passes source tests, normal preparation,
authenticated producer binding and unsigned Release compilation. Debug fails at a
concrete module/declaration mismatch. Further review found overlapping Rust/C
exports with incompatible ABIs in the linked static archives. A header-only patch
was rejected. The 35-file Rust FFI namespace/consumer candidate is independently
reviewed and backed up, but remains unpublished. No new native commit or run
is established. The original reviewed 70 web files are now published separately.

- Repository: [oskuhsiu/Tetherless](https://github.com/oskuhsiu/Tetherless)
- `develop`: `3d97ef75a224a76f84ba6741da8d9a6b89f99217`, unchanged
- Verification branch: `verify/staged-pairing-native`
- Current published head: [00c1c9397a01107b045d17b0ccba64431197d975](https://github.com/oskuhsiu/Tetherless/commit/00c1c9397a01107b045d17b0ccba64431197d975)
- Current tree: `6b535da4d6e85190a0474e56fbc046bef7c43993`, 699 leaves; original
  70 reviewed web files plus nine-file browser-QA delta, with unrelated entries unchanged
- Latest verified native consumer: [3f717ea5441d2cacee13e1d078e5ba7f1484edc5](https://github.com/oskuhsiu/Tetherless/commit/3f717ea5441d2cacee13e1d078e5ba7f1484edc5)
- Consumer tree: `a67e1e2436ec8614f644990cf51de29913484d18`; 621 blobs and one gitlink
- Native producer: [9ee2ccc9bd3519053781087acde54d4b4ee43236](https://github.com/oskuhsiu/Tetherless/commit/9ee2ccc9bd3519053781087acde54d4b4ee43236)
- Original plan SHA-256:
  `49d049cea36c0872224e888e20074d08d313031a72d6ed9a128ef320370fe3a6`

The retained producer is bound by explicit source/run/attempt identity. Later
consumer changes do not acquire new Rust or Apple producer test credit merely
because they consume its artifact. Neither branch is a completed product release.

## 1. Current diagnostic app run: failure with a Release pass

[Run 37407474925](https://github.com/oskuhsiu/Tetherless/actions/runs/37407474925),
attempt 1, job [112088119151](https://github.com/oskuhsiu/Tetherless/actions/runs/37407474925/job/112088119151),
ran at `3f717ea`. REST run/job evidence records terminal **failure**, completed
03:22 UTC on 2026-10-06.

| Stage | Result |
|---|---|
| Authenticate and retain exact producer artifacts | Passed |
| Core Debug | 345 Swift Testing + 40 XCTest cases passed |
| Core Release | 345 Swift Testing + 40 XCTest cases passed |
| Normal Integration | 499 collected: 492 passed, seven skipped before preparation |
| Diagnostic consumer tests | 231 passed |
| Normal app preparation | Passed |
| Prepared strict contracts | 13 passed, no skips |
| Bind verified composition into separate owned app copy | Passed |
| Unsigned Debug compilation | Failed, `xcodebuild` exit 65 after 200.459 seconds |
| Unsigned Release compilation | Passed, exit 0 after 378.501 seconds; `BUILD SUCCEEDED` |
| Retain evidence | Passed |

The compiler's Debug diagnostic is:

```text
'PLIST_OPT_COERCE' from module 'libimobiledevice' is not present in definition of 'plist_write_options_t' in module 'IDevice'
```

The note points to the generated `idevice.h` definition lacking that member.
This identifies the observed declaration/module boundary. It does not establish a
repair or the full reason Debug and Release differ. Both supervised compiler
processes were reaped, their groups were empty by `killpg_ESRCH`, and no cleanup
signals were sent. Debug's status marks `nonzero_exit`; it is not a timeout or a
Simulator boot/install failure.

The Release receipt labels the operation `diagnostic-only`: no app binary was
executed, no runtime capability gates were changed and no product activation was
performed. This is actual unsigned app/UIKit/composition build evidence, not
signed packaging, launch, live pairing or unattended renewal.

Retained artifact **11388930819**, 287,619,146 bytes, SHA-256:
`6fe740a1687b2f9d6fbfe01df4b7f82e02c0804d4a83a4d71b266289073648e9`.
Its contents include normal test logs, preparation/binding evidence, authenticated
producer handoff, both compiler logs/status and the Release compile receipt.

The normal Integration pass includes the real cold-reader test, ODA cleanup and
EMProxy spy. Seven skipped pre-preparation tests remain recorded as skips; the
separate 13-test prepared-contract pass does not make every skipped test a pass.

### New ABI/provider-ownership finding

Read-only export/header/link-command review found **100 global `plist_*`
exports** in the accepted Rust IDevice archive while `libimobiledevice` embeds C
libplist. The count comes from the genuine archive's BSD symbol index, without
Mach-O parsing. Eight mutator declarations return `void` in the Rust provider's
header but `plist_err_t` in pinned C libplist:

- `plist_array_set_item`, `plist_array_append_item`, `plist_array_insert_item`,
  `plist_array_remove_item`, `plist_array_item_remove`
- `plist_dict_set_item`, `plist_dict_remove_item`, `plist_dict_merge`

The overlap is not limited to plist: `afc_client_free`, `lockdownd_client_free`, `idevice_free`,
`misagent_install`, `house_arrest_client_free` and `debugserver_command_free`
also cross differing handle/return ABIs.

The actual Release command at retained log line 7005 directly links
`-lidevice_ffi` followed by `-limobiledevice`, with the existing `-Xlinker -w`
warning-suppression option. No link map was retained, so the selected implementation for each overlapping symbol is **not
proven**. A successful linker exit does not show that a consumer used its intended
provider or that runtime calls have compatible ABIs. The Release compilation pass
remains valid at its original evidence level; correct provider ownership and
runtime behavior are unverified.

A header-only patch is rejected as an insufficient repair. Full Rust FFI symbol
namespace isolation, matched consumer headers/call sites and discriminating
provider-ownership checks have an independently reviewed 35-file candidate.
The candidate remains unpublished; no new native commit, producer or app run is
claimed. This work concerns the FFI build/link boundary
and does not reopen paused signing/parser or manager-replacement scope.

The [exact diagnosis receipt](2026-10-06-native-ffi-diagnosis.json) records the
pinned headers, all eight declaration pairs, archive/export count and Release
command evidence. Receipt SHA-256:
`1968a248c780fe906c280e425699fa96139dd0d7a78c8fa6f77648e1966ba3d0`.

### Reviewed namespace candidate and newly available real C inputs

Independent review of the 35-file namespace/consumer candidate passes 255
consumer-diagnostic tests, 45 namespace tests and 11 mixed-provider tests, plus
C header-coexistence syntax checking and bounded fault checks. These are source/
portable checks. The candidate is backed up but remains unpublished; no new
native commit or workflow run exists at this cutoff.

The previously blocked C-provider download succeeded through a fresh retrieval of
the same artifact. The outer retained artifact has SHA-256
`809d7043b455bda5d30d6bb0048113de8a0a539a8d55427b4d3f5736a6605157`;
its nested actual release archive has SHA-256
`7ccbdd56b074807461fc43d2e32ba92f20df2501a6c14cf9f64a917e7f3fe6e7`.
Both actual device and Simulator slice inputs pass the unchanged
`mixed_provider.py` verifier. The retained actual-input receipt has SHA-256
`e1b3e4418fad1b6297c018b76bde8e3011a8f20e5d4f61c591ae081561d482ff`.
This supersedes the independent review's earlier missing-C-archive limitation.

The receipt binds device library SHA-256
`37151076240257494598a14a3df4cec3cc70b3800eb4be087b0cb54b0587740d`
and Simulator library SHA-256
`2f4ccf20c9744952c6ba2a9ec8a15a310f29d7de3071137919f6a70ceeec10a6`.
It explicitly records no binary-format inspection. Actual-input validation does
not establish new Apple compilation, disjoint Rust/C exports, mixed C/Swift link
probes, final app provider selection or runtime behavior. Those remain the next
native verification gates, with retained linker maps required.

### Preserved intermediate consumer failures

- `8164bba`, [run 37403018787](https://github.com/oskuhsiu/Tetherless/actions/runs/37403018787):
  Core passed 345 + 40 in each mode. Integration stopped before preparation with
  five owned-temporary-directory/symlink-guard errors. The bounded fixture-only
  repair normalized owned roots and retained production path guards
- `4f13ccd`, [run 37405019217](https://github.com/oskuhsiu/Tetherless/actions/runs/37405019217):
  Core, normal Integration, actual cold reader, 229 diagnostic tests and 13
  prepared contracts passed. Binding rejected the provider-kind label before
  compilation. The exact expected label was aligned to the accepted producer;
  real provider fixtures and provenance were added without changing the provider
  bytes or native implementation
- At `3f717ea`, binding now passes and the compiler is reached. The earlier
  fixture and provider-label failures are resolved within this observed flow;
  neither is the current Debug failure

## 2. Accepted source-locked native producer

[Run 37400684000](https://github.com/oskuhsiu/Tetherless/actions/runs/37400684000),
attempt 1 at `9ee2ccc`, has six successful, reconciled lanes:

| Lane | Verified result |
|---|---|
| Host components | 26 fixture tests |
| Acquisition components | 74 fixture tests |
| Combined components | 100 fixture tests |
| Full synthetic host transcript | Ten tests |
| Full synthetic acquisition transcript | Three tests |
| Apple producer, job 112066959183 | Device `ios-arm64` and `ios-arm64-simulator` release slices, six C/Swift link probes per slice and retained XCFramework |

The Apple evidence reconciles 61 complete joined commands, 166 package output
hashes and 167 checksum entries. Packaging completed in 6.706 seconds with a
naturally drained helper tail, reaped direct child and empty owned process group;
no cleanup signals were needed.

Artifact **11385154393**, 259,910,033 bytes, SHA-256:
`c90f04e44019e67e551dca9708e9e958729ca475094aa6eefbd8e42d638f0a77`.
Recipe index SHA-256:
`9971662d8f74774b7c6e23f2a42ff311baf8991f0302e1d0810882f52b0211ac`.
Both slices use header SHA-256:
`fd131679e900a2ab44ed2ced25a3cc9e56dad06e3a6147baeeb11bbc00ee0b64`.

The corresponding-source archive has 46,639 safe archive entries, 46,640 manifest
file hashes reconciled, and 189 recipe files matched to source. Its SHA-256 is
`004f310d48bdb1e4c8f9a407b95d8d9923f6a155cf7aff65e165339fd14730ca`.
The declared inward README symlink and case aliases retain their recorded scope.

Acceptance is **only for the closed diagnostic consumer**. Synthetic protocol
fixtures are not peer compatibility; link probes are not native iOS execution.
External OpenSSL input bytes are receipt-bound, but their source/binary equivalence
is not established. Rebuilds still require the separately locked toolchain/SDK.
No product-license, binary-format/signing, real-device or release conclusion follows.

### Earlier producer blockers and their limits

The generated Swift result-type import failure at `bdb4d45` is historical.
At `81146b9`, [run 37389963570](https://github.com/oskuhsiu/Tetherless/actions/runs/37389963570),
both Apple builds and 12 link probes passed, but packaging supervision failed
after the direct command exited zero. No production XCFramework was accepted
from that run.

A bounded diagnostic at `bba6850`, [run 37396649973](https://github.com/oskuhsiu/Tetherless/actions/runs/37396649973),
observed live same-group `xcrun`/`xcodebuild` helpers after leader exit and retained
the failure. It did not establish that all historical failures were zombie-related.
The tiny owned-leader successor at `7476bde`, [run 37399037692](https://github.com/oskuhsiu/Tetherless/actions/runs/37399037692),
passed 25 checks and exact toy-slice output checks with natural group drain.
That narrowly reviewed ownership change was then promoted to the source-locked
`9ee2ccc` producer. The accepted full production result is the latter run, not the
toy experiment.

## 3. App source fixtures now executed

At `4838168e2692e087b0465fca349f4cba8704011d`,
[run 37393328997](https://github.com/oskuhsiu/Tetherless/actions/runs/37393328997),
actual ODA cleanup positive/negative controls and actual EMProxy initializer/
callback spies in Debug/Release passed ten tests with zero skips. The artifact
reconciles 13 source inputs and three derived fixtures. Artifact **11381324996**
has SHA-256
`d0389fc75c6a9201a01393f1a2e48872476c12ed35bb19c92821fa271119ae66`.
The prior statements that these changes are unpublished/unrun are superseded.
The tests protect the ODA transfer pool and stable `usage.lock` ownership within
their fixture scope; they are not general app-lifecycle or logger-reconfiguration
acceptance.

At `a12b3ed7e2198669381a44c0693850054e32167f`:

- [Host Core 37391449382](https://github.com/oskuhsiu/Tetherless/actions/runs/37391449382):
  345 Swift Testing + 40 XCTest cases in each Debug/Release configuration
- [iOS Core 37391449448](https://github.com/oskuhsiu/Tetherless/actions/runs/37391449448):
  339 Swift Testing + 40 XCTest cases passed, including seven new scoped budget
  cases. This does not credit paused aggregate install-budget work
- [Swift fixtures 37391449492](https://github.com/oskuhsiu/Tetherless/actions/runs/37391449492):
  41 composition cases per Debug/Release mode, 24 source hashes; eight
  actual-manager promotion cases per Debug/optimized mode, 18 source hashes;
  all recorded commands reconciled

Composition uses a C ownership spy. Promotion uses synthetic parser/app-state/
process-lease acquisition seams. These passes do not by themselves prove native
parser, OS-lock, UIKit or live-backend behavior.

The [cold-reader fixture](../PAIRING_COLD_READ_FIXTURE.md) now executes in the
normal current macOS Integration phase. Actual manager/store/reset/mutation sources
and the ordinary upstream parser run in distinct writer and reader processes,
with nine scenarios each in Debug and optimized modes. Writer completion/group
termination is checked before reader launch. App directories, persisted preference
accessors, process-lock acquisition and gateway receiver are explicit seams.
There is no retained live gateway between processes, native-handle parse or device
traffic. The test adds no production startup call, reload, cache mutation or
manual-restart requirement.

The live contract remains open: the committed record and intended protocol must
reach the actual backend with callers and native adapter workers safely quiesced.
Saving bytes or passing a cold-reader fixture cannot establish that handoff.
Wireless product gates remain off.

## 4. Historical iOS and UI failures remain evidence

The `bf077f8` [iOS Core run 37386817629](https://github.com/oskuhsiu/Tetherless/actions/runs/37386817629)
remains terminal failure: all 33 XCTest cases and the separate 20-case target
passed; the 339-case Core target failed three unchanged 60-second limits. The
101.862882459-second interval between adjacent post-await traces has no established
cause. The later `a12b3ed` pass does not turn it into a diagnosed production lock
fix. Do not automatically repeat the historical failed run or weaken its bounds.

The last full product UI run remains `3d97ef7`,
[37298228388](https://github.com/oskuhsiu/Tetherless/actions/runs/37298228388): iOS
18.6 stopped at installation timeout; iOS 26.2 installed/launched and passed two
picker cancellations but did not open the local root to select a file. Fixture
installation/registration and document creation were observed; the original
241-byte file remained intact.

The retained archive analysis and [exact-event query 37381049415](https://github.com/oskuhsiu/Tetherless/actions/runs/37381049415)
remain inconclusive: four unsupported records leave gaps; the exact match yields
only the static assertion template, without the operation/error. That diagnostic
path is stopped without rerun or widening. Historical `c5f5547` iOS 18.6
invalid-input/signed-out acceptance remains scoped to its own source. New UI work
requires a distinct evidence-backed decision under the repository Simulator CI
rules, not a claim that these old failures have been fixed.

## 5. Reviewed source inventory is not BASE-02 clearance

The separately reviewed eight-file native supplement is **not published at this
cutoff**. Its archive is `Tetherless-native-supply-reviewed-9ee2ccc.zip`, SHA-256
`d1f8d4351efdbdb248c21f32e0d24f1a4a7f723e273f109b391120e80b86a126`.
Independent review reproduced six generated files byte-for-byte and verified all
eight candidate hashes, all 359 registry archive identities and notice bytes.

It records 359 registry and four workspace packages; 666 distinct source notice
files deduplicate to 232 exact text blobs. Actual compiler observations distinguish
161 device-target / 160 Simulator-target packages from 47 build-host-only packages
per target. Locked source presence is not final linked-symbol membership.
Three target-package and 13 additional source-only named-notice gaps remain;
metadata, README grants and 32 file-level LGPL statements are retained rather than
silently relabelled. Missing named files do not mean a package has no license.

The supplement does not complete the full product SPDX/source/notice/relinking
assembly, provider source/binary equivalence, ADI origin/admission/acquisition-use
basis or Unicorn combined-license compatibility. No legal clearance is claimed.

## 6. Web bootstrap: source published and Chromium QA passed

The original reviewed 70-file source packet is **published at `01bf960`**.
`Tetherless-web-bootstrap-reviewed-20261006.zip` has SHA-256
`7249d2692645ac0355c745e4ef03dd74420576c01adc907a10495ce50a1467b7`.
Its scope is `WebBootstrap/**`, `Tools/WebBootstrapService/**` and
`docs/WEB_BOOTSTRAP.md`; it does not change or review paused native work. All prior
622 branch leaves are unchanged; only the 70 original reviewed files were added.
The original source publication did not deploy the service or validate live
Apple/browser behavior. The later browser-QA result is recorded separately below.

Verified local evidence: 47 frontend tests, production build, real pinned zsign
WASM execution against a synthetic IPA, 19 offline Rust tests, formatting, strict
Clippy, release build and local release HTTP checks. Final source hashes match the
reviewed packet. Mock/DOM and self-signed synthetic tests were not real Apple or browser
acceptance. Browser execution was initially blocked in the local environment;
no restriction workaround was used. The later authorized GitHub Chromium run
below supersedes the earlier browser-unrun status within its explicit scope.

The prototype includes an optional transient account/provisioning service,
explicit consent boundaries and a UDID Profile Service exchange. No real account,
2FA, registration or certificate action occurred. Private signing material and
IPA output stay in browser memory in the implemented route; credential submission
to a selected service would require separate explicit authorization.

The service's ten-minute TTL applies to **account sessions and UDID enrollment**.
It does not implement a temporary signed-IPA hosting service. Signed output is a
browser Blob/download; the paid Ad Hoc helper only prepares a manifest/install
URL for separately authorized external HTTPS hosting, without uploading it.
Uncertain provisioning retains an exact request/key in memory for retry but has
no durable crash journal; session expiry/clear/navigation can lose that state.

Still open: Safari behavior and real Apple login/2FA/App Groups/profiles,
free Personal Team clean-phone install transport, first native login and
certificate/identity/data continuity. The native replacement dependency remains
paused. The known node-forge signature-verification advisory remains tracked;
absence of that API from reviewed application paths is not a clean-audit or
blanket safety result. Runtime hashes are not a reproducible WASM rebuild.
No hosting/deployment is authorized or performed, and paid Ad Hoc cannot substitute
for the free-account objective.

### Separate browser-test and hosted-delivery additions

The reviewed nine-file browser-QA delta is published at `00c1c93`.
[Run 37420583887](https://github.com/oskuhsiu/Tetherless/actions/runs/37420583887),
job [112128814238](https://github.com/oskuhsiu/Tetherless/actions/runs/37420583887/job/112128814238),
executes **18 Chromium tests in 16.118674 seconds**, with zero failures, errors or
skips. All nine cases execute at both root and project-subpath. Raw logs, JUnit,
implementation source, lock identities and retained report hashes reconcile.
Node is `v24.19.0`; Chromium is `145.0.7632.6`, revision `1208`.

Coverage includes real WASM signing of a synthetic IPA and exact embedded profile,
wrong-password rejection followed by a fresh attempt, explicit rights consent,
cancellation during inspection and worker loading, retry without stale output,
repeated clicks/clear/second signing/Back, asset resolution under both paths and
mobile-layout overflow checks. Actual Chromium mobile-viewport screenshots are
retained; they are not Safari or physical-device screenshots.

Artifact **11393390742** has SHA-256
`3a4034de154790454c6243fa4573db2690b153e8cb934cc38a6a4bee639cc689`.
The browser receipt ties it to exact source `00c1c9397a01107b045d17b0ccba64431197d975`.
This is genuine browser execution with synthetic signing material, not live Apple
login/provisioning, Safari, installation, deployment or hosted-OTA acceptance.
The paused OTA extension is absent from the run. No native parser change or
native-signing verification is credited by the test-only delta.

At the same source, [Core run 37420583864](https://github.com/oskuhsiu/Tetherless/actions/runs/37420583864)
reports API success. Its raw test counts have not been reconciled here; do not
transfer earlier exact counts to this run or treat it as a native app build.

The separate 18-file hosted-OTA extension is **unapproved and paused at review**.
Its checkpoint is retained, but it is neither published nor part of the accepted
70-file prototype. No signed-IPA hosting, deployment, live account action or
phone installation is credited. This documentation update does not inspect or
resume that paused extension.

## 7. Next bounded work and unchanged acceptance

1. Preserve the current failed artifact; complete publication of the reviewed
   namespace/consumer candidate, then verify the exact new producer and app
   consumer with actual C inputs and retained provider/linker-map evidence.
   No new native commit or run is claimed until independently observed
2. Finish unpaused pairing handoff, app/UI and integration work with unchanged
   acceptance assertions; keep product gates off and avoid per-renewal restarts
3. Integrate reviewed inventory work with accurate evidence levels; the original
   web source and browser-QA delta are published, and Chromium tests now pass.
   Keep the unapproved hosted-OTA
   extension paused. Finish feasible source/delivery and external provenance/rights
   work; deployment, live account actions and physical acceptance remain separate
4. Keep native signing-admission/certificate/Mach-O parser work, manager-replacement,
   aggregate install budgets and dependent startup/callback ownership paused. No
   paused draft was inspected, modified or credited for this documentation update
5. Finish feasible development before one consolidated authorized phone phase:
   login/setup, pairing/recovery, trusted install/launch, actual profile readback,
   next-day locked-screen renewal and original-expiry crossing. Keep the original
   30-day observation and clean-phone bootstrap as separately evidenced outcomes

No real login, live pairing, profile application, unattended renewal or soak has
passed. Normal renewal must remain mobile-only after initial setup, without
opening the manager, pressing refresh, using a computer or routinely restarting.
All 16 tasks remain open as detailed in [PLAN_PROGRESS.md](../PLAN_PROGRESS.md).
No phone-ready, release-ready, `main` promotion or deployment claim is made.
