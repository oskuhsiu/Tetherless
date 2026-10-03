# Current checkpoint — authentication diagnostic privacy

Updated 2026-10-03. Work remains on develop; main is not promoted. No physical-device handoff or live credentials requested. Previous verified recovery implementation is dd0b09c; this checkpoint adds authentication privacy hardening and a narrow test traversal correction.

## Implemented in this checkpoint

SideSign Authentication.swift's 72 free-form logging sites are removed. Raw/decrypted response copies no longer enter its errors or retry messages. The public authenticate boundary rebuilds propagated errors without server payloads, token-bearing URLs or arbitrary NSError userInfo, while retaining cancellation, authentication decision types and numeric server codes. Only typed fixed authentication events can log. Legacy SideSign debug/verbose autoclosures are not evaluated in either logging mode; enabling our events does not enable AnisetteKit verbose logging. The actual request fields, token processing and server-proof verification remain in place. See AUTHENTICATION_PRIVACY.md for tradeoffs and scope.

Both prepared inputs are hash-checked before any write. The transformation was applied to the exact retained dd0b09c native sources and syntax parsed. The test compiles the identical logging replacement and error policy with real upstream error enums; secret-shaped data is synthetic. This is not real Apple login/2FA validation or an exhaustive native/dependency logging audit.

## Previous UI result is now known

Run 37106719330 at dd0b09c failed at TetherlessUITests.swift:78 in the existing resume-setup traversal, BEFORE the new certificate recovery screen was reached. It is not a passed recovery UI test. Its downloaded artifact matched SHA-256 5671f1f7f18f62a3c7882634757e74d612486c368e891b9ffa978bfda10cb5f6. The actual log and failure-unreachable-renewal-control screenshot were inspected: on the SE-sized display, Continue setup was below the usable content area behind the tab bar. The fixed alternating full-speed swipes could overshoot it in both directions.

The bounded helper now follows the observed target row's geometry relative to navigation/tab bars and uses slow semantic Form swipes. The original attempt bound, exact target, hittability requirement, all navigation/consent/relaunch assertions and signed-out recovery checks remain. No coordinate taps or simulated account state. Fresh actual UI execution is required.

## Executed local checks

- Linux Swift core Debug: 207 passed (core unchanged).
- Linux Swift core Release: 207 passed on a completed rerun. The initial compilation hit the local command timeout and is not counted.
- Python integration checks: 134 passed with exact pinned SideSign sources supplied; no skips. Includes actual compiled diagnostic/error policy, URL validation, no-argument-evaluation tests and hash/reapplication contracts.
- Full transformed Authentication.swift and the changed UI test passed Swift frontend syntax parsing. This is not native typecheck or UI execution.
- Fresh native Debug/Release and full actual-app UI for this checkpoint are pending, not covered by old green runs.

## Resume next

1. Inspect fresh native and whole-app jobs for this commit. The last accepted navigation baseline is 00e5e10; dd0b09c's added recovery-screen acceptance remains outstanding.
2. Finish the two Anisette source findings in UPSTREAM_AUDIT.md: library digest mismatch/cache/transfer/extraction and coherent checked identifier/adi.pb persistence. Authentication changes here do not fix those boundaries.
3. Complete other native logging and pairing/maintenance callback lifetimes, aggregate resource reservations and abandoned staging cleanup.
4. Finish remaining first-signing/self-update, supported-configuration UI, branding and dependency/distribution checks before consolidated physical acceptance.

No real signing/profile install, physical pairing, locked-screen unattended renewal or expiry crossing was tested. Prior evidence remains in Git history and STATUS-00e5e10.md.
