# iOS Core assertion-boundary decision

## Observed boundary

The completed iOS Core workflow 37351051292, attempt 1, job 111901677965 tested
source 3ace3be97eddb164fca7372ef946aaadc00c3371. Its original Swift Testing run
reported 339 tests, three timeout issues and 145.109 seconds. All 12 new XCTest
Core cases passed in 0.455 seconds. The failed cases are:

- ProcessLeaseScopeTests.admittedChildRetainsTransferredDescriptorUntilItFinishes
- MutationScopeTests.admittedChildKeepsLeaseAfterParentReturns
- MutationScopeTests.lateChildCannotBorrowClosedScope

All three retain the original one-minute test limit. Later automatic XCTest
restart output for 19 other cases does not validate the three failed cases.
The full simulator-tests.log was retained from artifact 11363640310, ZIP SHA256
fa7aec3d8dfbdb75b10c078bbe9a0386a07f4827a7c0dd0e5c78959ebdc253a2.

The checked-in run/jobs projections and read-only classifier output refer only
to this exact source/run/job. The classifier's fixed category `ui` covers this
XCTest execution boundary; this was a Core package run, not product UI testing.
The step combines compilation and execution, so its map is incident-specific:
actual logs, not the step name alone, establish that compilation completed and
the failures occurred in running tests. Do not reuse this map to classify a
future build failure. Classifier report file SHA256: 25d9744a8c272b76c1f68eb02887b7f339f522c89f085b2e1c9f6d65b564f282.
No boot failure or application data mutation is inferred.

## Measured intervals and hypothesis

Existing fixed monotonic events show the admitted child enters its borrowed
scope in 10.834 microseconds. After the outer scope returns, 88.496618459 seconds
elapse across three expectation expressions before the parent signals the
waiting child. In the late-child case, the child already exits while its
expected-error assertion does not complete until about 96 seconds later.
Eighteen unrelated passing cases also report more than 140 seconds.

The cause is unknown. A discriminating hypothesis is that delay occurs after
the expected-error body returns, in assertion processing/runtime scheduling,
rather than during actual lease acquisition or the child await. The current
coarse markers cannot prove that hypothesis. This change adds fixed events
before/after each of the admitted case's three expectations and inside its
expected-error body; the late-child body gains entry/deferred-exit events. The
real ProcessLease case gains the same expected-error envelope/body markers.

Body-exit followed by a large expectation-exit gap supports a post-body delay.
Each clock is sampled before synchronous print, so measured gaps also include
trace-output overhead and runtime scheduling; they cannot alone attribute delay
to assertion internals.
A gap within the body or before body entry instead narrows a different boundary.
No delay on the next run is an observation only, not proof that instrumentation
fixed production code. A repeated gap without a new discriminator blocks another
identical full-run loop. Preserve the next exact logs/results before deciding.

## Unchanged acceptance and environment

Only two test sources gain diagnostic markers. The instrumented ProcessLease
closure explicitly returns its original ProcessLease result, preserving the
implicit-return type and value lifetime even on unexpected success. Removing those marked additions
and normalizing whitespace reproduces each complete original source, verified
by fixed SHA256 tests. Original assertions, exception values, task count,
awaits, lock ownership, cleanup and one-minute traits remain unchanged. No
serialization, sleeps, deadline changes, Simulator resets or runtime changes
are introduced. New output contains only closed-enum event names and clocks.
Five portable diagnostic contract checks pass; no local Swift compiler exists.

The existing simulator.yml launcher, destination selection, recorded Xcode 16.4 build 16F6
contract and original package test command remain unchanged. The failing run
used macos-15-arm64 image 20260907.0337.1 and iPhone SE 3/iOS 26.2, matching the
accepted 1fc8968 Core observation's recorded image/Xcode/runtime. The incident
logs do not directly print a Swift compiler version. Matching
seeded Simulator UUIDs do not establish the same machine. Record the actual
next environment again; no tested binary is reused across changed test sources.

Current runs are terminal before this diagnostic is eligible for publication.
The later app composition source additions are intentionally excluded from this
narrow test-diagnostic candidate, avoiding a new test-load confound. No complete
product UI rerun is requested. This diagnostic cannot establish new pairing ABI,
app UI compilation, device behavior or a fix for the existing import UI issue.

After one planned iOS Core run, record its exact source/run/job, read these new
intervals and stop to classify the next boundary. A green result keeps the prior
three timeouts visible and does not authorize broader product-completion claims.
