# Certificate lifecycle CI decisions

## 2026-10-28 — first draft verification and bounded repair

Draft PR #16, source `c1219b02203a475260932617a81cf2e908aba7d2`, parent
main `c3b8f7c736f2b6c56ab1a20ed085a83ea672573b`. No merge or deployment.

Passed: Renewal core PR run `40658333337`; real-image nonaccount Docker run
`40658333320`; iOS Simulator **core** push run `40658248822` (not native app
installation or Apple acceptance).

Browser run `40658333326` stopped before browser launch. The harness expected
only the old two WebKit spec names, while the configuration intentionally adds
certificate-lifecycle coverage. Repair the exact expected list, retaining all
assertions and all three spec names. Local harness 12/12, web 172/172 and build
passed after that one-line correction. Actual browser scenarios remain pending.

Native run `40658333292`, Release job `122714776555`, stopped in Patch
transformation tests, before native source preparation and full iOS compilation.
The new macOS fixture compiled Swift and ran JSCore, then failed its combined
Security import assertion. That combined failure did not distinguish correct,
empty or wrong password statuses, and is not evidence of an AES incompatibility.

Apple documents different defaults: macOS SecPKCS12Import adds to the default
Keychain, whereas iOS imports into memory. The macOS 15 fixture now explicitly
uses `kSecImportToMemoryOnly`, avoiding a headless runner Keychain dependency.
It retains correct-password success and empty/wrong-password rejection assertions,
and prints only synthetic fixture OSStatus codes on failure. OpenSSL-generated
AES/PBES2 and test-only 3DES controls distinguish a Forge-format issue from a
platform parser limitation; neither control changes the product algorithm or
substitutes for the original assertion. Tampered and missing resource cases are
both explicit. OS/OpenSSL versions are recorded. No password, key or account
content is logged.

Evidence sources: Apple's [identity import documentation](https://developer.apple.com/documentation/security/importing-an-identity)
and [SecImportExport.h](https://github.com/apple-oss-distributions/Security/blob/main/keychain/headers/SecImportExport.h).

One discriminating next CI run is justified by those changes, not an unchanged
retry. Acceptance remains unchanged. No Simulator source, workflow, timeout,
signing, selector or environment setting changes; the narrow Web/Integration/docs
patch does not match the Simulator push path filters.

## 2026-10-28 — distinguish decoder format from algorithm assumptions

Second source `2e8d6f8d732be8ec93ce095daf52012bcfd80f1a`: Browser run
`40659627118` passed actual 98 browser cases (15 new lifecycle executions),
34 production-gate and 13 transport cases. Its merge commit `f196bd9` has the
same tree `1514fc203affd27128f91152cf469c7ae2473e0f` as the head.

Native's memory-only fixture produced a real encrypted P12, but correct-password
Security import returned -26275 (decode), whereas wrong/empty passwords returned
-25293 (authentication). This supports password/MAC enforcement followed by a
decode problem, not a proven general AES limitation. The runner is macOS 15.7.9
with OpenSSL 1.1.1w. Previous OpenSSL controls did not exist because that version
does not support the chosen `-iter` flag; their missing statuses are not evidence.

Next bounded diagnostic: use supported OpenSSL default-iteration controls and
print their actual MAC/keybag parameters; add identical-pinned-Forge test-only
AES256/2048/SHA1, AES256/100000/SHA256 and 3DES/100000 controls. These distinguish
iteration, PBKDF2 PRF, library format and cipher/container behavior in one run.
Local fixture generation and OpenSSL decoding for all three Forge controls passed.
Product AES256/100000 output, native readback assertions, negative tests and all
workflow/environment settings remain unchanged. No cipher downgrade, custom
cryptography or bypass of failed validation is introduced.
