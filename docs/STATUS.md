# Current checkpoint — Simulator entitlement inspection

Development integration only. No physical-device handoff. Progress remains approximately 80% toward feature-complete implementation plus feasible non-device verification, not reliability.

## Latest narrow change

The `12fa693` whole-app workflow 37022756438 failed before app installation/UI execution. Its actual log shows `plistlib.InvalidFileException` when parsing codesign stdout, not a failed product signature or a new UI assertion. The verified artifact digest is `388e13d6003dc529c0e3771be27cbdc86bc39d1df305ee957445c4343487b427`.

The same build log shows the host signature `.xcent` is an empty dictionary, while the simulated iOS application identifier is linked from `SideStore.app-Simulated.xcent` into `__TEXT,__entitlements`. Treating host signature entitlements as the simulated iOS identity was incorrect.

The inspector now requests explicit XML from codesign, keeps strict signature verification, then reads the actual thin 64-bit Simulator Mach-O entitlement section with command/section/platform bounds. It never signs, repairs, uses source xcent as evidence, or adds entitlements. Missing/wrong Simulator identity still fails. Evidence retains its failing stage, and runtime Keychain/Apple/device/renewal claims remain false.

Local Python integration tests: **98 passed**. This includes synthetic Mach-O extraction/bounds and command-contract tests; it is not local macOS codesign execution. Swift production code is unchanged by this inspection fix. A fresh whole-app/UI run is required.

## Next actions

1. Inspect this commit's signature and real UI results. Preserve prior failed runs. The old review-page error `Setup status could not be read` is still unresolved until actual UI passes or its failed stage is identified.
2. Complete resumable setup/reopen/consent UI coverage without fake credentials or weaker assertions.
3. Finish certificate uncertainty decisions, Anisette/pairing/log lifecycle, resource cleanup, remaining integration and distribution work before consolidated physical acceptance.

Previous checkpoints: `4fbb8fd` describes resumable setup and `1a4831d` the recovered CSR/onboarding work. All source and historical evidence remain in Git; changes continue directly on develop, never main.
