# Implementation and evidence status

Updated 2026-10-02. **Integrated development build; not a stable release or a request for physical-device testing.**

## Repository state

PR #1 was merged into `develop` as `7a7c9e0b986a54e6824216e15060494e542fa883`. Subsequent development is committed directly to `develop` under the owner's authorization. `main` has not been promoted.

Major implementation checkpoints:

- `e95d4171684a3620b62e537d9bb05bc2a353de84`: per-app fault isolation, durable preflight gates, identity-bound recovery, evidence/history UI, alerts and unsigned packaging.
- `0d12ec6c6b4a5a75d8a2443aabee012863fc0c0a`: real iOS Simulator core-test workflow.
- `1dd34256d1b168668ddb2494223e7f4400f90d11`: remove embedded signing private keys, isolate product identity and disable URL-triggered secret exports.
- `3919a405b691283a8eb1c841893a24d0d93b761b`: move bounded directory enumeration out of the async context to address the native adapter's Swift concurrency warning.

## Implemented and wired

The native adapter is no longer a placeholder. It creates local-anisette Apple sessions, discovers app/certificate/profile state, fetches compatible profiles, installs only missing batch components and reads back actual profile-store bytes. Durable journal and Core Data commits distinguish verified results from ambiguous or failed updates. An unchanged expiry never becomes successful renewal.

Ordinary work is manager-first and proactive daily, with Debug-only accelerated eligibility. Invalid metadata or a changed signing identity in one target is isolated from unrelated apps. Shared authentication/pairing failures gate future attempts before contacting Apple again. Interrupted plans remain bound to their original app identity. Explicit repair and re-enrollment do not silently revoke certificates or reinstall apps.

The no-foreground App Intent, supplementary BGProcessing and legacy background fetch call the same runtime. Primary foreground pipeline/portal operations share a real OS mutation lease, including admitted-child lifetimes. Central fake audio/location keepalive and automatic full-console capture are disabled.

The Auto Renewal screen includes account/pairing and app-library navigation, consent and Shortcut instructions, manual check, recovery preflight, observed expiry, recent runs, warnings and a whitelist-only diagnostic export. Foreground/manual execution cannot be recorded as an observed non-foreground manager renewal. A non-foreground result still does not attest a locked screen or a scheduled invocation.

The product base ID is `org.tetherless.Tetherless`. Both reviewed signing paths now embed public certificate DER only, not the manager's signing P12. The inherited embedded-key recovery fallback and URL-triggered certificate/pairing exports are disabled. Credentials use an independent, non-synchronizing Keychain namespace.

## Verified evidence

The test suite uses scripted backend/transport outcomes for Apple/device protocol behavior; it does not contact Apple. Filesystem, bounded persistence, cross-process lock and signing-resource boundary tests use real temporary files; the host cross-process test actually spawns another process.

| Verification | Observed result | Revision / evidence |
| --- | --- | --- |
| Local Linux Swift Debug | 82 tests passed | Core at `1dd3425`, Swift 6.2.1 |
| Local Linux Swift Release | 82 tests passed | Same core |
| macOS CI Swift Debug | 82 tests passed | `1dd3425`, run 36978518983 |
| macOS CI Swift Release | 82 tests passed | Same run |
| iOS Simulator core execution | 81 tests passed; `TEST SUCCEEDED` | `1dd3425`, run 36978518903 |
| Python transformation/packaging tests | 29 tests passed locally | Security increment |
| Actual pinned-source transformation | Passed, including all hardening hashes | Native preparation, not just small synthetic fixtures |
| Native iOS Debug compilation/link | Passed | `3919a4`, native run 36979130985 |
| Native iOS Release compilation/link and packaging | Passed; artifact uploaded and inspected | Native run 36979130985 |

