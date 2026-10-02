# Pinned integration audit

Source review on 2026-10-02, not a complete independent security audit.

## Pins

- SideStore/SideStore: `0dd743f75afc358b0ba4a002feb5f19474492371` (AGPL-3.0).
- Its SideSign gitlink: `6b68651697f99791ef85404b7aea1891a26a285d` (GPL-3.0).
- Its minimuxer gitlink: `12be70dc2627307a16bfd2dc7a009080d5bec909` (AGPL-3.0).

Use recorded gitlinks and Package.resolved; no `submodule update --remote`. License and binary redistribution review is still required before release. Keep notices and full license files in the upstream tree. Do not relabel a third-party helper as an original Tetherless component.

## Confirmed source findings

- `RefreshAppOperation.swift` used `profiles.values.first!` for the main app. `FetchProvisioningProfilesOperation.swift` keys that entry by `context.targetBundleIdentifier`. Preparation fixes the selector and validates existence before device mutation.
- `RefreshAllAppsIntent.swift` swallowed the initializer error with `try?` and returned without resuming its continuation when no operation was created. Preparation preserves the error. Its separate foreground-timeout behavior remains a blocker for using it as the new unattended route.
- `BackgroundRefreshAppsOperation.swift` wraps callback/detached execution and logs some persistence failures. Do not equate its success callback with durable, read-back-verified renewal. Its cancellation/running-app behavior needs integration review.
- `AppBootManager.swift` and `MinimuxerWrapper.swift` include device identifiers in debug messages. Production diagnostic redaction requires an audit; do not claim logs are sanitized yet.
- SideSign's `ProvisioningProfile.swift` extracts XML from CMS data. Parsing metadata is NOT CMS signature/trust validation. The adapter must not set `validatedForInstalledBinary` merely because this parser returned an object.
- `AuthManager.getAuthenticatedSession` uses stored tokens and Anisette; `DeveloperPortalProxy` exposes separate fetch/create/revoke methods. The renewal adapter should use the narrow compatible-profile route and never silently enter certificate creation/revocation.
- minimuxer provides raw profile dumps through `.dumpProfiles(docsPath:mode:.raw)`. Build a bounded, private, cleaned-up readback adapter; don't upload raw dumps or pairing records as diagnostics.

## References

- https://github.com/SideStore/SideStore/tree/0dd743f75afc358b0ba4a002feb5f19474492371
- https://github.com/SideStore/SideSign/tree/6b68651697f99791ef85404b7aea1891a26a285d
- https://github.com/SideStore/minimuxer/tree/12be70dc2627307a16bfd2dc7a009080d5bec909
- https://github.com/jkcoxson/idevice — device protocol reference.
- https://github.com/mahee96/AnisetteKit — on-device Anisette; separately review ADI binary rights.
- https://github.com/jkcoxson/LocalDevVPN — existing helper; custom attribution/rebranding license, not plain MIT.
- https://github.com/StikDebug/StikPair — on-device pairing reference; non-commercial restrictions, not plain MIT.
- https://github.com/nab138/iloader — one-time bootstrap reference; no custom desktop GUI in the first scope.
- https://developer.apple.com/forums/thread/685525 — background execution limits.
- https://developer.apple.com/documentation/appintents/appintent — native intent entry point.
