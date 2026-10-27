# MutationScope timing-only diagnostic decision

Date: 2026-10-05. Status: reviewable instrumentation; no run dispatched by this change author.

## Boundary and evidence

- Failing source: 3d97ef75a224a76f84ba6741da8d9a6b89f99217
- iOS core workflow: .github/workflows/simulator.yml
- [Run 37298228262](https://github.com/oskuhsiu/Tetherless/actions/runs/37298228262), attempt 1, [job 111724485345](https://github.com/oskuhsiu/Tetherless/actions/runs/37298228262/job/111724485345), xcodebuild exit65
- First failure: actual test execution. Compilation and test-process launch succeeded
- Failure fingerprint: 5cf4b45946a31dc3ca573249429e829db6490f37a0fc40c3c1f79b4f75972a0d
- Report checksum: 3974f1b348be414503a182fcfec98c9fbf4af46c37d0d011f08a95b63b6089ef
- [Artifact 11340563936](https://github.com/oskuhsiu/Tetherless/actions/runs/37298228262/artifacts/11340563936), 63, 203, 344 bytes, verified ZIP SHA-256: 9e8da303057c1cb19044be61c726456d7ed50d4f773260fc9914189238df1304
- automaticRetryAllowed=false; root cause remains unconfirmed

The first Swift Testing launch reports 339 tests and two 60-second issues: lateChildCannotBorrowClosedScope and admittedChildKeepsLeaseAfterParentReturns. They finish at 132.652 and 132.620 seconds. Among 336 passing-test lines in that launch, 277 exceed 60 seconds and 229 exceed 130 seconds. The real-descriptor admitted-child analogue passes at 132.454 seconds.

The later 20-test pass is **an automatic ODAMetadataTests restart**, not archive validation. The restarted MutationScope suite executes zero scope cases. Its empty-suite pass label does not revalidate either failure. The xcresult adapter aggregates one failure while the first-launch console records two deadline issues; retain both layers.

The attached spindump begins10:46:25.793, after test-plan completion. xctest is reporting completed tests with idle workers. It cannot locate the earlier delay. No early wait stack is established.

## Baseline comparison and environment

Source baseline for this narrow change is cb8e4ddea50da972661eb78324f83998663a26ec, whose parent is 3d97. Its only intervening change is an unrelated portable native-probe test. There is no MutationScope, package source, package test or core-workflow change from the prior passing c1482e0e615f56bfa37fa9437c43aa1669550cec to 3d97.

Prior passing iOS core [c148 run 37291091619](https://github.com/oskuhsiu/Tetherless/actions/runs/37291091619) and [c5 run 37286010392](https://github.com/oskuhsiu/Tetherless/actions/runs/37286010392) use the same recorded Xcode 16.4/16F6, iOS 26.2, iPhoneSE3 destination and macos-15-arm64 image 20260907.0337.1 as the failure. c148 scope cases took65.799/65.800 seconds and were reported passed; c5 took8.186/8.190 seconds. This is not evidence of a new environment drift or grounds to raise the unchanged limit.

Current fingerprint: macOS 15.7.9/24G830; Xcode 16.4/16F6; iOS 26.2/23C54; SDK iPhoneSimulator18.5/22F76; Swift Testing 124.4; arm64; Swift language mode 6; Debug; CODE_SIGNING_ALLOWED=NO. Exact swiftc compiler-version text was not recorded. Keep this existing contract for the discriminator; a 26.3 pin would be a separate change.

## Hypothesis and exact change

Hypothesis: the large reported duration arises outside these test bodies or at scheduling of an existing await, rather than a permanent local ownership deadlock. The current evidence cannot distinguish test-framework overhead, cooperative-executor contention, Simulator services and host pressure.

Only MutationScopeTests.swift is instrumented, apart from this decision document:

- One private enum of 35 fixed typed event cases
- One synchronous helper emitting the fixed event plus DispatchTime monotonic nanoseconds and UTC Unix seconds
- 35 observation calls in the two existing bodies, including two observation-only defer calls
- No new tasks, sleeps, waits, catches, guards, queries, polling, lock-state reads or async work
- No production source, workflow, suite parallelization, test-selection or environment change

All original statements stay in their original order. Every assertion line and the 60-second trait remain unchanged. The late-child outer closure remains its original single Task expression. No user identifiers, paths, input values, secrets or lock state are logged.

## Interpreting the fixed events

- admittedOuterBefore → admittedParentEnter: outer scope entry
- admittedParentChildCreated / admittedChildEnter: original child scheduling
- admittedChildScopeBefore → admittedChildScopeEnter: admission to the inherited scope
- admittedParentWaitBefore → admittedParentWaitAfter: original admission wait
- admittedChildSignalBefore/After and admittedChildResumeWaitBefore/After: original actor signal/wait
- admittedParentReturning → admittedOuterAfter: original root scope unwinding
- admittedParentSignalBefore/After and admittedParentValueBefore/After: resume and retained-child completion
- lateOuterBefore/After: original root scope execution
- lateChildEnter and lateChildResumeWaitBefore/After: late-child scheduling and wait
- lateParentOwnerAcquired: original external owner acquired before resume
- lateChildScopeBefore → lateChildExit: expected busy throw
- lateParentExpectBefore/After: original unchanged busy-error expectation completed
- admittedTestEnd / lateTestEnd: observations following original final checks/cleanup

lateChildScopeAfter should be absent on the expected busy path. The unchanged expectation remains authoritative. Defer records child exit on ordinary return or throw without intercepting it.

Compare captured monotonic times, not just output order. Short body spans with inflated framework durations locate delay outside the observed body; long spans identify an existing awaited boundary. Neither result by itself establishes host pressure or another suite as the cause. A missing event or a trace-only pass is not proof of a repair. Clock sampling and output have observer overhead.

## Verification already executed

An automated canonical-source check removed only the exact reviewed helper block, Dispatch import and 35 typed observation/defer lines. The **entire remaining file** is byte-identical to the pre-instrumentation baseline, stronger than comparing only the two bodies.

- Baseline/canonical SHA-256: 8b56d690c9bcf235f0b2378376c69cf8fffed7328b265639b136aaa62eae21d0
- Reviewed declaration-block SHA-256: 5ab041785492564429807af01633bb57a017db3d0f8a0837da440c80b441b43b
- 15 assertion lines unchanged; existing time-limit text unchanged
- Negative checks reject a modified assertion, changed time limit, arbitrary marked work, changed clock helper, renamed event, unmarked statement and mismatched baseline
- No local Swift or Xcode is available, so this is source-equivalence evidence, not a successful Swift compile or Simulator execution
- Existing Integration Python discovery was attempted: 395 tests, 349 passed, 39 skipped, 7 errors. Every error is FileNotFoundError for unavailable swiftc; the aggregate is not green. No test was skipped or changed to hide this environment limit

The separate reviewer comparison script and JSON result accompany the implementation handoff; neither changes repository scope.

## One-run gate and stopping condition

After independent review, parent may publish this two-file change to the verification branch. Confirm its actual base and workflow path filters/concurrency before publishing. Tests/** should select the existing core and iOS-core workflows; no full-product UI dispatch is part of this decision.

Keep every original test, assertion, 60-second trait and data-preservation check. Preserve full raw event output and xcresult for the exact diagnostic SHA. Record the new SHA/run/job/attempt after parent dispatch; none is recorded as already dispatched here.

If the timeout repeats without new localization, stop full retries and inspect the new boundary spans. If it passes, report exact-SHA acceptance and that the cause remains unconfirmed. Do not silently turn a timing observation into a production fix, larger timeout or test relaxation.

No paused MachO/CMS/signing-admission, manager-replacement, startup or resource implementation is in scope. Full-product run 37298228388's separate install/UI evidence is not this diagnosis.

