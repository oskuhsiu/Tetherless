# Host crypto regression fixtures

Run from the repository root after authenticating and applying the namespace
transform to a separate prepared source directory:

```sh
python3 Integration/Dependencies/libimobiledevice/host_tests.py \
  --source /absolute/prepared-source --output /absolute/new-results \
  --cc /absolute/path/to/installed/cc
python3 -m unittest discover \
  -s Integration/Dependencies/libimobiledevice/probes/host -p 'test_*.py' -v
```

The source directory contains `root/3rd_party/ed25519` and `glue`. The optional
compiler path selects an existing host GCC/Clang. No dependency installation,
source rewriting, cross-compilation, or phone-binary execution occurs.

For an exact Xcode toolchain, also pass `--sdk /absolute/path/to/MacOSX.sdk`.
The SDK must be an existing directory. Its explicit `-isysroot` is applied to
every compile/link operation, including the ASan availability probe, but never
to executable launches. Ambient `SDKROOT` and `DEVELOPER_DIR` are not inherited.
Without `--sdk`, the compiler arguments remain unchanged.

## What is exercised

- Independent Ed/glue translation units use each library's real header. Both
  complete SHA512 implementations are compiled as separate objects and linked
  into the same executable. All four namespaced Ed SHA entry points and all
  four unchanged public glue SHA entry points are called.
- SHA512 empty, `abc`, the standard 112-byte long vector, and one million `a`
  bytes are checked against fixed digests with one-shot, single-update, and
  irregularly chunked input. Explicit zero-byte updates are included.
- Immediate context/output canaries are checked after every SHA operation.
  The fixture asserts and prints both actual context sizes, asserts the Ed
  context ends at `buf`, and verifies glue's additional `num_qwords` location
  and value. On x86_64 the observed sizes are 208 and 216 bytes.
- Ed25519 uses the public RFC8032 section 7.1 TEST 1 seed, expected public key,
  and exact empty-message signature. Repeated signing, verify, changed-message,
  changed-signature, and changed-public-key rejection are checked.
- A fixed synthetic scalar checks combined, public-only, and private-only
  `add_scalar` paths, matching adjusted keys/signatures, adjusted-key verify,
  original-key rejection, tamper rejection, and output guards. This is an
  algebraic consistency test, not an independently published scalar KAT.

## Evidence and bounds

`result.json` retains source/fixture SHA256 hashes, compiler identity, command
arguments, context layout, stage outcomes, and limits. Every compiler, linker,
and executable invocation uses the existing `idevice/bounded_process.py`
supervisor. Each command has a log and status JSON with cleanup receipts.
Compile/link commands are bounded to 120 seconds, runs to 30 seconds, each log
to 4 MiB, and summaries to 64 KiB. Output directories must be new.

A separate tiny compile/run establishes ASan availability. If it exits with an
ordinary supervised failure, availability is explicitly reported; bounds,
cancellation, and cleanup failure are fatal. If availability succeeds, any
sanitized fixture compile/run failure is fatal. ASan runs with leak detection
off; this suite targets memory corruption in the linked crypto calls. UBSan is
not run: unmodified upstream arithmetic may contain signed-shift undefined
behavior, so ASan success must not be reported as general UB safety.

These are host-only regression results. They do not establish iOS integration,
real-device acceptance, or a complete cryptographic/security audit. No private
keys or credentials are used beyond the explicitly public RFC test seed.
