# Single-item checkpoint — document activation verification

Updated 2026-10-04. UI change: **c4b3f90fec2aefe8999a141472d434783e8e7498**. Product Swift remains **b67a36264dd0baddf69fe65cd156b6f3ced42e58**. This final update is documentation only. All work is on develop; main remains unpromoted. No device or credentials requested.

## Standalone next item: AUTO-02 / PAIR-01

Read full-App run **37191398887**, job **111404163196**, for c4b3f90. It was **in_progress**, conclusion null, at the last check and started 2026-10-04T09:12:29Z. Do not infer success, rerun it automatically, or mix waiting on it with another large feature/audit. The one-long-running-item-per-turn rule is saved in AGENTS.md.

Required result: the actual invalid public plist is activated through the system picker, the picker dismisses, the app explicitly rejects it, the original file remains byte-identical, pairing stays incomplete, consent stays off, and the existing setup/recovery/cold-relaunch assertions pass. Original-file verification is a required separate workflow step. A seeded file or a successful tap alone is not acceptance.

## Observed current failure that motivated this change

At starting head 81554d8, run **37189390107** / job **111398218234** FAILED in the XCTest, not installation. Compile/signature/install/launch and fixture seeding passed. Both real Cancel operations passed. The correct folder cell and then the correct `Tetherless-Invalid-Pairing.plist, plist` cell were tapped (file at t=64.27s), but onboarding.status did not appear within the original ten-second wait. The final hierarchy and a late screen-recording frame still show the Files picker with its file; the wizard's Choose button remains disabled. Original-file verification was skipped, not passed.

UI artifact **11298695803** matched SHA-256 `69aba8546bf51e9b7ea4bb4cd346a92a1ceecea3c7bea8fea40bf2d81c0e526e`. Actual native-ui.log, final hierarchy `5E394C88-5E0D-4E4D-A4D2-2F8554C98934.txt` and the video frame were inspected. The hierarchy contains one real Image in the matched document cell. This establishes no visible completion after the aggregate cell tap; it does not prove an activation, delegate or dismissal root cause.

## Narrow change, not a proven product fix

For that observed icon-mode fixture, the test now taps its unique hittable preview Image inside the matched document Cell rather than the center of the cell's filename/metadata area. The cell must be enabled and the preview unique. It taps once, without coordinates, double-taps, retries or fallback. Folder/location navigation is unchanged. Screenshots before activation and after the original ten-second outcome wait distinguish the missing stage. Both explicit rejection and actual picker dismissal are mandatory; all earlier cancellation, pairing/consent, recovery and cold-launch checks remain.

No production UIKit/file-type/parser/storage/signing/renewal code was changed to manufacture success. This is a targeted test-input hypothesis awaiting actual UI execution. If the fresh run still leaves the picker visible, inspect the selection/delegate lifecycle instead of rotating tap methods or increasing waits. The full inspected evidence and initial checkpoint are retained in STATUS.md at c4b3f90.

## Local verification this turn

- Six document-fixture/activation tests passed: real fixture file IO plus two new source-contract checks.
- Five existing pairing-picker contracts passed, including syntax parsing of native picker/onboarding sources.
- Changed XCTest source parsed separately with swiftc -frontend -parse.
- These **eleven focused checks** are not executed XCUITest or native typechecking. Unchanged core Debug/Release and the full integration suite were not rerun; previous counts are not new results.
- Saved XCTest blob `28a2d1b72ae6c08bcce397959673ebc48d613635` was read back from c4b3f90 and matches the tested local file.
- Starting source artifact **11298254179** matched ZIP SHA-256 `d95a65e506bdc61b30490e3f444613269d71a5166ca50c1e6b23d84eef6656ea`, TAR `165cc9c8eaf0b37f9d4a425a8ad80fceb5f4354f228e7dc6a13edbfb50a3361d` and recorded 81554d8 before editing.

No other plan item is completed here. Valid pairing, preserving an already-installed real pairing record, third-party file providers, real Apple login/profile install, locked-screen scheduling and expiry crossing remain separate unverified conditions. The broader original inventory is docs/PLAN_PROGRESS.md. Stop at this saved checkpoint; no after-turn background work is promised.
