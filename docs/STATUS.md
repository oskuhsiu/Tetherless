# Current development checkpoint — resumable setup

Updated 2026-10-02. Development only; no physical-device handoff yet.

## Current increment

Setup navigation now persists a stable step name. A normal relaunch resumes the unfinished step and rereads local prerequisites. Auto Renewal has a Continue setup entry that presents the same production wizard. Dismissal is disabled while a wizard operation runs. Restoring navigation or dismissing the wizard never grants unattended consent, activates an account or marks a renewal verified.

The real-app XCUITest has been extended to terminate/relaunch in the pairing step, check that Continue remains disabled without pairing, reopen setup from Auto Renewal, and confirm that consent remains off. These are test definitions, not yet executed UI evidence for this increment.

## Verification at commit time

- Local Linux core Debug and Release: 175 tests passed each.
- Local Python integration checks: 88 passed.
- Current native Debug/Release and real UI execution: not yet verified. They require this increment's CI.
- Recovered baseline `1a4831d`: native Debug and Release both passed in run 37019229281. Its full-app/UI workflow 37019229377 was still running when last inspected. These results do not validate the changed resume flow.

## Resume next

Inspect this increment's native and UI runs first; diagnose actual UI failures rather than loosening assertions or adding fake credentials. Then complete pending issuance recovery decisions, Anisette/pairing-callback lifecycle and log review, resource cleanup, supported configuration tests and distribution/branding checks. Progress remains roughly 80% toward consolidated physical acceptance readiness, not a reliability percentage.

The earlier recovery checkpoint below is historical evidence for its named commits, not for this increment.

Previous recovery details: [1a4831d checkpoint](https://github.com/oskuhsiu/Tetherless/blob/1a4831d0c687b2cc9d1f9df4d3383de374b18be7/docs/STATUS.md). Earlier architecture and evidence remain in Git history.
