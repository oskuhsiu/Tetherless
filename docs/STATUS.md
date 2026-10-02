# Implementation and evidence status

Updated 2026-10-02. **Development in progress; not a release or a request for device testing.**

## Verified implementation

The standalone Swift renewal core implements daily and accelerated policies, manager-first ordering, bounded retries, account-wide interaction stops, identity/expiry evidence checks, required-component profile selection, write-ahead journaling, recovery-before-retry, cancellation, actor reentrancy protection and a real cross-process file lock. The journal rejects corrupt/future-schema state and symlink reads.

Local Linux Swift 6.2.1: `swift test` and `swift test -c release` each passed 36 tests in five suites. Patch-shape Python tests passed five tests. Those patch fixtures are deliberately small; they are not a claim that the full upstream app was checked out locally.

macOS core CI for commit `e8b59facfb714b61de4f5e640adbf087f89644ce` passed Debug and Release, 36 tests in each configuration. Actual runner: macOS 15.7.9 arm64, Xcode 16.4, Swift 6.1.2. Evidence: https://github.com/oskuhsiu/Tetherless/actions/runs/36961980003

The later core run for integration commit `68e721a146e1d1e846e629cbc1e35d6130493b08` also completed successfully: https://github.com/oskuhsiu/Tetherless/actions/runs/36962942683

The scripted backend models outcomes; it never calls Apple and is not an implementation of the native adapter. File lock tests include a separate Python process; filesystem tests use real temporary files.

## Native preparation and build: passed

`Integration/prepare.py` verifies the exact upstream commit and reviewed Git blob hashes, rejects dirty/mismatched dependencies, creates a disposable native tree, includes the core in the synchronized app target, and applies two narrow source fixes:

1. Select the main profile by `context.targetBundleIdentifier`, not arbitrary dictionary order; validate its presence before installing profiles.
2. Preserve and resume an operation-initialization error instead of stranding a checked continuation.

The actual native workflow for commit `68e721a146e1d1e846e629cbc1e35d6130493b08` completed successfully. The final job steps and decoded logs confirm:

- Five Python patch tests passed.
- Real pinned source/dependency verification and source preparation passed.
- Package resolution passed with the checked-in lockfile requirement enabled.
- The unsigned **Debug iOS application** compiled and linked, including all four TetherlessCore source files and the patched native operations.
- The final log contains `** BUILD SUCCEEDED **`; the job exited with success.

Actual native toolchain: Xcode 16.4 (16F6), Swift 6.1.2, macOS 15.7.9 arm64.

Evidence: https://github.com/oskuhsiu/Tetherless/actions/runs/36962942671/job/110700389754

An earlier interim assessment reported a dependency-resolution blocker. The final successful job logs supersede that assessment: there is no outstanding dependency-resolution failure established by this run. This does not waive future dependency-change verification.

The native build warns that update signing is disabled for unsigned CI and that App Shortcut phrases may need regeneration after Tetherless branding. These remain packaging/branding items. Native Release and simulator execution have not been validated by this Debug build.

**Compilation is not runtime integration.** The new core is compiled into the native target, but the production adapter and new unattended entry point are not yet connected. The application must not be described as a completed unattended-renewal product.

## Remaining implementation gates — do not ask for a device to finish these

- Real native `RenewalBackend`: capture installed identity and effective profile/certificate expiry; fetch compatible authorization; install profiles; read back actual device state; reconcile interrupted and partially applied extension batches. No fabricated `.deviceReadback` evidence.
- New no-foreground App Intent, actual runtime construction, lock-screen consent and background scheduling. The inherited intent still contains foreground continuation and does NOT meet the unattended requirement.
- Serialize inherited foreground install/sign paths with the new engine, not just the new actor.
- Complete foreground login/2FA repair, certificate rotation and manager self-update as separate explicit flows; no silent certificate revocation.
- Onboarding, proactive alerts, evidence display, secret-storage/log audit, local Anisette default, safe IPA handling and recovery UI.
- Native Release build, simulator-compatible tests, dependency and packaging checks, then a single consolidated device handoff.

These are implementation tasks, not a request for the owner to provide a device. The draft integration must remain visibly incomplete until they are addressed.

## Not performed

No Apple login, personal credentials, signing keys, pairing records, physical iPhone, live profile installation, unattended lock-screen run, simulator execution or real-time expiry crossing has been used. An unsigned compilation is not an installable signed IPA. A green core CI or native build is not a completed mobile app.
