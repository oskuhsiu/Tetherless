# Native host and acquisition component verification decision

Source base: `3ace3be97eddb164fca7372ef946aaadc00c3371` on the owner-authorized
`verify/staged-pairing-native` branch. The previous helper/RSD input at
`6bf7b891ad59a5ae00fbf45e527b7412dfca597d` passed all 43 native fixtures in
run 37348967899. Its original/derived/workspace source audits passed. This run
adds separately reviewed host and OpenSSL acquisition components; it is their
first native execution, not a retry of the iOS UI or concurrency-test failures.

## Exact scope and hypothesis

The independently reviewed host packet selects 20 fixtures with upstream AWS-LC
defaults. The reviewed component packet selects 72 acquisition/helper/RSD fixtures
or 92 including the host module, with OpenSSL explicitly added to the unchanged
defaults. Their only divergent shared source is the exact allowed-profile tuple
in `apply_patch.py`. This integration takes the union of those already reviewed
profile names. The standalone Swift verifier updates only its pin for that
staging module; no Swift source, assertions or fixtures change.

Three fresh isolated matrix jobs use the same pinned source, original lock,
Rust 1.98.1 and Xcode 26.3 selection as the successful helper run. Each records
the observed image/toolchain instead of claiming the rolling label is immutable.
Source and registry acquisition remain pinned and credential-free. OpenSSL
inputs are checked and copied by the existing exact-input capture, then verified
by the reviewed split-provider adapter. The host-only job does not acquire or
use those inputs. Cargo commands remain frozen and offline after acquisition.

The expected discriminators are actual Rust compilation, exact 20/72/92 suite
summaries, header syntax compilation, resolved feature graphs and selected
openssl-sys build output, followed by all required input audits. The component
runner's per-command deadlines, capture limits and success rules are unchanged.
The 300-minute workflow step is an outer resource ceiling for up to twelve
individually bounded 20-minute suite commands plus compiler/feature probes, not
a fixture deadline increase. The 350-minute job ceiling leaves room for the
existing bounded setup and final evidence upload. An outer timeout remains a
failure and cannot provide missing native evidence.

## Trigger and evidence boundaries

The new workflow matches only the explicit verification branch and dependency
paths or its own workflow file. Matrix fail-fast and concurrency cancellation
are disabled. It does not edit any develop/PR acceptance workflow. The changed
shared staging module legitimately retriggers the existing helper and Swift
component checks. No `Sources/**`, `Tests/**`, Package.swift or simulator workflow
changes are included, so the iOS Core workflow is not triggered by this slice.
All existing runs were terminal before publication preparation.

The 3ace3be iOS Core run 37351051292 remains failed: three unchanged 60-second
concurrency cases exceeded their limits, while all twelve newly added XCTest
cases passed. Large measured gaps occur within the assertion/runtime/scheduling
region; those observations do not yet establish a lock defect. This component
run does not retry or resolve that failure. The latest full product import UI
results also remain failed at their previously retained install/selection stages.

Each matrix artifact retains unique per-suite logs/statuses, source and toolchain
identities, success evidence or partial failure/audit files, and exact public
provider input bytes where applicable. The workflow does not publish test
executables or enable an app route. Passing components cannot establish Apple
single-provider final linkage, generated-header ABI, synthetic whole-transcript
success, real device pairing or unattended renewal. Those remain separate gates.
