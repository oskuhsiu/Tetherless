# Pinned source and security audit

Source review dated 2026-10-02. This is a targeted engineering review, not a full independent security certification. Findings refer to the fixed source below, not every version of the upstream product.

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

The inherited `PairingFileManager` still uses Documents for pairing files and legacy import/migration behavior. A protected-storage migration and bounded import review remain required before handoff; the new profile-batch storage does not automatically secure this old path.

The full standalone maintenance/settings/pairing/authentication mutation inventory is not yet complete. In particular, old maintenance may reset account state and must not race a headless renewal. Do not infer total mutual exclusion from the main pipeline's lock.

The untrusted IPA extraction/import pipeline, archive expansion limits, symlink handling, all update paths, binary supply chain and legal redistribution inventory remain explicit release gates. Build packaging input checks are not a substitute for runtime IPA-import security.

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
