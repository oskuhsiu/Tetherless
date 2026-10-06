# Apple pairing dependency verification candidate

This source recipe composes the independently reviewed stack-storage and bounded
controller-signature production repairs with the reviewed staging-helper union.
The full recipe index covers the exact production and separately selected fixture
profiles. Production Apple staging excludes every synthetic peer variant and
feature. Actual native component and Apple artifact results remain separate
parent-controlled prerequisites for diagnostic consumer use.

This separate recipe compiles the reviewed production pairing overlays for iOS
arm64 and iOS Simulator arm64, checks generated C/Swift interfaces through ordinary
native linking, and creates a local Rust XCFramework. It does not execute iOS
binaries, update a consumer package, publish a release or activate a product gate.
The existing component runner and main source lock remain unchanged.

The Apple source profile has its own explicit verification authorization. It uses
the current combined production overlay bytes and upstream default FFI features,
adding `openssl` for both targets and preserving `obfuscate` for the device target.
Both deployment targets remain 17.0. The fixture-only `tetherless-synthetic-peer`
feature must be absent from selected defaults, the resolved feature graph and
actual compiler-artifact feature records. No transcript fixture source is staged.

## Invocation and locked inputs

```sh
python3 Integration/Dependencies/idevice/build_pairing_apple.py \
  --source "$PINNED_IDEVICE_SOURCE" \
  --crate-cache "$PINNED_CRATE_ARCHIVE_DIRECTORY" \
  --provider-inputs "$VERIFIED_OPENSSL_INPUT_DIRECTORY" \
  --work-dir "$NEW_APPLE_WORK_DIRECTORY" \
  --output "$NEW_APPLE_VERIFICATION_DIRECTORY" \
  --toolchain-lock "$OBSERVED_TOOLCHAIN_LOCK_JSON" \
  --toolchain-lock-sha256 "$RECORDED_TOOLCHAIN_LOCK_SHA256" \
  --recipe-lock-sha256 "$REVIEWED_APPLE_RECIPE_INVENTORY_SHA256"
```

`apple-recipe-files.json` names the exact reviewed recipe/source/provenance files
and their hashes. Its SHA256 is a separate invocation input. This prevents an
arbitrary workspace directory, old build output or unregistered recipe file from
entering the matching-source bundle. The recipe inventory itself is retained in
the final provenance directory.

The source, Cargo.lock, registry archives, production Rust overlays and approved
five-file provider contract retain their existing pins. The provider module is
loaded through the component runner's reviewed receipt verification. Rust 1.98.1,
Xcode 26.3, SDK/tool versions, installed target libraries and actual executable
identities must match the supplied observed toolchain lock. The runner installs
nothing and uses no ambient compiler/provider environment.

## Per-target build and link evidence

Each target gets its own fresh source tree, pristine/derived vendor trees,
CARGO_HOME, Cargo target directory, provider include view and evidence directory.
The existing derived-cbindgen metadata command and exact README filename alias
handling are reused unchanged. The original manifests and lockfiles stay intact.

All native invocations, including toolchain/SDK queries, use the existing bounded
process supervisor: 20 minutes per command, 32 MiB retained log quota, explicit
owned-process cleanup and status receipts. The toolchain adapter reuses the
reviewed command inventory and identity assertions with bounded capture.

For each target, the recipe:

1. Prepares the selected framework's verified 144-header view and an empty owned
   native library directory. Target-prefixed OPENSSL_LIBS is present and empty;
   separate Apple ssl/crypto archives are not supplied
2. Compiles the approved provider header probe with `-fsyntax-only`, without
   linking or executing it
3. Retains `cargo tree --frozen --edges features` and release Cargo JSON. It checks
   the actual FFI compiler artifact retained all defaults and requested features,
   rejects the synthetic-peer feature and binds the chosen archive filename
4. Reuses the component output-selection API for the selected release openssl-sys
   output. Reads remain capped at 1 MiB + 1 byte. The approved provider checker
   requires the expected include/search/version and zero OpenSSL link libraries
5. Asks the same Rust compiler for `native-static-libs`. The strict existing parser
   retains legitimate system library/framework flags; additional ssl, crypto or
   OpenSSL requirements fail the selected single-provider contract
6. Verifies the generated FFI declarations and copies the exact header/module map
7. Compiles and links both reviewed pairing and host probes in C and Swift. Every
   link force-loads the Rust archive with `-Xlinker -force_load` and explicitly
   roots the probe symbol with `-Xlinker -u`. It uses the provider receipt's exact
   selected framework arguments, with no extra OpenSSL search/provider input

