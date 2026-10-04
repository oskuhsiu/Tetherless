# Single-item checkpoint — actual document activation

Updated 2026-10-04. Starting/current inspected head: 81554d87aa7f7b68c8247ef383e81a4b6771d11f. Product Swift remains b67a36264dd0baddf69fe65cd156b6f3ced42e58. This increment changes the UI test, its source contracts and documentation only. Develop only; main is not promoted. No physical device or credentials requested.

## One item for this turn: AUTO-02 / PAIR-01 selected invalid document

The owner requested that each long-running item be isolated into its own turn. The matching rule is saved in AGENTS.md. Do not bundle the next native/full-App wait with an unrelated implementation or audit. The acceptance condition remains: select the actual invalid public plist via the system picker, observe dismissal and explicit rejection, retain the original file, keep pairing incomplete and consent unchanged, and complete the existing setup/recovery/cold-relaunch path.

## What the current UI run actually did

Full-App run **37189390107**, job **111398218234**, at 81554d8 FAILED in the XCTest, not in installation. The owned simulator, compile, signature, install/launch and public-fixture seed steps passed. Both Cancel operations passed. The test reached On My iPhone, tapped the correct `Tetherless, Container` cell, then the correct `Tetherless-Invalid-Pairing.plist, plist` cell at t=64.27s. At line 54 it timed out waiting ten seconds for onboarding.status. Verification of original-file preservation was skipped; it is NOT accepted as passed.

Artifact **11298695803** was downloaded and verified against SHA-256 `69aba8546bf51e9b7ea4bb4cd346a92a1ceecea3c7bea8fea40bf2d81c0e526e`. The actual native-ui.log, final hierarchy `5E394C88-5E0D-4E4D-A4D2-2F8554C98934.txt` and a late frame of its screen recording were inspected. The system Files picker remained on screen with the fixture, and the background wizard's Choose button was disabled. The hierarchy contains one Image inside that exact document cell. These observations establish no visible completion after the cell tap. They do not establish whether UIKit failed to activate the file, delayed its callback, or encountered a production dismissal problem; do not claim an import-parser failure from this evidence.

## Narrow test correction, pending actual execution

For this observed icon-mode fixture only, activate the unique real preview Image inside the already matched document Cell instead of the aggregate cell's center/metadata area. Require the cell enabled and the preview unique and hittable; tap once, with no coordinates, double-tap, retry or fallback. Location/folder navigation stays unchanged. Capture before activation and after the original ten-second outcome wait. Require explicit rejection AND real picker dismissal. Preserve both cancellations, enabled Choose button, incomplete pairing, unchanged consent, recovery and cold-launch assertions. Original-file verification is still a separate required workflow step.

This is a targeted test-input hypothesis, not a proven product fix. No production file-type restrictions, UIKit coordinator, parser, storage, signing or renewal code was changed to manufacture success. If the next actual run still shows the picker, inspect selection/delegate lifecycle rather than cycling through different taps or increasing waits.

## This turn's local checks

- Six document-fixture/activation contract tests passed (real temporary fixture IO; two added source-contract checks).
- Five existing pairing-picker integration contracts passed, including Swift frontend parsing of native picker/onboarding sources.
- Swift frontend parsing of the changed XCTest source passed separately.
- These eleven focused checks are not executed XCUITest or native typechecking. Unchanged core Debug/Release suites and the full integration suite were not rerun this turn; no inherited test counts are advertised as new results.
- Source artifact **11298254179** matched ZIP SHA-256 `d95a65e506bdc61b30490e3f444613269d71a5166ca50c1e6b23d84eef6656ea`, TAR `165cc9c8eaf0b37f9d4a425a8ad80fceb5f4354f228e7dc6a13edbfb50a3361d` and the recorded 81554d8 commit before editing. Current macOS core run 37189390115 is successful, but does not validate this later UI-only correction.

## Standalone next verification

Read the one fresh full-App run for this commit. Check the actual activation target, dismissal/rejection, final existing assertions and original-file verification, not merely the workflow's aggregate state. If it passes, close only this signed-out invalid-document route; valid pairing, preservation of an already-installed real pairing record, third-party providers and physical acceptance remain separate. If pending, record its run ID and stop rather than repeatedly waiting while adding more features. Keep the latest exact result and a concrete next action in this file.

The broader task inventory remains docs/PLAN_PROGRESS.md, but no other task is claimed complete here. No real Apple login, physical pairing/profile install, locked-screen scheduling or expiry crossing was tested.
