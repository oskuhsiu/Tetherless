# Signing test app, not Tetherless

This is our small, original UIKit app for a separately authorized custom-IPA web
signing test. It has no dependencies beyond Apple's system frameworks and Swift
runtime, no account login or network requests, no credentials, no user-data
persistence, no background modes, and no entitlements. Its UI and embedded build
identity explicitly say **Signing test app, not Tetherless**.

A successful build proves only that this fixture compiled and packaged. It does
not prove that the full Tetherless app builds, that an Apple account works, that
signing/provisioning succeeds, that anything installs or launches, or that pairing,
renewal, background operation, or any product acceptance gate passes.

## Portable checks

From the repository root, using installed Python 3.11 or later:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s Tools/WebSigningTestApp/tests -v
```

Tests use conspicuously synthetic, non-Mach-O bytes. They cover strict CI identity,
run-derived App IDs, exact app contents, executable mode, ZIP integrity, source
snapshot integrity, signature classification, platform inspection, provenance
cross-checks, and fail-closed native-host guards. They do not invoke Apple tools.

## Native CI

`.github/workflows/web-signing-test-app.yml` is isolated to changes in this folder
and its own workflow on `develop` or `verify/staged-pairing-native`. It uses the
existing `macos-15` arm64 runner and installed Xcode 26.3. It checks out without
submodules or persisted credentials, runs the portable tests, and compiles exactly
one arm64/iOS 17.0 executable with Apple's `swiftc`. No dependency acquisition,
Homebrew, simulator, device, signing identity, provisioning, release publication,
or deployment is involved. There is no retry, matrix, archive export, or cache.
The build command has a three-minute subprocess timeout and a six-minute step
limit; the whole workflow is bounded at fifteen minutes.

The build refuses a dirty checkout, an unexpected full source/workflow commit,
other branches/events, other host architecture, or a different Xcode selection.
The actual Xcode build, compiler version and digest, SDK version/build/path,
logical approved developer directory and actual resolved toolchain paths, runner image, source commit, run ID, and run attempt are retained. Build subprocesses
receive a small explicit environment, without GitHub tokens or Apple credentials.

The executable is inspected with Apple's `lipo`, `otool`, and `codesign`. A linker
ad-hoc code signature is allowed and labeled explicitly. It is **not an Apple
Developer signature**, has no Team identity, and does not authorize installation.
A completely unsigned executable is also allowed. An unexpected signing authority,
Team, entitlement, platform, profile, or app file fails the build. No signature is
created, removed, replaced, or repaired by this tooling.

## Artifact contract

Successful artifact name:
`owned-signing-test-app-<full-commit>-<run-id>-<attempt>`

- `Signing-test-app-not-Tetherless.ipa`: exactly three regular files under
  `Payload/SigningTest.app/`: `SigningTest`, `Info.plist`, `BuildIdentity.json`
- `provenance.json`: full source/workflow and GitHub run identity, observed
  toolchain, unsigned/ad-hoc classification, IPA SHA-256 and byte count, source
  snapshot digest, app/binary inventory, and explicit acceptance limitations
- `app-manifest.json`: every app file's relative path, mode, bytes, and SHA-256
- `binary-inspection.json`: binary digest, device architecture, signature state,
  and linked-library evidence; raw Apple-tool output is retained separately
- `signing-test-source.tar` and `source-manifest.json`: exact tracked bytes of
  this folder, this workflow, and the unchanged root `LICENSE` from the recorded
  commit; not a full-repo snapshot
- `SHA256SUMS`: checksums for all the other successful artifact files

A separate `owned-signing-test-evidence-<full-commit>-<run-id>-<attempt>` artifact
retains portable-test logs, native command arguments/results, raw tool output,
and pass/fail status, including partial timeout output, spawn-error receipts, and
a pending-command receipt written before each tool starts. It excludes the build
cache and working directory. Both artifacts expire after fourteen days.

The deterministic bundle ID is `org.tetherless.signingtest.r<GitHub-run-id>`.
Run IDs and attempts must be 1–20 decimal digits, beginning with 1–9. Rerunning an
attempt preserves the bundle ID; a new run has a new ID. Provenance keeps both the
run and attempt. Never substitute an ID derived from an unrelated run.

## Next verification and authorization gate

1. Review these new files, then have the authorized repository writer publish
   only this delta on the approved branch and record the resulting full commit
2. Prefer the single automatic path-filtered CI run from that publication;
   do not also dispatch a duplicate run. If manual dispatch is needed, select
   `Owned signing test app (not Tetherless)` at that exact approved branch commit
3. Verify the run's source SHA, run ID, attempt, portable result, native
   compile/inspection result, artifact digest, and retained provenance. A queued,
   skipped, failed, or missing result remains unverified
4. Before any real Apple mutation, the owner must approve the exact Apple Team,
   target device, this run's App ID, certificate action, and provisioning profile.
   Account login alone does not authorize these mutations. Do not put credentials,
   private keys, provisioning material, or device identifiers into CI or source
5. Only after those approvals, use the exact retained IPA in the separately
   authorized custom-IPA web signing test. Preserve its hash and the tested
   account-path result separately from full Tetherless and device acceptance

If native CI fails, classify the first failed command from retained evidence;
review one bounded repair before another native run. Do not infer a simulator,
SDK, or code-signing problem from a missing artifact alone.

## Apple references

- [UIKit scene lifecycle](https://developer.apple.com/documentation/uikit/transitioning-to-the-uikit-scene-based-life-cycle): the app delegate supplies the scene configuration and the scene delegate creates the window
- [Ad-hoc signature flag](https://developer.apple.com/documentation/security/seccodesignatureflags/adhoc): ad-hoc code has no signing identity
- [UIApplicationDelegate main entry point](https://developer.apple.com/documentation/uikit/uiapplicationdelegate/main()): the UIKit application entry point used by this app
