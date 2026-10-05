# Independent host-generation native fixture profile

This separate host-only packet rebases the reviewed source/test profile onto the
shared tooling in `tetherless-helper-plist-key-types-delta`. The shared vendor,
toolchain, bounded-process, helper runner and helper profile files are copied
unchanged. `apply_patch.py` retains its already reviewed one-line admission of
`candidate-profiles/host-only.json`. Only the host runner, its scoped wiring tests
and this document are newly adapted from the earlier host-only packet.

The host-only profile stages exactly three reviewed overlays:

- `ffi/src/bounded_pairing_host.rs` (new)
- `idevice/src/remote_pairing/responder.rs` (exact original preimage replaced)
- `idevice/src/remote_pairing/opack.rs` (exact original preimage replaced)

The only other source change is the guarded declaration:

```rust
#[cfg(all(unix, feature = "remote_pairing"))]
pub mod bounded_pairing_host;
```

It does not stage helper/RSD validation overlays, composite acquisition, custom
CBC, OpenSSL feature changes or packet-I/O additions. Both Cargo manifests and
Cargo.lock retain their original bytes. Default FFI features remain intact.

The immutable host-source receipt is SHA256
`6ea4370a0ec3c9470ff2c6690c576bc93b063cf010be9d14df5928e82949818a`.
Only fixture execution is authorized by this profile; artifact/application
activation remains false. The combined/acquisition profile is a separate disabled
registration and is unnecessary for this run.

## Invocation

Reuse the exact verified source, registry archives and observed toolchain inputs
from the helper preparation, with fresh work and evidence directories:

```sh
python3 Integration/Dependencies/idevice/run_host_tests.py \
  --source "$PINNED_IDEVICE_SOURCE" \
  --crate-cache "$PINNED_CRATE_ARCHIVE_DIRECTORY" \
  --work-dir "$NEW_HOST_TEST_WORK_DIRECTORY" \
  --output "$NEW_HOST_TEST_EVIDENCE_DIRECTORY" \
  --toolchain-lock "$OBSERVED_TOOLCHAIN_LOCK_JSON" \
  --toolchain-lock-sha256 "$RECORDED_TOOLCHAIN_LOCK_SHA256"
```

All executions use Cargo `--frozen`; native tool/source/archive identity must
match their locked inputs. The runner selects exactly these reviewed groups:

1. idevice-ffi `bounded_pairing_host::`: 8 passing tests
2. idevice `bounded_host_tests`: 5 passing tests
3. idevice `bounded_host_frame_tests`: 3 passing tests
4. idevice `bounded_opack_tests`: 4 passing tests

Logs/statuses have stable per-suite names: `01-idevice-ffi.txt`,
`02-idevice.txt`, `03-idevice.txt`, `04-idevice.txt` and each matching
`.status.json` sidecar. The evidence explicitly records all four pairs.

Twenty authored fixtures are expected. Six older OPACK tests outside the new
filter must not inflate this count. Each group requires one exact final summary
with zero failed, ignored or measured tests. Cargo-list output is not yet available;
a runtime test-name receipt can be added when native evidence supplies it.

The host runner calls `prepare_offline_vendor(..., derive_metadata=True)` and
reuses the reviewed separate build-vendor preparation. The pristine authenticated
registry inputs remain in `work/vendor`; `work/build-vendor` contains the exact
reviewed cbindgen metadata adaptation and its generated checksum metadata.
The isolated `CARGO_HOME` points to that derived copy. The nested cbindgen Cargo
metadata command uses the owned workspace cwd/manifest, `--frozen`, and the
unchanged workspace lock. `derived_cbindgen.py` is included in the tooling hashes.

The existing exact README filename-alias reconciliation is inherited unchanged.
Its raw inventory and explicit reconciliation evidence remain separate. This
host adaptation introduces no inventory, reconciliation or dependency change.

All three audits are retained in `work/completed` when a fixture command fails,
and included in the evidence directory on success:

- `vendor-input-audit.json`: pristine registry inputs and owned Cargo config
- `derived-vendor-input-audit.json`: derived inputs and newly generated outputs
- `workspace-input-audit.json`: workspace inputs, lock and generated headers

The derived audit records newly generated `plist_ffi-0.1.6/plist.h` by hash.
The workspace audit records presence, hash and byte length for newly generated
`ffi/idevice.h` and `cpp/include/idevice.h`, including after command failure.
Generated-header paths never exempt an authenticated input from its hash check.
An unchanged-input failure blocks publication and retains all three audits.
Preparation failures before a vendor receipt exists remain preparation failures;
any inventory diagnostics already written stay in the owned work directory.

The process supervisor retains the reviewed 20-minute per-command, 32 MiB log,
128 KiB tail and bounded TERM/KILL cleanup limits. Since four groups are selected,
the outer job budget must account for all selected command budgets plus preparation
and evidence upload. Keep incremental logs and status sidecars on failure. The
supervisor's Darwin EPERM state handling is reused; uncertain groups never count
as empty.

Success produces host-only test evidence and exact input/tooling manifests. It
creates no XCFramework, runs no C/Swift link probe, and executes no real device,
account, pairing acceptance or app route. Host C/Swift probe sources are registered
separately for later compile/link work and must never be executed.

## Local evidence

The complete pinned source is staged and compared with the earlier reviewed host
stage. It contains 487 manifest files, with only the three host overlays and one
guarded module declaration changed from the pinned source. No helper/acquisition
source or declaration is included. The Cargo manifests and lock remain unchanged.

Six scoped profile tests verify source boundaries, counts, guards and receipts.
Five host wiring tests use controlled archives and the real bounded supervisor
with Python subprocesses. They verify all four exclusive log/status pairs and
the aggregate count of 20; fail each of the four suite positions independently;
retain three audits and generated-header evidence; reject changed pristine,
derived, workspace and Cargo config inputs; reject incorrect fixture counts;
and reject helper/acquisition staging before vendor preparation.

Shared checks cover 12 derived-metadata, 18 vendor/audit, 10 packaged-config,
8 inventory-diagnostic and 10 README-alias tests. The positive real-volume alias
test skips on a case-sensitive local filesystem: 68 checks pass and one skips,
out of 69 total. These checks and the synthetic
Python summaries are portable wiring evidence. Rust compilation and the actual
20 Rust fixtures remain pending parent-controlled native execution.

```sh
python3 -m unittest discover -s Integration/Dependencies/idevice/tests \
  -p test_host_profile.py -v
python3 -m unittest discover -s Integration/Dependencies/idevice/tests \
  -p test_host_vendor_wiring.py -v
```
