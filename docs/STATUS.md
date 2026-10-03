# Current checkpoint — coherent Anisette identity foundation

Updated 2026-10-03. Development remains on develop, no promotion to main and no device/credential request.

## Confirmed previous results

The b7b597f full-app run 37120735783 is now completed successfully, including whole-app setup/recovery navigation and diagnostic retention. Its earlier pending state is historical. Existing native Debug/Release and core results are recorded in the previous 733c9e2 checkpoint. These are not live Apple authentication or physical renewal tests.

## This saved increment

AnisetteIdentityStore groups the identifier and provisioning blob in one versioned, generation-bound record. Invalid, incomplete or unavailable legacy records fail closed instead of generating a new identifier against an old blob. Canonical UUID and historical 16-byte Base64 UUID migration preserve identity. Fresh material must be saved and read back before headers are returned. Readback/write errors do not report success or delete the old pair. Cancellation after the provider returns preserves the returned material first; a changed generation cannot receive a stale response.

Migration cleans split fields only after a verified coherent save, and retries cleanup through the authoritative new record without reading partially deleted legacy fields. Explicit resets produce a new generation or secret-free tombstone; late results and old split fields cannot resurrect erased material. Corrupt/future envelopes remain errors. Blob limit is 32 KiB, envelope limit 64 KiB; syntactic validation does not establish ADI/Apple validity.

Completed local Linux Debug and Release suites: 231 tests each, including 17 new production-store tests against real private files and injected provider/storage failures. Initial test macro compilation errors were corrected before these results. Two initial Release commands timed out during compilation and are not counted as successful; the completed incremental run passed. A new macOS-only real Keychain test uses a unique temporary service and synthetic blob; its CI result is not yet known.

## Exact next step

Connect this saved core to both on-device and remote providers under the common mutation lease plus process reentrancy guard; migrate checked Keychain legacy fields and update explicit sign-out/reset routes. The core is NOT yet the active native identity path in this checkpoint. Run integration contracts and fresh unsigned/native UI CI before claiming native wiring.

Remaining independent blockers: Anisette library existing-cache validation/promotion/provenance, other native logging and pairing/maintenance lifetimes, aggregate resources/staging cleanup, first-sign/self-update and supported-configuration coverage, branding/distribution. No physical signing, pairing, locked-screen unattended renewal or expiry crossing has been verified.
