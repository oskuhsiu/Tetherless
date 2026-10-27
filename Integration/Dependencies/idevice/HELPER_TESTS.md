# Separate helper-only native fixture profile

`helper-test-profile.json` is distinct from the incomplete composite source lock.
It permits exactly:

- The reviewed `ffi/src/staged_pairing.rs` helper
- Five reviewed bounded RSD/XPC/HTTP2 replacements
- The helper module declaration and existing plist streaming feature
- Unchanged upstream Cargo.lock and the entire existing default FFI feature set

It contains no staged acquisition module, custom CBC code, OpenSSL opt-in feature,
OpenSSL target input, iOS executable, XCFramework or app integration change.
The main composite gates remain false. This runner does not call the composite
builder or its C/Swift/iOS compile-link probes.

## Input preparation owned by repository CI

No user-supplied Rust version or uploaded public source is needed. Rust 1.98.1 is
the selected candidate. The repository owner may use a separate official
`actions/checkout@11d5960a326750d5838078e36cf38b85af677262` step with:

- repository: `SideStore/idevice`
- ref: `3e55c8486b2057e40c1f74aaaa1155c82341cf76`
- an explicit isolated path
- persist-credentials: false
- submodules: false

Verify the complete pristine source with `apply_patch.py --verify-only` before
patching or invoking Cargo. The unused `cpp/plist_ffi` gitlink is neither fetched
nor used by the Rust build. The independently materialized tar remains an
additional hash-locked input option, not a requirement to upload public source.

A separate reviewed registry-acquisition stage may run official Cargo with
`fetch --locked` against the exact upstream workspace lock and a fresh CARGO_HOME.
Retain the `.crate` archives. The offline runner accepts the registry cache folder
containing those archives directly and rechecks every archive's Cargo.lock
checksum before generating its own isolated vendor directory. It never fetches,
updates dependencies, executes the producer's build script, or uses an ambient
Cargo/OpenSSL configuration.

Record the exact installed candidate tools with `record_toolchain.py`; the
repository owner supplies that JSON and its recorded SHA256 to the runner.
The evidence must distinguish first observed candidate identity from previously
validated native-build identity. The existing Xcode 26.3/Rust 1.98.1 profile is
shared with the full recipe; required target components must already be present.

## Exact runner invocation

```sh
python3 Integration/Dependencies/idevice/run_helper_tests.py \
  --source "$PINNED_IDEVICE_SOURCE" \
  --crate-cache "$PINNED_CRATE_ARCHIVE_DIRECTORY" \
  --work-dir "$NEW_HELPER_TEST_WORK_DIRECTORY" \
  --output "$NEW_HELPER_TEST_EVIDENCE_DIRECTORY" \
  --toolchain-lock "$OBSERVED_TOOLCHAIN_LOCK_JSON" \
  --toolchain-lock-sha256 "$RECORDED_TOOLCHAIN_LOCK_SHA256"
```

The runner enforces fresh directories and verifies every source/patch/archive
input. It runs only these host fixture groups using Cargo `--frozen`:

1. `idevice-ffi`, filter `staged_pairing::`, exactly 18 passing tests
2. `idevice`, filter `bounded_rsd_tests`, exactly 25 passing tests

The second command maps the entire pinned default FFI feature set onto `idevice`,
including `rsd`; it does not substitute reduced/default `idevice` features. The
lock and source hashes are rechecked after testing. Missing, failed, skipped or
wrong-count fixture groups do not produce completed evidence.

## Evidence and limits

### Bounded helper-process capture

Only `run_helper_tests.py` uses the new bounded streamed process supervisor. The
incomplete full composite builder remains disabled and its separate capture path
has not been changed or validated by this repair.

Each Cargo fixture group has these fixed limits:

- 20 minutes of command runtime
- 32 MiB of merged stdout/stderr written incrementally to its unbuffered log
- A 128 KiB final-output tail retained in memory for exact summary checks
- Up to 5 seconds after SIGTERM, then up to 5 seconds after SIGKILL for cleanup

Run the surrounding CI job with enough time for both command budgets plus source,
registry preparation and evidence upload; its outer timeout must not be the first
limit. Always retain the work directory's `completed/*.txt` and
`completed/*.txt.status.json` on step failure. Those files are created while a
compiler is still running, rather than after its exit. On success they move into
the completed output directory. Status sidecars distinguish timeout, output quota,
nonzero exit, cancellation and cleanup failure. The primary `stop_reason`, explicit
`output_truncated` flag and observed excess-byte count are retained separately
from final cleanup outcome; a quota failure is never converted
to a passing test even if a success-looking summary appeared earlier.

Commands run in a new owned POSIX session/process group without a shell. The
supervisor terminates that group, escalates if needed, reaps its direct child and
requires an empty group before success. A child exiting zero while descendants
remain is failure, even if they closed stdout/stderr. EOF while the child is still
running does not bypass the deadline. SIGTERM/SIGINT to the main-thread supervisor
request the same bounded cleanup. Trusted Cargo/compiler commands must not detach
into a new session; the supervisor does not search for or kill unrelated processes.
An unconfirmed group-empty state is a failure, including an orphan zombie awaiting
system reaping. Logs remain available for diagnosis; there is no completion claim
when cleanup cannot be confirmed.

Exactly one final Rust summary must report the reviewed passing count and zero
failed, ignored or measured tests. Missing, duplicated, wrong-count or failed
summaries are rejected. The bounded tail must contain that complete summary.
Source/Cargo.lock integrity checks and both fixture filters are unchanged.

Controlled local supervisor checks (no native build or device work):

```sh
python3 -m unittest discover -s Integration/Dependencies/idevice/tests \
  -p test_bounded_process.py -v
```

Success publishes `test-evidence.json`, each group's native output, the exact
profile/source/registry/toolchain manifests, and SHA256SUMS. Failure leaves logs
inside the work directory but does not publish the completed output directory.
Neither success nor source staging establishes iOS compilation/linking, composite
TLS correctness, account/device behavior, or application acceptance.

Portable checks are in `tests/test_native_build.py`. The full materialized source
has also been successfully staged with this helper-only profile locally, producing
487 hash-bound source files with no composite acquisition source or declaration.
Rust fixture execution remains pending until the repository owner runs native CI.
