# Native integration checkpoint

Updated 2026-10-02. The live runtime is wired into the generated app. This document supersedes earlier checkpoints describing an unconnected standalone core. It is not a device-validation or release claim.

## Normal execution

`RefreshAllAppsIntent`, `BGProcessing` and legacy background fetch call the same `NativeRenewalRuntime`. Manual checks use that runtime with a separate trigger classification. The runtime constructs the native backend, journal and renewal engine; permission to perform unattended work defaults to off until explicit setup.

The engine takes the same cross-process lease used by the patched foreground signing pipeline. After taking the lease, it loads durable gates/journal state, then requests a live snapshot. Global authentication/pairing faults persist a gate before another trigger can contact Apple. A per-app descriptor/profile fault does not prevent unrelated apps, especially the manager, from renewing.

The native snapshot establishes the local pairing/VPN path, constructs a local-anisette Apple session, fetches the team certificate/App ID inventory, and reads actual installed profile bytes. The manager's certificate is read from its running Mach-O. Other apps use successful-install metadata recorded by the upstream pipeline. Required components, exact entitlement templates and the matching signing certificate bound each usable expiry.

## Profile-only transaction

A durable pending record is saved before mutation. Compatible new profile bytes are obtained through SideSign, parsed and bound to the selected app/device/team/certificate, then saved as a prepared batch. The profile batch executor reads back before installation, applies only missing parts and requires exact returned profile bytes. The adapter computes the minimum required-component/certificate expiry and commits Core Data before reporting readback evidence. An unchanged expiry is not a successful renewal.

Interrupted batches are bound to an identity digest covering the app version/build, device binding, signing certificate and component entitlements. Recovery must not apply an old batch to a changed identity. Explicitly re-enrolling a successfully reinstalled app validates a new live snapshot before retiring obsolete recovery metadata; it does not install an app or revoke certificates.

## Scheduling and evidence UI

Daily and two-hour Debug policies express eligibility, not a timer. The backend's 22-second budget is checked cooperatively between operations; it is not a promise that an uncooperative native/network call is forcibly interrupted in 22 seconds. Expiration handlers request cancellation and leave recoverable work.

The Auto Renewal screen provides account/pairing and app-library navigation, Shortcut setup instructions, opt-in, manual checks, repair preflight, re-enrollment, last observed expiries, recent runs and a sanitized diagnostic export. Expiry warnings are pre-scheduled at 48/24 hours and expiry, using stable identifiers to avoid repeated notifications. Notifications do not perform renewal.

A non-foreground run is explicitly different from an attested locked-screen scheduled run. Manual/foreground execution cannot earn the background-renewal status. The app cannot prove whether a Shortcut was scheduled or tapped merely from the App Intent invocation.

## Signing and product boundary

Preparation and hardening retain original project/module names but change the product base identity and self-recognition constants to `org.tetherless.Tetherless`. Debug signing may append its Team suffix. The general URL scheme is `tetherless`; the existing backup callback remains unique to the actual product identifier.

The target-app signing operation and manager re-sign operation write only the chosen public certificate DER, removing the known inherited `ALTCertificate.p12` metadata resource. Unrelated application-owned P12 assets are not indiscriminately deleted. The embedded-private-key recovery fallback is disabled; the manager's authorized private signing material belongs in its own Keychain. URL-triggered certificate/pairing exports are disabled. Explicit foreground export functionality is a separate user-controlled path, not an unattended export.

## Boundaries still requiring validation

- SideSign metadata parsing is not an independent CMS trust/chain validation. Exact profile-store readback proves returned bytes, not kernel launch acceptance or all future revocation state.
- Simulator installation methods throw; upstream simulator no-ops cannot become `.deviceReadback` evidence. Simulator tests use scripted transports and are not a physical installation.
- Non-manager identities depend on recorded successful-install metadata. External replacements and unsupported shared/wildcard profiles require explicit repair/enrollment.
- The primary pipeline, portal mutations and ordinary boot use shared locking. Remaining standalone maintenance/settings/pairing mutations need an exhaustive ownership/lifetime audit.
- First-install credential initialization and explicit manager identity rotation must be checked after disabling embedded-key import. A software update feed is not the daily profile-renewal mechanism and is not implemented by pointing at a GitHub release page.
- See STATUS.md for remaining input-security, storage, distribution and UI-test gates. Do not request the owner's device to bypass these implementation tasks.
