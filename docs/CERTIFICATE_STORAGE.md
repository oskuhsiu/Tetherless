# Signing material and first-certificate provisioning

## Storage

Active signing material is one device-local Keychain envelope containing the P12 bytes, its password and expected certificate serial. The cached signing identity uses a separate per-serial envelope. Both use the checked Security-framework storage adapter, non-synchronizing `AfterFirstUnlockThisDeviceOnly`, and byte-for-byte readback after writes.

Public DER observations are stored separately. Reading a certificate from the running binary or refreshing portal metadata cannot overwrite a cached private key. Removing a private key is a distinct, explicitly requested action, not a side effect of saving DER.

Explicit deactivation/removal writes an authoritative secret-free tombstone before legacy cleanup. Subsequent reads must not fall back through that tombstone to old split fields. Inaccessible, malformed or future-version records are errors, not "no certificate" and not permission to create a replacement. Checked old-format migration preserves the old active copy until the coherent destination and private cache exist. Failed cleanup is reported; it is not a claim that all old bytes were removed.

P12 round-trip parsing, serial and public-certificate comparison are performed before storing a new identity. Tests with synthetic bytes verify persistence semantics only. Independent key-pair/chain trust validation is still part of the cryptographic-input review, not implied by decoding a P12. The inherited serial-based P12 password is public information: confidentiality relies on the OS Keychain, not on that password.

## Provisioning decisions

The foreground provisioning flow first checks local storage, then the current Team's portal certificates. It reuses only an available local private key whose public certificate matches a non-expired portal entry. It no longer bypasses Team checks using a Subject/Issuer string heuristic.

When no usable local identity is found, creation is attempted without first revoking other certificates. Only Apple's actual certificate-capacity error opens the existing explicit selection UI. Keeping existing certificates does not silently revoke anything. Selected revocations must match the current list, cannot contain duplicates, and are executed only as requested.

A successfully returned new certificate/private key is committed and read back in the proxy before additional caller work. The flow does not perform an unnecessary second portal fetch that could discard that returned private key on failure. Account sign-out, activation and private-material changes share mutation ownership. The existing public-only observation cache is independent and must not deadlock database startup.

An explicit advanced skip leaves setup incomplete; it is not proof that the manager can renew or sign. Advanced import/removal screens propagate persistence errors instead of reporting unconditional success. File imports are bounded; the original parser and cryptographic-input acceptance still need their separate audit.

## Not yet solved by this change

If Apple accepts a CSR but the process dies or the response is lost **before SideSign returns the certificate/private key**, caller-side persistence is not sufficient. A durable pre-submission CSR/key transaction plus reconciliation of an uncertain response remains required to close that recovery boundary. Do not declare this case idempotent or solved by the new returned-key cache.

Physical Keychain protection, real Apple provisioning, quota UI behavior, private-key parser robustness, and end-to-end first-login/self-update remain acceptance items. This change does not collect real accounts, signing keys or pairing records in CI.
