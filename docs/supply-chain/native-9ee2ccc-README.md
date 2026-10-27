# Native 9ee2ccc inventory supplement

This additive supplement records the accepted native producer's source packages,
actual Cargo compiler inputs and retained notice evidence. It fills a concrete
gap in the existing 32-package SPDX draft, which describes the earlier 3dd8641
candidate and contains none of these 359 exact registry package/version pairs.
It does not replace that historical draft or claim a complete product SBOM,
legal compatibility, final linked-symbol membership or source/binary equivalence.

Producer: **9ee2ccc9bd3519053781087acde54d4b4ee43236**, [run 37400684000,
attempt 1](https://github.com/oskuhsiu/Tetherless/actions/runs/37400684000), Apple job
112066959183. Artifact 11385154393 has SHA-256
c90f04e44019e67e551dca9708e9e958729ca475094aa6eefbd8e42d638f0a77.
The corresponding-source ZIP has SHA-256
004f310d48bdb1e4c8f9a407b95d8d9923f6a155cf7aff65e165339fd14730ca.
Its full source remains the retained artifact; this supplement does not duplicate it.

## Files and evidence levels

- [Inventory](native-9ee2ccc-inventory.json): all 359 locked registry packages and
  four workspace packages, exact manifest/archive hashes, verbatim declared license
  expressions, authors/repository metadata, locked dependency references and
  per-target compiler observations
- [Notice index](native-9ee2ccc-notice-index.json) and
  [exact notice texts](native-9ee2ccc-license-texts.zip): 666 distinct source notice
  files, with every path/hash mapping preserved. Exact-byte deduplication, including
  the pinned upstream additions, yields 232 text blobs in one ZIP
- [License qualifications](native-9ee2ccc-license-qualifications.json): retained
  README statements and 32 file-level LGPL notices from plist_ffi, with source
  paths/hashes and original-crate comparisons
- [Pinned upstream additions](native-9ee2ccc-upstream-notices.json): retrieved
  license texts missing from three compiled crates, and complete pinned-tree
  absence evidence for the other three
- [Verification](native-9ee2ccc-verification.json): completed data/identity checks
  and their limits. License conclusions remain `NOASSERTION`

| Set | Device | Simulator | Meaning |
|---|---:|---:|---|
| Locked registry source archives | 359 | 359 | Retained inputs; not all were compiled |
| Workspace source packages | 4 | 4 | idevice, idevice-ffi, test harness and tools |
| Packages with compiler-artifact records | 208 | 207 | Includes Apple target and build-host output |
| Packages with Apple-target output records | 161 | 160 | Includes idevice and idevice-ffi; 159/158 are registry crates |
| Build-host-only packages | 47 | 47 | Build tools/macros and their dependencies |

Across the two builds, 155 packages have source in the lock/bundle but no observed
compiler artifact: 153 registry crates and two workspace packages. The only
device/Simulator package-set difference is obfstr 0.4.4. Cargo.lock edges retain
optional, platform, build and development relationships; they are not presented
as the exact active dependency graph. Compiler output records do not prove which
objects survive into a final application binary.

The archive's 189 recipe files and patched workspace are covered by the retained
source manifest. Both known README case aliases remain represented in the
authenticated original crate; the declared inward README symlink stays opaque.
This audit reads archive members as data and performs no source-code execution,
filesystem extraction of code, binary-format parsing or signing inspection.

## Concrete corrections to the old inventory

The actual target build includes **aws-lc-rs 1.16.2 and aws-lc-sys 0.39.0** through
retained default features. rustls/tokio-rustls compiler records explicitly include
aws-lc features; aws-lc-sys emits `static=aws_lc_0_39_0_crypto`. The separately
captured OpenSSL framework remains an external link input. Describing this graph
as containing only OpenSSL would omit observed inputs. This finding does not
establish a provider conflict or inspect retained symbols.

The exact aws-lc composite license declarations and nested notices are preserved.
Other distinctions also remain intact: cbindgen 0.29.2 declares MPL-2.0 and is
observed only on the build host; webpki-roots 1.0.6 declares CDLA-Permissive-2.0 and
has Apple-target output; ring 0.17.14 is present in the lock/source but has no
compiler-artifact record in these builds. No license alternative is selected,
exception removed or package relabelled MIT by this supplement.

### Six compiled crates lacked named license files in their original archives

All six exact Cargo.toml.orig files match Git blobs at the VCS revisions recorded
inside their checksum-verified original crate archives. Read-only GitHub retrieval
then obtains the available upstream evidence without changing the crate contents.

| Package | Declared metadata | Exact upstream evidence and result |
|---|---|---|
| async-compression 0.4.41 | MIT OR Apache-2.0 | [269174b](https://github.com/Nullus157/async-compression/tree/269174b4be20e3cfcbb7e7fa4d7d9596183e287b): root LICENSE-MIT and LICENSE-APACHE recovered |
| compression-codecs 0.4.37 | MIT OR Apache-2.0 | [9d848a0](https://github.com/Nullus157/async-compression/tree/9d848a02f13f3a56542e4123be8947a8da06097e): same exact root texts recovered |
| compression-core 0.4.31 | MIT OR Apache-2.0 | [2a28343](https://github.com/Nullus157/async-compression/tree/2a28343998e67ea519b87005b9d295b134c00dd0): same exact root texts recovered |
| ns-keyed-archive 0.1.5 | MIT OR Apache-2.0 | [f8cec65](https://github.com/jkcoxson/ns_keyed_archive/tree/f8cec65e865cb48301d33b2244bec45a2f3d2bc2): complete eight-entry tree contains no named license/notice file |
| plist-macro 0.1.6 | MIT | [d1d4855](https://github.com/jkcoxson/plist_macro/tree/d1d48559ddc8e9bd263f36180bbe1d4f2a3d55e5): complete ten-entry tree contains no named license/notice file; packaged README states MIT |
| plist_ffi 0.1.6 | MIT | [2653791](https://github.com/jkcoxson/plist_ffi/tree/265379167ab3f9a5664621a7f1c0f494b2ac7c96): complete 155-entry tree contains no named license/notice file; README and copied source carry the qualifications below |

The recovered MIT text retains the rustasync developers' copyright attribution;
the Apache text is also preserved exactly. Each fetched blob is checked against
its Git SHA and size, and is clearly labelled as an upstream addition that was
absent from the original crate. This closes an obtainable-text gap for the three
compression packages without claiming legal compatibility or new rights.

plist_ffi's README distinguishes its author's Rust code from copied libplist
headers, C++ and tests. The copied files retain LGPL-2.1-or-later notices. Those
32 complete leading notices are retained, alongside the README, rather than
letting the Cargo MIT field erase them. Cargo records show plist_ffi and its
`static=plist_shims` build input. They do not show that copied C++/test files are
included in the final binary. The source bundle itself contains those files.

## Remaining BASE-02 gaps and smallest closures

1. **Use the new native inventory/notices in the final delivery assembly.** The
   existing product SPDX still needs an explicit relationship to this exact
   producer. Preserve target, host-tool and source-only scopes when assembling it;
   do not mark all 359 registry archives as linked application dependencies
2. **Resolve the three remaining compiled-package notice records.** The exact
   pinned repositories have no additional named text to retrieve. Preserve their
   metadata/README grants and original attribution, and establish the applicable
   notice treatment before declaring delivery complete. Do not fabricate missing
   copyright text or erase plist_ffi's mixed file-level grants. This is a specific
   notice/attribution gap, not a claim that these packages have no license
3. **Complete the broader source-distribution notice review.** Thirteen additional
   locked source-only registry packages have no named notice file in the bundle;
   they are listed with exact metadata/VCS identities in the inventory. Their
   absence from the observed compile set does not settle obligations for distributing
   the complete source bundle. Filename discovery and the selected inline review
   are not an exhaustive grant audit of every source file
4. **Keep provider and product gates separate.** The OpenSSL input receipts bind
   exact external framework/header bytes; source/binary equivalence is unproved.
   The SDK/toolchain and their system inputs are separately supplied. ADI origin,
   admission and acquisition/use basis, Unicorn compatibility, full-product source,
   notices/relinking and durable release delivery remain outside this supplement

The original source ZIP is unchanged. Existing SPDX, notices, status documents and
product code are unchanged. No legal agreement, release, external write or paused
signing/manager-replacement/install-budget inspection is part of this work.
