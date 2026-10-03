# Current checkpoint — explicit pairing picker and dismissal-bound import

Updated 2026-10-04 (Asia/Taipei). Starting integration head e704ed29598f206948a4b674f6bd114da4f7fc84, product 7045e13. Development remains on develop; main is not promoted. No device or credentials requested. This is not a release candidate.

## Confirmed previous outcome

7045e13 native Debug and Release both passed run 37143684846. Its whole-App run 37143684889 FAILED the document-picker Cancel assertion at TetherlessUITests.swift:30. The current downloaded UI artifact 11281747494 matches SHA-256 4e5701887b587ccb191d0002404ffd56927e4b361f7eaac1af02ee2e5edceaa1. Actual test log and app stdout were inspected: database startup succeeded, while the presented picker container had no Cancel control during the wait. This is the continuing picker symptom, not an inferred App Group or metadata-parser regression. Earlier UI failures remain failures.

The verified 7045e13 source archive matched outer SHA-256 55309b6a0a36b344e75e3fdba58818696886e68d8b1df1d78fb510eebe1d49c0 and inner TAR f40fd91b8c24f1cf7ad8e48fd6b1d66b2cea9f8001301bc635a54d80ee88f1c1. The additional e704ed2 truncation test was read from GitHub and matched blob a67d9720d69aad2ae92bd6e7e3b03b131d2e2f86. No previous uncommitted edits were required.

## Connected change

Replace the Form-bound Boolean fileImporter with a concrete UIKit picker owned by a stable request and presented from the root NavigationStack via fullScreenCover. Delegate callbacks are single-shot and invalidated on teardown. The core PairingImportFlow requires matching request identity and actual dismissal before an import can start. Repeated selection, cancellation, dismissal and late completion are rejected; another request is not admitted while importing. Normal account, protected-pairing validation/storage and unattended-consent rules are retained.

Open-mode selection uses security-scoped, coordinated, bounded reading instead of creating a raw copy in a public Inbox. Coordination failure is not a successful read; cancellation never calls import. The system picker itself still supplies the real Cancel control. The UI test now requires two consecutive real presentations/cancellations with the same ten-second wait, then all prior setup/recovery/cold-launch assertions. No warm-up, fake picker, fake account, auto-granted permission or disabled assertion was added.

See PAIRING_IMPORT.md. This is a concrete presentation/lifetime repair, not a proven diagnosis of an Apple framework defect. It still requires fresh Xcode/UI results to know whether the observed blank sheet is resolved.

## Checks before commit

- Linux core Debug and Release: 286 tests in 37 suites passed each, including nine new request-lifecycle cases.
- Python integration: 160 tests passed with no skips against retained exact dd0b09c authentication, ae9fd0a cache and 582953d metadata inputs. Their artifact hashes were checked before reuse. Five new contracts and the strengthened setup-dismissal guard passed.
- Swift frontend parsing passed; it does not replace UIKit typechecking or NSFileCoordinator execution on Apple platforms.
- Initial local test compilation failed because Swift Testing captured a mutating method on an immutable macro argument. Calls are now evaluated before assertions, with all cases retained; that initial failure is not counted as success. The old literal dismissal-guard assertion was updated to require the stronger guard including picker activity, not removed.
- Native Debug/Release, Apple-platform core tests and complete App/UI results for this implementation are pending fresh CI. Prior green builds do not validate it.

## Next

1. Inspect fresh native compilation and actual UI, especially BOTH system Cancel operations, cancellation status, released request and unchanged pairing/consent gates. Preserve any real failure and inspect current logs rather than rerunning until green.
2. Complete native selected-file/callback and broader logging/lifecycle checks. UI cancellation alone does not validate a real pairing import, file-provider access or account operation.
3. Independently verify/pin library provenance and distribution rights; complete remaining install-wide budgets, first-sign/self-update/configuration coverage and branding before consolidated physical acceptance.

No real Apple login, selected cloud pairing file, physical pairing, actual profile installation, hardware protection, locked-screen renewal or expiry crossing was verified. Code and continuation state are saved together.
