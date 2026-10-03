# Current checkpoint — native certificate recovery controls

Updated 2026-10-03. Development only on develop; main is unpromoted. No device handoff or credentials requested.

## Saved foundation

062cd57ca17cf53a93f68f9e78c8b462d8a451fe introduced read-only request lookup and explicit owner/UUID/phase-bound save, submission and discard. Its macOS core CI passed (run 37106200138). Local Linux Debug/Release each passed 207 tests; the unchanged baseline Python suite passed 122. No real Apple responses were used.

The preceding 00e5e10 baseline has successful core 37088160550, native Debug/Release 37088160572 and full-app/UI/diagnostic-retention 37088160526 checks. Previous App Group, catalog crash and diagnostic-copy failures are historical, not current diagnoses.

## This increment

Dedicated Certificate request recovery screen is connected to Auto Renewal. No-account controls are disabled; local reload/discard are non-networking. Check uses the restricted core lookup path, not issue(allowNew:false). The portal checks exact request identity before fetching session headers, owns the common mutation lease and verifies the current account/Team. Shared owner-scoped Keychain construction is reused by both normal issuance and recovery.

Save and submit have explicit confirmations capturing the original request/type/action. Possibly submitted requests cannot be resent or erased. Recovery caches and reads back the request-specific signer without selecting it as active, revoking other certificates, reinstalling anything or changing renewal consent. Leaving the screen cancels its task and rejects late UI updates; accepted material remains subject to the issuance coordinator's preserve-before-cancel rule.

See CERTIFICATE_RECOVERY.md. The no-account actual-app UI flow has been extended; it uses no fake credentials, portal success fixtures or private swizzling. It requires the real recovery screen and all four disabled mutation/check controls, then checks consent again after returning.

## Verification at commit time

- Core code is unchanged from 062cd57: completed local Linux Debug and Release each passed 207 tests.
- Python integration checks: 127 passed, including five new recovery wiring/confirmation/isolation checks.
- New native and UI Swift sources passed frontend syntax parsing, not native typechecking.
- Portal and SideSign transforms executed on exact retained 1ef23cf inputs with expected blob hashes 3db4f94ddd0f0f112591c9b998d1ac12f6f3c3f5 and 6127e16f8a265471e01ed8d03d6ba4a496caddb0. No source drift was bypassed.
- Fresh native and UI execution are required for this increment. Prior green results do not validate the new controls.

## Resume next

1. Inspect the new native and complete-app/UI CI results. Fix actual compiler/UI failures without weakening assertions or resetting credentials.
2. Finish Anisette/pairing callback and logging lifecycle review, aggregate input/resource limits and abandoned staging cleanup.
3. Finish remaining first-sign/self-update, supported-configuration coverage, branding and dependency/distribution checks before consolidated device acceptance.

Older artifact evidence: STATUS-00e5e10.md. Tests/builds do not establish physical installation, Apple sign-in, locked-screen renewal or real expiry crossing. No unfinished workspace is required to recover the saved core checkpoint.