Each probe produces only an opaque output hash. Neither the probe nor any iOS
binary is run. There is no nm, disassembly, architecture-format inspection or
Mach-O/CMS/signature admission. Ordinary compiler/linker success is the evidence
being sought, and remains pending the parent-controlled native run.

Every target writes the four reused pristine-vendor, derived-vendor, workspace
and provider input audits on success or failure. A successful earlier target is
reaudited even if a later target fails. Known generated headers remain explicit
outputs in the existing audit receipts. Any failed audit blocks final publication.

## XCFramework and matching source

After both targets and all six language/probe links per target pass, the runner
uses normal `xcodebuild -create-xcframework` with the two Rust archives and their
matching generated headers. It checks only generated Info.plist slice metadata
and opaque file hashes: exactly iOS arm64 and iOS Simulator arm64, and packaged
library/header/module bytes matching the checked compiler inputs. OpenSSL remains
outside IDevice.xcframework as the already selected consumer framework.

The unchanged bounded supervisor launches the exact indexed
`xcframework_operation.py` using the current Python executable and `-I`. That
operation starts only the fixed xcodebuild command, reaps that direct child and
stays alive until Darwin's bounded process-group enumeration contains only the
operation itself. It passes the original four-key PATH/DEVELOPER_DIR/HOME/TMPDIR
environment to xcodebuild. Timeout, interruption, output limits and group cleanup
remain the outer supervisor's responsibility. Child failure or uncertain group
enumeration cannot produce a successful operation.

The byte-identical operation passed the separate tiny-archive macOS proof at
source `7476bde6280c8fec042cf7d12c7fcf4bca68fc31`, run `37399037692`, job
`112061790073`. It observed a live helper tail, then drained naturally in 4.043
seconds under the existing 30-second diagnostic limit, with no cleanup signals.
The retained receipt is `registration/receipts/xcframework-operation-tiny-proof.json`.
That toy result does not establish a complete IDevice artifact. This production
recipe retains its existing command deadline and still requires its own full run.

The output retains per-target command logs/statuses, exact source/provider/input
receipts, feature/build output, compiler/SDK/toolchain identities, link arguments,
opaque output hashes and notices. Successful packaging is followed by another
all-target input audit before the artifact directory is moved to its final path.
Failure evidence remains in the owned work roots.

`create-xcframework.txt` retains bounded `tetherless-packaging-operation` lifecycle
lines; its existing `.status.json` remains the outer supervisor's authoritative
result. Both files already have success-artifact and failure-upload paths. The
Apple build receipt records the underlying xcodebuild command, actual operation
argv and operation source hash separately.

`corresponding-source.zip` reuses the reviewed deterministic ZIP helper and includes:

- All registered staged workspace inputs and the two known generated FFI headers
- Both sibling pristine and exact derived vendor input trees, plus the known new
  plist_ffi header
- Every original checksum-authenticated registry `.crate` archive, preserving
  logical archive keys even where filesystem filename spellings alias
- The explicit reviewed recipe/patch/source/provider metadata files and notices

The recipe inventory includes the exact operation module, its controlled tests
and the tiny-proof receipt, so the existing recipe copy loop places all three in
the corresponding-source bundle. No additional source archive helper is used.

Copies are selected by exact inventories, not arbitrary recursive build output.
Unregistered target, probe, provider or other generated binaries cannot enter the
source ZIP. The committed idevice README symlink is retained through the existing
explicit safe-symlink map. Original and copied source/archive/recipe hashes are
checked around packaging; no source input is edited to make a bundle pass.

The source bundle is made from one fully audited representative target. The
production source input manifest and generated FFI header must match across the
two target builds; both targets' full audit/provenance receipts are retained
separately. The bundle records external dependencies honestly: the exact selected
OpenSSL payloads and separately locked toolchain/SDK remain external inputs.
Provider source/binary equivalence and a byte-identical publisher rebuild are not
established by this recipe.

## Verification boundary

Local verification uses controlled Python processes, synthetic archives/provider
views and simulated compiler/linker output. It checks command construction,
feature/provider exclusion, input/packaging failures and retained evidence. It is
not native Apple build, provider runtime, 74/100 component success, installation or
device acceptance evidence. The parent owns all actual native runs/publication;
consumer activation and the separately paused application work remain outside
this candidate.
