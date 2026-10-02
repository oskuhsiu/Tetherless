# Tetherless

Mobile-first iOS sideloading with proactive, unattended renewal using a personal Apple account.

**Development branch — not a finished or device-validated app.** The standalone renewal core is implemented and locally tested. Integration and release gates are tracked separately; passing mocks is not evidence of iOS execution or Apple authorization.

## Development contract

Finish implementation, integration and all available non-device checks before asking the owner to connect an iPhone. Collect device-dependent checks into one acceptance pass; do not stop unrelated work to request a device. Renewal is daily by default, not a job that waits until day seven. Accelerated testing never alters Apple's signed expiry dates. Never request account passwords, 2FA codes, pairing records, private keys or device identifiers in chat or GitHub.

## Test the core

Requires Swift 6.0+ and Python 3 (the cross-process lock test uses a separate Python process).

```sh
swift test
swift test -c release
```

The test backend is intentionally synthetic. Tests cover policy, identity/evidence selection, write-ahead recovery, bounded retry, cancellation, durable commit and real filesystem/process exclusion. They do not call Apple or validate background execution.

## Upstream baseline

`Vendor/SideStore` is pinned to `0dd743f75afc358b0ba4a002feb5f19474492371`. This is a candidate source baseline, not a security endorsement or stable-release claim. Initialize pinned dependencies with:

```sh
git submodule update --init --recursive
```

Do not use `--remote`. This repository is independently maintained and is not an official SideStore release. Upstream names, copyrights and licenses are retained. Do not submit automated issues or contributions to upstream maintainers.

## Architecture

- `Sources/TetherlessCore`: dependency-free policy, evidence, journal and coordinator.
- `Tests/TetherlessCoreTests`: executable fault-injection and filesystem tests.
- `Vendor/SideStore`: pinned native app, authentication, signing and device stack.
- `Integration`: reviewed native integration and deterministic source patches.
- `docs`: verification evidence, remaining gates and consolidated device acceptance.

A native adapter must provide real snapshot, refresh and readback implementations. It may report `appliedUnverified` when installation was acknowledged but device readback cannot establish effective expiry. It must never invent readback evidence, silently rotate certificates, revoke another tool's certificates or switch an unattended run to foreground.

## Licensing

Original Tetherless code is AGPL-3.0-only. The complete AGPL text is retained in `Vendor/SideStore/LICENSE` after submodule initialization and is available at https://www.gnu.org/licenses/agpl-3.0.txt. Dependencies retain their respective licenses; see the integration audit before distributing binaries.
