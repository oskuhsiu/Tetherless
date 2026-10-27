# Authenticate OCI bottle receipts before installation

The four approved, hash-pinned bottles omit `INSTALL_RECEIPT.json`. Their
runtime receipt data is in Homebrew's OCI `sh.brew.tab` annotations. This
correction authenticates that metadata separately and retains the bottle
archives and member inventories for independent verification.

## Failure and subsequent input inspection

Run `37498745445`, attempt 1, job `112389961061`, source
`7b7acbf597461141105afbd92933d3cd204a243a`, completed seven setup subprocesses.
The reader and metadata gates passed, and m4 was fetched and passed the
archive size/hash gate. Inspection then failed with `one bottle receipt required`.
No installation or native compilation started. All 13 preservation audits passed.

The run's artifact omitted the bottle bytes and member list, so it alone could
not establish the receipt count. Its independent report SHA-256 is
`32d282c2537bd5fb790c1f27b984162291523e13e84e47a589e452ce91976f03`;
the bottle-failure analysis SHA-256 is
`c7daa200ef04d5b4df05a2e45a6762e3665ad5481d4a4451422a95768772cebe`.

On 2026-10-06, subsequent authorized read-only acquisition checked all four
unchanged archive pins and their official GHCR OCI metadata before this repair:

| Formula | Version | Archive bytes | Members | Embedded receipts | Runtime dependencies |
| --- | --- | ---: | ---: | ---: | --- |
| m4 | 1.4.21 | 283,974 | 20 | 0 | None |
| autoconf | 2.73 | 1,121,278 | 86 | 0 | m4 1.4.21 |
| automake | 1.19 | 1,077,801 | 149 | 0 | m4 1.4.21, autoconf 2.73 |
| libtool | 2.6.2 | 1,123,741 | 97 | 0 | m4 1.4.21 |

Each index's complete byte hash matched the official registry's
`Docker-Content-Digest` response. For the selected arm64 Sequoia descriptor,
the child manifest's digest and size matched; its single layer matched the
original bottle digest and size; its tab matched the index annotation; and
its config digest and uncompressed tar hash matched. All selected platform
metadata is arm64 Darwin/macOS 15.7. No package contents were executed or
installed during these checks. These are input inspections, not a native CI pass.

## Supported format and separate metadata identity

The observed Homebrew commit is
`08e85c4e42f5d8f1ea17c36cb59cf61c2ccb26c3`.
Its [bottle command](https://github.com/Homebrew/brew/blob/08e85c4e42f5d8f1ea17c36cb59cf61c2ccb26c3/Library/Homebrew/dev-cmd/bottle.rb)
supports `--only-json-tab`, which removes the embedded receipt and retains its
metadata in bottle JSON. The [publisher](https://github.com/Homebrew/brew/blob/08e85c4e42f5d8f1ea17c36cb59cf61c2ccb26c3/Library/Homebrew/github_packages.rb)
places that tab in the OCI annotation. The [bottle manifest reader](https://github.com/Homebrew/brew/blob/08e85c4e42f5d8f1ea17c36cb59cf61c2ccb26c3/Library/Homebrew/resource.rb)
selects it by both the bottle digest and exact image reference; the
[installer's receipt loader](https://github.com/Homebrew/brew/blob/08e85c4e42f5d8f1ea17c36cb59cf61c2ccb26c3/Library/Homebrew/utils/bottles.rb)
uses it to reconstruct the installed tab.

Homebrew explicitly warns that annotations are not covered by the bottle
checksum. The four complete official index files are therefore retained under
`bottle-manifests/` and separately pinned in `bottle_metadata.py`. Their recorded
origin is the public official GHCR endpoint for each locked formula/version.
These byte identities are independent metadata pins, not a signature or an
attestation claim. Existing formula and archive pins are unchanged.

The helper validates these retained inputs before any setup subprocess. After
normal Homebrew fetch, it reads the matching manifest from the fresh owned
cache using the filename defined by the observed [Bottle resource](https://github.com/Homebrew/brew/blob/08e85c4e42f5d8f1ea17c36cb59cf61c2ccb26c3/Library/Homebrew/bottle.rb).
No downloader, registry authentication code or cache rewriting is added to CI.
The entire cached index must match its separate pin. Selection requires one
matching bottle digest and exact `<version>.arm64_sequoia` reference; this matters
because autoconf uses the same archive digest for several platform descriptors.

Runtime dependencies must equal the transitive four-formula closure, including
their exact locked version, revision, rebuild, package version and compatibility
value, plus whether each is a direct dependency. Missing or unverified tab data
still fails. Duplicate embedded receipts fail, and any embedded runtime metadata
must agree with the authenticated OCI tab. Source-built packages, other formulas
and unrelated upgrades remain outside the accepted setup.

## Evidence and one next-run decision

Each archive passes its original size and SHA-256 gate before being copied into
the retained evidence directory. Inspection records member names, types, sizes,
link targets, receipt paths, completeness and errors. A later missing-manifest
or receipt error therefore retains the exact verified archive and member data.
The workflow adds only the four retained archive paths to its evidence upload.
Packages are not added to the app or C XCFramework.

Cached archive and manifest hashes are rechecked immediately before the offline
install and in the final audit. Audit or evidence failures cannot make setup
successful; evidence-write errors preserve an existing primary inspection error.
The previous namespace, source, ABI, OpenSSL, host-crypto and force-load gates
remain required. The installed receipt and executable checks are unchanged.

After independent review, the parent may publish this exact delta once on the
verification branch. Expect all four pinned cached manifests and archives to
pass inspection before installation. Native cache filenames and actual install
behavior still need that run's evidence. Any new mismatch stops with the retained
inputs; this decision permits no unchanged rerun, new package or relaxed pin.
