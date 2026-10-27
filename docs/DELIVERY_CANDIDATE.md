# Unsigned delivery candidate evidence

This packaging increment prepares reviewable unsigned **candidates**, not a release.
`candidateStatus` is always `candidate-incomplete`; `releaseReady`, device acceptance
and unattended-renewal acceptance remain false. None of these files is a final
SBOM, a signed provenance attestation, an independent binary trust anchor or a
license-clearance decision. An unsigned IPA still requires authorized signing.

## What one successful packaging run produces

All files below are generated together under `artifacts/<configuration>/`:

- `Tetherless-unsigned.ipa`: the existing unsigned app packaged with Apple's
  `ditto`; the native project, compiler flags and dependency graph are unchanged
- `manifest.json`: source SHA, configuration, bundle metadata, exact IPA SHA-256,
  companion artifact identities, evidence scope and explicit unresolved gates
- `ipa-inventory.json`: every final ZIP file/link's size and SHA-256; bundle,
  framework and extension identifiers from their plists; embedded IPA inventories
  recursively tied to their exact parent bytes. No payload is executed or extracted
- `inputs.json`: actual repository HEAD/gitlinks and initialized child HEADs,
  committed-tree Git identities versus observed working bytes/modes, Swift lock pins,
  observed matching checkout revisions, all available prepared-source and Swift
  checkout files, and resolved binary artifact file hashes
- `available-source.tar.gz`: the actual tracked top-level source **including
  recursive initialized submodule bodies**, available tracked Swift checkout
  source, and the complete prepared input tree subject to the exclusions below.
  There is no source-extension allowlist, so `.mm`, `.S`, build scripts, resource
  files, license variants and other source/build formats are retained
- `available-notices.tar.gz` and `notices.json`: available LICENSE/LICENCE,
  COPYING, NOTICE, AUTHORS, COPYRIGHT and README files, plus the compact historical
  supply-chain review and its collected unmodified license texts
- `toolchain.json`: observed Xcode build, Swift/Clang versions, iPhoneOS SDK and
  SDK build, macOS version/build, Git and Python versions. Missing tools are
  explicitly unavailable. No hostname, environment dump, credential configuration
  or installed tool path is collected
- `SHA256SUMS`: a non-circular checksum list covering the IPA, manifest and all
  companion files. The checksum file cannot authenticate itself or its publisher

The candidate source and notice tarballs have sorted paths, fixed uid/gid, empty
owner names, fixed mode/mtime and a fixed gzip header. Their hashes are
repeatable for identical input bytes, links and executable bits. The IPA itself
is not claimed to be reproducible: `ditto` preserves relevant app metadata.
Every archived source file is hashed while being emitted and checked against its
input record. Final output is renamed into place only after the whole candidate
succeeds; an earlier candidate is never overwritten.

The proposed native workflow also replaces the old suffix-filtered diagnostic
archive with `native-review-source.tar.gz` and its `.json` inventory **before
compilation**. Both snapshot files are staged before exclusive publication; either existing
target is refused, and a publication error rolls back only the files created by
that attempt. It remains available if compilation fails. This prebuild snapshot
is diagnostic evidence; it is not the full candidate source bundle.

## Input origins and boundaries

`repository/` means the checkout at the requested complete source commit, with
recursive Git gitlink identities. `prepared/` means the actual disposable tree
produced by preparation. `swift-packages/<checkout>/` means an actual resolved
checkout, with its observed HEAD. `binary-inputs/` means existing files in
DerivedData's `SourcePackages/artifacts`; their package-relative paths and hashes
are recorded. They are **not redistributed in the source tarball**, and a binary
file is never substituted for its missing producer source. The final IPA retains
whatever native build inputs it actually embeds.

The requested commit and every initialized gitlink HEAD must agree. A missing,
uninitialized or mismatched submodule fails packaging. Files and gitlinks are enumerated from the verified commit tree, never the
mutable index. Working bytes or executable/symlink modes that differ from that
tree are preserved and explicitly flagged, including staged changes. A staged
gitlink cannot replace the required committed child revision. Swift pins are parsed from actual
available lockfiles and compared to observed checkout revisions; a pin not
observed is labeled `not-observed`. Cargo lock bytes are preserved when present,
but lock membership does not establish linked crates. Swift package manifests,
workflow/compiler invocations, preparation scripts, resources and lockfiles stay
in the source bundle as exact build-input bytes.

