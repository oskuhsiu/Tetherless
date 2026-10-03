# Current checkpoint — native certificate recovery controls

Updated 2026-10-03. Latest product implementation: **dd0b09c729cf4d45972cd60fc95ffde52b5bc755**. A later documentation checkpoint does not change it. Development only on develop; main is unpromoted. No device handoff or credentials requested.

## Saved foundation

062cd57ca17cf53a93f68f9e78c8b462d8a451fe introduced read-only request lookup and explicit owner/UUID/phase-bound save, submission and discard. Its macOS core CI passed (run 37106200138). Local Linux Debug/Release each passed 207 tests; the unchanged baseline Python suite passed 122. No real Apple responses were used.

The preceding 00e5e10 baseline has successful core 37088160550, native Debug/Release 37088160572 and full-app/UI/diagnostic-retention 37088160526 checks. Previous App Group, catalog crash and diagnostic-copy failures are historical, not current diagnoses.

## This increment

Dedicated Certificate request recovery screen is connected to Auto Renewal. No-account controls are disabled; local reload/discard are non-networking. Check uses the restricted core lookup path, not issue(allowNew:false). The portal checks exact request identity before fetching session headers, owns the common mutation lease and verifies the current account/Team. Shared owner-scoped Keychain construction is reused by both normal issuance and recovery.

Save and submit have explicit confirmations capturing the original request/type/action. Possibly submitted requests cannot be resent or erased. Recovery caches and reads back the request-specific signer without selecting it as active, revoking other certificates, reinstalling anything or changing renewal consent. Leaving the screen cancels its task and rejects late UI updates; accepted material remains subject to the issuance coordinator's preserve-before-cancel rule.

See CERTIFICATE_RECOVERY.md. The no-account actual-app UI flow has been extended; it uses no fake credentials, portal success fixtures or private swizzling. It requires the real recovery screen and all four disabled mutation/check controls, then checks consent again after returning.

## Verification for dd0b09c

| Check | Observed result |
| --- | --- |
| Local Linux core Debug / Release | 207 tests passed each; core unchanged from 062cd57 |
| Local Python integration checks | 127 passed |
| macOS core Debug / Release | Both test steps and complete job passed, run 37106719353; no exact count inferred |
| Native iOS Debug / Release | Both compiled, linked, packaged and uploaded, run 37106719347 |
| Whole-app Simulator compile / signature | Passed in run 37106719330 |
| Complete existing UI plus new recovery screen | Still in progress at the latest inspection; not yet accepted |

The core tests use the production recovery coordinator and real durable journal files with a scripted portal. They prove byte-preserving checks and explicit action guards under those test conditions, not live Apple visibility or physical Keychain protection.

Portal and SideSign transforms also executed locally on exact retained 1ef23cf inputs (expected blobs `3db4f94ddd0f0f112591c9b998d1ac12f6f3c3f5` and `6127e16f8a265471e01ed8d03d6ba4a496caddb0`). Native compile success is separate from these local syntax/contract checks.

## Independently checked saved source and native artifact

The current CI source archive (artifact 11267978170) matched outer SHA-256 `ca8bd92526f5b059256f8c921ad8894cbaa1459344634ba4eedfba206e6a0420`, inner TAR `be628c2590f6a318848ea2606d464505094b241f1a99d932c1d0bacb8517551a` and its recorded dd0b09c commit. All code/config matched the tested local files; a wording-only difference in CERTIFICATE_RECOVERY.md was synchronized. The archive contains 133 files.

The current native Debug artifact (11267354036) matched outer SHA-256 `dbcb612333e16d97dc016260f76918fd9ad53cf3ca635f3238e1890ef9c2e8d9`. Its actual IPA digest `ece7579a660aee9330f7211092d00d433b3953d24b2701f4d4de6f3da1a4a50d` matches the manifest. Debug product identity is `org.tetherless.Tetherless.XYZ0123456`, version 0.1.0/build 0100. Forty copied core/native Swift files and the two transformed portal/SideSign files were compared byte-for-byte against the tested sources. No .p12/.p8/.key/.mobileprovision resource filenames were found; this is not an exhaustive secret scan. The unsigned IPA still requires user signing.

## Resume next

1. Complete the recovery-screen UI result from run **37106719330** at dd0b09c. Existing setup/resume/cold-launch assertions remain; a new signed-out recovery screen must expose no enabled request action. Inspect its actual screenshot and failure hierarchy if needed.
2. Address the concrete pre-handoff blockers now recorded in UPSTREAM_AUDIT.md: raw authentication logs/error payloads; Anisette library hash mismatch/cache/transfer handling; and unchecked identifier/adi.pb persistence. These were checked against the current prepared Debug artifact, not dismissed as hypothetical or solved by account/signing storage. Then finish pairing callback lifetimes, aggregate resource limits and abandoned staging cleanup.
3. Finish remaining first-sign/self-update, supported-configuration coverage, branding and dependency/distribution checks before consolidated device acceptance.

Older artifact evidence: STATUS-00e5e10.md. Tests/builds do not establish physical installation, Apple sign-in, locked-screen renewal or real expiry crossing. No unfinished workspace is required to recover the saved core checkpoint.
