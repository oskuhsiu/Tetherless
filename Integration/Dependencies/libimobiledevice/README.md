# Isolated C-provider namespace derivation

Status: source/test candidate only. No new C XCFramework is accepted until its exact macOS producer run and retained output have been independently verified. This directory does not change the Rust recipe, application consumer, signing/parser/admission, manager startup/replacement, OTA delivery or stopped picker diagnostics.

## Defect and strictly bounded correction

At Tetherless `6af17537bcebfa797bf3c2659f749edd4c9d53eb`, producer run `37446415281` passed the complete 382-name Rust namespace and Rust/C disjointness checks, then failed device mixed-C force loading. The unchanged upstream C archive contains two definitions of `sha512`, `sha512_init`, `sha512_update`, `sha512_final`, in archive members 41 and 81. Removing force loading would hide the condition. The Ed25519 context is smaller than glue's context, which has an additional `int num_qwords`; wrong lazy binding is therefore a source-level ABI hazard, not merely an untidy duplicate. Historical app link success does not prove that hazard executed.

`namespace.py` authenticates all retained review files and the entire bundled Ed25519 subtree before changing six exact source files. It renames exactly 30 code identifiers, excluding comments and string literals, from the four names above to `tetherless_c_ed25519_sha512` and its matching suffixes. The complete before/after Git-blob SHA, SHA-256, byte counts and replacement counts are in `namespace-contract.json`. Inverse transformation must reconstruct every original byte. Context types/layouts, includes/filenames, static `sha512_compress`, all algorithm bodies and glue's public names remain unchanged. There is no binary archive rewriting, member deletion or symbol filtering.

## Immutable sources and first-observed toolchain

The complete authenticated tree manifests in `provenance/` pin:

- Main: `SideStore/libimobiledevice-xcframework@0f88f7bbd1aa9713d8c8c2255df31f2b25ff9d8a`
- libplist: `libimobiledevice/libplist@32428abacb909988e8e960a8845a6430b17b6a60`
- glue: `libimobiledevice/libimobiledevice-glue@da770a7687f35fbb981db4d7b47b1b032cd5c2c7`
- usbmuxd: `libimobiledevice/libusbmuxd@93eb168bf6b07472d17781328c21df0c60300524`

The latter three exactly match the main tree's Git links. `upstream/` retains a review/host-fixture subset with original license bytes. It is not substituted for complete source acquisition. The producer verifies every acquired file against full tree Git-blob/size/mode metadata, rejects missing/extra source files or symlinks, retains pristine complete trees, and scans every C/H source for the original four names. It copies fresh source trees for each build and retains the complete source manifest and scan. Only authenticated source files enter the build.

The original upstream recipe uses `macos-latest` and unpinned Homebrew installation. This is a new owned derivation, not a claim to reproduce original release bytes. The producer enforces the currently verified Apple fingerprint: arm64 macOS 15.7.9/24G830, Xcode 26.3/17C529, Clang 17.0.0 clang-1700.6.4.2, Swift 6.2.4, iOS/Simulator SDK 26.2/23C57. The `macos-15` label alone is not immutable.

No tool installation or upgrade is performed. Preinstalled Autoconf, Autoheader, Automake, Aclocal, GNU libtoolize, pkg-config, m4 and make must exist. The keg-only GNU m4 dependency must resolve through the existing /opt/homebrew/opt/m4 route (minimum 1.4.16); system-m4 fallback, installation and relinking are rejected. Their exact paths, versions and executable hashes, selected Homebrew installation scripts/macros and the pkg-config macro are recorded before use, and checked again afterward, including on build failure. The exact current recipe, pristine/derived source and original/provider inputs receive final integrity audits without replacing the primary error. Aclocal's system macro search is restricted to the captured pkg-config macro; pinned local m4 and libtoolize-generated macros remain in each owned source. Their immutable prior runner pins are unavailable, so the first observation and output still require review. Missing tools or fingerprint drift fail without installing anything.

## Build differences and preserved contract

The producer invokes the original five Autotools generation stages separately through the existing joined, process-group-bounded supervisor. Upstream `autogen.sh` does not use `set -e`; running stages separately prevents a failed generation command from being hidden. No upstream `just` command, cleanup/update recipe or curl-to-shell action is executed.

