# Owned native signing-test input

This is a genuine unsigned UIKit iOS-device app, labeled **Signing test app, not
Tetherless**. It is test-only input, not the Tetherless product or an installable
release. Do not replace it with a synthetic signed output or update its hashes
to accept unrelated bytes.

- Original IPA: `Signing-test-app-not-Tetherless.ipa`, 14,853 bytes
- SHA-256: `fda8c913af9d6f39f8a4351bd94d7953bb99b2b25506e67a3e7d943dafaf8111`
- Bundle ID: `org.tetherless.signingtest.r37503567286`
- Executable: `SigningTest`, 99,200 bytes, arm64 MH_EXECUTE, iOS 17.0 minimum
- Executable SHA-256: `7372b58465e9f1c8893938787084176ddba2292fc7ddc98ef7a30a77d580708f`
- [Exact source commit](https://github.com/oskuhsiu/Tetherless/commit/cfd8c6ede2c85970344e9e9c0f19cc672a95df71)
- [Native build, attempt 1](https://github.com/oskuhsiu/Tetherless/actions/runs/37503567286/attempts/1)
- [Native build job](https://github.com/oskuhsiu/Tetherless/actions/runs/37503567286/job/112406415684)

`provenance.json` and `signing-test-source.tar` are unchanged companions from that
run. The tar contains the seven exact source/workflow/LICENSE files listed in
the provenance, under their original paths. Its SHA-256 is
`4db8c444bf899d3a18f9a58b43834e199734986290b588b1114f5bcf2b28b76a`.
The repository's included GNU Affero General Public License and existing
copyright notices apply; the full license is included in the source tar.
The tar is source evidence only and is never executed by this browser test.

Native classification comes from the authenticated build's standard Apple
`lipo`, `otool`, and `codesign` evidence. There was no local native rebuild and no
new Mach-O parser. The fixture and its three members, provenance, source files,
Git blob identities, and retained 17 command receipts were checked against that
exact build. Portable tests pin the immutable IPA/source tar and validate archive
members and embedded BuildIdentity; they do not independently establish native
compilation or Apple trust.

The browser case selects these exact bytes through the visible custom-IPA input
at both existing mount paths. It uses the existing guarded synthetic account
seam, local CSR generation, a fresh synthetic certificate/profile and actual
browser WASM signing. Only the fixed test Team, dummy device and `.invalid`
credentials are accepted. No account, Apple service, deployment or device is used.
All runtime keys, P12s and signed output remain ephemeral. CI retains a digest-only
output proof and synthetic UI screenshots, not a signed IPA or private key.

A passing case proves the account-free custom-IPA browser path processed this
native input. It does not establish Apple CMS trust, real provisioning, Safari,
iOS installation, launch, pairing, renewal or unattended operation. The UI must
continue to say installation and launch are unverified and block installation.
