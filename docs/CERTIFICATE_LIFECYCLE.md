# Certificate lifecycle and recovery

## Evidence boundary

This feature is under development from main `c3b8f7c736f2b6c56ab1a20ed085a83ea672573b`.
Synthetic tests do not prove Apple account acceptance, certificate quota, iPhone
installation, or mobile-only unattended renewal. No test may use a real account,
private key, password, 2FA code, provisioning profile, or certificate revocation.

## Required safety contract

- A public `.cer` is not a signing identity. Reuse requires its matching private
  key, normally in an encrypted `.p12`, and valid profiles for the exact Team,
  device and every app/extension bundle. Neither an IPA nor a certificate can
  reconstruct a lost private key.
- Before web issuance, the user explicitly creates and downloads an encrypted
  recovery file and confirms it has been saved. A download event is not evidence
  that the user retained the file; verification by reimport is stronger evidence.
- Web recovery files contain the same locally generated key and CSR. Imported
  requests default to read-only certificate recovery, not permission to issue a
  replacement. A missing list result does not prove an earlier CSR was rejected.
- Certificate issuance and profile creation are separate stages. Once a matching
  certificate is received, encrypted P12 export must remain available even if
  later profile/device/App ID processing fails. A profile failure must not cause
  another CSR submission.
- Server state is not a durable Apple transaction journal. Process-local guards
  cannot prove exactly-once issuance across restarts or multiple instances. After
  an uncertain result, read back the matching public key; do not blindly resubmit.
- Revocation is a separate explicit foreground action. Show the exact certificate
  identifier/serial and explain that existing profiles and installed apps using
  it may stop working. Never preselect all certificates, revoke silently, or
  automatically loop through revoke-and-create.
- Keys and backup passwords remain in the browser or on device. Web storage must
  not silently persist them. Native Keychain storage is distinct from export;
  any user export must use a newly chosen password, not an internal storage label
  or certificate serial. Do not expose raw private-key clipboard shortcuts.
- Cancel, session expiry, navigation and service restart must clearly distinguish
  loss of a login session from a lost signing identity. Recovery relies on the
  explicitly retained encrypted file, not an assertion that an HTTP abort undid
  Apple's operation.

## Self-signing versus self-installation

Local signing means assembling a signed IPA from a matching private key,
certificate and provisioning profiles. It is not proof that iOS will install or
launch that IPA. Replacing the running manager additionally needs an authorized
installation route and post-restart identity/readback verification. An unsigned
first install is not made possible merely by implementing local signing.

For a free Personal Team, exported P12 material does not extend profile expiry.
Renewal still needs valid replacement profiles from Apple. Native source and
unsigned build evidence must be reported separately from actual-device execution.

## Consolidated test matrix

| Boundary | Required synthetic evidence | Real-world evidence remains separate |
| --- | --- | --- |
| Recovery file | password authentication, tamper rejection, size bounds, matching private/public key/CSR, cross-session reimport | user's retained file |
| Certificate | exact public key and Team, validity interval, early P12 export, no repeated issuance after uncertainty | Apple issuance/status |
| Profiles | per-bundle/device/Team/cert validation, partial failure and retry without issuing | Apple profile validity |
| Revocation | empty default selection, exact identity, stale/replay/cross-Team rejection, explicit confirmation | actual account revocation (not run by tests) |
| UI | double clicks, cancel, expiry, reload, cross-tab, interrupted response; Chromium and WebKit using synthetic HTTP | real iPhone browser and Settings |
| Native | Keychain readback, export re-encryption, source transformations, Debug/Release core and unsigned integration builds | self-update install and launched binary readback |

Final implementation SHA, test counts and remaining blockers are recorded in
`docs/STATUS.md`; this design checklist is not a claim that each row passed.

## Native export finding and replacement boundary

At pinned CodeSignKit `d0c67710fda9a2646b9e829cb2cf443892728371`,
`Sources/PKCS12Builder.swift:15–19` accepts a password but never uses it;
lines 58–65 emit a plaintext `keyBag`, and lines 77–82 emit no `MacData`.
Therefore the old method name `encryptedP12Data` is not evidence of encryption.
This source finding does not establish that any user's key was exported or leaked.
The internal legacy record is protected by Keychain custody; it must not be reused
as a supposedly password-protected downloaded backup.

The candidate routes explicit external export through the existing pinned
node-forge 1.4.2 in a fresh, local JavaScriptCore context. It does not use a web
view or network service. Fixed resources are checked by SHA-256; Security.framework
supplies entropy and failure cannot fall back to `Math.random` or the old builder.
The implementation must prove an encrypted key bag and a MAC, not merely accept a
password argument. Import preflight bounds KDF work inside encrypted containers,
then the native Security parser must read back the same identity.

This introduces approximately 310 KB of resources and a maintenance requirement
to keep their integrity hashes, license and pinned package version synchronized.
It also introduces transient private-key/password strings inside JavaScriptCore;
context disposal is not a guarantee that memory has been immediately erased.
Node/OpenSSL tests of the identical resources are useful interoperability evidence,
but cannot establish Swift bridge compilation, iOS Security compatibility, or
that each relevant app/extension bundle contains the resources. Those remain
separate required native gates. Missing, changed or failing resources must disable
export rather than release an unprotected P12.
