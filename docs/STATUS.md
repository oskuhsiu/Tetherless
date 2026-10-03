# Current checkpoint — explicit read-only certificate recovery core

Updated 2026-10-03. All development remains on develop; main is unpromoted. No device handoff yet.

## Verified starting point

Actual GitHub checks for 00e5e109673156c0e2c958d666b3a1396efe7f09 are all successful: core run 37088160550, unsigned native Debug/Release run 37088160572, and whole-app/UI plus diagnostic retention run 37088160526. The previous diagnostic copy failure is no longer current. Source artifact 11260838951 matched SHA-256 62f8b42fb277c69f175bf8d9fd36d8951a9fe374cb13c71ee88a54ef17c6ca6b; its embedded commit and TAR digest were checked before editing.

## Current coherent increment

CertificateRecoveryCoordinator separates non-mutating checks from explicit submission, save and discard. Checking has a read-only backend capability and never writes the request journal, caches or active identity. Possibly submitted requests are never blindly resent or discarded. Owner/Team/type, exact request UUID, phase and cancellation are rechecked; stale lookup results are rejected. Details: CERTIFICATE_RECOVERY.md.

Local Linux Swift Debug/Release each passed 207 tests, including 13 recovery tests (one parameterized across the three phases). A first test macro compile error and a timed-out combined command were corrected/rerun; only completed final runs are counted. The new core is not yet wired to native controls in this checkpoint. No claim of real Apple or hardware validation.

## Resume next

1. Wire the check-only and explicit actions through NativeCertificateIssuance and the authenticated portal proxy, preserving the common mutation lease and current-account guard.
2. Add dedicated foreground recovery controls and actual no-account UI coverage. Do not use allowNew:false as a check API. Never activate or revoke a signing identity as a side effect of checking/saving recovery material.
3. Review native/Simulator CI for the actual implementation SHA; then continue Anisette/pairing/log lifecycle, aggregate resource reservations, staging cleanup and distribution checks.

Historical baseline evidence: STATUS-00e5e10.md. Progress is still an engineering estimate toward implementation plus feasible non-device acceptance, not a reliability percentage. No credentials, pairing or phone are requested.
