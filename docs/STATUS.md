# Implementation and evidence status

Updated 2026-10-02. **Integrated development build; not a release candidate or a request for physical-device testing.**

## Repository state

Development continues directly on `develop` with the owner's authorization. PR #1 was already merged as `7a7c9e0b986a54e6824216e15060494e542fa883`; `main` remains unpromoted. Latest implementation for this checkpoint: **`1ef23cfd5297343e3d9a1e5415e6946d8ffe0501`**. A later documentation-only commit does not change the implementation.

This increment adds:

- `f5310216a68ef029c62e67fc7433f0d30e1e1fe0`: explicitly confirmed manager replacement, durable exact-identity receipt/reconciliation, recovery controls, cancelled stale suspension timers, and content-derived cache fingerprints.
- `1ef23cfd5297343e3d9a1e5415e6946d8ffe0501`: coherent active/cached signing envelopes, independent public-certificate storage, checked old-format migration and advanced actions, returned-key persistence, and current-Team provisioning with explicit certificate-capacity decisions.

Earlier token-only account state, generation-bound failed-login cleanup, protected pairing, bounded HTTPS downloads and production archive extraction remain connected. Their implementation and earlier evidence are preserved in Git history.

## Implemented and wired

Daily proactive manager-first profile renewal, required-component/identity checks, readback, write-ahead recovery, per-app isolation, shared authentication/backoff gates, no-foreground App Intent and supplementary background entry points remain connected to the native app. These are implemented code paths, not evidence of a live Apple login or unattended physical-device use.

Account state is one non-synchronizing Keychain envelope. New login records retain a token, not the Apple password; staged records cannot enable renewal. Sign-out and failed-login cleanup cannot resurrect stale credentials or sign out a later account generation. This does not guarantee that Apple will never require another login/2FA challenge. See AUTHENTICATION.md.

Protected pairing storage/migration/reset markers and production streaming IPA extraction remain integrated. HTTPS downloads are bounded by actual received bytes; nonempty `ALTDependencies` are refused rather than injected after archive validation. Exact limits and unsupported inputs remain documented in INPUT_SAFETY.md. URL-triggered secret export, embedded manager signing P12 and fake audio/location keepalive remain disabled.

### Manager replacement

Normal daily profile refresh does not replace the manager executable. Complete manager installation now requires foreground confirmation and the same bundle/Team/container. A bounded checked receipt is saved before invoking the installer. Recovery compares the actually running version/build plus every main/extension executable and embedded-profile SHA-256. Only matching, saved and independently read-back manager database metadata can complete the receipt. Corruption, unchanged/wrong bundles and failed saves retain recovery rather than erasing it.

The old bundle-path-change heuristic and arbitrary serialized Core Data graph restoration are removed. Pending replacement receipts temporarily stop profile transport; explicit abandonment only accepts the original running identity. A delayed Home-screen task is cancelled when its install operation exits. The Auto Renewal screen includes recovery controls. Exact identity matching is not independent CMS trust or kernel attestation. See MANAGER_UPDATES.md.

Cache fingerprints now hash streamed file content, not only filenames and lengths. Same-length byte changes and hidden payload changes are covered by production Darwin tests. File/link/type/count/depth/byte limits apply. The defined signature/profile/OS metadata exclusions are documented, not a blanket hidden-file exclusion.

### Signing material and first-certificate provisioning

Active P12 bytes, their password and expected serial are one checked Keychain item. Per-serial signing cache envelopes and public-only DER items use separate namespaces: observing a public certificate can no longer overwrite its private key. Explicit private-key removal is separate from saving public information. Tombstones prevent old split fields from reactivating; checked migration commits and reads back the coherent identity before deleting legacy material.

Native sign-out, startup public-certificate observation, certificate imports and advanced activation/removal propagate persistence errors rather than reporting unconditional success. New signers are round-trip parsed before persistence; synthetic persistence tests do not independently validate P12 cryptography or key-pair trust.

