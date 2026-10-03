# Current checkpoint — provider-pinned cache reclamation

Updated 2026-10-03. Starting integration head: 8f7d76d0390ad6b6ab28f418ad1faee8330008fb. This increment adds automatic cache cleanup and actual provider lifetime ownership. Work stays on develop; main is not promoted. No device or live credentials requested. Not a release candidate.

## Prior UI result is a real failure

Product 5a7b5ab whole-App run **37126826524** completed with failure in `TetherlessUITests.swift:30`: the system document picker never exposed the expected Cancel button after Choose pairing file. The test reached welcome and pairing, and the retained app stdout confirms Started DatabaseManager. Its failure hierarchy contains a blank presented container. It does not establish that cache code caused the picker issue, or that the entire flow passed. The previous App Group/catalog faults are not diagnosed again. No test assertion or product requirement is removed here.

The downloaded result ZIP matches SHA-256 `f63e9a45599a89f8d258a00a98724d55321cb271c9424f60ee0f82a825fb6a7c`. The actual native-ui.log, stdout and failure hierarchy `23708258-8AFE-4F05-A6AD-FE46AF524D63.txt` were inspected. The still-open picker presentation/cancellation behavior requires follow-up if reproduced. New CI for this changed implementation must be read independently.

## Connected increment

Stable per-slot shared/exclusive usage locks protect all returned managed Anisette clients and in-progress installs. Cleanup can only run exclusively; it verifies the active receipt and removes canonical obsolete generations/abandoned stages, never the active generation, receipt, lock or arbitrary unknown files. All candidates undergo bounded no-follow preflight before removal. Partial obsolete-tree deletion can be retried. Bad current data aborts rather than triggering destructive repair.

The native local and managed remote ODA paths now return a protocol-conforming wrapper retaining both the upstream client and PinnedGeneration throughout async operations. Upstream db8b410 AnisetteClient does NOT retain the resolver closure; a pin captured solely by that callback would have expired too early. The wrapper avoids that bug and changes no actual provisioning/wire data. Normal provider entry and installation attempt safe cleanup; repeated unpinned updates no longer exhaust the four-generation cap. Busy providers defer cleanup and keep the cap effective.

See CACHE_RECLAMATION.md. Independent binary provenance, other HTTP/staging cleanup, aggregate budgets and remaining logging/lifecycle/configuration coverage are separate unfinished gates. This change does not imply publisher trust.

## Checks before commit

- Local Linux core Debug and Release: **244 tests passed each** on completed runs. Nine new portable lifetime/cleanup tests ran, including an independent process respecting the real lock. Earlier timed-out local Release invocations are not passes.
- Python integration: **149 passed, no skips**, with exact retained native inputs. The cache transform is exercised, and copied helper/wrapper content and both native client routes are checked.
- Four new Darwin cache tests are defined in addition to the existing twelve, but do not run on Linux. They must pass in fresh macOS/iOS CI. Native compilation and UI are likewise pending for this increment.
- The 834f599 source baseline matched archive SHA-256 `3d558589b08d64138d2c39bf987e3413f50e12a24fa8e363ac35a076bb59cc5a`, inner TAR `8285ff8f64d3bce8d34aa08110df7e3e5b8c24fac1b1798f75ed1cdef8aa0b4f` and recorded commit. The intervening 8f7d76d is documentation-only. Native input is from the retained ae9fd0a review artifact; auth/identity inputs are from the retained dd0b09c artifact, hash-checked by the tests.

## Resume

1. Inspect fresh macOS, iOS Simulator, unsigned native and full UI results for this implementation, particularly Darwin retention tests and the actual protocol wrapper. Preserve any compiler or runtime failure.
2. Resolve a reproduced system pairing-picker presentation failure using actual hierarchy/stdout, not by skipping cancellation or retrying blindly until green.
3. Independently review/pin library provenance; finish separate download/staging cleanup, native logging and callback lifetimes, aggregate limits, supported-configuration/first-sign/self-update coverage and distribution/branding.

No real Apple login, downloaded library execution, physical pairing, actual profile install, hardware Data Protection, locked-screen renewal or expiry crossing has been verified. Source and checkpoint are saved together before further work.