The simulator excludes the host-only process-spawning test, explaining 81 rather than 82. Its recorded destination was iPhone SE (3rd generation), iOS 26.2; the CI reported Xcode 16.4/Swift 6.1.2. These are observations from the runner, not a blanket supported-device matrix. The native target retains inherited warnings; no warning-free or strict-Swift-6 certification is claimed for the entire upstream app.

Evidence links:

- Core: https://github.com/oskuhsiu/Tetherless/actions/runs/36978518983
- Simulator: https://github.com/oskuhsiu/Tetherless/actions/runs/36978518903
- Native security build: https://github.com/oskuhsiu/Tetherless/actions/runs/36978518949
- Native concurrency fix: https://github.com/oskuhsiu/Tetherless/actions/runs/36979130985

### Artifacts inspected

The `3919a4` Debug artifact was downloaded and inspected, not merely inferred from a green job. The archive hash matched its manifest:

`d53af4fac7513b73c1d1058b2e3fb41b769263fd0d56aed8b80df4d02756a030`

Its actual Info.plist identifies `org.tetherless.Tetherless.XYZ0123456`, display name Tetherless, version 0.1.0, build 0100 and general URL scheme `tetherless`. Its transport configuration allows local networking without a blanket arbitrary-load exception. No `.p12`, `.p8`, `.key` or `.mobileprovision` resources were present in that unsigned app archive. The prepared source artifact confirmed both public-only signing paths and removal of embedded-key fallback.

The inspected latest Debug log contains `BUILD SUCCEEDED` and no compiler warnings originating in `TetherlessCore` or `TetherlessNative`. Inherited upstream warnings remain; this is not a warning-free app claim.

The same implementation's Release artifact was also downloaded: its manifest hash is `e6c3c2ec0fbde833ec4d84449bbd558097dcf193af58a7644e6309b33ea2326e`, actual Bundle ID is `org.tetherless.Tetherless`, and version/build are 0.1.0/0100. The hash matched, the Release log contains `BUILD SUCCEEDED`, and the unsigned archive contained no `.p12`, `.p8`, `.key` or `.mobileprovision` resources.

The manifest explicitly states `requiresUserSigning: true`, `deviceValidated: false` and `unattendedRenewalValidated: false`. An unsigned package is not directly installable or approved for general use. It remains a development artifact, not a request to test on an iPhone.

## Remaining implementation gates before device handoff

| Gate | Required work / evidence |
| --- | --- |
| Pairing storage and import | Migrate inherited Documents-based pairing storage to protected, bounded, backup-excluded storage; verify bootstrap compatibility and all import/reset paths |
| Complete mutation/secret audit | Cover remaining standalone maintenance, advanced settings, pairing and auth repair; no account reset or competing mutation during renewal; audit silent Keychain write failures and log destinations |
| Runtime untrusted IPA handling | Adversarial tests for extraction, traversal, symlinks, expansion/entry limits and unsupported entitlements; packaging checks are not runtime import validation |
| Bootstrap and explicit manager updates | Validate first-login certificate initialization without embedded-key import, user-approved certificate-capacity handling, identity rotation and self-update/data recovery; do not confuse a release-page URL with an implemented update feed |
| Whole-app UI and support matrix | Exercise actual onboarding/recovery screens and accessibility/layout in supported simulator configurations; core tests are not UI tests; classify supported/unsupported profile and connection modes |
| Supply chain and distribution | Complete binary/dependency inventory, provenance/rights review, original branding assets and release notices before presenting a distributable candidate |

These are implementation tasks, not reasons to request the owner's iPhone now. Keep development moving on non-device work. First physical acceptance should be a consolidated candidate, with next-day proactive refresh and a separate longer observation.

## Not performed

No user Apple Account login, real signing key, actual pairing record, physical iPhone, real profile installation, locked-screen unattended run or real-time expiry crossing was used. Simulator core tests do not prove native Apple/device behavior. Profile XML parsing and returned bytes are not independent CMS/OS-launch attestation. The complete product has not passed release acceptance.