Foreground provisioning first checks storage and actual current-Team portal matches. It attempts creation without first revoking others. Only an actual certificate-capacity response opens the existing explicit certificate-selection UI. The proxy stores and reads back a successfully returned new key before extra caller work. This does **not** cover a crash/lost response before SideSign returns: durable pre-submission CSR/key persistence and uncertain-response recovery remain open. See CERTIFICATE_STORAGE.md.

## Executed verification

| Check | Observed result | Scope / revision |
| --- | --- | --- |
| Local Linux core Debug / Release | 150 passed each | `1ef23cf`, Swift 6.2.1 |
| Python preparation/packaging/evidence tests | 69 passed locally | `1ef23cf` |
| Actual manager and certificate transformations | 4 manager and 8 certificate input hashes matched and transformations passed | Applied to actual pinned/prepared native source, not only synthetic anchors |
| macOS core Debug / Release | 157 passed each | `1ef23cf`, run 37009100908; includes two actual-system-Keychain tests and four content-hash tests |
| Core iOS Simulator | 154 actual passing test records; 1 explicitly skipped hardware-protection test | `1ef23cf`, run 37009100832; downloaded log inspected |
| Native iOS Debug | Compiled, linked, packaged and uploaded successfully | `1ef23cf`, run 37009100819 |
| Native iOS Release | Compiled, linked, packaged and uploaded successfully; actual artifact inspected | `1ef23cf`, run 37009100819 |
| Whole native App simulator | Passed build, install, launch, process-alive and screenshot checks; artifact inspected | `1ef23cf`, run 37009100813; not full UI-flow coverage |
| Earlier manager-change native Debug / Release | Both passed | `f531021`, run 37006637704; not substituted for current certificate changes |
| Earlier complete native App simulator smoke | Passed including install, launch, process-alive and screenshot | `318faae` run 36998496066 and `f531021` run 37006637747 |
| Production archive package | 17 Debug / 17 Release and 17 iOS Simulator passed | Unchanged archive sources, prior run 36988598288 |

The macOS count includes Darwin backup exclusion, two isolated actual-system-Keychain tests and four Darwin content-hash tests absent on Linux. The Simulator excludes host process spawning and the macOS Keychain tests; it records one explicitly disabled physical Data Protection test. Its summary reports 155; 154 actual passing records and one skip were checked, including three passing records prefixed by zero-width console characters. The skip is not successful hardware verification.

Observed macOS core toolchain: macOS 15.7.9 arm64, Xcode 16.4 / Swift 6.1.2. These are CI observations, not a guaranteed supported-device matrix. A test-only unused-result warning, one unnecessary-await warning in the manager recovery controls, and inherited warnings remain. No warning-free whole-app claim is made. Live TLS/CDN, Apple login and physical Data Protection are not tested by these runs.

Latest evidence:

- Core and actual system Keychain: https://github.com/oskuhsiu/Tetherless/actions/runs/37009100908
- Core iOS Simulator: https://github.com/oskuhsiu/Tetherless/actions/runs/37009100832
- Native Debug/Release: https://github.com/oskuhsiu/Tetherless/actions/runs/37009100819
- Whole-app Simulator: https://github.com/oskuhsiu/Tetherless/actions/runs/37009100813
- Previous manager-change whole-app smoke: https://github.com/oskuhsiu/Tetherless/actions/runs/37006637747
- Unchanged production archive package: https://github.com/oskuhsiu/Tetherless/actions/runs/36988598288

### Whole-app evidence and earlier failures

Earlier runs `36995550010` and `36996650009` retain their failed status: the former timed out capturing a screenshot, the latter timed out at the launch command. They were not relabelled as passes. The later screen-readiness/phase-evidence workflow completed successfully at `318faae` and at `f531021`. The `318faae` artifact was downloaded and checked: actual installation/launch/process/screenshot evidence is true, physical device/unattended renewal/full UI-flow fields are false. The viewed screen is inherited onboarding with a notification-permission dialog, not proof that login, pairing or repair navigation has been exercised.

