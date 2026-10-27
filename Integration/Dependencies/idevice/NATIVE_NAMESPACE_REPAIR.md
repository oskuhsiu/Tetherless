# Native provider namespace repair

This is a build/link integration candidate. It does not activate the application,
change a parser, add `PLIST_OPT_COERCE` support, or establish device acceptance.

## Evidence and rejected shortcuts

At consumer `3f717ea5441d2cacee13e1d078e5ba7f1484edc5`, diagnostic run
37407474925 / attempt 1 / job 112088119151 passed preparation and artifact
authentication. Debug first failed at `xcodebuild.txt:8989`: Clang could not merge
the `plist_write_options_t` definitions imported through IDevice and
libimobiledevice. The latter has `PLIST_OPT_COERCE`; the appended Rust-provider
header does not. Release completed, but its final command at line 7005 directly
links `-lidevice_ffi` and `-limobiledevice`. No retained link map establishes which
old overlapping symbols were selected. Release's compile pass remains valid
evidence of that narrower result.

The authenticated Rust artifact from producer
`9ee2ccc9bd3519053781087acde54d4b4ee43236`, run 37400684000, contains 100
`_plist_*` names in its device archive index. Its pinned `plist_ffi` allocations
are Rust `PlistWrapper` values. The pinned C provider's build recipe merges C
libplist into libimobiledevice.a. Its public header also changes eight mutator
returns from `void` to `plist_err_t`: array set/append/insert/remove/item-remove
and dictionary set/remove/merge. Other overlapping names include
`afc_client_free`, `lockdownd_client_free`, `idevice_free`, `misagent_install`,
`house_arrest_client_free`, and `debugserver_command_free`, with different
provider-specific handle and return declarations.

Adding only an enum member, replacing the entire Rust header with the newer C
header, hiding imports, renaming only header spellings, or changing archive order
would leave incorrect declarations or unresolved provider ownership. None is used.

Pinned C sources:
- libimobiledevice build: `SideStore/libimobiledevice-xcframework` at
  `0f88f7bbd1aa9713d8c8c2255df31f2b25ff9d8a`, `justfile`
- libplist: `libimobiledevice/libplist` at
  `32428abacb909988e8e960a8845a6430b17b6a60`, `include/plist/plist.h`,
  blob `e720aac920447186f9ce04c70bc972b7a842c15e`
- Existing C release ZIP SHA-256:
  `7ccbdd56b074807461fc43d2e32ba92f20df2501a6c14cf9f64a917e7f3fe6e7`

## Exact adaptation

`namespace/contract.json` pins all source preimages/postimages and symbol names.
Only the Apple verification profile opts into this adaptation. Host fixture
profiles and pristine upstream/registry bytes remain unchanged.

1. Change 655 Rust export attributes across 61 FFI and seven plist_ffi source
   files from `no_mangle` to explicit `export_name = "tetherless_native_..."`.
   Rust function names, bodies, signatures, layouts, internal calls, features and
   cfg attributes are unchanged. The nine already-unique pairing exports remain
   byte-identical. Two C varargs entry points and their Rust shim reference use
   the same explicit namespace. There are no old-name aliases.
2. Record the plist_ffi changes and generated checksum metadata in the owned
   derived vendor. Keep the original crate checksum and pristine vendor intact.
3. Preserve the existing baseline/scoped result-header comparison. Apply a
   separate, recorded public-header token transformation to the generated result:
   plist typedefs, enum members, macros and function declarations receive the
   namespace. Every old declaration and numeric value is retained. Existing
   void-returning Rust mutators stay void; modern C declarations stay separate.
4. In the diagnostic consumer only, transform exactly 244 code-token occurrences
   across 102 names in the exact privacy-prepared IdeviceGateway.swift.
   Comments, logs, flow and lifetime code remain byte-identical. The C gateway
   and both Tetherless pairing bridges are unchanged. Normal prepare.py still
   targets the old release and is deliberately not changed.

The complete pinned-source caller scan covered 407 SideStore Swift files, its
C-family sources, and 34 minimuxer Swift files. Both gateways keep their own plist
handles internally; their common API passes Swift Data/String/dictionaries and
primitive values. Renaming raw-pointer typedefs does not create new runtime type
checking. Safety here depends on that verified existing boundary plus separate
linker symbols, not on a claim that all void pointers are interchangeable.

## Verification contract

- Each target must expose exactly the 382 expected namespaced exports present in
  the authenticated prior target, with no old aliases. Source registration also
  covers exports behind inactive features.
- Independently authenticate the entire existing C release archive before safe,
  bounded extraction. Preserve its original ZIP; rederive the inventory from it
  on every audit rather than trusting editable receipt claims.
- Compare ordinary `nm -g -U -j` output for both providers. Their defined external
  symbol sets must be disjoint. No Mach-O parser is introduced.
- Retain all six old C/Swift probes per target and add two mixed-provider probes
  per target. Force-load both actual archives, import both modules, check old
  Rust void-return and C error-return shapes, and retain the linker maps. Probes
  take function addresses; neither provider functions nor probe binaries execute.
- Recompute the exact public-header transform and namespace symbol checks when
  authenticating the producer artifact for consumer binding. A prior unnamespaced
  producer cannot satisfy the new contract.
- In the actual app build, require the processed C archive and selected C
  plist header/module map to match the mixed-provider proof, in addition to all
  existing Rust/OpenSSL/source/sentinel checks. Retain the app linker map.
- Preserve all process deadlines, synthetic-feature rejection, input audits,
  Swift fixture assertions, runtime capability gates and no-signing settings.
  Failed secondary audits must not erase a primary build/link failure.

The source/profile/recipe/workflow hashes necessarily change. A new genuine
producer and then a separately authenticated Debug/Release consumer build are
required. The old producer remains genuine historical evidence and is never
relabeled as verification of this namespace. Until those native results exist,
Clang/Swift import/link compatibility remains pending.
