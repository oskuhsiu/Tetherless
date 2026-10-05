# Prepared-source link boundary

## Observed native failure

[Native run 37291091604](https://github.com/oskuhsiu/Tetherless/actions/runs/37291091604)
at `c1482e0e615f56bfa37fa9437c43aa1669550cec` passed its pre-preparation tests
and all 13 strict prepared contracts. Debug job `111701387350` and Release job
`111701387025` then failed in the prebuild source snapshot, before native
compilation, because strict link resolution required a generated target to exist.
The Debug traceback ends at the absent `.generated/SideStore/build` directory.
This is source-inventory evidence, not a compiler or Simulator failure.

## Verified input, not an inferred target

At pinned SideStore commit `0dd743f75afc358b0ba4a002feb5f19474492371`, the complete
Git tree reports one symlink:

- Path: `AltStore/Resources/SideBackup.ipa`
- Git mode: `120000`
- Exact target: `../../build/SideBackup.ipa` (26 bytes, no appended newline)
- Git blob SHA-1: `54a080c4e8a5029ad8d22842c16acde4d6d01b43`
- Target-byte SHA-256: `044eee43b24175359f83da07d98d41ce4d957e6e8c006e72fbf60c9c13815bbc`

The target bytes were checked against that Git blob. The pinned
[project build phase](https://github.com/SideStore/SideStore/blob/0dd743f75afc358b0ba4a002feb5f19474492371/AltStore.xcodeproj/project.pbxproj)
invokes `make -B clean-sidebackup copy-sidebackup ipa-sidebackup`. The pinned
[Makefile](https://github.com/SideStore/SideStore/blob/0dd743f75afc358b0ba4a002feb5f19474492371/Makefile)
sets `TARGET_BUILD_DIR := build` and `TARGET_IPA_NAME := SideBackup.ipa`.
Thus the source link legitimately exists before its build-produced target.
The build recipe was read, not executed as part of this diagnosis.

## Narrow source-inventory behavior

The collector retains the link's original target text and hash. It examines only
path/link metadata in root, with the existing path-depth limit and a 32-hop link
limit. Symlink expansion occurs before subsequent parent components are handled.
Only `FileNotFoundError` becomes missing-input evidence; permission failures and
other errors still fail. Root escapes, absolute/chained escapes, private target
paths, loops, special files and non-directory traversals remain rejected.

Each retained source link has `targetResolution` metadata:

- `path`: resolved root-relative target path
- `existence`: `missing` or `present`, never an assertion that missing bytes exist
- `pathPolicy`: whether that target path is included or excluded by source policy
- `crossedExcludedPath`: whether chain inspection encountered an excluded path
- `contentRead`: always false; target contents are not read through a link
- `missingAt`: first missing root-relative component, when applicable

For the exact SideBackup link, the target is `build/SideBackup.ipa`, excluded by
source policy, and missing before the build. After a generated file appears,
its status becomes present but excluded; its bytes are still not swept into the
source archive. The tar member remains the same exact symlink in both cases.
The final unsigned IPA inventory remains a separate inspection of actual output.

## Verification scope

Regression fixtures cover the exact pinned link before and after a synthetic
build output appears; ordinary dangling in-root links; committed link blob
identity; chained missing targets; chained/root escapes and private targets;
loops, special files and permission errors; and unchanged deterministic tar link
identity without reading generated contents.

This repair does not modify the native project, SideBackup production flow,
metadata policy or UI. It does not establish native compilation or completed
packaging. Re-run the focused native verification against the repair commit,
then inspect the next actual stage. Device and release gates remain unresolved.
