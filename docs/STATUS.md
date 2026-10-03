# Current checkpoint — authentication privacy and bounded ODA package input

Updated 2026-10-03. Development only on `develop`; `main` stays unpromoted. No phone or live credentials requested. This remains an integration build, not a release candidate. The previous rough 80% estimate concerns implementation plus feasible non-device verification, not reliability.

## Saved authentication change: 3fbed9f

`3fbed9f8d6d1cb2c463052abda9ea6a21ae711cb` removes 72 free-form SideSign authentication logging sites and raw/decrypted response copies in error/retry messages. The public authenticate boundary recreates errors without arbitrary response text/userInfo or token-bearing repair URLs; cancellation, typed decisions and numeric codes survive. Legacy SideSign log autoclosures never evaluate, including when diagnostics are enabled; only typed fixed events can print, without enabling AnisetteKit verbose logs. The real wire fields, SRP/server-proof and verification operations remain. See AUTHENTICATION_PRIVACY.md. Other native/dependency logging still requires review.

Local Linux core Debug/Release each passed 207 tests on completed runs; an initial Release command timeout is not counted. Python passed 134 checks with exact pinned inputs and no skips, including compiled real logging/error policies and upstream error enums using synthetic secrets. Native Debug/Release both compiled, linked, packaged and uploaded successfully in run **37119710500**. macOS core run **37119710497** passed. Full UI run **37119710499** is not yet accepted at this checkpoint.

The downloaded source artifact 11272806994 matched outer SHA-256 `05f4dcd38bccec6fb631007e43a00376b5928390f2c90f85b7f8a3d4916d1dbc`, recorded 3fbed9f commit and inner TAR SHA-256 `ebd6624330fa6568f24b5243b0519b8127403ee5af7683e201e87be51e46c82b`. All nine first-batch changed files were compared byte-for-byte with the local tested checkpoint. It contains 139 files. Native prepared output still needs its independent inspection; this archive is not an IPA.

## Current ODA increment

Hash-lock AnisetteDataManager input; require a valid SHA-256 and stop on mismatch **before library destination mutation or extraction**. Keep the existing Crypto digest computation. Reject overlapping download calls explicitly with a synchronized generation-bound lease instead of treating a previous caller's failure as success. Metadata and payload transfer use the existing bounded downloader with only its type namespace changed, private temporary files, ordinary TLS/HTTPS redirect policy, no shared cookies/credentials and cancellation cleanup. Base64 is bounded/strict, and the existing safe extractor gets explicit smaller ODA budgets. See ANISETTE_PACKAGE_INPUT.md for limits and still-open cache/provenance work.

Checks for this increment: Linux core Debug/Release each **214 passed**; Python **139 passed** with pinned inputs and no skips. Exact transformed source parses; the namespaced downloader and actual wrapper compile/run in a no-network invalid-URL test. Digest/Base64/admission tests execute real production code, while HTTP responses in the preexisting downloader suite are scripted. Native/UI for this newer increment require their own fresh run; the 3fbed9f native result does not validate it.

## Prior recovery UI failure, not a new startup diagnosis

Run **37106719330** at dd0b09c failed `TetherlessUITests.swift:78` in resume-setup traversal **before reaching the recovery screen**. Its artifact matched SHA-256 `5671f1f7f18f62a3c7882634757e74d612486c368e891b9ffa978bfda10cb5f6`. The actual failure screenshot showed Continue setup below the usable content behind the SE tab bar; fixed alternating swipes could overshoot. The first saved batch now guides slow semantic Form swipes by observed row geometry, preserving the original attempt bound, all hittability/navigation/consent/relaunch assertions, and signed-out recovery checks. No coordinate taps, fake account or disabled assertions. The last accepted full navigation baseline is 00e5e10; recovery-screen acceptance is still outstanding until the new run proves it.

## Resume next

1. Read current native and actual UI results, retaining exact implementation SHAs and failures. Confirm recovery-screen signed-out controls and retained consent. Do not re-diagnose resolved App Group/catalog traps absent new evidence.
2. Complete ODA existing-cache validation/promotion recovery and independently reviewed binary provenance. The new mandatory checksum only protects the download path and does not authenticate mutable metadata. Existing cache/local-library presence-only reads remain open. Finish coherent checked identifier/adi.pb persistence.
3. Finish remaining native logging, pairing/maintenance callback lifetimes, metadata structural and aggregate RAM/disk budgets, and crash-abandoned staging cleanup.
4. Complete remaining first-sign/self-update, supported-configuration UI, branding and dependency/distribution checks before consolidated physical acceptance.

No real Apple login/2FA, profile installation, physical pairing, locked-screen unattended renewal or expiry crossing has been tested. Earlier failed checks remain historical failures, not silently relabelled successes. Every coherent change is saved before moving to another boundary.
