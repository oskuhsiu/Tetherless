# Pairing composition Swift verification decision

The source packet adds the protected container challenge, independent cancellation
controller, numeric endpoint/resolver and separate staged-validator bridge. Its
lease-owning UI model and PIN presentation are source-reviewed and gated off;
only OnboardingView.swift changes an existing app file. The standalone fixture
package compiles the exact selected Core/bridge source against an explicitly
synthetic C ownership spy. It excludes the UIKit model, SwiftUI view and real
Onboarding integration, and cannot establish generated-header ABI or app linkage.

The original 21-file packet has manifest SHA256
e63484590a8bdff3235fd58aa7d99ddca33bea69003cc474c7f6dfc271890312.
Its independently reviewed one-hash correction binds the staging-module pin to
132a633318faa7df826997570cc122993d6ce878abf183db61ca2472ad856ce6;
the process supervisor remains unchanged. The corrected wrapper SHA256 is
9fd0a32d6f1013ff0f140d997f1177bf1901e0bc9375b90f856757d34085cb5e.
All 22 local wrapper/contract tests pass. Actual Swift execution is pending.

The new workflow reuses the accepted Xcode 26.3/macOS source-fixture envelope:
separate Debug and Release commands, each with the original bounded supervisor,
exact 41 unique passing XCTest names, joined process groups and retained logs.
The per-command 60-second limit and six-minute execution step remain unchanged.
Observed toolchain, source and runner identities are retained with the result.
No C spy is copied into the application or registered as its native provider.

The workflow is scoped to the existing explicitly authorized verification branch
and exact relevant source/workflow paths, with cancellation disabled. It adds no
change to develop or PR acceptance rules. The existing ordinary host Core and
iOS Core workflows also test the newly added package sources. Before publication,
confirm no same-branch Core check is still active and reconcile the immediately
preceding assertion-boundary diagnostic result; do not cancel its observation.
An unresolved iOS timing failure remains explicit and requires a new evidence-backed
decision before another full iOS Core run. This record alone does not authorize
repeating that failure without such evidence.

The independent native host/acquisition matrix uses other paths and its own
noncancelling concurrency group. This Swift-only slice changes no Rust source,
profile, dependency/provider input or shared staging helper. It does not rerun
that matrix. Native Apple archive/header/probe and real iOS composition compilation
remain separate gates, followed by a single consolidated physical acceptance pass.
