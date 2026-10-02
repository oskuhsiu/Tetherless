# Current development checkpoint — resumable setup

Updated 2026-10-02. Development only; no physical-device handoff yet.

## Current increment

Setup navigation now persists a stable step name. A normal relaunch resumes the unfinished step and rereads local prerequisites. Auto Renewal has a Continue setup entry that presents the same production wizard. Dismissal is disabled while a wizard operation runs. Restoring navigation or dismissing the wizard never grants unattended consent, activates an account or marks a renewal verified.

The real-app XCUITest has been extended to terminate/relaunch in the pairing step, check that Continue remains disabled without pairing, reopen setup from Auto Renewal, and confirm that consent remains off. These are test definitions, not yet executed UI evidence for this increment.

## Follow-up: simulator signing and observed UI failures

`1a4831d` run 37019229377 really executed the UI flow. Its log records a failure on the review page: actual "Setup status could not be read", expected "Setup is not finished". It had already failed that assertion before being cancelled by a later push. The downloaded artifact SHA-256 was verified as `06678321e264191e6d18d7a71c794bd94191562a4fc76f62889190e22254e4a1`. Do not classify this as merely a timeout or a passing UI flow.

`d5b2938` native Debug/Release passed (run 37021324336). Its whole-app/UI run 37021324491 failed during simulator screen initialization, before building or running the app. This is a separate failure, not evidence about the changed resume behavior.

The simulator-only workflow now enables ordinary ad-hoc code signing and checks the actual built signature/application-identifier before launching. The previous workflow disabled signing even though the UI reads Keychain. This removes a suspect test-environment deficiency; the exact cause of the earlier read error is not yet proven. No Keychain check, UI assertion or production security error was weakened. The distributable native workflow remains unsigned. Local Python checks including the new inspector tests: **93 passed**. The signed simulator rerun is pending for this checkpoint.

If the same review assertion fails after the signature gate passes, collect the failing local-read stage/OSStatus without secrets and fix that cause. Do not accept unreadable setup as a normal empty installation.

## Original increment verification at commit time

- Local Linux core Debug and Release: 175 tests passed each.
- Local Python integration checks: 88 passed.
- Current native Debug/Release and real UI execution: not yet verified. They require this increment's CI.
- Recovered baseline `1a4831d`: native Debug and Release both passed in run 37019229281. Its full-app/UI workflow 37019229377 was still running when last inspected. These results do not validate the changed resume flow.

## Resume next

Inspect this increment's native and UI runs first; diagnose actual UI failures rather than loosening assertions or adding fake credentials. Then complete pending issuance recovery decisions, Anisette/pairing-callback lifecycle and log review, resource cleanup, supported configuration tests and distribution/branding checks. Progress remains roughly 80% toward consolidated physical acceptance readiness, not a reliability percentage.

The earlier recovery checkpoint below is historical evidence for its named commits, not for this increment.

Previous recovery details: [1a4831d checkpoint](https://github.com/oskuhsiu/Tetherless/blob/1a4831d0c687b2cc9d1f9df4d3383de374b18be7/docs/STATUS.md). Earlier architecture and evidence remain in Git history.