Two fresh slices are built, device arm64 and Simulator arm64, with the original iOS minimum 13.0, `-O3 -fPIC -DHAVE_STPNCPY=1`, static/no-shared and root debug enabled. Root wireless pairing remains explicitly enabled. Each target has a clean allowlisted environment, target-only PKG_CONFIG_LIBDIR/PATH, empty CPPFLAGS and no ambient host OpenSSL search; exact effective environment and config.log/config.h are retained. Cython/tools/tests/readline and alternative TLS discovery are excluded where applicable. `.tarball-version` is generated from each pinned NEWS release number plus `-tetherless-c1`; this labels new derivation metadata without altering the public headers or algorithm code. Root's empty libtatsu variables and library/header-only make stages retain the original recipe's handling; no libtatsu tool is built.

The same four fresh archives, main/plist/glue/usbmuxd, are merged with Apple's libtool. No OpenSSL archive is merged. The complete public include tree and module map must be byte-identical to the authenticated original C release and identical across slices. The original module map comes directly from pinned `justfile`. The XCFramework must contain exactly device-arm64 and Simulator-arm64, and packaging must preserve tested archive/header hashes.

## One OpenSSL owner

The producer reuses the exact existing Rust `split-provider/provider_inputs.py` contract and all 443 authenticated inputs at `krzyzanowskim/OpenSSL@fdc9231384f37f053dffe058fd6dfc6c5072dae5`. Both Apple framework headers report OpenSSL 3.6.2. The original C recipe's download line is the 3.6.2000 package, but no binary equivalence is inferred from that version label.

For this new derivation, C compiles against byte-verified include views of the already-reviewed framework and links only that selected external `OpenSSL.framework`. It does not create `libssl.a`/`libcrypto.a` aliases, bundle the framework in the C archive, silently choose host OpenSSL or change the existing provider. C public headers have no OpenSSL includes; public-header equality and actual force-load links remain required, not presumed. The new source choice is compatible in design; actual Apple compilation/linking is still pending.

`CoreFoundation` and `SystemConfiguration` are explicit C dependencies from pinned `src/Makefile.am`. Both are retained in all link probes and output metadata. Existing consumers will need those flags in the later reviewed handoff.

## Acceptance and evidence

Portable tests verify exact/inverse transforms, authenticated sources, incomplete/extra callers, source mutation/symlinks, source paths, internal duplicate detection, full symbol-set equality, malformed/partial nm text, dead-stripped/ambiguous/wrong-owner map entries, branch isolation and provider identity. Host fixtures use public synthetic data and fixed SHA512 and RFC8032 vectors; both distinct layouts and all eight SHA function definitions coexist. ASan is attempted separately and its actual availability/result recorded. Host success is not device or cryptographic security acceptance; UBSan is not claimed.

For each Apple slice, complete `nm -g -U -j` logs must contain exactly the original complete export set plus four namespaced Ed25519 symbols, with every new C global definition unique. The two new slices must have identical full export sets. Both original glue and namespaced Ed25519 families must be present exactly once. Nothing is filtered to make a duplicate disappear.

Actual C and Swift compile/link probes force-load the entire new C archive against the single OpenSSL framework and declared Apple frameworks. They are never executed. Every required C global must have exactly one live link-map row owned by that tested archive, and the two SHA families must map to distinct archive members. Link-map existence alone is insufficient. Packaging rechecks tested bytes.

All build, generation, compiler/linker, nm and host-test commands use bounded joined supervision; failure retains logs/status JSON. The offline phase is a new owned `sandbox-exec` process tree with network denied, not a machine setting change. The workflow acquires sources only beforehand, with pinned checkouts and no saved credentials. It runs only on `verify/staged-pairing-native` and changes in this directory/its own workflow. It does not trigger the Rust producer paths or stopped diagnostic jobs. The repository's existing general Core push check remains independent.

Output is `libimobiledevice-derived-candidate.zip` in the Actions artifact, containing the two-slice XCFramework, matching complete pristine source, namespace recipe, original notices and a source/run/attempt/job-bound receipt. It is not a release. The receipt's acquisition-time job status is deliberately not success; later GitHub API verification must establish successful completion and artifact identity.

See [one-run decision](ONE_RUN_DECISION.md) and [next-stage handoff](HANDOFF.md). No new C bytes have been consumed by Rust or the app yet.

## Local portable checks

`python3 -m unittest discover -s Integration/Dependencies/libimobiledevice/tests -v`

`python3 -m unittest discover -s Integration/Dependencies/libimobiledevice/probes/host -p 'test_*.py' -v`

Run `host_tests.py` only against a fresh prepared copy of the retained host sources after applying `namespace.apply_to_directory(prepared / 'root')`. Use an absolute existing GCC/Clang path; Apple CI also supplies an explicit host SDK. Preserve each output directory and its failure evidence rather than overwriting a prior run.
