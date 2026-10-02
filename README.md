# Tetherless

Mobile-first iOS sideloading with proactive profile renewal using the user's own Apple Account. Independently maintained from a pinned SideStore baseline; not an official SideStore release.

**Integrated development build, not a device-validated release.** The native renewal backend, no-foreground App Intent, background entry points and Auto Renewal screen are connected. Debug/Release native builds and tests are tracked in [implementation status](docs/STATUS.md). Passing compilation or a scripted test is not proof of Apple authorization or unattended execution on an iPhone.

## Development workflow

Work goes directly to `develop`, or through development PRs merged into `develop`. The owner authorized this workflow; `main` remains the stable/release branch and is not automatically promoted. PR #1 was merged into `develop`.

Finish implementation, integration and feasible non-device verification before requesting one consolidated device acceptance pass. Do not ask the owner to connect an iPhone at each development step. Do not request passwords, verification codes, keys, UDIDs or pairing records in chat or GitHub.

## Implemented

- Daily proactive renewal, with Debug-only two-hour eligibility; neither setting changes Apple's signed expiry or guarantees an OS wakeup.
- Local-only renewal authentication and profile transport, manager-first ordering, required-extension/identity checks and exact profile-store readback.
- Partial-batch recovery, write-ahead journaling, cross-process mutation exclusion, per-app fault isolation and persistent authentication/backoff gates.
- A replacement `Renew Managed Apps` App Intent without foreground continuation; supplementary iOS background processing/fetch.
- An Auto Renewal screen with setup instructions, consent, explicit repair, observed expiry/history, advance warnings and privacy-whitelisted diagnostics.
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
python3 Integration/prepare.py
```

Do not use `git submodule update --remote`. Preparation rejects changed source hashes, dirty dependencies and an existing generated output; inspect that directory before removing it for a fresh preparation. Do not edit `Vendor/SideStore` or `.generated` as the authoritative source of Tetherless changes.

The native CI builds the generated `AltStore.xcodeproj` / `SideStore` scheme in both configurations. Internal target names are retained to keep the derivative patch small; the product's bundle identity is separate. The simulator workflow executes the Swift core tests on an installed iOS Simulator runtime, not on a macOS host masquerading as iOS.

CI retains source revisions, build logs, prepared review sources and unsigned IPA manifests. **An unsigned IPA is input to an authorized signing/bootstrap process, not directly installable and not a stable release.** See [build and bootstrap notes](docs/BUILD_AND_BOOTSTRAP.md).

## Structure

| Path | Purpose |
| --- | --- |
| `Sources/TetherlessCore` | Policy, identity/evidence, journal, batch recovery, mutation lifetime and diagnostics |
| `Tests/TetherlessCoreTests` | Fault injection, real filesystem/process tests and output-boundary tests |
| `Integration/Native` | Actual SideSign/minimuxer adapter, runtime, intents, scheduling and UI |
| `Integration/prepare.py`, `harden.py` | Hash-locked, reviewable transformations of the pinned native app |
| `Vendor/SideStore` | Native upstream gitlink; dependencies retain their licenses |
| `docs/STATUS.md` | Verified evidence and remaining implementation gates |

## Security and licensing

Tetherless uses its own non-synchronizing Keychain namespace. Renewal never silently falls back to remote anisette, revokes a certificate, reinstalls the manager, enables fake audio/location keepalive or turns off another VPN. Diagnostic export excludes credentials and identifiers. These safeguards are not a completed independent security audit: inherited import, pairing storage, maintenance and explicit repair paths still have release gates in the status document.

Original Tetherless code is AGPL-3.0-only. Preserve upstream copyrights and licenses; the full upstream license is retained in `Vendor/SideStore/LICENSE` after initialization. See [pinned source audit](docs/UPSTREAM_AUDIT.md) before distributing a product. Do not submit automated contributions/issues to upstream maintainers.
