# Frozen workspace metadata with separate build inputs

## Result and scope

This helper-only packet addresses both preparation issues observed before the
43 native fixtures: inactive packaged Cargo configs were rejected globally, and
plist_ffi's nested metadata would independently resolve its older packaged lock.
It keeps original registry inputs intact and makes the generator use the existing
workspace graph. It does not claim a native fixture result.

Source evidence comes from parent-controlled run 37334149741, artifact SHA256
`4ec950881fa9765554be351401ae9f30c47a27eb60316b7414bbb256357e443e`.
The retained plist_ffi and cbindgen source files were verified against the archive
identities in the unchanged workspace lock. The packaged plist_ffi lock has 80
packages, including 59 exact registry versions absent from the current vendor set.
Its five direct dependencies all name older locked versions. The package contains
no plist.h, so writing that header creates a generated output rather than changing
an authenticated input.

## One exact generator adaptation

The new layout is:

- `work/source`: verified patched idevice workspace, with unchanged Cargo.lock
- `work/vendor`: pristine authenticated registry files and generated vendor checksums
- `work/build-vendor`: a separate copy used for this build
- `work/cargo-home/config.toml`: owned offline source replacement pointing to build-vendor

Only this registry source file changes in build-vendor:

`cbindgen-0.29.2/src/bindgen/cargo/cargo_metadata.rs`

Original SHA256:
`d616faea349e4e7ff5a81f944e9c25c3a7b1acc4d7cc421e437464c906d4bd8d`

Derived SHA256:
`fb696646cd0ad4c47711303ac8a8cad26cde38a00923077e87b0d2e364a0b90f`

Its archive origin remains cbindgen 0.29.2 checksum
`befbfd072a8e81c02f8c507aefce431fe5e7d051f83d48a23ffc9b9fe5a11799`,
with registry VCS commit `76f41c090c0587d940a0ef81a41c8b995f074926`.
The derived tree is explicitly different from that archive. Its generated
`.cargo-checksum.json` updates only this source file's hash; both original and
derived checksum-document hashes are retained. No dependency version, package
manifest or packaged lock changes. The original source and MPL license remain
under `upstream/registry-build/cbindgen-0.29.2/` for review.

The adapter requires `TETHERLESS_CBINDGEN_WORKSPACE_MANIFEST`, supplied by the
helper preparation code as the exact owned `source/Cargo.toml` path. Missing,
relative or invalid context fails. It sets Cargo's current directory to that
workspace root and adds `--frozen`, retaining `--all-features`, format version 1,
and the existing optional target filter. It passes the same workspace manifest
to `--manifest-path`. Changing manifest selection alone would not change Cargo's
configuration discovery directory; both are explicit here.

The original binding-crate manifest remains the argument to cbindgen's metadata
function and to its package-selection code. Cargo::load still infers the binding
package from that original manifest and matches its manifest path against the
returned metadata. It obtains the lock from metadata.workspace_root. Thus
plist_ffi's original lock is not the nested resolver's workspace lock. The only
workspace consumers of cbindgen are idevice-ffi and plist_ffi.

The adapter does not change the calling build script's cwd. plist_ffi still writes
its new plist.h beside its own source in build-vendor and builds its normal C shim.
Its authenticated build.rs and packaged lock stay byte-identical. Header bytes and
actual C/Rust compilation remain next-run evidence.

## Configuration discovery, not a content allowlist

The exact owned Cargo invocations are top-level helper tests and patched cbindgen
metadata. Both run from `work/source`. Cargo checks that cwd and its ancestors,
plus the isolated CARGO_HOME. Those effective configurations remain checked before
execution and in the failure-safe final audit.

Crate-root configs under sibling vendor/build-vendor directories are not in those
cwd chains. They remain authenticated source/provenance even if their content is
unknown, malformed or different from the four observed files. This packet removes
the old blanket rejection and exact-file exception mechanism. It does not add a
new generic rule for hypothetical unobserved Cargo invocations.

The four observed raw config files are retained with their provenance and without
line-ending normalization. The existing bounded inventory remains at:

`helper-work/vendor-config-inventory.json`

It records identities, hashes, parsed key names and discovery classification, never
values. Parsing/size/count/output limits produce explicit diagnostic uncertainty;
an unreadable or oversized inactive config is not converted into an admission
failure. Archive/hash/path integrity remains a separate check. All four observed
configs classify as inactive. An effective workspace/ancestor config or changed
CARGO_HOME config still fails independently of vendor inventory completeness.

## Retained evidence and audits

Before native commands, `completed/vendor-layout.json` records pristine and derived
file inventories, the exact source/checksum transformation, offline config hash,
and nested metadata cwd/manifest context. The old archive checksum is origin
provenance, not a claim that the derived source still matches the archive bytes.

The helper's existing failure-safe finally block now retains all three audits:

- `completed/vendor-input-audit.json`: pristine registry tree and owned Cargo config
- `completed/derived-vendor-input-audit.json`: exact derived inputs and generated outputs
- `completed/workspace-input-audit.json`: workspace source/lock and effective Cargo config integrity

Both source trees must preserve all registered input hashes. No general mutation
allowance exists. A changed original or derived packaged Cargo.lock fails. The
pristine tree must not acquire build outputs. The workspace audit also records presence/hash/size for the known generated
ffi/idevice.h and cpp/include/idevice.h outputs, including after failure. These
paths never exempt a registered original from its input hash check. New files in
the derived tree are reported with hashes; a new plist.h is an output, not an original input. Missing,
substituted or symlink roots fail before traversal. The existing process-group,
timeout, log-quota and retained-status guarantees remain unchanged.

The parent workflow needs to retain the new derived-vendor audit alongside the
existing inventory, vendor-layout, workspace and process evidence. It must not
retain or execute native code through this source-only preparation packet locally.

## Controlled validation and remaining evidence

Local checks cover 12 derived-source/wiring cases, 10 config-discovery cases,
18 vendor/audit cases and the unchanged 23 process/summary cases. Fixtures exercise
one-file derivation, checksum changes, immutable original and derived locks,
new-header evidence, effective-config rejection, inactive-config uncertainty, and
all three audit files after a simulated native failure. Synthetic archive tests
substitute their own archive identity inside the fixture only; the production
archive pin and source preimage remain explicit.

No Rust, Cargo or Xcode toolchain ran locally. The exact patch must still compile,
the workspace metadata must identify the correct derived plist_ffi manifest, and
all 18 helper plus 25 RSD fixtures must pass on the parent-controlled native runner.
The helper profile, source overlays, dependency graph, supervisor, host-next-step
packet and acquisition registration are otherwise unchanged.
