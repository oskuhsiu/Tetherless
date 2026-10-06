# UNAPPROVED proposal: four build tools on the disposable CI runner

No owner approval has been received. No Homebrew command, tool installation, executable-tool download, native build, publication or dispatch has been performed for this proposal. Independent source review is not permission to execute it. The parent must obtain and preserve the owner's explicit four-package approval before publishing any dependent workflow source.

## Actual blocker

Run `37456626052`, source `80265213253940a904a0d1d0eae2bdbcd34066ce`, passed all Apple/Swift/SDK identity checks and authenticated inputs. Its complete preflight found no autoconf, autoheader, automake, aclocal, glibtoolize or GNU m4 through the approved lookup paths. Existing pkg-config 3.0.7 and make 3.81 were observed and hashed. No host-crypto or C build started.

This proposal changes only the disposable GitHub-hosted arm64 macOS workflow's setup. It does not install anything on the user's computer, switch runners, use sudo, change OS/network security settings, update Homebrew, upgrade other software, modify the C/Rust source/ABI/crypto namespace, or weaken any existing native gate.

## Read-only official metadata checked 2026-10-06

The selected ordinary Homebrew/core formulas are:

- [Autoconf 2.73](https://formulae.brew.sh/api/formula/autoconf.json), which supplies autoconf/autoheader and depends on m4; it uses the existing macOS Perl
- [Automake 1.19](https://formulae.brew.sh/api/formula/automake.json), which supplies automake/aclocal and depends on autoconf
- [GNU Libtool 2.6.2](https://formulae.brew.sh/api/formula/libtool.json), which supplies glibtoolize and depends on m4
- [GNU m4 1.4.21](https://formulae.brew.sh/api/formula/m4.json), which has no further formula dependency and remains keg-only

The declared dependency closure is exactly those four formulas. Formula source files were read, never executed, at Homebrew/core commit `b297eb47435775b292f454304434ee59c6916c04`. Their official API SHA-256 values match the retained text in metadata-sources/, together with the original Homebrew/core LICENSE.txt. `formula-lock.json` records exact versions/revisions, source URLs/checksums, formula-source identity and the arm64_sequoia bottle URLs/checksums. These are newly selected build-tool inputs, not a claim that the original C release used these versions.

## Deliberately unresolved boundaries

Bottle archives have not been downloaded, so their embedded runtime-dependency receipts have not been inspected. After explicit approval, the helper may fetch only these four fixed bottles into a fresh owned cache, verify their exact SHA-256 values and inspect their bounded receipts before any installation. A runtime dependency outside the four names fails closed and is not covered by the four-package request. System Perl is an existing OS dependency, not permission to install a Homebrew Perl formula.

The runner's Homebrew/Ruby/Bundler state and exact CLI JSON shape have not been observed. Homebrew can bootstrap its portable Ruby or gems. The helper therefore requires a matching already-present portable Ruby and Bundler, runs an offline Homebrew config check while protecting Homebrew's runtime/code from writes, and refuses bootstrap or upgrade requirements. Any blocker here must be reported before expanding the installation request.

Current standard Homebrew command semantics were checked in its [manual](https://docs.brew.sh/Manpage). Source inspection at Homebrew/brew `8304895a0c22292c5ea5f8c0511fe5f41dfeacad` confirms portable-runtime bootstrap paths and force-bottle behavior. That inspected source is background for the guard design, not an assertion that the runner has that Homebrew revision. Existing CLI/runtime identities are recorded on the runner, and remain protected from writes throughout setup.

Standard Homebrew fetch can fall back to downloading official source tarballs for the same four selected packages. Those source downloads are part of ordinary package acquisition, not authorization to install another package. The four pinned formula texts have no custom fetch hook or extra resource blocks. The helper does not claim bottle-only acquisition: it still requires the selected bottle bytes before installation and fails if they are unavailable. No unsupported dependency-skipping option, formula-file execution, custom tap, arbitrary installer or source build is proposed. If current metadata, cached bottle selection, existing packages or runtime behavior differ, stop and retain the evidence. Do not relax a guard merely to make installation proceed.

## Proposed flow, only after owner approval

1. The same C workflow keeps its existing verification-branch C-path push trigger. This activation-ready proposal must remain local and unpublished until the parent has the owner’s approval. The reviewed setup step supplies its explicit approved-CI marker and flag; these record the controller’s prior approval check and never substitute for actual owner permission. No new manual-dispatch input, UI step or later unreviewed gate edit is needed.
2. The setup helper requires the approved verification branch, exact repository, GitHub-hosted arm64 macOS context and a valid source SHA. It refuses local, self-hosted, other-branch or unapproved invocation before launching any command.
3. Record existing Homebrew/Ruby/Bundler identities, all existing Cellar version/receipt entries and the existing make/pkg-config hashes. Require the current macOS version/build. Refuse an installed target version that would need replacement or upgrade.
4. Disable Homebrew auto-update, install-upgrade, installed-dependent repair, cleanup/autoremove, analytics, bootstrap caching and sudo. Use a new owned HOME/cache/log/temp tree. Protect Homebrew's code/runtime and unrelated existing kegs from writes using only an owned process sandbox, not a global security setting. This sandbox does not claim whole-prefix immutability or exclusive Cellar write permissions; standard dependency resolution is bounded by the authenticated four-formula and bottle-runtime closures, then revalidated offline immediately before installation. Normal linking of the approved packages is allowed. Any unexpected installed package or changed unrelated receipt rejects setup and blocks the C build. Missing runtime software causes refusal.
5. Read the selected formula metadata through existing Homebrew and require exact formula/source/version/bottle/dependency agreement with the lock. Unexpected output is retained and rejected; warnings are not silently stripped from JSON.
6. Ask standard Homebrew to fetch missing approved arm64_sequoia bottles, without a dependency-fetch flag; it may also download the official source of the same package on a bottle-fetch failure. Authenticate cache paths and complete file hashes, then check bounded embedded runtime-dependency receipts. No bottles or source assets are fetched before owner approval.
7. Install those missing formulas with standard Homebrew --formula --force-bottle --no-ask inside a network-denied process using the fresh cache after all selected bottle hashes and dependency closures pass. The four are supplied in dependency order. Homebrew's usual dependency logic remains enabled. Additional assets or source fallback cannot be downloaded during installation; a missing asset is a failure, not permission to go online.
8. Require exact installed versions and bottle provenance, record executable hashes and version output, recheck unrelated installed state and the prior make/pkg-config/runtime hashes. Retain commands, complete logs/status receipts and partial state on failure. The unchanged native preflight must then independently accept every toolchain/source gate before any host/C work begins.

The workflow uploads setup JSON/log/status evidence on failure. Bottle metadata and source identities are in the receipt; packages themselves are not bundled into the app or the C XCFramework. Existing full source, license, public-header, both-SHA, namespace, force-load, map, single-OpenSSL, packaging and final-integrity checks remain untouched.

## Proposed next-run decision

There is no authorized next run yet. After owner approval and independent review, the parent may publish only the reviewed setup delta so that the existing C-path source push starts the isolated workflow once. Expect the four tool installations to be recorded, other installed software unchanged, and the existing preflight to pass before native work. Any new formula/runtime/dependency requirement must return to the parent. A failed install may have partially installed some approved tools; preserve receipts and never infer success or blindly retry.

Portable tests use mocked context, synthetic metadata and synthetic tar receipts only. They prove proposal guards, not actual Homebrew installation or C native acceptance. Current CI limitations and unresolved metadata/runtime boundaries must remain visible until an authorized native run supplies evidence.
