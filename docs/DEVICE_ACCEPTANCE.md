# Consolidated device acceptance — only after implementation gates

This is the final handoff procedure, not a request to connect a device during ongoing development. Resolve the non-device gates in STATUS.md before presenting a candidate to the owner. No password, 2FA code, UDID, private key, raw profile or pairing record belongs in chat, issues or CI.

## Candidate preparation

Record the source commit, tested core/simulator/native CI runs, exact Xcode version and artifact integrity manifest. Confirm the actual bundle identifies as Tetherless, not SideStore; account/team signing may append an expected suffix. Confirm manager recognition and its callback scheme agree with that identity. The build is unsigned unless a separate authorized signing step actually succeeded.

Supply a small trusted test IPA and an extension variant. Test both the straightforward case and per-component expiry/partial-batch handling. Initial bootstrap should not overwrite an existing SideStore installation or silently revoke its certificate. Free-account capacity must be assessed separately from product-name collision.

Both the target-app and manager signing output must exclude the inherited signing-private-key resource. Do not confuse an application's unrelated client P12 asset with Tetherless's signing identity. Verify login/certificate initialization and explicit self-resigning with the new no-embedded-key policy.

## Fast acceptance: no seven-day development cycle

1. Complete authorized installation, login, local helper/VPN, pairing and required system confirmations. Account and pairing recovery routes remain user-controlled.
2. Enable local Anisette, opt in to unattended renewal, and establish one compatible manager/target identity. Save baseline profile UUIDs and effective expiry through safe local evidence.
3. Create a daily Shortcut automation containing **Renew Managed Apps**, not an **Open App** step. Permit the applicable immediate/locked execution settings. Notification permission is separate.
4. On the next day, allow the authorized automation to run while the phone is locked and the manager is not foregrounded. A Debug two-hour eligibility setting may shorten initial iterations, but cannot guarantee when iOS grants execution or when Apple extends a profile.
5. Compare live/read-back effective expiry with the baseline, including required extensions. An unchanged profile, no-op, partial batch, reminder, manual invocation or merely edited countdown is not a successful renewal.
6. Confirm no computer is involved in that renewal. A foreground check may be used afterward to retrieve diagnostics, but it is not counted as the unattended trigger. The recorded non-foreground indicator alone does not attest that the screen was locked or the trigger scheduled.

## Recovery and safety cases

| Scenario | Expected result |
| --- | --- |
| One target has invalid metadata or changed identity | Manager and other eligible apps can still renew; affected target is diagnosed |
| Session challenge or invalid pairing | Durable interaction gate; no repeated login attempts from every trigger |
| Temporary network/server failure | Bounded retry with backoff; force does not bypass retry limits |
| Partial extension batch or termination after apply | Next run reads back and applies only missing compatible profiles |
| Changed app/certificate after interruption | Old batch rejected; explicit validated re-enrollment, not silent reuse |
| Database/journal write failure | No verified-success claim; recovery state retained |
| Overlapping foreground install and headless refresh | Shared device mutation exclusion; no lock-inode deletion |
| Budget expiration or OS cancellation | Completed renewals kept; pending work recoverable; no forced foreground UI |
| Reboot before first unlock, other VPN, low-power mode | Accurate classified limitation, no silent bypass or VPN shutdown |
| Expiry warnings | Own stable notifications only; no duplicate warning storm or fake refresh |
| Diagnostic export | Timestamps, trigger types, counts and known error codes only |
| Explicit manager version/identity update | Data/journal preserved where supported; no assumption code keeps running after self-reinstall |

## Longer observation

After the next-day mechanism works, observe recurring renewals across the original expiry. Keep the scheduling observation separate from manual/debug fault testing. Never advance the device clock to impersonate an Apple-issued authorization period. Unattended observations should not be repeatedly disturbed by opening the manager merely to inspect its status.

Record the precise device/OS, app/profile conditions and every intervention. A multi-day pass is evidence for those conditions, not a universal reliability guarantee. Remaining unsupported conditions belong in the user-facing support matrix.
