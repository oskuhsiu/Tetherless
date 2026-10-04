# Current checkpoint — external document source isolates resolver failure

2026-10-04. Starting develop: **8b7b02bf8011bc3854c49cb1b9072e3ddab78fe2**. This is one AUTO-02 / PAIR-01 test-integration increment, not a new production feature. Tetherless's Swift, picker delegate/content policy, pairing parser/storage and renewal core are unchanged. Main is unpromoted. No physical device or credentials requested.

## Apply the Simulator skill

Read `.agents/skills/ios-simulator-ci/SKILL.md`, `docs/SIMULATOR_CI.md`, and the current decision `docs/simulator-ci/next-run-decision.md`. This conversation's installed-resource listing did not yet expose the newly uploaded skill, so the identical supplied skill archive and repository copy were read and used. No claim of controlling the user's account installation state.

The current source was recovered from artifact **11302891252**, ZIP SHA-256 `8d61664cc52b1e8a827570d045784d702907f4a03b8df6a221bfb7b85977b3d1`, inner TAR `936f577b7fc09cddf18f37743a7a173cd2b087507fe4af21ece044726b248008`, recorded 8b7b02b. Skill classifier executed against the live-checked failed job projection and verified smoke artifact: earliest failure remains UI, not boot/install. No active UI job was found or rerun.

## New evidence, precise scope

In the previously retained but now specifically inspected app stdout, **DocumentManager fails bookmark resolution before delivering a selected URL**: NSFileProviderErrorDomain -1005, underlying NSFileProviderResolverErrorDomain -1012, then an empty array because the item could not be prepared/materialized. The line occurs at 10:40:36 immediately after the single file-cell tap. It explains why no app selection callback was observed, but does not establish why the provider's resolution failed.

The fixture was created by host Python inside the target's Documents before Xcode patched/re-registered and relaunched that target. The new evidence-backed hypothesis is that this fixture's provider identity is unstable/invalid; neither tap selection nor the product's parser should be changed to conceal it. See next-run-decision.md for source hash, timeline, expected evidence and refutation conditions.

## Narrow change

A **Simulator-test-only document-source app** now creates the same one invalid 241-byte public plist with NSFileCoordinator inside its own container. XCTest launches it once, requires its actual ready label and terminates it before testing Tetherless. The source is distinct from the app Xcode rebuilds/reinstalls. It holds no secret groups/credentials, invokes no Tetherless API, supplies no delegate/backend response and is not distributed or compiled into the product. The normal Files picker must select it from Tetherless Test Documents and exercise the real parser.

Two cancellations, exact single document-cell tap, original outcome deadline, actual dismissal, visible rejection, pairing incomplete, consent off, recovery/cold-launch and byte-preservation checks remain. Preservation runs after failed UI too when the fixture installation succeeded; successful preservation cannot override a failed test. The producer itself is an additional test prerequisite, not a success fixture. Its new native build/runtime is pending.

## Local checks actually completed

- **20 focused checks passed:** 8 new producer/bundle/command/ownership contracts and real-file tests; 6 retained document fixture/activation checks; 6 retained lifecycle/export checks.
- **16 Simulator skill tests passed**, including real read-only CLI/report behavior. Current classification remains failed/ui and productAccepted=false.
- Actual helper and XCTest source passed Swift frontend syntax parsing; workflow YAML parsed. These are not UIKit typechecking or native execution.
- No new core Debug/Release or whole-integration-suite count is advertised; production core did not change. No original failed UI is relabelled successful.

## Next standalone item

Inspect the single full-App workflow triggered by this commit. Require helper compile/sign/install and ready UI, then the actual product selection/rejection/dismissal, all existing assertions and independent original-byte verification. Read fixed callback markers and exact FileProvider errors. If the source isolation does not resolve materialization, record that refutation rather than repeating full runs. If callbacks arrive but state/dismissal fails, fix that now-visible product boundary separately.

The originally host-seeded own-container route remains failed historical evidence, not newly accepted. No real Apple login, valid pairing, physical installation, locked-screen scheduling or expiry crossing was tested. The broader scope remains PLAN_PROGRESS.md; no other task is claimed complete in this turn.
