# Current checkpoint — checked setup observations and Simulator verification

Development integration only. Latest implementation: **7dbaac4a3360e351ed65aca2cfc199f0a6ed73a1**. A later documentation-only commit does not change it. Progress remains approximately 80% toward complete implementation plus feasible non-device verification, not reliability. No physical-device handoff yet.

## Saved changes

`5217156` corrected CI entitlement inspection: verify the real host signature, request explicit codesign XML, and inspect simulated iOS identity in the actual linked Mach-O `__TEXT,__entitlements` section. No source-xcent fallback, signing repair or fabricated entitlement is used.

`7dbaac4` adds stage-specific setup observations. Missing, unreadable and not-yet-checked are different states. Account/signing/pairing reads run within the common mutation lease; the first error retains only an allowlisted stage/category, never arbitrary errors, paths, keys or tokens. Onboarding uses a checked pairing accessor rather than silently treating corruption as absence. Cancelled/superseded observations do not replace a current result or consent. Existing UI expectations are unchanged; failures additionally report the safe readiness detail.

The same commit removes a demonstrated CI boot race: Simulator.app and `bootstatus -b` both attempted boot, producing CoreSimulator 405, already Booted. CLI now owns boot, completion is monitored without a second boot request, then GUI and screen capture are required. No timeout increase or continue-on-error.

## Executed verification for 7dbaac4

| Check | Observed result |
| --- | --- |
| Local Linux Swift Debug / Release | 182 tests passed each |
| Local Python integration checks | 102 passed |
| macOS core | Passed, run 37031170064; no exact count inferred here |
| iOS Simulator core | 191 actual passing records and 1 explicit hardware-protection skip, run 37031170023; downloaded log inspected |
| Native iOS Debug / Release | Both compiled, linked, packaged and uploaded successfully, run 37031170188 |
| Whole native App Simulator | Boot/screen, compilation, actual signature/linked identity, installation and launch passed in run 37031170226 |
| Full setup/resume/reopen/consent UI flow | In progress at this checkpoint; NOT yet counted as passing |

The Simulator core summary says 192, including the skipped Data Protection test. The actual 191 pass records were counted separately. Local read-failure tests inject outcomes; they do not authenticate to Apple. Simulator signature metadata is not proof of runtime Keychain writes, device authorization or unattended renewal.

Exact runs:
- Core: https://github.com/oskuhsiu/Tetherless/actions/runs/37031170064
- Simulator core: https://github.com/oskuhsiu/Tetherless/actions/runs/37031170023
- Native Debug/Release: https://github.com/oskuhsiu/Tetherless/actions/runs/37031170188
- Real App and UI: https://github.com/oskuhsiu/Tetherless/actions/runs/37031170226

## Independently inspected artifacts

The exact Actions source archive was downloaded; outer SHA-256 `348297d465ffd5f0bcba7a1d9f7a4e787bc2a03870742ad2f200ea5b8e6c36cb`, inner TAR SHA-256 `de6983d9906eee9a9d3bbb547837809648507a7aefd1f41665684eb7d6404a11`, recorded commit and all 116 files were checked. Only the intentionally newer documentation differed locally; all code/config matched.

The Simulator test artifact matched `1f3f10d46b48b968afc4d179d90d344c9bfd4a9ec945fa971fbd44fcd255a287`.

The current Release artifact matched outer SHA-256 `2e19dd8ac7c8197e3650c5dd74d91800f75f4a877e4065b1857779f9f7d019e6`. Its actual IPA SHA-256 `78690a8523918ade11218935986511a531916f0b3779bf78413e42c6d2308c4c` matches its manifest. Bundle ID is org.tetherless.Tetherless, version 0.1.0/build 0100. No .p12/.p8/.key/.mobileprovision resources are present in the unsigned IPA. The prepared SetupReadiness, OnboardingView and PairingFileManager bytes match the tested sources. The manifest still requires user signing and reports device/unattended validation false.

## Failures remain historical failures

- `12fa693` run 37022756438 failed codesign-output parsing before installation/UI, not signature verification. Its log also established distinct host and simulated entitlement locations.
- `5217156` run 37029268767 failed boot before product execution with code 405. Its downloaded artifact matched `d54daf85d3e2d10b269c064679d96dd562ba1e63a958999974783adae34ff909`.
- `1a4831d` run 37019229377 genuinely failed review-page readiness before later cancellation. The earlier setup-read error is not declared fixed until the real flow passes or its native failed stage is resolved.

## Resume next

1. Inspect the complete UI result and screenshots for **37031170226** before changing code. It had entered the actual UI test at this checkpoint. If review fails, use its `setup/<stage>/<category>` detail; do not accept unreadable storage as normal absence or weaken assertions.
2. Finish remaining certificate uncertain-state recovery decisions, Anisette/pairing/log lifecycle, aggregate resource reservations and crash-abandoned staging cleanup.
3. Finish remaining first-signing/self-update integration, supported-configuration UI coverage, branding and dependency/distribution checks before consolidated physical acceptance.

All changes remain on develop. No real Apple credentials, signing/profile installation, physical pairing, locked-screen unattended renewal or expiry crossing have been tested. Earlier checkpoints remain in Git history.
