# Implementation and evidence status

Updated 2026-10-02. **Integrated development build; not a release candidate or a request for physical-device testing.**

## Repository state

Development continues directly on `develop` with the owner's authorization. PR #1 was already merged as `7a7c9e0b986a54e6824216e15060494e542fa883`; `main` remains unpromoted. Latest implementation for this checkpoint: **`318faaefb116a60dee86c5cddccfd9df4c865719`**. Later documentation-only commits do not change that implementation.

This increment adds:

- `4c2475885c42b8f5a2a33f895f83c9fb88227724`: bounded ephemeral HTTPS IPA downloads; no post-extraction remote dependency injection; compatible-version download uses the selected app URL.
- `71bfb18ba2f0b27c62ac5af7c9815283791d9abd`: coherent system Keychain envelope, staged/ready/signed-out account phases, checked sign-out, native login/renewal integration and disabled legacy account archives.
- `43006f73d8758c868804a67525e96916da0ec0fb`: whole-app simulator build/install/launch/screenshot workflow, separate from core package tests.
- `38177ef64ad7b1915bfc606942734abb33489008`: portal mutation ownership before session/team reads, generation/team checks, noninteractive LAContext Keychain queries and retained smoke diagnostics.
- `4b48e47de26ebe5a687f39172637e2930a3c16bf`: new sessions retain token but not Apple password; earlier coherent records can remove a retained password without losing token/team; simulator GUI readiness checked separately.
- `318faaefb116a60dee86c5cddccfd9df4c865719`: generation-bound failed-login cleanup and password cleanup attempted on every native launch, independent of old maintenance counters.

## Implemented and wired

Daily proactive manager-first profile renewal, required-component/identity checks, readback, write-ahead recovery, per-app isolation, shared authentication/backoff gates, no-foreground App Intent and supplementary background entry points remain connected to the native app. Auto Renewal shows consent, setup/repair navigation, observed expiry/history, warnings and whitelist-only diagnostics. These are implemented code paths, not evidence of a live Apple login or unattended device launch.

Protected pairing storage/migration/reset markers and the production streaming archive extractor remain integrated. Prior pairing/archive evidence is retained in Git history and linked below. The product base identity is `org.tetherless.Tetherless`; reviewed signing paths embed public DER rather than the manager's signing P12. URL-triggered secret export and fake audio/location keepalive are disabled.

### Account lifecycle

The native path reads one device-local, non-synchronizing Keychain record, not four independent credential fields. Login stages a coherent generation, saves the selected team, then activates it. Session use checks that same team/generation; portal mutations obtain the shared OS mutation lease before reading them. An incomplete stage cannot enable renewal. Storage/readback errors are not converted into successful login or a generic expired-session condition.

New stages discard the entered Apple password and retain email/DSID/token only. A checked migration removes any password retained by an earlier development envelope while preserving its generation/team/token. It is attempted on every startup, not only first launch. This does not guarantee that Apple will never expire the token or require another 2FA challenge.

Sign-out commits a secret-free tombstone before legacy cleanup. Failure to write the tombstone is reported; later cleanup failure cannot resurrect the account. Failed-login cleanup may discard only its own staged generation and cannot sign out a newer or ready account, nor remove certificates. Legacy account archive/JSON imports and exports are disabled rather than left as a bypass. Existing application-data backup code is a separate boundary. See AUTHENTICATION.md.

### Download lifecycle

HTTPS-only GET and every redirect are checked; redirects rebuild the request without inherited credentials/cookies. A full 200 response is required. Declared length and actual bytes are independently bounded to 1 GiB, and truncation, partial bodies and transport compression are rejected. The ephemeral session has no shared cookie, credential or cache store. Cancellation/error removes only the transfer's partial file, never unrelated caller data. The returned file must be complete.

Nonempty `ALTDependencies` in an IPA are rejected: no resource can be fetched and injected after archive validation. This intentionally requires a self-contained IPA. The native operation now uses the selected compatible app version's URL. Tests use URLProtocol-scripted responses with actual URLSession callbacks and file IO; they are not internet/TLS/CDN tests. Aggregate disk/memory and abandoned staging cleanup remain separate gates. See INPUT_SAFETY.md.

## Executed verification

| Check | Observed result | Scope / revision |
| --- | --- | --- |
| Local Linux core Debug / Release | 131 passed each | Current implementation, Swift 6.2.1 |
| Python preparation/packaging/evidence tests | 56 passed locally | Current implementation |
| Actual native auth transformations | 11 reviewed input hashes matched and transformations passed | Current implementation; not only synthetic anchors |
| macOS core Debug / Release | 133 passed each, including the actual synthetic system Keychain test | `318faae`, run 36998496062 |
| Core iOS Simulator | 131 actual passing test records; 1 explicitly skipped hardware-protection test | `318faae`, run 36998496073 |
| Native iOS Debug / Release | Both compiled, linked, packaged and uploaded successfully | `318faae`, run 36998496012; final Release artifact inspected |
| Production archive package | 17 Debug / 17 Release and 17 iOS Simulator passed | Unchanged archive sources, prior run 36988598288 |
| Whole native App simulator | No complete passing smoke yet at this checkpoint | Latest run 36998496066 is still in progress; not a full UI test suite |

