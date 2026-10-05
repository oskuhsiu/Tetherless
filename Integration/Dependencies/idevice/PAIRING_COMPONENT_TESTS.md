# Pairing component fixture runner

This opt-in host runner selects either 72 acquisition/helper/RSD fixtures or 92
fixtures including the separate bounded host module. It produces component-test
evidence. It does not build an Apple artifact, enable a product route or change
upstream default features. The main source lock remains the approved baseline;
only the explicitly named component profile is staged.

The acquisition profile stages 11 reviewed overlays plus the guarded FFI module
and plist streaming-feature edits. The combined profile stages 14 overlays and
adds the reviewed host declaration. The helper overlay is the approved
`e827e5a464782009f4be7ab5557fecc449fe266836a3851bd1cbc97fa5637933` version.
All upstream source/dependency pins and Cargo.lock bytes remain unchanged.
The test-only source profiles are complete; artifact and consumer activation
fields remain false.

## Invocation and selected tests

Use a fresh work/output directory and the same pinned source, authenticated crate
archives, observed toolchain lock and exact captured OpenSSL input root:

```sh
python3 Integration/Dependencies/idevice/run_pairing_component_tests.py \
  --profile acquisition-only \
  --source "$PINNED_IDEVICE_SOURCE" \
  --crate-cache "$PINNED_CRATE_ARCHIVE_DIRECTORY" \
  --provider-inputs "$VERIFIED_OPENSSL_INPUT_DIRECTORY" \
  --work-dir "$NEW_COMPONENT_WORK_DIRECTORY" \
  --output "$NEW_COMPONENT_EVIDENCE_DIRECTORY" \
  --toolchain-lock "$OBSERVED_TOOLCHAIN_LOCK_JSON" \
  --toolchain-lock-sha256 "$RECORDED_TOOLCHAIN_LOCK_SHA256"
```

Use `--profile combined` for the additional 20 host fixtures. These are separate
runs with separate work/output roots. The selected counts are:

- Helper `staged_pairing::`: 18
- RSD `bounded_rsd_tests`: 25
- Composite `staged_acquisition::`: 9
- Contributory guard: 3
- Remote-pairing socket: 2
- OpenSSL tunnel tests: 4
- OpenSSL tunnel fixtures: 4
- Owned packet I/O: 7
- Combined only: host FFI 8, host tests 5, host frame tests 3, OPACK tests 4

Every suite requires one final passing summary with its exact count and zero
failed, ignored or measured tests. The total must be exactly 72 or 92. Per-suite
logs/statuses are numbered from `01-idevice-ffi.txt` through the selected eighth
or twelfth suite; suites sharing a package never share an evidence path.

## Explicit host provider and compilation inputs

The runner verifies the five provider-contract files against reviewed manifest
SHA256 `2f4e49207716cc79c8561d517011fdc7d5bf775cfe55d612f40380de2e36302e`
before importing its module. It calls the reviewed `prepare_inputs` for
`aarch64-apple-darwin`, then `build_environment` and `audit_inputs`. The host view
contains the exact 143-header tree and separate verified static ssl/crypto
archives. Its target-prefixed LIBS is explicitly `ssl:crypto`; STATIC and NO_VENDOR
are both `1`. The host runner refuses framework final-link arguments.

The provider adapter accepts only the explicit verified native environment. The
runner then adds the recorded Xcode selection, selected macOS SDK/compiler paths
and owned path-remap flag. It never merges ambient process variables. FFI tests
use their existing defaults plus explicit `openssl`; idevice tests retain the
same FFI default feature mapping plus `openssl`.

The approved header probe runs through clang with `-fsyntax-only`, the selected
macOS SDK, arm64 architecture and verified include root. It is neither linked nor
executed. Two bounded `cargo tree --frozen --edges features` logs retain the
resolved package feature graphs. Every fixture command also uses `--frozen`.

Apple device/simulator builds are outside this runner. Their separately reviewed
contract retains present-empty OPENSSL_LIBS, an empty owned native-search directory
and the selected framework as final-link provider. Host success cannot establish
that Apple linkage or runtime result.

## Selected openssl-sys evidence

Cargo fixture commands request JSON compiler/build messages while retaining normal
Rust fixture summaries. The runner selects only `build-script-executed` events
for the exact crates.io openssl-sys 0.9.112 package ID. It uses the event's OUT_DIR
to locate the corresponding output file under the owned target/configuration
path. It never chooses an output by an unconstrained filesystem glob.

[Cargo's message protocol](https://doc.rust-lang.org/cargo/reference/external-tools.html#build-script-output)
provides these events even for cached build-script results. JSON compiler output
and later fixture-harness output are distinct; the summary parser still requires
the exact fixture outcome.

Each selected output file is read with a 1 MiB + 1 byte cap, retained before
validation, and passed to the approved provider `check_build_script_output`.
That check reaudits the inputs and verifies exact include/search paths, OpenSSL
header version and static ssl/crypto directives. Rejected provider output stays
available for diagnosis. This proves selected build-script directives, not Apple
single-provider linkage or product acceptance.

The reusable output helpers accept an explicit `debug` or `release`
configuration. This runner selects host debug only. A later Apple orchestrator
can reuse output selection and retention without duplicating it; it must retain
its own separately reviewed target and final-link controls.

## Failure retention and publication boundary

Source staging and vendor preparation reuse the reviewed exact derived-cbindgen
and README alias implementation. The original vendor tree stays separate from
the exact derived build tree. Before commands, the source and vendor-layout
receipts are retained. Existing bounded capture limits apply to SDK/tool lookup,
header compilation, feature graphs and every Cargo fixture command.

The runner's finally block independently attempts and writes all four audits:

- `vendor-input-audit.json`
- `derived-vendor-input-audit.json`
- `workspace-input-audit.json`
- `provider-input-audit.json`

One audit error does not suppress the remaining receipts. Generated header
presence/hashes remain in the existing workspace/derived audits. Any changed
original, derived, workspace or provider input blocks success publication.
A pre-existing command/preparation failure remains the primary error after its
audits are retained. No audit failure can convert it into success.

All failure evidence remains in `work/completed/`; preparation inventory receipts
remain at their existing work-root paths. On full success only, completed evidence
is moved to the requested output directory with hashes, selected profile,
toolchain observations, feature graphs, compiler inputs, provider outputs and
fixture results. Produced native test executables are not published as a product.

No native compiler or Rust fixture has been executed by this worker. The 72/92
native outcomes, host provider runtime behavior, Apple final linkage and separate
product integration acceptance remain pending parent-controlled verification.
