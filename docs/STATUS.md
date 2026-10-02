# Current checkpoint — checked setup observations and single-owner Simulator boot

Development integration only. Progress remains approximately 80% toward complete implementation plus feasible non-device verification. No phone or Apple credentials are requested.

## Saved changes in this increment

Setup now distinguishes a missing record from an unreadable record and from a later component that was never checked. Reads run in account/signing/pairing order within the common mutation lease. The first failure retains only an allowlisted stage/category, never an arbitrary error string, path, account, key or token. A corrupt pairing file is no longer silently displayed as absent in onboarding. Compatibility callers still fail closed. Cancelled or superseded SwiftUI observations cannot replace the current result or its consent value.

The actual-app UI assertions retain their original expectations; failures additionally report the allowlisted readiness detail. This is diagnosis support, not a claim to have fixed the earlier review-page error.

`5217156` already saved the CI entitlement inspector fix: strict host-signature verification and explicit XML, with simulated iOS application identity read from the actual linked `__TEXT,__entitlements` section. No source xcent fallback or signing repair is used.

Its UI run 37029268767 failed in Simulator boot **before** product preparation, signing inspection or UI. The downloaded artifact matched SHA-256 `d54daf85d3e2d10b269c064679d96dd562ba1e63a958999974783adae34ff909`. The actual log reports CoreSimulator code 405: "Unable to boot device in current state: Booted" after starting Simulator.app and `bootstatus -b` concurrently. Boot now has one owner: inspect selected state, CLI boot if Shutdown, monitor without `-b`, then open GUI and require the normal screen capture. No timeout increase, skipped assertion or continue-on-error is used.

## Executed local checks

- Linux Swift Debug: 182 tests passed.
- Linux Swift Release: 182 tests passed.
- Python integration checks: 102 passed.
- Observation tests inject read failures; boot/signature tests inspect command contracts and synthetic structures. They are not real Apple authentication or native UI proof.
- Native builds, Simulator signature and real resumed-setup UI for this revision require fresh CI. Earlier green builds do not validate this change.

## Exact next actions

1. Inspect this revision's native and whole-app runs. Retain failed stage artifacts. A boot failure says nothing about product setup behavior.
2. Require actual signature inspection and real setup/resume/reopen/consent navigation. If review fails, use its `setup/<stage>/<category>` message to locate the native operation; unreadable storage must not be accepted as a normal missing account.
3. Finish certificate uncertain-state recovery decisions, Anisette/pairing/log lifecycle, aggregate resource and abandoned staging cleanup, remaining integration and distribution work before consolidated physical acceptance.

Prior evidence: `12fa693` run 37022756438 failed codesign-output parsing before installation/UI; `1a4831d` run 37019229377 genuinely failed review-page readiness before later cancellation. Neither is a passed UI flow. Historical checkpoints remain in Git.
