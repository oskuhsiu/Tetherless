# Disabled OpenSSL target-input contract

`target-inputs.json` describes the approved direction for an opt-in existing-library
TLS implementation. It does not activate that feature or alter the executable
builder, main source lock, helper-only test profile, consumer package or app routes.
It contains no custom TLS/CBC implementation.

## Pinned evidence

- Repository: `krzyzanowskim/OpenSSL`
- Commit: `fdc9231384f37f053dffe058fd6dfc6c5072dae5`
- Git tree: `e7c94a8efdade4b77561c7176ba7cc4865bc32ee`
- Existing package version: **3.6.2000**, OpenSSL engine **3.6.2**
- Static-configuration producer script: Git blob
  `65f0c109ced0bacd0aa4526531d1ccefa526a55e`

The complete metadata inventory pins 143 header blobs per platform, three complete
header-tree hashes, and six separate static archive blobs with their byte counts.
The producer's [Apple build script](https://github.com/krzyzanowskim/OpenSSL/blob/fdc9231384f37f053dffe058fd6dfc6c5072dae5/scripts/build.sh)
passes `no-shared`. This records the recipe; it does not prove what any local
library binary contains. No producer script, native binary or artifact inspector
has been executed here.

Existing unchanged Cargo.lock packages are openssl 0.10.76, openssl-sys 0.9.112,
and tokio-openssl 0.6.5. Their exact registry checksums are included. There is no
openssl-src entry in that lock. Activating the opt-in feature must retain the
existing AWS-LC/rustls defaults and requires the separately reviewed source change.

## Exact input layout

For the respective Rust target, use only these repository input paths:

- aarch64-apple-ios: `iphoneos/lib/libssl.a`, `iphoneos/lib/libcrypto.a`,
  complete `iphoneos/include/OpenSSL/`
- aarch64-apple-ios-sim: `iphonesimulator/lib/libssl.a`,
  `iphonesimulator/lib/libcrypto.a`, complete `iphonesimulator/include/OpenSSL/`
- aarch64-apple-darwin fixture host: `macosx/lib/libssl.a`,
  `macosx/lib/libcrypto.a`, complete `macosx/include/OpenSSL/`

After all bytes match their pinned Git blobs and sizes, create a fresh isolated
input view under `$VERIFIED_OPENSSL_INPUTS/<rust-target>/`:

- `lib/libssl.a` and `lib/libcrypto.a`
- `include/OpenSSL/` and `include/openssl/`, both exposing the exact same complete
  verified header tree

Both capitalizations matter: packaged headers include `OpenSSL/...`, while
openssl-sys expects `openssl/...`. Use byte-identical views or explicit safe
internal aliases. Do not rely on case-insensitive lookup or permit an alias to
escape the verified input root. On a case-insensitive filesystem one physical
directory can satisfy both lookups. Preserve original source headers/notices.

## Target environment isolation

Each target's JSON has its explicit uppercased/underscore-prefixed variables:

- `<TARGET>_OPENSSL_LIB_DIR`: that target's isolated `lib`
- `<TARGET>_OPENSSL_INCLUDE_DIR`: that target's isolated `include`
- `<TARGET>_OPENSSL_STATIC=1`
- `<TARGET>_OPENSSL_NO_VENDOR=1`

For example, the simulator prefix is `AARCH64_APPLE_IOS_SIM_`; the fixture-host
prefix is `AARCH64_APPLE_DARWIN_`. A later enabled runner must start with a clean
environment/config and use only the intended target's explicit input values.
Do not inherit arbitrary OPENSSL, PKG_CONFIG, Homebrew, system-search, framework
or host-library fallbacks. Preserve Cargo.lock and verify its existing crate
archive checksums before compiling. Target-library setup is not dependency update
authority.

All three pinned configuration.h files were read and Git-blob verified. They
define `OPENSSL_NO_SSLKEYLOG` and `OPENSSL_NO_DYNAMIC_ENGINE`. The target contract
requires rechecking those exact headers and compiling preprocessor assertions
against each actual selected include view. Header text alone does not prove binary
configuration correspondence or runtime behavior.

## Package-resolution mapping still needs explicit treatment

The [Swift package](https://github.com/krzyzanowskim/OpenSSL/blob/fdc9231384f37f053dffe058fd6dfc6c5072dae5/Package.swift)
selects `Frameworks/OpenSSL.xcframework`. Its platform framework directories are
recorded in the contract. The six requested `platform/lib/*.a` inputs are separate
repository paths, outside that binary target. An XCFramework-only artifact or a
successful Xcode package resolution does not establish that these static paths
are available, equivalent, or already linked.

If the pinned resolved package checkout contains the separate static paths, verify
them there before staging. If it contains only the XCFramework, this contract is
not satisfied: report the missing paths rather than renaming/extracting a framework
binary or substituting a system library. Authorized repository CI can obtain the
same pinned repository source through the existing pinned official checkout Action;
no local shell clone or download is part of this contract.

Final linkage ownership is also unresolved. Do not silently introduce a second
OpenSSL provider alongside the existing consumer framework, or remove that
framework. The integration owner must select and verify a compatible final link
arrangement. Matching version labels alone are insufficient.

## Current evidence level

The metadata inventory and source configuration are checked. Static archive bytes,
complete local header sets, target native compilation/linking, runtime behavior,
and final consumer linkage remain pending. The contract stays disabled, and the
helper-only native test run does not consume it.

Portable metadata checks:

```sh
python3 -m unittest discover -s Integration/Dependencies/idevice/openssl-candidate/tests -v
```
