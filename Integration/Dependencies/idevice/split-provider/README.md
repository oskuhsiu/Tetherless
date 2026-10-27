# Disabled split OpenSSL provider inputs

This opt-in build adapter prepares authenticated inputs for the separately reviewed
staged-pairing source. No existing consumer, source profile, Cargo dependency,
global OpenSSL initialization or app gate is changed. Native compilation and
runtime proof remain pending.

## Exact provider ownership

The pinned provider is `krzyzanowskim/OpenSSL` commit
`fdc9231384f37f053dffe058fd6dfc6c5072dae5`, package 3.6.2000, headers 3.6.2.
`target-inputs.json` locks 443 permitted files / 40,506,667 bytes from the
parent-controlled capture in run 37339519028. Every entry pins its path, length,
Git blob, SHA256 and executable mode. Framework payloads and archives are handled
only as opaque bytes. Signing/privacy resources are outside this inventory and
are neither inspected nor admitted here.

- Host `aarch64-apple-darwin`: 143 macOS headers and the exact separate
  `macosx/lib/libssl.a` and `libcrypto.a`; explicit `OPENSSL_LIBS=ssl:crypto`
- Apple `aarch64-apple-ios` and `aarch64-apple-ios-sim`: the selected framework's
  144 headers, an empty owned native-library directory, and an explicitly present
  empty `OPENSSL_LIBS`. The final consumer link uses the selected existing
  `OpenSSL.framework`. The separate Apple static archives are not selected

These values are target-prefixed, alongside explicit INCLUDE_DIR, LIB_DIR,
STATIC=1 and NO_VENDOR=1. Empty LIBS is intentional: omission would make pinned
openssl-sys 0.9.112 default to ssl/crypto. STATIC=1 with an empty list does not
declare the framework's binary linkage type or add a native library.

## Build-owner API

Import `provider_inputs.py` by path; no import has side effects.

1. `prepare_inputs(source, destination, target)` verifies the locked inventory
   and creates a fresh owned header/library view with a JSON receipt. Both
   `OpenSSL/` and `openssl/` header spellings resolve to identical verified bytes.
   It preserves the provider's complete LICENSE.txt. It runs no external tool
2. `build_environment(base, receipt)` rechecks source/view identities and extends
   the already verified `native_environment` dictionary, never `os.environ`.
   Only that helper's explicit environment keys and the owned cbindgen workspace
   pointer survive. The caller then adds its locked target SDK/compiler settings
   and reproducible path-remapping flags. Do not remerge ambient variables
3. Compile `header_probe.c` with each selected target compiler/SDK and include
   view. Retain the command, toolchain identities, output and bounded process
   status. It checks version, key-log/dynamic-engine configuration and PSK API
   header availability; it does not prove binary configuration
4. Build using the existing frozen Cargo lock and offline authenticated vendor.
   Capture the selected openssl-sys build script's own `output` file, not a merged
   Cargo log. `check_build_script_output(bytes, receipt)` checks exact header and
   library-search paths, version metadata and library directives. Apple must emit
   no link-lib directive; host must emit exactly static ssl and crypto. Both Cargo
   directive spellings are checked. Additional link arguments/compiler flags and
   unsupported modern metadata are rejected; pinned openssl-sys uses legacy
   metadata output
5. `audit_inputs(receipt)` rechecks all allowed source bytes and the selected view
   before final consumer linking and after every build, including failure. Retain
   this receipt alongside original/derived vendor and workspace audits. Apple
   `final_link_arguments` names the selected framework's parent and OpenSSL only;
   the integration runner must inspect its complete command to exclude any second
   OpenSSL provider. Original framework Headers/Modules inventories are checked
   completely to prevent unlisted umbrella-header or module discovery. This API
   alone cannot establish the complete link graph

Framework sources stay in the verified input root, so keep that root and the view
alive and immutable through final linking. Use separate owned target/output roots
for host and Apple work. The adapter never edits a captured framework or extracts
archives from one. It does not modify process-global configuration or introduce a
custom OpenSSL initialization override; standard binding initialization can still
consult runtime configuration. Runtime isolation is not proved by these inputs.

## Provenance and remaining proof

Pinned binding sources are the existing Cargo.lock versions openssl 0.10.76,
openssl-sys 0.9.112, tokio-openssl 0.6.5 and jktcp 0.1.7. Selected authenticated
registry files were retained in runs 37323350367 and 37334149741. The source basis
for present-empty LIBS and explicit-directory discovery is openssl-sys
`build/main.rs:219-239,497-503` and `build/find_normal.rs:7-12`. Source and callback
review receipt hashes are recorded in the input contract.

Actual captured bytes have been staged and reaudited locally for all three
targets. Portable controlled fixtures cover key presence, byte/mode/path changes,
owned-view substitution, environment preservation and output directives. These
checks do not execute Rust, Clang or OpenSSL. Native tests, resolved feature graph,
forced C/Swift/Rust single-provider linking, actual version/configuration/PSK
behavior and Apple compatibility still require the parent-controlled build.
Neither header labels nor matched hashes establish source/binary equivalence.

Official pinned provider source:
https://github.com/krzyzanowskim/OpenSSL/tree/fdc9231384f37f053dffe058fd6dfc6c5072dae5

Run portable checks with:
`python3 -m unittest discover -s Integration/Dependencies/idevice/split-provider/tests -v`
