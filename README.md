# Tetherless

Mobile-first iOS sideloading with proactive profile renewal using the user's own Apple Account. Independently maintained from a pinned SideStore baseline; not an official SideStore release.

**Integrated development build, not a device-validated release.** The native renewal backend, no-foreground App Intent, background entry points and Auto Renewal screen are connected. Debug/Release native builds and tests are tracked in [implementation status](docs/STATUS.md). Passing compilation or a scripted test is not proof of Apple authorization or unattended execution on an iPhone.

## Web signing prototype

The [web frontend](WebBootstrap/README.md) signs a custom IPA locally in the browser with the pinned WASM runtime. Its optional [account service](Tools/WebBootstrapService/README.md) provides the login-first journey: read the selected Team's registered devices, explicitly choose an active record, then separately approve provisioning. It never silently registers a device. Profile-based new-device collection is a separate explicit route.

At source [`f4d208ce`](https://github.com/oskuhsiu/Tetherless/commit/f4d208ce8d991e84b5836c5c5d9bc1573f7d2bdc), [browser CI](https://github.com/oskuhsiu/Tetherless/actions/runs/37517431324) passed 32 Chromium cases, 91 UI tests and five harness tests. The browser cases include the owned UIKit test IPA at both supported mount paths, signed with synthetic test material. At [`cfafe763`](https://github.com/oskuhsiu/Tetherless/commit/cfafe7635b74ed509511796ccc7ecef0bbf557f3), [container CI](https://github.com/oskuhsiu/Tetherless/actions/runs/37518746038) passed 26 packaging, 29 Rust and 91 UI tests, plus an isolated production-container smoke test without Apple calls. Exact receipts and limits are in [web bootstrap evidence](docs/WEB_BOOTSTRAP.md).

There is no deployed public HTTPS service, GitHub Pages site or official unsigned Tetherless Release asset at this checkpoint. The official-asset configuration remains `null`; choosing a custom IPA is supported without one. The 150 MiB input cap is enforced, but the current unsigned Tetherless IPA has not been produced to prove it fits. Read the [bounded hosting contract](Tools/WebBootstrapService/deployment/README.md) before any separately approved test deployment. Real Apple login/2FA, Safari, iPhone installation and unattended renewal remain unverified. [All 16 original tasks remain open](docs/PLAN_PROGRESS.md).

## Development workflow

Work goes directly to `develop`, or through development PRs merged into `develop`. The owner authorized this workflow; `main` remains the stable/release branch and is not automatically promoted. PR #1 was merged into `develop`.

Finish implementation, integration and feasible non-device verification before requesting one consolidated device acceptance pass. Do not ask the owner to connect an iPhone at each development step. Do not request passwords, verification codes, keys, UDIDs or pairing records in chat or GitHub.

## Implemented

- Daily proactive renewal, with Debug-only two-hour eligibility; neither setting changes Apple's signed expiry or guarantees an OS wakeup.
- Local-only renewal authentication and profile transport, manager-first ordering, required-extension/identity checks and exact profile-store readback.
- Partial-batch recovery, write-ahead journaling, cross-process mutation exclusion, per-app fault isolation and persistent authentication/backoff gates.
- A replacement `Renew Managed Apps` App Intent without foreground continuation; supplementary iOS background processing/fetch.
- An Auto Renewal screen with setup instructions, consent, explicit repair, observed expiry/history, advance warnings and privacy-whitelisted diagnostics.
- Protected, bounded pairing storage with atomic replacement, conflict-safe legacy migration, durable full-reset markers and serialized wireless import.
- Bounded ephemeral HTTPS IPA downloads, independent declared/streamed byte limits, cancellation cleanup and no post-extraction remote dependency injection.
- Token-only coherent Keychain account records with staged/ready/signed-out phases, checked writes and sign-out, generation-bound failed-login cleanup and shared portal mutation ownership. The entered Apple password is not retained in new records.
- Checked, separate active/cached signing-identity envelopes and public-certificate observations, with explicit capacity decisions and returned-key persistence in first-certificate provisioning.
- Foreground manager replacement with exact expected identities, durable receipts, database readback and explicit recovery; normal profile renewal never initiates a replacement.
- Content-derived cache fingerprints rather than filenames and lengths alone.
- Shared streaming IPA extraction with ZIP structure/CRC/path/expansion limits and nested bundle metadata checks; real adversarial archive tests use the production extractor.
- Distinct `org.tetherless.Tetherless` product identity. Private signing keys are no longer embedded by the target-app or manager signing paths; only public certificate material crosses that boundary.

A failure requiring user interaction is not counted as unattended success. Manager version updates, identity rotation and first installation are separate from everyday profile renewal. A clean phone's fully computer-free first installation is not claimed to be solved.

## Test and build

The core requires Swift 6.0+ and Python 3 for its host cross-process test. Native compilation requires a compatible macOS/Xcode installation.

```sh
git switch develop
git submodule update --init --recursive
swift test
swift test -c release
python3 -m unittest discover -s Integration/tests -v
swift test --package-path Packages/TetherlessArchive --force-resolved-versions
swift test --package-path Packages/TetherlessArchive --force-resolved-versions -c release
python3 Integration/prepare.py
```

Do not use `git submodule update --remote`. Preparation rejects changed source hashes, dirty dependencies and an existing generated output; inspect that directory before removing it for a fresh preparation. Do not edit `Vendor/SideStore` or `.generated` as the authoritative source of Tetherless changes.

The native CI builds the generated `AltStore.xcodeproj` / `SideStore` scheme in both configurations. Internal target names are retained to keep the derivative patch small; the product's bundle identity is separate. The package simulator workflows execute core and production-archive tests on iOS Simulator. A separate whole-app workflow builds, installs, launches and captures the unmodified production first-run UI; its result is recorded separately and is not a full onboarding/repair test.

CI retains source revisions, build logs, prepared review sources and unsigned IPA manifests. **An unsigned IPA is input to an authorized signing/bootstrap process, not directly installable and not a stable release.** See [build and bootstrap notes](docs/BUILD_AND_BOOTSTRAP.md).

## Structure

| Path | Purpose |
| --- | --- |
| `Sources/TetherlessCore` | Policy, identity/evidence, journal, batch recovery, mutation lifetime and diagnostics |
| `Tests/TetherlessCoreTests` | Fault injection, real filesystem/process tests and output-boundary tests |
| `Integration/Native` | Actual SideSign/minimuxer adapter, runtime, intents, scheduling and UI |
| `Integration/Overrides` | Reviewed native replacements, including the protected pairing manager |
| `Integration/prepare.py` and its hash-locked hardening stages | Hash-locked transformations of the pinned native app |
| `Packages/TetherlessArchive` | Production streaming extractor and real ZIP adversarial tests |
| `Vendor/SideStore` | Native upstream gitlink; dependencies retain their licenses |
| `WebBootstrap` | Browser signer, progressive account/custom-IPA UI and synthetic browser tests |
| `Tools/WebBootstrapService` | Transient account/UDID adapter and bounded same-origin container packaging |
| `docs/WEB_BOOTSTRAP.md` | Web evidence, data recipients and remaining bootstrap gates |
| `docs/STATUS.md` | Verified evidence and remaining implementation gates |

## Security and licensing

Tetherless uses its own non-synchronizing Keychain namespace. Renewal never silently falls back to remote anisette, revokes a certificate, reinstalls the manager, enables fake audio/location keepalive or turns off another VPN. Diagnostic export excludes credentials and identifiers. [Account-state notes](docs/AUTHENTICATION.md), [signing-material storage](docs/CERTIFICATE_STORAGE.md) and [manager update recovery](docs/MANAGER_UPDATES.md) describe the separate lifecycles and verification boundaries. These safeguards are not a completed independent security audit: remaining authentication, maintenance, bootstrap, download-resource and lifecycle paths still have release gates in the status document. [Input-safety notes](docs/INPUT_SAFETY.md) distinguish implemented protections from unverified platform behavior. ZIP64/encrypted/link-bearing archives and unpacked .app imports are explicitly unsupported in v1; there is no unsafe fallback.

Original Tetherless code is AGPL-3.0-only. Preserve upstream copyrights and licenses; the full upstream license is retained in `Vendor/SideStore/LICENSE` after initialization. See [pinned source audit](docs/UPSTREAM_AUDIT.md) before distributing a product. Do not submit automated contributions/issues to upstream maintainers.
