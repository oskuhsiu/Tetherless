# Pinned idevice native build candidate

This is an additive, offline build recipe for a Tetherless-specific dependency
candidate. It does not switch the app's dependency, modify Minimuxer, publish a
release, run CI, or change existing renewal/import routes.

## Evidence and current limits

- idevice source: `SideStore/idevice` commit
  `3e55c8486b2057e40c1f74aaaa1155c82341cf76`, Git tree
  `5df506b11db33b97d3b963e3be3f095729a409da`
- Consumer baseline: `SideStore/minimuxer`
  `12be70dc2627307a16bfd2dc7a009080d5bec909`
- Exact upstream source/build/license files were read using the GitHub connector.
  `source-tree.json` pins every source blob; `source-lock.json` additionally pins
  SHA256 evidence and the precise preimage/postimage of each edit
- Rust **1.98.1 is a candidate**, not an observed installed toolchain. Xcode
  **26.3** is the selected existing project profile. Exact build numbers, SDK
  versions, compiler observations and executable hashes are intentionally unset
  in the template until a macOS observation is reviewed
- The composite Rust overlays, test filters and exported symbol list must be finalized and hash-locked
  before staging/building. Missing hashes or symbols fail closed
- Python tooling tests are portable. Rust compilation, native fixture execution,
  generated headers, native libraries, C/Swift link probes, and the XCFramework remain unverified
  until this recipe passes on the recorded native host
- These controls make source inputs repeatable and bind outputs to their observed
  build. They do **not** establish bit-identical rebuilds of publisher artifacts

Upstream links:

- [Cargo.lock](https://github.com/SideStore/idevice/blob/3e55c8486b2057e40c1f74aaaa1155c82341cf76/Cargo.lock)
- [FFI manifest](https://github.com/SideStore/idevice/blob/3e55c8486b2057e40c1f74aaaa1155c82341cf76/ffi/Cargo.toml)
- [Header generator](https://github.com/SideStore/idevice/blob/3e55c8486b2057e40c1f74aaaa1155c82341cf76/ffi/build.rs)
- [Apple build recipe](https://github.com/SideStore/idevice/blob/3e55c8486b2057e40c1f74aaaa1155c82341cf76/justfile)
- [Upstream CI](https://github.com/SideStore/idevice/blob/3e55c8486b2057e40c1f74aaaa1155c82341cf76/.github/workflows/ci.yml)
- [idevice license](https://github.com/SideStore/idevice/blob/3e55c8486b2057e40c1f74aaaa1155c82341cf76/LICENSE.txt)
- [Minimuxer license](https://github.com/SideStore/minimuxer/blob/12be70dc2627307a16bfd2dc7a009080d5bec909/LICENSE)
- [Cargo configuration and source path rules](https://doc.rust-lang.org/cargo/reference/config.html#config-relative-paths)
- [Cargo source replacement](https://doc.rust-lang.org/cargo/reference/source-replacement.html)
- [Rust 1.98.1 release](https://doc.rust-lang.org/releases.html#version-1981-2026-09-03)

## Preserved dependency and feature boundary

The workspace Cargo.lock stays byte-for-byte unchanged. It has lockfile format 4
and 363 package entries; every external package is pinned to a crates.io checksum.
The locked build dependency is cbindgen **0.29.2**. `ffi/build.rs` uses that library
to generate `ffi/idevice.h` and appends the committed `ffi/plist.h`. Neither a
cbindgen CLI install nor a header download is needed.

The FFI default feature set is preserved in its entirety, including `house_arrest`
and `aws-lc`. No `--no-default-features`, crypto-provider replacement, package
version update, or `cargo update` is used. The sole proposed manifest edit exposes
the existing plist 1.8.0 streaming API via its feature
`enable_unstable_features_that_may_break_with_minor_version_bumps`; its existing
crate version and checksum remain locked. The exact feature edit is reviewable
in `source-lock.json`.

Tetherless only needs these candidate XCFramework slices:

1. `aarch64-apple-ios`, iOS 17.0, upstream default features plus `obfuscate`
2. `aarch64-apple-ios-sim`, iOS 17.0, upstream default features

The macOS host builds/runs the locked fixture filters for `staged_pairing::`,
`staged_acquisition::` and bounded decoder/TLS tests, but is not packaged.
This is an explicit product-specific reduction from the upstream build recipe's
five ARM64 slices. It is not a claim about how many slices any publisher artifact
contains. No x86_64, tvOS, macOS or Catalyst release is produced here.

## Review and toolchain observation

`observe-toolchain.yml.example` is a disabled proposal, outside active workflows.
Only the integration owner may activate, publish or run it. It uses the project's
existing pinned checkout/upload Actions and the already-installed official
rustup to install/select exactly 1.98.1 and two iOS targets, without changing the
global default. Missing rustup, CMake, Ninja, Python 3.11+, Xcode, or unavailable
archived toolchain downloads stop the job. It never bootstraps an installer.

`record_toolchain.py` itself is read-only apart from its new JSON output: it never
installs software or builds. It finds real compiler binaries behind rustup,
records SHA256 digests, all verbose Rust/C/Swift compiler/tool versions, macOS version/build,
Xcode version/build, and iOS/simulator/macOS SDK version/build. The JSON must be
reviewed and supplied to the builder with its independently recorded SHA256.
Do not substitute the null-valued template or accept a newly recorded hash
silently in the same automated step. The first native observation is evidence
for selecting a toolchain lock, not evidence of a successful native build.

## Offline inputs

A complete pristine input has now passed this recipe's verifier: 486 Git blobs,
3,646,249 content bytes, including the exact internal README symlink. The separate
`tetherless-idevice-pinned-source.tar` archive is bound by SHA256
`2ceadeee2cd42f89732da917a7fe953764f375a65f46f6a314abc57a6b4c7cf0`.
`source-input.json` records its filename, byte count, Git identity and provenance;
the archive is a separate input and is not embedded in this recipe. This establishes
pristine source integrity only. It does not approve the composite patch or prove a
native build. No source acquisition, Git checkout or submodule initialization is
performed by the verifier.

Verify an existing materialized input without applying any patch:

```sh
python3 Integration/Dependencies/idevice/apply_patch.py \
  --source /path/to/pinned-idevice --verify-only
```

Provide an existing pinned idevice source checkout/snapshot and a directory of
`.crate` archives matching **all** registry entries in the exact workspace lock.
The builder does not fetch source, initialize submodules, contact registries,
resolve a newer dependency, or use a prebuilt external release.

Source acquisition and registry-cache provisioning are separate, authorized
native-CI preparation steps. Keep the full commit and Cargo.lock pinned during
that preparation. The full upstream files are verified against
Git blob IDs before use; unrelated/untracked input files are not copied.

Every `.crate` is authenticated against Cargo.lock before extraction, then copied
into a new local vendor directory. The builder rejects missing/checksum-mismatched
archives, unsafe paths, links, duplicate archive entries and unexpected source
registries. It generates vendor checksums from authenticated bytes. A fresh
HOME/CARGO_HOME, rejection of all ancestor Cargo configs, and fixed offline Cargo
config prevent ambient user configuration
or a modified extracted Cargo cache from changing the build. The exact upstream `idevice/README.md -> ../README.md` Git symlink is preserved,
hash-checked as link text, and must target a committed regular file inside the
source tree. Other input symlinks are refused. Gitlink entries remain provenance
only: the FFI build uses no submodule checkout.

## Commands

Portable checks:

```sh
python3 -m unittest discover -s Integration/Dependencies/idevice/tests -v
python3 -m py_compile Integration/Dependencies/idevice/*.py
```

Review-locked source staging (optional standalone check):

```sh
python3 Integration/Dependencies/idevice/apply_patch.py \
  --source /path/to/pinned-idevice \
  --destination /path/to/new-staged-source
```

After reviewing the observed native toolchain JSON and its digest:

```sh
python3 Integration/Dependencies/idevice/build_xcframework.py \
  --source /path/to/pinned-idevice \
  --crate-cache /path/to/authenticated-crate-archives \
  --work-dir /path/to/new-build-work \
  --output /path/to/new-native-result \
  --toolchain-lock /path/to/reviewed-toolchain-lock.json \
  --toolchain-lock-sha256 REVIEWED_64_CHARACTER_SHA256
```

All work/output directories must be new. A failed build leaves its diagnostic
work directory but never publishes a completed result. The runner executes
fixture-only native test filters first and refuses a zero-test result for any filter, builds both slices
with `cargo --frozen`, verifies unchanged source/lock bytes, checks reviewed FFI
names in generated headers and static-library exports, compiles and links locked C
and Swift probes against each slice, and checks exactly the
two requested XCFramework slices. It neither signs nor inspects app admission.

## Result and later integration

Successful output contains:

- `bundle/IDevice.xcframework`
- `bundle/LICENSE-idevice.txt`, preserving Jackson Coxson's upstream notice
- `bundle/provenance/`, including exact source/toolchain/registry manifests,
  unchanged Cargo.lock and the fixture test output
- `bundle/corresponding-source.zip`, with the patched source, build recipe,
  authenticated vendor sources and their original licenses/notices
- `artifact-manifest.json`, binding every bundle file to SHA256 and recording
  source, tooling, target flags, C/Swift link-probe outcomes and observed toolchain identity
- `IDevice-local.zip`, a deterministically packaged local artifact
- `SHA256SUMS`, binding the ZIP and artifact manifest

The corresponding-source bundle retains all vendored package sources and notices;
this does not replace final distribution/license review. Minimuxer's AGPL license
is preserved as consumer-baseline evidence; no Minimuxer binary is built here.

`verify_artifact.py --bundle /path/to/bundle --manifest /path/to/artifact-manifest.json
--manifest-sha256 REVIEWED_64_CHARACTER_SHA256` checks both
the independently reviewed manifest digest and exact file inventory, rejecting
extra/missing/tampered files. A later integration change must consume a specific
verified local artifact/path and manifest through separate review. The scripts
never edit the active Minimuxer Package.swift, app import path, wrappers, gates,
or an existing packaged dependency. A CI artifact may carry the completed result;
no external release is necessary or authorized by this tooling.