Known private/generated paths are excluded: Git internals, caches, build output,
user Xcode state, environment files, key material and pairing/provisioning files.
The generated `CodeSigning.xcconfig` is retained only when byte-identical to its
checked-in sample; otherwise it is omitted explicitly. No arbitrary untracked
repository/checkout files are swept into the bundle. Exclusions and absent input
roots are recorded. This is a scoped CI-source collector, not a general-purpose
secret detector; do not point it at a personal home directory or secret-bearing
workspace.

Traversal is bounded at 150,000 entries, 512 MiB per file, 6 GiB aggregate bytes
and 64 path levels. Excluded entries and gitlinks count toward the entry limit.
Git stdout is capped at 32 MiB while the subprocess runs, with timeout and child
reaping on failure; it is not accumulated without a bound first. Case-insensitive nested IPA inspection is bounded to three nested levels and
256 MiB per nested IPA; plist/link capture is limited to 8 MiB. The main app plist also uses a bounded, non-following regular-file reader before
parsing. ZIP central-directory reads are capped at 32 MiB. File size and
CRC are checked while streaming. Duplicate/unsafe paths, encrypted archive
entries, unsupported special files, root-escaping links and known private/signing
material (including inside nested IPAs) fail closed. Source links are not followed to collect content. A bounded metadata-only chain
inspection rejects escapes, private targets, loops and special files. Safe
in-root links are retained with their exact target identity and explicit
present/missing plus included/excluded target status. A generated output may be
absent before compilation without inventing its bytes; see the
[SideBackup boundary repair](delivery/PREPARED_SOURCE_LINKS.md).
Dependencies are never executed; there is no custom Mach-O, code-signature,
certificate or APK-signature parser and no network download.

## Prior review is historical evidence

`docs/supply-chain/` was copied unchanged from the compact review at baseline
`3dd8641e84698b97f96d53a6c53ed8c6ca4675bd`. All 40 entries in
`review-file-hashes.json` are checked before packaging. Its baseline and manifest
hash are recorded, separately from the current source commit. Consistent copied
hashes do not authenticate publishers or automatically reconcile that historical
candidate graph with a newly linked binary. The report's original observations
remain historical, including gaps later addressed by adding a root license.

## Release gates that remain open

1. Complete corresponding source, binary-producer source and applicable LGPL
   relinking materials; source-bundle completeness must be reviewed explicitly
2. Actual linked Rust/C component closure and complete notices/attribution. The
   [supplemental GPLv3 reference](supplemental-notices/README.md) supplies the
   standard text identified as missing by the historical SideSign review; it does
   not establish component-wide licensing or distribution clearance
3. Independent rebuild/attestation evidence for retained prebuilt frameworks
4. A documented compatible license basis for the exact combined Unicorn app
5. Independent ADI authentication, usable admitted input and acquisition/use basis
6. Native integration and separate physical-device install/launch/renewal and
   unattended-renewal acceptance for this exact candidate
7. Authorized durable distribution of the binary, exact source and notices;
   fourteen-day GitHub Actions artifact retention is not a release channel

No gate is marked passed by metadata consistency or by synthetic packaging tests.
No dependency was removed, no trust policy installed, no credential used and no
release/main promotion enabled. The pending evidence cannot be manufactured in
this packaging-only increment.

## Verification

Run `python3 -m unittest discover -s Integration/tests -v`, plus the repository's
required `swift test` and `swift test -c release`. The focused synthetic coverage is
`python3 -m unittest discover -s Integration/tests -p test_delivery_candidate.py -v`.
It covers recursive gitlinks, exact source and artifact hashes, deterministic
bundles, all-extension snapshots, historical review identities, dirty/missing
inputs, symlinks, traversal/size bounds, nested IPA/framework identities, private
nested material, missing tool evidence and atomic failure. These tests mock IPA
creation and use fixtures, not native app or device evidence.

On macOS CI, the next evidence is successful preparation, unsigned compilation
and this packager against the same implementation SHA in both configurations,
followed by inspection of the generated manifests, actual nested IPA contents,
resolved checkout observations and remaining source/notice gaps. The workflow
patch is proposed separately so the parent can preserve unrelated pending native
workflow evidence steps.
