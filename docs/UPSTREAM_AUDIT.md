# Pinned source and security audit

Initial source review dated 2026-10-02; remaining-gate reconciliation updated 2026-10-03 against the prepared `dd0b09c` source. This is a targeted engineering review, not a full independent security certification. Findings refer to the fixed source below, not every version of the upstream product.

## Pinned sources

| Component | Revision | Scope |
| --- | --- | --- |
| SideStore/SideStore | `0dd743f75afc358b0ba4a002feb5f19474492371` | Native app baseline; AGPL source |
| SideStore/SideSign | `6b68651697f99791ef85404b7aea1891a26a285d` | Authentication/signing library gitlink |
| SideStore/minimuxer | `12be70dc2627307a16bfd2dc7a009080d5bec909` | Device communication gitlink |

Use recorded gitlinks and Package.resolved. `prepare.py` and `harden.py` require reviewed file hashes and reject changed anchors. Dependency/binary rights, checksums and redistribution obligations still require a complete release inventory; a successful build does not resolve them.

## Findings addressed in this derivative

| Pinned source finding | Tetherless response |
| --- | --- |
| Main profile chosen with `profiles.values.first!` | Select exact target Bundle ID and validate before mutation |
| Inherited refresh intent strands a continuation on initialization failure and can request foreground | Replace the refresh implementation with the native renewal runtime; retain required declaration compatibility |
| Inherited background persistence callbacks do not constitute durable verified renewal | New journal and profile-readback transaction; explicit storage failures |
| Main signing pipeline and portal mutations can overlap with new automatic work | Shared OS lease, serial per-app pipeline and child-lifetime retention |
| Global console capture, verbose logs, audio/location keepalive and boot JIT probes | Remove automatic activation/central keepalive routes; new diagnostics export has a field whitelist |
| Keychain uses synchronized storage | Tetherless-specific service, non-synchronizing, after-first-unlock/this-device-only policy |
| `EmbedSigningCertOperation` converts a signable certificate to P12 and writes it into target apps | Replace with public DER only; remove known inherited P12 metadata resource |
| `ResignAppOperation` additionally embeds the active certificate's P12 into the manager | Use the operation's selected certificate and public DER only |
| `CertificateManager.getSignableCertificate` may recover private keys from the running bundle | Remove embedded-private-key fallback; rely on authorized Keychain state |
| Shared self-recognition and base Bundle ID remain SideStore even after a display-name change | Assign distinct Tetherless base ID and matching constants; preserve internal project names |
| Deep links provide certificate/pairing export callbacks and raw URL logging | Reject those URL-triggered export hosts, restrict accepted schemes and remove router URL logs |
| Info.plist allows arbitrary transport loads | Require normal transport security except explicitly local-network traffic |

The P12 observation is especially important: the fixed certificate manager's ordinary password selection uses the certificate serial, which is public metadata. The code therefore cannot be treated as keeping a target app away from the signing private key merely because a P12 is encrypted. This is a source-level trust-boundary finding, not evidence of an observed compromise. Both identified bundle-writing paths are removed in Tetherless.

Explicit user-requested certificate export is distinct from automatically embedding a key into another installed app. This review does not claim every legacy UI export path is removed or that all possible logging/secret paths have passed an exhaustive audit.

## Evidence and remaining gates

SideSign `ProvisioningProfile.swift` extracts XML from CMS bytes. Successful parsing is not cryptographic signature/trust validation. The native adapter checks device/profile binding and reads actual device-store bytes; it does not claim independent OS launch attestation.

The manager certificate comes from its running Mach-O. Other app identity uses successful-install metadata. External replacement requires enrollment. Dumped profile data and prepared batches are bounded, device-local, protected and excluded from support exports.

The protected pairing-store replacement, bounded parser, verified migration and reset tombstone are implemented; the old Documents-first storage description is historical. Real hardware protection and remaining pairing-callback/maintenance lifetimes still need their separate acceptance. See INPUT_SAFETY.md and the current STATUS.md.

The full standalone maintenance/settings/pairing/authentication mutation inventory is not yet complete. In particular, old maintenance may reset account state and must not race a headless renewal. Do not infer total mutual exclusion from the main pipeline's lock.

The streaming IPA validation/extraction boundary, path/link checks and per-transfer HTTP limits are implemented and tested. Aggregate disk/memory reservations, crash-abandoned staging cleanup, complete update-path coverage, binary supply-chain and redistribution inventory remain open. Runtime input checks, packaging checks and physical acceptance remain separate evidence levels.

## Original source findings and current follow-up — 2026-10-03

