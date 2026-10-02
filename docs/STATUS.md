# Implementation and evidence status

Updated 2026-10-02. **Integrated development build; not a release candidate or a request for physical-device testing.**

## Repository state

PR #1 was merged into `develop` as `7a7c9e0b986a54e6824216e15060494e542fa883`. Subsequent development is committed directly to `develop` under the owner's authorization. `main` has not been promoted. The latest implementation covered by this checkpoint is **`76f88f5cf6eb6a506b01a4499cc46e28ca2a7c14`**. A later documentation-only commit does not change the tested implementation.

This increment:

- `1eea8fc95dd8d960635675812a63259591fdf6f5`: protected pairing storage, bounded import, migration and wireless-session ownership.
- `0258030071d772736d5d44188ea765cee6c337a5`: shared streaming archive extractor, actual ZIP integration tests and separated simulator/hardware protection checks.
- `ca9663b4f428dab3445671dd2686fffc42a93c73`: durable pairing reset, nested bundle metadata validation and forged-size deflate regression tests.
- `779932be04ce8dfa924b11cf6c3955da6396ae9b`: execute the production archive package on iOS Simulator.
- `8b8d468ad8589dcb60588bbcf835fa4a2d4c9e0f`: retain the reset marker until leftover pairing cleanup finishes.
- `76f88f5cf6eb6a506b01a4499cc46e28ca2a7c14`: migrate bootstrap pairing before the cold-boot missing-record decision.

## Implemented and wired

The existing native adapter creates local-anisette Apple sessions, discovers app/certificate/profile state, obtains compatible profiles, applies only missing batch components and reads back profile-store bytes. The journal and Core Data commits distinguish verified metadata from ambiguous/failed updates. Daily renewal is proactive, manager-first and has no foreground fallback. Per-app faults do not block unrelated apps; shared account/pairing failures persist a retry/interaction gate. App Intent, supplementary background work and manual checks use the same runtime. These are implemented call paths, not proof of live Apple/device success.

The Auto Renewal UI provides consent, setup/repair navigation, observed expiries, recent runs, notifications and whitelist-only diagnostics. Manual/foreground results cannot earn non-foreground renewal evidence. A non-foreground invocation alone still cannot prove lock state or scheduled triggering. Fake audio/location keepalive and automatic full-console capture are disabled.

Product identity is `org.tetherless.Tetherless`. Both reviewed signing paths use public certificate DER instead of embedding the manager's private P12. Embedded-key recovery and URL-triggered certificate/pairing exports are disabled. Credentials use an independent, non-synchronizing Keychain namespace.

### Pairing protection

The native manager now uses bounded protected Application Support storage rather than Documents. File replacement preserves the old record until the new file has been prepared; migration preserves conflicting legacy data and removes it only after verified destination readback. Imports reject invalid plist types, oversized/deep data, links and special files. Syntactic validation is not cryptographic pairing validation.

Full reset writes and flushes a persistent marker before deletion. Read/migration paths honor the marker after restart. A new verified import must clean reset leftovers before it can unblock pairing; cleanup failure preserves the marker. Ordinary replacements do not delete another protocol. Cold boot handles the migration/maintenance ordering race without requesting a duplicate import.

Reviewed import/reset/maintenance/protocol-switch paths share the renewal lease. Wireless pairing uses a protected random staging directory, fixed filename and callback-owned lease; it does not automatically export the resulting secret file or substitute a fake PIN. Callback cancellation and abandoned staging cleanup remain lifecycle-verification work.

### Runtime IPA boundary

The production `TetherlessArchive` sources are compiled both in the standalone integration tests and into the shared SideSign extractor. ZIPFoundation is fixed at `22787ffb59de99e5dc1fbfe80b19c97a904ad48d` (0.9.20). Full ZIP32 preflight precedes extraction; a partial iterator cannot become accepted success. Paths, collisions, file types, streamed byte counts and CRC are checked. Output is staged and existing destination data is not overwritten. Main and nested bundle metadata are validated before IPA publication.

V1 deliberately rejects ZIP64, encrypted/multidisk archives, links/special files and unpacked .app directory imports. Current extraction caps are 1 GiB archive, 4 GiB expanded, 512 MiB per file and 30,000 entries. Legitimate inputs outside those limits are unsupported, not silently sent to an unsafe fallback. HTTP download quotas and signature/entitlement approval are separate unfinished boundaries. See INPUT_SAFETY.md.

## Executed verification

No personal Apple Account, live signing key or real pairing record was used. Protocol outcomes in core tests are scripted. File/lock/reset tests use real files and archive integration tests use real ZIP bytes plus the actual decompressor.

