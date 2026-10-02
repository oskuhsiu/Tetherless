# Live native integration — development checkpoint

This checkpoint connects the core to the pinned SideStore app. It is not a release and not a request for the owner's device. Native CI must be checked for this commit, independently of earlier green builds.

## Implemented paths

- Cold-start, local-only anisette session construction and authenticated on-device profile transport.
- Active portal certificate inventory check, exact Team/device/certificate/profile authorization matching, required extensions, conservative exact entitlement matching.
- Persisted prepared profile batches before the first device write; readback-before-write; missing-parts-only recovery; exact raw-byte readback and independently re-parsed effective expiry.
- Core Data persistence before returning evidence. Private profile batches are device-local, protected, excluded from backups and omitted from diagnostics.
- Runtime construction and replacement no-foreground App Intent, explicit unattended consent, daily policy and Debug-only two-hour eligibility.
- Supplementary BGProcessing registration and cancellation, plus an Auto Renewal screen with setup instructions, manual checks and limited repair preflight.
- Shared process lock on inherited pipeline operations and portal mutations; serial inherited per-app operations; database save errors no longer swallowed.
- Central audio/location keepalive service disabled; background modes limited to fetch/processing; no boot-time JIT probe; full-console capture disabled.

## Evidence boundaries

The manager's certificate is read from its running Mach-O. Other managed apps use the certificate and templates recorded by the inherited successful-install pipeline, NOT a live read of another app's sandbox. Externally replaced apps must be re-enrolled. Exact profile-store readback proves that the paired device service returned the expected bytes; it does not independently attest the kernel's launch policy, real lock state, an unrevoked certificate at all future times, or survival beyond the original expiry. Upstream profile parsing is not independent CMS chain validation.

Simulator paths explicitly throw rather than turning upstream no-op installation into success. The 12 new batch tests use a scripted transport and are labeled as such. File-lock and journal tests remain separate. Native Swift syntax parsing is not SDK type checking. Debug/Release native CI has been added and its actual result must be recorded in STATUS.md.

## Still required before consolidated device handoff

- Full native build verification of the new wiring and resolution of all compile failures.
- Audit non-pipeline maintenance, pairing, authentication and other settings mutation paths; the shared lock is not yet asserted to cover every upstream side effect.
- Complete explicit identity rotation and manager self-update flows, secret-storage/log and IPA-input security review, alerts, and richer onboarding/recovery.
- Fault tests for integration boundaries, available simulator execution, deterministic packaging and unsigned artifact provenance.
- Only after implementation gates: owner login and one consolidated device acceptance pass. Do not request credentials in chat or substitute a notification/manual refresh for unattended success.