The current `1ef23cf` whole-app workflow also completed successfully. Its downloaded artifact matches the Actions SHA-256 `12cec40041060d447bda700a1ba6c7248c71fae216e05dfc0d750f58a43ea263`. The evidence JSON records installation, launch, a five-second alive check, screenshot and smoke pass; physical-device, unattended-renewal and full-UI-flow flags remain false. The actual image was viewed: inherited onboarding and the Tetherless notification dialog are rendered. The existing upstream logo/text are still present and require the tracked branding work; they are not declared finished Tetherless design. A smoke pass is not a complete UI or hardware acceptance suite.

### Exact-source verification

The exact tested `1ef23cf` source artifact was independently downloaded. Its outer ZIP SHA-256 matched the Actions digest (`12cb8b60d66627761b7014662b325bbf4cea7f8ab003c97268b24216efc58b09`); its recorded commit and inner tar digest also matched. All 83 code/config files compared against the local implementation matched, including the manually submitted native overrides and transformation scripts. Documentation changes were deliberately kept separate.

The `1ef23cf` Simulator artifact SHA-256 matched `484f272ead77e0af2f3629dc2c77262d885813a4bf571aa10fb49521e77a2ccd` and its actual test records were inspected. The current Release artifact was downloaded and inspected, not inferred from an older green job. Its outer ZIP matches the Actions digest `1a2400f6dc75eb8084b39f62a456556ae3d773ce37ffb6a867c2d708dcc0f7f5`. Its actual IPA SHA-256 matches the manifest:

`44c3293d7903e17c16d60ec3d9fd3f77bdd052cd3a3d5ccc184795c1aab4a521`

The actual Release Info.plist reports `org.tetherless.Tetherless`, display name Tetherless, version 0.1.0/build 0100, local-network ATS allowance without a blanket arbitrary-load exception. There are no `.p12`, `.p8`, `.key` or `.mobileprovision` resources in this unsigned IPA. The build log records `BUILD SUCCEEDED`. All 31 retained core/native Swift files and all 12 manager/certificate transformed files byte-match the checked local implementation. This proves source integration and packaging, not physical installation or cryptographic trust. No live accounts, private signing key or pairing record were used or included in CI. Unsigned builds require the owner's authorized signing/bootstrap process; they are not already installable or device-validated distributions.

## Remaining gates before a consolidated device handoff

| Gate | Remaining implementation / verification |
| --- | --- |
| Certificate submission recovery | Persist CSR/private-key material before a remote create operation; reconcile ambiguous response/crash without duplicate creation or silent revocation |
| Remaining secret and mutation audit | Anisette storage errors/advanced settings, remaining log destinations, pairing callback cancellation and retained lease lifetime, certificate-cache cleanup lifecycle |
| Bootstrap and manager updates | End-to-end first-login/signing-repair/self-update integration, certificate-rotation decisions, delayed-install/interrupted-container recovery; same-Team replacement is not cross-Team migration |
| Untrusted-input resources | Aggregate disk/memory reservation, crash-abandoned staging cleanup, live download/redirect integration and unsupported entitlement/Mach-O/signature parser review |
| Whole-app UI / supported configurations | Actual setup, login, repair, import and manager-recovery navigation/accessibility/layout tests across supported configurations; passing launch smoke is not flow coverage |
| Supply chain / distribution | Dependency and binary inventory, provenance/rights review, original branding and notices |

No live Apple login, real signing/profile installation, physical pairing, locked-screen unattended run or expiry crossing was performed. Profile parsing/readback is not independent CMS trust or kernel launch attestation. The implementation gates remain development work; physical checks are one consolidated acceptance after those gates, not repeated requests for the owner's phone.