The macOS count includes Darwin backup-exclusion and a real synthetic system Keychain test absent on Linux. The Simulator excludes the host process-spawn and macOS Keychain tests, includes Darwin backup exclusion and records one explicitly disabled Data Protection test. Its summary reports 132; inspection of actual records found 131 passes and one skip. The skip is not successful hardware verification.

Observed macOS core toolchain: macOS 15.7.9 arm64, Xcode 16.4 / Swift 6.1.2. These are CI observations, not a guaranteed supported-device matrix. A test-only unused-result warning and inherited upstream warnings remain. Live TLS/CDN behavior, Apple login and physical Data Protection have not been tested.

Latest evidence:

- Core and real synthetic Keychain: https://github.com/oskuhsiu/Tetherless/actions/runs/36998496062
- Core iOS Simulator: https://github.com/oskuhsiu/Tetherless/actions/runs/36998496073
- Native Debug/Release: https://github.com/oskuhsiu/Tetherless/actions/runs/36998496012
- Whole-app Simulator: https://github.com/oskuhsiu/Tetherless/actions/runs/36998496066
- Unchanged production archive package: https://github.com/oskuhsiu/Tetherless/actions/runs/36988598288

### Whole-app evidence and failures

Run `36995550010` (`43006f7`) compiled and installed the entire native app, obtained a process ID, and verified it remained alive after five seconds. Its screenshot command timed out after 30 seconds and produced a zero-byte PNG. The workflow failed; it is not a complete smoke pass.

Run `36996650009` (`38177ef`) compiled and installed, but the launch command timed out after 60 seconds before returning a process ID. It also failed. The second failure must not be misreported as another screenshot failure. No root cause is declared solely from these timeouts.

The updated smoke workflow explicitly initializes Simulator.app and validates a Home-screen capture before the product build/install. It persists phase-specific command logs and false-by-default launch/screenshot evidence. It never uses `continue-on-error` to turn launch failure into acceptance and does not inject successful login/device fixtures. Latest run `36998496066` has passed simulator screen readiness and native source preparation and is still compiling the full app at this checkpoint. A complete launch/screenshot pass has not yet been observed.

### Inspected artifacts and exact-source verification

The latest `318faae` Release artifact was downloaded and checked, not inferred from a green job. Its outer ZIP SHA-256 matched the Actions digest. The actual IPA SHA-256 matches its manifest:

`06916a664a859461e6748adade7794b395e78f3c8e2344b67516bb0747f9b4c8`

Actual bundle ID `org.tetherless.Tetherless`, display name Tetherless, version 0.1.0/build 0100. The unsigned IPA contained no `.p12`, `.p8`, `.key` or `.mobileprovision` resources. The Release log contains `BUILD SUCCEEDED` and no compiler warnings attributed to TetherlessCore/TetherlessNative; inherited upstream warnings remain. Transport configuration permits local networking without a blanket arbitrary-load exception.

All 25 current core/native Swift files in the retained prepared source byte-match the checked local implementation. All 11 auth-transformed native files and the bounded native download route also byte-match, including token-only records, generation-bound failed-login cleanup, and startup migration. This proves source integration, not a live Apple login.

The exact tested `318faae` source artifact was independently downloaded and its commit, outer ZIP digest and inner tar digest checked. Comparing 80 files against the evolving local tree found only the intended uncommitted documentation differences; code, tests and workflows matched. No live credentials, signing key or pairing record were used in these tests or placed in CI artifacts. Unsigned manifests state `requiresUserSigning: true`, `deviceValidated: false` and `unattendedRenewalValidated: false`.

Earlier `71bfb18` Release inspection is retained in history; it is not substituted for these latest results.

## Remaining gates before a consolidated device handoff

| Gate | Remaining implementation / verification |
| --- | --- |
| Remaining secret and mutation audit | Certificate and Anisette storage errors/advanced actions; all log destinations; pairing callback cancellation and retained lease lifetime; not just account-envelope tests |
| Bootstrap and manager updates | First-login certificate initialization without embedded keys, explicit certificate-capacity handling, identity rotation/self-update and interrupted data recovery |
| Untrusted-input resources | Aggregate disk/memory reservation, crash-abandoned staging cleanup, live download/redirect integration and unsupported entitlement/Mach-O/signature parser review |
| Whole-app UI / supported configurations | Reliable full native launch evidence; actual setup, login, repair and import navigation/accessibility/layout tests; package tests are not UI flows |
| Supply chain / distribution | Dependency and binary inventory, provenance/rights review, original branding and notices |

No live Apple login, real signing/profile installation, physical pairing, locked-screen unattended run or expiry crossing was performed. Profile parsing/readback is not independent CMS trust or kernel launch attestation. These limitations are not a reason to request the owner's phone while implementation work remains.
