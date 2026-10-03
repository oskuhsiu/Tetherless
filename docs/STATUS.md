# Current checkpoint — real database startup before UI transition

Updated 2026-10-03. Development integration, approximately 80% toward complete implementation and feasible non-device verification. No phone or Apple credentials requested. Work remains on `develop`; `main` is unpromoted.

## Inspected cb60e00 UI failure

Run **37033589178** passed build, actual Simulator signature/linked identity checks, installation and launch. The real UI flow passed wizard resume, incomplete review, Settings and My Apps navigation, reopening setup and retained off-by-default consent. It failed at the final cold relaunch (`TetherlessUITests.swift:91`).

The retained accessibility hierarchy shows the real error **App Group Container Inaccessible**, over the Starting screen. This is not an offscreen-control failure. The UI artifact was downloaded and verified against Actions SHA-256 `1877a5d035ac62f37bed0d86d23c6517b845b87031f816f0bd93ba3db3ceceea`. Hierarchy `D545ABD6-C4F5-48DE-918B-4EF855CD8A5A.txt` was inspected. The run is failed, not partial acceptance.

## Repair included here

The actual reviewed Bundle extension only extracted code-signature entitlements. For the already-loaded main Simulator executable, it now reads the genuine `__TEXT,__entitlements` section using MachO's getsectiondata, with a 1 MiB payload limit and typed plist decoding. It neither invents an App Group nor selects an alternative database directory. Device and other-bundle extraction paths are unchanged. The normal FileManager container lookup and the database's fail-closed missing-group error remain in force.

The first-run wizard previously called transitionToMainInterface directly even if database startup failed. A new small LaunchReadiness state gates **every** transition on both completed database startup and wizard dismissal, claiming it only once. Finishing the wizard first waits for the database; finishing the database first waits for the wizard. A normal relaunch still requires a new successful database start. No account or unattended-renewal permission is inferred from UI readiness.

Both native edits are hash-locked post-onboarding transforms. The exact retained production inputs were reviewed and the transforms executed locally. The UI test retains all original navigation/relaunch/consent assertions, adds an explicit missing-group alert rejection and a final relaunch screenshot.

## Executed checks at this checkpoint

- Linux core Debug: **186 tests passed**.
- Linux core Release: **186 tests passed**.
- Python integration checks: **109 passed**.
- Four state-machine tests exercise both completion orders, prior dismissal, failure/retry and duplicate callbacks.
- Native input transformations executed on exact reviewed LaunchViewController and Bundle+AltStore files. Swift frontend syntax checks are not native compilation.
- Fresh native Debug/Release, Simulator core and real UI run are required for this new revision. Older green runs do not validate these changes.

The first local test attempt failed due to Swift Testing's expansion of a mutating struct call inside #expect. Tests now evaluate the mutation once into a local result before asserting; both final configurations passed. No test assertion was removed.

## Next actions

1. Inspect this revision's native and real UI runs. The critical acceptance is a clean first startup **and final cold relaunch** using the genuine shared App Group database. If group resolution still fails, inspect actual entitlements/container access; do not add a private-sandbox fallback or bypass database readiness.
2. Complete remaining certificate uncertain-state recovery decisions, Anisette/pairing/log lifecycle, aggregate resource reservation and abandoned staging cleanup.
3. Finish first-signing/self-update integration coverage, supported configurations and branding/dependency/distribution checks, then one consolidated physical acceptance.

No live Apple login, device signing/profile installation, pairing, locked-screen renewal or expiry crossing was performed. Historical evidence is retained in Git; latest prior product checkpoint is `7dbaac4`, not evidence for the new launch behavior.
