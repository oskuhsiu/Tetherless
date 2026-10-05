# Pairing source-fixture verification decision

Decision recorded before the first run of the new Swift fixture packet. This is
new-code verification, not a retry of the unresolved document-picker UI.

## Source and execution scope

The implementation commit containing this record inherits the component branch
from b7f9a59276402347c53491539498fc022d4f3840. Its exact SHA is recorded by GitHub and
in each retained run-context file. The app-boundary source packet has independently
reviewed lifetime, promotion and mocked transport fixtures. The wrapper embeds
exact input hashes, so copied or stale source cannot silently supply its result.

The new workflow is confined to verify/staged-pairing-native. It runs 19 unique
Swift fixtures in Debug and Release with the existing bounded process supervisor.
They exercise source code, registration spies and local socket pairs. The native
IDevice bridge is not linked or executed; no Bonjour service is published and no
phone, account or pairing credential is used. Product gates remain disabled.

The first compiler command exercises Debug code. Each command retains its own log,
exit, timeout and cleanup evidence; repeated XCTest aggregate lines are accepted
without letting a duplicate fixture replace a missing one. The wrapper stops
further phases if cancellation or unconfirmed cleanup occurs. The workflow retains
only its new evidence directory, never scratch build products or user files.

## Existing Core and Simulator coverage

Adding NativeCallLifetime/PairingPromotion under TetherlessCore also triggers the
existing host Core and iOS Core workflows. This is warranted by new production
source and 12 new core fixtures. No existing test assertion or timeout changes.
The full document-picker UI workflow remains develop-only and is not triggered by
this temporary branch.

The last accepted iOS Core comparison is source 1fc8968, run 37303840210,
job 111742646601: 339 tests passed with the two mutation-scope test bodies around
1.15 seconds and their original 60-second bounds intact. Its evidence is scoped to
that source. It does not validate the added fixtures. Latest full product UI
run 37298228388 at 3d97ef7 still failed: 18.6 at installation, 26.2 at source-folder
readiness before file selection. This run does not attempt to repair those stages.

The existing Core workflows and environment selection remain unchanged. Retain
the new run's actual Xcode/runtime/device identity and compare with the recorded
accepted environment; any drift must remain explicit rather than being called an
identical reproduction. The standalone macOS job selects the already-used
Xcode 26.3 path and records actual compiler path/version, runner architecture and
image. It does not install or upgrade tools.

## Expected result and stopping condition

A pass requires all 19 distinct named fixtures in each configuration, a successful
final XCTest suite, unchanged source identities and joined process cleanup.
Separate host/iOS Core results must be checked at the same implementation SHA.
A mock/native-source pass is not native ABI, container-challenge, device pairing or
application acceptance.

On failure, retain and classify the first actual compile, fixture, timeout or
cleanup boundary before changing source or running again. Do not change selectors,
reset a simulator or extend any deadline. Record the new run IDs and exact artifact
hashes after publication. No relevant Simulator run is active at this decision.
