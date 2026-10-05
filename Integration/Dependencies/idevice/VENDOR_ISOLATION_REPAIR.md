> Historical checkpoint. The current helper recipe is described in DERIVED_METADATA_REPAIR.md; it uses a separately audited build-vendor copy and classifies configs by actual Cargo discovery scope.

# Helper-only sibling-vendor repair

## Exact failure evidence

Helper CI run 37323350367 at `bcff221ea744303e190049aa452c4785c49e1d74`
passed 71 portable checks and reached the first offline Cargo fixture build. Cargo
exited 101 after 71.119856416 seconds while compiling plist_ffi 0.1.6, before any
Rust fixture executed. Its build script asked cbindgen for Cargo metadata on:

`helper-work/source/vendor/plist_ffi-0.1.6/Cargo.toml`

Cargo found the enclosing idevice workspace at `helper-work/source/Cargo.toml`
and rejected the vendored crate as an unregistered workspace member. The retained
process sidecar confirms normal nonzero-exit evidence retention, a reaped direct
child and `killpg_ESRCH` empty-group evidence. This is a workspace/configuration
failure, not a process-supervision or Rust fixture result.

The supplied artifact ZIP SHA256 was checked:
`9daff12bf36d07ce905eea3885981a23872bc4c61268a2409849e7b37cbc28aa`.
The observed toolchain was Rust 1.98.1/LLVM 22.1.8, Xcode 26.3 build 17C529,
SDK 26.2. This repair does not change those inputs.

## Narrow change

Only helper fixture preparation is changed:

- Workspace: `helper-work/source/`, retaining the pinned manifests and lock
- Authenticated vendor tree: `helper-work/vendor/`, a sibling outside the workspace
- Offline config: `helper-work/cargo-home/config.toml`, in the isolated CARGO_HOME

The config contains source replacement with a TOML-quoted absolute vendor path and
`net.offline=true`. The existing sanitized environment retains
`CARGO_NET_OFFLINE=true`. Nested Cargo metadata inherits that CARGO_HOME and offline
setting regardless of its working directory. No project-local config is created
inside the pinned source.

[Cargo's documented configuration hierarchy](https://doc.rust-lang.org/cargo/reference/config.html#hierarchical-structure)
searches the invocation directory/ancestors and CARGO_HOME. The preparation checks
both source and vendor ancestry, and every vendored crate root, for overriding
`.cargo/config` or `.cargo/config.toml`, including symlinks. It also rejects any
Cargo.toml above the sibling vendor root, rather than silently nesting it in a
different workspace. Existing config or directory destinations are never replaced.

No upstream workspace members/excludes, authenticated crate manifests, lockfiles,
features, dependency versions or source bytes are edited. Crate archive checksums
and generated vendor checksum metadata are still authenticated before use. The
same exact 18 helper and 25 RSD filters run with top-level Cargo `--frozen`.

Nested cbindgen Cargo metadata is **offline, not asserted frozen**: the top-level
`--frozen` argument is not inherited as a nested CLI flag. Its resolution can only
see the authenticated vendor set. This repair does not delete or rewrite nested
lockfiles to force resolution.

## Retained input and generated-output evidence

Before native commands, `completed/vendor-layout.json` records the isolated paths,
config hash, registry archive identities and authenticated original file hashes.
After command execution, including a command failure,
`completed/vendor-input-audit.json` records:

- Changed or missing authenticated input files, with expected/actual hashes
- Unexpected symlinks/config overrides
- New generated files and their hashes, separately from original inputs
- Whether the isolated CARGO_HOME config remains unchanged

The staged source manifest is also retained before execution. A separate
`completed/workspace-input-audit.json` checks every original staged source input
and the unchanged workspace Cargo.lock even when Cargo exits nonzero. Both audits
reject a missing, non-directory or symlink root before inspecting descendants.

Any authenticated input mutation fails the helper run; no automatic restoration
is attempted. A newly generated Cargo.lock/header that did not exist in the crate
archive is recorded as generated output rather than silently treated as an
original input. A newly introduced Cargo config is rejected. If such nested
outputs occur in the next native run, their exact evidence remains available even
when Cargo fails before tests.

The generic XCFramework builder and corresponding-source ZIP layout are unchanged
and remain separately disabled. Host/provider registration, app routes and feature
gates are untouched by this helper-only delta.

## Controlled checks and remaining proof

```sh
python3 -m unittest discover -s Integration/Dependencies/idevice/tests \
  -p test_offline_vendor.py -v
```

Eighteen controlled checks pass locally. They cover sibling placement, unchanged
workspace/crate manifests, quoted absolute paths including non-BMP Unicode, inherited config/offline values
in a real Python child/grandchild, enclosing-workspace/ambient/symlink rejection,
generated-output accounting, and audit retention on a simulated Cargo failure.
That failure-wiring fixture does not execute a native toolchain or claim a Rust
result. No Cargo executable is available here; actual nested Cargo/cbindgen
verification remains pending the parent's next native run.

The bounded process limits, Darwin transition repair, exact 43-fixture profile,
source identities and all existing cleanup assertions are unchanged.