| Verification | Observed result | Revision / evidence |
| --- | --- | --- |
| Local Linux Swift core Debug / Release | 104 passed in each configuration | Current core, Swift 6.2.1 |
| macOS CI Swift core Debug / Release | 105 passed in each configuration | `76f88f5`, run 36989824003 |
| iOS Simulator core execution | 104 actual passing test records; 1 explicitly skipped hardware-protection test | Same core at `8b8d468`, run 36989184036 |
| Local Linux production archive package Debug / Release | 17 passed in each configuration | Current production sources; disposable local manifest used the verified dependency source snapshot |
| macOS production archive package Debug / Release | 17 passed in each configuration | Same archive sources at `779932b`, run 36988598288 |
| iOS Simulator production archive package | 17 passed; `TEST SUCCEEDED` | Same run's separate archive-ios-tests job |
| Python transformation / packaging checks | 41 passed locally | `76f88f5` |
| Actual hash-pinned native source preparation | Passed | `76f88f5`, native run 36989824052 |
| Native iOS Debug compilation and packaging | Passed; actual artifact inspected | `76f88f5`, native run 36989824052 |
| Native iOS Release compilation and packaging | Passed; final job and artifact-upload steps succeeded | `76f88f5`, same native run |

The macOS count includes a Darwin backup-exclusion test absent on Linux. Simulator does not compile the host process-spawn test, but does record the separate disabled hardware-protection test. Swift Testing's summary says 105 in the simulator log; inspection found 104 actual pass records and one skip. We do not count the skipped test as successful verification.

The first pairing simulator run failed because reading `.protectionKey` returned nil. The hardware-specific assertion remains enabled for physical iOS and is explicitly disabled with a reason on Simulator. Backup exclusion, file permissions and IO are independently tested there. Setting a Data Protection attribute is not a claim that hardware encryption or locked-device access has been verified.

Observed CI toolchain: macOS 15.7.9 arm64, Xcode 16.4, Swift 6.1.2. The core simulator recorded iPhone SE (3rd generation), iOS 26.2. These are runner observations, not a guaranteed supported-device matrix. Upstream warnings and a test-only unused-result warning remain; no warning-free whole-app claim is made.

Evidence:

- Core: https://github.com/oskuhsiu/Tetherless/actions/runs/36989824003
- Core simulator: https://github.com/oskuhsiu/Tetherless/actions/runs/36989184036
- Archive host and iOS Simulator: https://github.com/oskuhsiu/Tetherless/actions/runs/36988598288
- Native integration: https://github.com/oskuhsiu/Tetherless/actions/runs/36989824052

### Artifact verification

Both final native jobs completed successfully for `76f88f5`. The earlier in-progress Release status is superseded by the completed job, including compilation, packaging and artifact upload. The detailed local archive inspection below was performed on Debug, not inferred for Release.

The latest `76f88f5` Debug artifact was downloaded, not merely inferred from job status. Its IPA SHA-256 matches the manifest:

`234c6d916a18ca828f591c5049752ff31e4827c122c8f1a94b290653f4059cf2`

Actual Info.plist: `org.tetherless.Tetherless.XYZ0123456`, display name Tetherless, version 0.1.0/build 0100. The unsigned archive contains no `.p12`, `.p8`, `.key` or `.mobileprovision` resources. The log contains `BUILD SUCCEEDED`. No warning from TetherlessCore/TetherlessNative was found in this inspected Debug build; inherited warnings remain.

The prepared-source artifact byte-matches the checked production pairing-store override, reset marker and all three archive source files. It also contains the cold-boot migration before the missing-pairing guard. This verifies integration content, not execution against a real device.

Unsigned archives require the user's authorized signing/bootstrap process. Their provenance flags do not claim `deviceValidated` or `unattendedRenewalValidated`. Core/archive package tests and unsigned app builds are not whole-app UI or physical sideloading tests.

## Remaining gates before one consolidated device handoff

| Gate | Remaining implementation / verification |
| --- | --- |
| Authentication and mutation audit | Remaining advanced settings/authentication/sign-out ownership; silent Keychain write failures; all relevant log destinations and callback cancellation/lifetime behavior |
| Bootstrap and manager updates | First-login initialization without embedded keys, explicit certificate-capacity decisions, manager identity rotation/update and data recovery; native wireless success/cancel/retry integration |
| Remaining untrusted-input budgets | Streaming HTTP quotas, aggregate disk/memory budget, crash-abandoned staging cleanup, unsupported-entitlement and Mach-O/signature parser review |
| Whole-app UI and support matrix | Actual onboarding/repair/import screens, accessibility and layout tests across supported simulator configurations; package tests are not full UI coverage |
| Supply chain and distribution | Binary/dependency inventory, provenance/rights review, original branding assets and release notices |

The protected-store and runtime extractor implementations are no longer placeholders. Their unresolved lifetime/resource checks remain visible rather than being declared complete because unit tests pass. Data Protection, live Apple authentication/profile installation and next-day locked-screen renewal belong to the final consolidated physical acceptance after the implementation gates, not recurring requests for the owner's phone.

No real-time expiry crossing or locked-screen unattended renewal was performed. Profile parsing/readback is not independent CMS trust or kernel launch attestation. The complete product has not passed release acceptance.
