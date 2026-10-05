# Product import verification decisions

Historical first decision, reviewed 2026-10-05 before 0dfceb5: This decision authorizes one changed-source full-product verification, alongside native Debug/Release regression checks for the reviewed privacy/cache increment. The commit carrying this decision is the implementation candidate; each workflow records its exact GitHub source SHA and job-owned evidence. Run/attempt/job IDs must be recorded when GitHub creates them. No native result is claimed here.

## Current evidence

- Full-product source 89c157dbc6acd3c16eb31a32bdc6d73af6c40f57, run 37247923030 attempt 1, job 111569414544: build/signature/boot/install/launch passed; selected-document XCTest failed. The Simulator booted. Original source verification passed
- Discriminating standalone source 9a49417dc6f6b707b94786882722ca907870fa9c, run 37273262340 attempt 1, job 111644618374; downloaded artifact SHA-256 3558700b84e0326ae64aae2e11a9c2bab954367bf8933bc0ec1eb7b2c788983e independently verified
- On the same observed host and unchanged signed diagnostic artifacts, iOS 18.6 delivered one file URL and dismissed after two actual cancellations; iOS 26.2 delivered no selected callback and remained open. Both original public files were unchanged
- iOS 26.2 evidence points to the service-URL/bookmark-materialization boundary before the delegate, with -1005/-1012 and empty URLs. This is a runtime-associated observation, not proof of a unique cause or an Apple defect
- The standalone diagnostic overall failed; its iOS 18.6 UI passed but evidence collection remained incomplete. It did not test the full product parser, protected storage, or navigation

## Hypothesis and discriminating increment

The independently observed delivery path on exact iOS 18.6 can now exercise the complete production selected-import rejection and subsequent navigation/relaunch. This is supplemental coverage, not a substitution for the unresolved iOS 26.2 case. The two jobs rebuild independently and do not claim a same-binary causal comparison.

Both matrix lanes run the same complete production flow on exclusively job-owned fresh SE3 devices. They require exact installed runtime/build (18.6/22G86 or 26.2/23C54), arm64, Xcode 26.3 build 17C529 and Simulator SDK 26.2 build 23C57. No download, Xcode installation/selection mutation, fallback runtime or generic architecture build is added. The macOS 15 runner image identity is recorded; image drift from 20260907.0337.1 is explicitly flagged in the preflight manifest, not assumed to be unchanged.

## Expected observation and unchanged acceptance

Two actual system cancellations; one actual document-cell selection; the original ten-second outcome deadline and real picker dismissal; actual typed PrivateFileError.invalidContent from the selected-import catch; original source bytes unchanged by the independent postcheck; fresh protected pairing store observed missing before import, after rejection and after relaunch; no automatic pairing/account/consent granted; the rest of the existing product navigation/recovery flow must still pass.

The public fixture has neither pairing schema. The actual normalization throws invalidContent. The external file reader and coordination guard use different failure categories, so a generic access/coordination/storage failure cannot satisfy the new typed assertion. Classification changes observation only and rethrows the same error. No paths, contents, account IDs, device IDs, raw errors or secrets are exposed.

## Failure and closure rules

A missing/mismatched runtime, architecture or toolchain fails preflight before allocation/build. If it reaches UI, any missing outcome, unresolved picker, non-parser failure, unavailable/unchecked fresh-store state, source mutation or later navigation/relaunch failure fails that job. A red 26.2 lane cannot cancel the separate 18.6 lane. Artifacts are runtime-specific.

A pass on 18.6 establishes only its actual tested full-product path. It does not resolve the 26.2 pre-delegate failure, prove retention of an existing valid pairing, prove successful valid-pairing import, or establish live Apple/device/unattended renewal acceptance. The fresh-store observation establishes readable absence, not general storage acceptance.

Stop after the single planned exact-source verification and inspect any new earliest failure. Do not repeat the known 26.2 full-run loop without new discriminating evidence. Preserve failed evidence and collector gaps.

## Next changed-source decision: fix actual dismissal/result ordering

The completed 0dfceb5 run [37277414175](https://github.com/oskuhsiu/Tetherless/actions/runs/37277414175), attempt 1, supplies a new discriminator on both runtimes. Both received exactly one selected-file callback **after** the product had already finalized cover dismissal as cancellation. Full event scans are complete; both original files remain intact. The exact artifacts, assertions and unexecuted later checks are in [the checkpoint](../checkpoints/2026-10-05-0dfceb5.md). This newer failure is not the earlier absent-delegate/provider boundary.

The reviewed correction keeps explicit delegate outcome and completed dismissal as independent, generation-bound events. Import consumes a selected URL once only after both. A minimal stable UIKit presenter owns one actual system picker until result/teardown; it does not re-present, copy the file, change allowed content types or rotate targets. A physical cover token prevents a logically abandoned request from admitting a new cover before the old one finishes. Teardown cannot initiate import or cancel an already delivered result. If the native picker returns without any result, an explicit “Return to setup” recovery action abandons only that unresolved generation; it is never used as the system Cancel in acceptance tests.

Core/adapter tests add both event orders, duplicate/late/wrong-generation events, explicit cancellation, invalid URL/multiple selection, teardown/recovery and reentrant callbacks. Independent static review passed. Local Swift execution is unavailable; the next exact-source core and native jobs must actually compile and exercise them. The existing full-product UI test, exact-runtime workflow, ten-second selected-result deadline, real two-cancel sequence, fixture bytes, protected-store observations, relaunch and later navigation assertions remain byte-identical to 0dfceb5.

Authorize one changed-source verification on both existing product lanes, alongside native Debug/Release checks for the reviewed independent privacy/backup/delivery increment. Preserve each result independently. Expected observation: real selection is accepted, actual import starts only after matching dismissal, the real parser rejects invalid content, source bytes remain intact, and the remaining untouched UI flow executes. Any earlier compile/environment failure or later UI failure stays failed and must be classified from its own evidence before another run. A pass does not establish valid pairing import, preexisting-record retention, Apple authorization, installation or unattended physical renewal.

The same next native workflow also repairs the demonstrated maintenance-test wait bridge, requires all six formerly skipped transient-preimage contracts to execute after verified preparation, and produces explicitly incomplete candidate byte/source/notice inventories. These are separate evidence levels and do not turn this into a release.
