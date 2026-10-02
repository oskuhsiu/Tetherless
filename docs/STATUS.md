# Current development checkpoint — resumable setup

Updated 2026-10-02. Development only; no physical-device handoff yet. Progress remains approximately **80% toward feature-complete implementation and feasible non-device verification**, not reliability or production-readiness.

## Saved changes

- `d5b29383b02b1fb12a8dc663cc944c7d77bed5e7`: resumable setup navigation and Auto Renewal's Continue setup entry.
- `12fa69338173886043f53304f9a1513b90ff2489`: Simulator-only ad-hoc signing, actual built-signature/application-identifier inspection and regression checks.
- This later documentation-only checkpoint changes no Swift source or workflow. All changes are on `develop`; no promotion to `main`.

Setup navigation persists a stable step name. Relaunch resumes the unfinished step and rereads local prerequisites. Auto Renewal presents the same production wizard. Interactive dismissal is disabled while a wizard operation runs. Restoring navigation or dismissing the wizard never grants unattended consent, activates an account or marks a renewal verified.

The actual-app XCUITest now includes termination/relaunch in the pairing step, missing-pairing gating, reopening setup from Auto Renewal, and retained off-by-default consent. These are test definitions, not yet passing UI evidence for the new resume flow.

## Observed verification

| Check | Observed result and scope |
| --- | --- |
| Local Linux core Debug / Release | 175 passed each; Swift source at `d5b2938`, unchanged by `12fa693` |
| Local Python checks | 93 passed after the signing follow-up; includes five parsing/command-contract tests, not execution of macOS codesign locally |
| Native iOS Debug / Release | Both passed for `d5b2938`, run 37021324336; the newer `12fa693` run 37022756517 remains unverified at this checkpoint |
| Latest macOS core | Run 37022756129 at `12fa693`: both Debug and Release test steps succeeded; job cleanup was still in progress when inspected; no exact test count inferred |
| Signed whole-app/UI workflow | Run 37022756438 at `12fa693` was in Simulator initialization; signature, app launch and UI-flow success have not been observed |

The manually submitted onboarding, settings and UI-test files were checked by Git blob SHA against the tested local files. The follow-up workflow and signature inspector were also checked against their remote blob SHAs. These checks establish saved source identity, not a physical test.

## Failures retained as failures

`1a4831d` run 37019229377 really executed the UI flow. Its log records a review-page assertion failure: actual "Setup status could not be read", expected "Setup is not finished". This occurred before a subsequent push cancelled the workflow. It is neither a passing UI flow nor merely a timeout/cancellation. The downloaded artifact SHA-256 matched `06678321e264191e6d18d7a71c794bd94191562a4fc76f62889190e22254e4a1`.

`d5b2938` run 37021324491 failed during Simulator screen initialization before preparing/building/executing the product. Its UI steps were skipped. This separate environment failure does not explain the earlier setup-read failure or validate the new resume behavior.

## Simulator signing change: hypothesis, not proven repair

The old Simulator workflow disabled signing despite exercising Keychain reads. `12fa693` enables ordinary ad-hoc signing only for Simulator build/test and inspects the actual product signature and application identifier before launch. The inspector never signs a product, supplies missing entitlements or turns failure into successful evidence. The distributable device build remains unsigned.

This corrects a suspected environment deficiency. The earlier setup-read error's exact cause remains unresolved. No production Keychain check, real UI assertion or error was weakened. If the review assertion persists after the signature gate passes, record the failing local-read stage and safe OSStatus without secrets and investigate that operation; do not classify an unreadable setup as a normal empty installation.

## Exact next actions

1. Inspect `12fa693` runs: signed whole-app/UI **37022756438**, native **37022756517**, core **37022756129**. Read failed-stage logs before changes. Do not substitute old green results for the new signing configuration.
2. Complete the real resume/reopen/consent UI flow and retain its actual screenshots and result bundle. A successful launch alone is insufficient.
3. Finish pending certificate-issuance recovery decisions; Anisette, logging and pairing-callback lifecycle review; bounded resource reservation and crash-abandoned staging cleanup.
4. Finish first-signing/self-update integration, supported configurations, branding and dependency/distribution checks before one consolidated physical acceptance handoff.

No live Apple credentials, real signing/profile installation, physical pairing, locked-screen unattended renewal or expiry crossing were tested. No phone is requested while these implementation gates remain.

Historical recovery details: https://github.com/oskuhsiu/Tetherless/blob/1a4831d0c687b2cc9d1f9df4d3383de374b18be7/docs/STATUS.md. Earlier architecture and evidence remain in Git history.
