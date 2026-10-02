# Account state, Keychain and explicit recovery

Tetherless's native login and renewal paths now use one coherent authentication record instead of independently reading and writing four legacy Keychain fields. This document describes the implementation, not a live Apple authentication or locked-device acceptance result.

## Stored data

A dedicated service, `org.tetherless.session.<product base ID>`, stores one generic-password item with a version, generation ID, phase, credentials and selected team. It is separate from `org.tetherless.credentials.<product base ID>`, which still contains inherited certificate/Anisette material. It does not synchronize through iCloud. Access uses `AfterFirstUnlockThisDeviceOnly`; reads use a noninteractive LocalAuthentication context, not a UI prompt fallback.

New records retain email, DSID and the Apple-issued session token needed for renewal, **not the entered Apple password**. The optional password field remains decodable only to remove passwords saved by an earlier development build. Startup/maintenance rewrites such a record without its password while retaining its token, generation and team. Migration write/readback failures are thrown and are not reported as successful removal. The native startup path attempts this on every launch; it is not conditional on a first-launch or old maintenance flag. This is not a claim that Apple will never invalidate a token or request another 2FA challenge.

Writes update an existing item without deleting it first. New-item creation occurs only after an item-not-found result. Every envelope transition reads the item back and compares exact stored bytes. Missing, malformed, oversized and unsupported-version data do not fall back to old split credentials.

## Transitions

| Phase | Meaning | Usable for renewal |
| --- | --- | --- |
| Missing | No coherent record has been established | No |
| Staged | Apple login succeeded and the coherent record was saved, but team setup is unfinished | No |
| Ready | The selected team was saved in Core Data and the same staged generation was activated | Yes, subject to subsequent live authorization/device checks |
| Signed out | An authoritative secret-free tombstone was committed | No |

A process stopping between staging and activation cannot leave a half-written ready session. A late authentication attempt cannot activate another attempt's generation. The selected database team must match the record; a supplied old team cannot be used for a portal mutation with a new account.

Authentication, sign-out and reviewed portal mutations hold the common native mutation lease. Portal mutation ownership starts **before** session/team reads, not merely around the final API call. Dynamic team-profile download/generation is included. Native renewal uses the same coherent record and local-anisette policy.

Failed-login cleanup is generation-bound: after reacquiring the lease it can remove only that exact staged attempt, never a newer staged account or any ready session. It does not delete signing certificates.

Session getters recheck the generation after asynchronous setup. Ordinary UI boot/old maintenance counters never clear a newly established coherent account. A missing coherent record is initialized as signed out rather than importing legacy split credentials whose consistency cannot be established.

## Checked sign-out

The secret-free tombstone is written and verified first. Legacy credential cleanup and requested certificate/Anisette cleanup follow. A failure to write the tombstone is an error and is not shown as successful sign-out. A failure after the tombstone leaves the account unusable even if some legacy items remain; the UI reports the failure so explicit cleanup can be retried. There is no automatic fallback to those remnants.

This guarantee does not claim that every inherited certificate/Anisette setter is already audited. Their remaining write-error and mutation boundaries are tracked separately in STATUS.md.

## Unsupported legacy routes

Account archive import/export and debug raw-JSON account import/export are disabled. They must not restore split passwords/tokens, private keys or team state outside the validated login transaction. Existing app-data backup handling is separate and is not certified by these changes. Normal explicit login and 2FA are the supported account entry path.

## Verification

Core fault-injection tests cover missing/staged state, process reconstruction, late generation activation, readback mismatch, failed writes, failed activation, tombstone contents, failed sign-out, malformed/future records and invalid input. These storage fixtures are synthetic; they do not contact Apple.

A separate macOS-only test uses the real system Keychain with a random service name and synthetic data to exercise replacement, activation, tombstoning and exact-item removal. iOS Simulator core tests do not imply physical Data Protection or a real Apple login. Native full-app build/launch evidence and hardware acceptance are recorded separately.