Current follow-up: `3fbed9f` removes the identified SideSign authentication logs/raw-error paths and has passed native Debug/Release plus the complete signed-out setup/recovery UI. `b7b597f` adds mandatory package checksums, bounded ODA metadata/archive downloads and synchronized admission; its current verification is recorded in STATUS.md. Existing-cache trust/promotion, independent executable provenance and coherent Anisette identity persistence remain open. These fixes do not amount to an exhaustive native logging or binary supply-chain audit. See AUTHENTICATION_PRIVACY.md and ANISETTE_PACKAGE_INPUT.md.

The observations below describe the pre-fix reviewed input, not a claim that all of those exact paths remain in the newer prepared output.

These are code findings in the exact prepared `dd0b09c` Debug artifact (outer SHA-256 `dbcb612333e16d97dc016260f76918fd9ad53cf3ca635f3238e1890ef9c2e8d9`). They are **not fixed by certificate recovery**, not evidence of a compromise, and not exercised with live credentials. Keep them as pre-handoff blockers instead of treating an unsigned build or safe support export as a complete logging/supply-chain audit.

1. **Authentication log/error payloads.** `Dependencies/SideSign/Sources/DeveloperPortal/Authentication.swift` still interpolates DSID and an authentication token into `verboseLog` after parsing, and constructs some errors from raw decrypted response dictionaries. `Sources/Logging.swift` emits every `debugLog` regardless of the verbose setting. Disabling automatic verbose activation and full-console capture reduces exposure but does not remove these source paths. Remove sensitive interpolation and raw authentication payload propagation, preserve only structured safe error categories, and verify both logging modes with synthetic secret-shaped fixtures.
2. **Downloaded Anisette libraries.** `Dependencies/SideSign/Sources/Anisette/AnisetteDataManager.swift` currently logs a SHA-256 mismatch and proceeds with extraction. Its remote metadata/body paths use unbounded `URLSession.shared.data`, existing cache reuse checks file presence, and a concurrent caller waits for `isCaching` to clear without receiving the first caller's error. Require fail-closed integrity and reviewed provenance, bounded transfer/extraction, validation before cache promotion and explicit failure propagation. A digest supplied by the same mutable metadata is not independent provenance.
3. **Anisette identity persistence.** `SideStore/Core/Anisette/AnisetteConfigManager.swift` exposes nonthrowing legacy Keychain setters for the identifier and `adi.pb`; `OnDeviceAnisetteManager.swift` reports a newly provisioned blob saved without checked readback. Make the identifier/blob coherent and error-reporting without deleting the last usable state. Account, pairing and signing journals do not automatically secure this separate state.

Reviewed prepared-input Git blob identities for the next narrow transformations:

| File | Blob SHA |
| --- | --- |
| `Dependencies/SideSign/Sources/DeveloperPortal/Authentication.swift` | `f60d4c67dcca0f093dc3ac949fdd0492ef7431a2` |
| `Dependencies/SideSign/Sources/Logging.swift` | `5a90099f4c017db759c5446946d13f348cc90f2a` |
| `Dependencies/SideSign/Sources/Anisette/AnisetteDataManager.swift` | `8c6448563e030dd991daefec52c42fcf3dbc3a0d` |
| `SideStore/Core/Anisette/OnDeviceAnisetteManager.swift` | `03cc650766360eb6512f2a4543c2f288b2399d11` |
| `SideStore/Core/Anisette/AnisetteConfigManager.swift` | `161f608c43ec40b30f390a7e245c143796e5e2a0` |

No copying of actual passwords, tokens, private keys, pairing records or raw account traffic is required for these fixes or their non-device tests.

## References

- https://github.com/SideStore/SideStore/tree/0dd743f75afc358b0ba4a002feb5f19474492371
- https://github.com/SideStore/SideSign/tree/6b68651697f99791ef85404b7aea1891a26a285d
- https://github.com/SideStore/minimuxer/tree/12be70dc2627307a16bfd2dc7a009080d5bec909
- https://github.com/jkcoxson/idevice — device protocol reference.
- https://github.com/mahee96/AnisetteKit — on-device Anisette; ADI binaries require separate rights/source review.
- https://github.com/jkcoxson/LocalDevVPN — existing helper, not an original Tetherless component; inspect custom terms before reuse.
- https://github.com/StikDebug/StikPair — pairing UX/protocol reference; inspect non-commercial terms before copying code.
- https://github.com/nab138/iloader — candidate one-time bootstrap tool, not a daily dependency.
- https://developer.apple.com/forums/thread/685525 — background execution limits.
