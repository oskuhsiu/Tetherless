# Next run: exact Swift stream identity and reviewed packaging operation

- Current isolated C run: `37453986835`, attempt `1`, job `112236993217`
- Exact source: `673eb9c7039010355905b6c3c8823bed0a4eb699`
- Earliest failure: Apple identity preflight, `Apple toolchain drift: swift`, before host fixtures or C compilation
- Authenticated Actions artifact: `11407882361`, 4,140,526 bytes, SHA-256 `173a7e0243bc9cd8a6be5c5168e1ad0006211497746b419f8507fd00dc8f2207`
- Full decoded job log SHA-256: `0a48e0d00fc770a231f0c2e4896cd3660fcf25ee938575ac8e833f79c7a52108`
- Independent verification report SHA-256: `4067be836571578af8609e7e00c0fc2b3c9cd622dadab9bfe4f2876f1fc4e417`

Portable contracts passed (66 C and 16 host-runner). All authenticated input acquisition passed: 581 pristine source files, 299 recipe files, 443 OpenSSL entries and 286 original C archive members matched. Xcode 26.3/17C529, macOS 15.7.9/24G830 and Apple Clang 17.0.0 passed. SDK and GNU-tool observations were not reached. Final input audit remained false because no accepted toolchain.json had been written; pristine source, recipe, OpenSSL and original C audits passed. This run produced no rebuilt C archive and is not native acceptance.

## Measured Swift mismatch and exact correction

`/usr/bin/xcrun swiftc --version` completed with zero exit, complete output and joined cleanup. Its retained `work/evidence/005-toolchain-swift.txt` is exactly 127 bytes, SHA-256 `355986b284d60fc60e4b3c24d2bc54ff2562ee37b60ef688917cf2e531315105`. It contains the exact Swift driver 1.127.15 stderr prefix followed by Swift 6.2.4 (swiftlang-6.2.4.1.4 clang-1700.6.4.2) and `Target: arm64-apple-macosx15.0`. The bounded supervisor intentionally merges stderr and stdout.

Those bytes are identical to the existing Rust producer's retained observation and exactly match its already-reviewed `SWIFT_26_3_MERGED` identity. The previous C first-line check wrongly treated this known stream combination as drift. Reuse `build_pairing_apple.require_toolchain_observation` with its full `SWIFT_26_3_STDOUT` expectation and `swiftc` label. Do not strip arbitrary prefixes, discard stderr, accept extra text or loosen driver/compiler/Clang/target validation. Retain the original complete raw log, its bytes/hash and the full observed identity. The exact 127-byte artifact is a regression fixture.

## Complete read-only preflight before any build

Collect the remaining bounded version/SDK observations and preinstalled-tool availability before reporting identity mismatches. Retain `toolchain-preflight.json` incrementally, with all values, raw-log references/hashes, errors and explicit complete/pass fields. A missing tool is recorded without installing anything. An actual command or cleanup failure stops further commands immediately, preserving partial observations rather than assuming its process group is settled.

Only when every original identity/macro gate passes may the build macro view and accepted toolchain.json be created. Host fixtures, source generation, compilation, linking and packaging remain after that barrier. Controlled tests prove real drift fails closed, SDK/GNU evidence survives an identity mismatch, and the actual build entry point does not proceed to source/provider/host work after rejection. All prior SDK, architecture, GNU-m4 minimum, source and provider constraints remain intact.

## Avoid the already-known Xcode packaging tail regression

The C producer's direct `xcodebuild -create-xcframework` supervision would repeat an operation-path problem already handled in the existing Rust producer: historical failure 37396649973, followed by reviewed successful operation-path verification in 37399037692 and 37400684000. This C run has not reached packaging; this is reuse of known reviewed compatibility handling, not a newly observed C packaging failure or a reason to retry unchanged source.

Use the unchanged `idevice/xcframework_operation.py`, SHA-256 `98df3ef86806a707fb898dd9e59ff0a3612b330a91522d4995b793360ed0f044`, which matches the existing Apple recipe lock. The wrapper remains the owned session/group leader while its exact xcodebuild child and natural helper tail drain. Preserve the same outer supervisor, cleanup checks and existing C operation's 900-second bound. Use its exact four-key child environment and absolute device/header/simulator/header/output arguments. Do not change the generic supervisor, enumerate unrelated groups or hide nonzero exits.

Record the wrapper source digest, exact supervised and underlying command vectors/hashes and exact environment in the C evidence/receipt. The same tested archives, public-header hashes, two-slice packaging checks and post-build input audits remain required. Controlled tests cover source-pin drift, command/environment identity, preserved failures and changes during the operation; existing Swift-stream and packaging-operation suites are rerun unchanged. No native packaging acceptance is claimed for this new C path.

## One next-run decision

After independent review and parent-controlled publication of this narrow correction, one next isolated C run may verify the unchanged native acceptance condition. Expected observation: the exact known Swift pair is accepted, all remaining genuine identity checks pass (or expose their actual blockers with retained evidence), and only then host/C work begins. Packaging, if reached, uses the previously reviewed operation path. SDK/tool availability remains unverified until that run.

No source pin, namespace transform, crypto algorithm/context layout, OpenSSL provider, public ABI, complete symbol scan, force-load/map ownership assertion, general process limit, runtime boundary or device acceptance is weakened. Preserve both prior failed runs. A repeated failure still requires new evidence and a separate decision; no blind retries or tool upgrades. This worker performs no publication or dispatch.

## Historical fixture-root correction

# Next run: canonical owned fixture roots and early evidence

- Actual first isolated C run: `37452546963`, attempt `1`, job `112232293033`
- Exact source: `7d89a9f35e105e0bc66df0fad66f9739e4816147`
- First failed step: `Portable contract checks` (step 3), before any source acquisition, host-crypto execution or Apple C compilation
- Actual assertion: `test_map_owns_all_globals_and_both_families` failed at `symbols.py:75`, `required global has wrong archive owner: _afc_client_free`
- Result: 62 of 63 portable tests passed; host-contract command did not execute; every acquisition/native step was skipped
- Exact decoded job log SHA-256: `34bee3dde85d3d48b957757c989a43ff8aa5990e37b62f8c2bdd555ab8cc12b2`
- Evidence export also failed because all configured paths belonged to later, skipped steps; GitHub API reported zero artifacts

The owned test fixture rendered `str(lib)` while the unchanged production checker requires `lib.resolve(strict=True)`. A controlled temporary symlink reproduces the exact failure. Canonical fixture paths pass the unchanged checker. The actual macOS temporary path was not logged, so `/var` versus `/private/var` is a plausible platform explanation, not a directly observed path from that run.

## Narrow correction and regression evidence

Canonicalize each owned temporary fixture root immediately after creation: namespace/path fixtures, link-map fixtures, build-audit fixtures and host-runner mock fixtures. Add a controlled symlink-root regression. Keep a separate negative regression proving a raw alias in a map is still rejected by the unchanged production ownership check.

All temporary-root creation sites in the new C and host fixtures were audited. Production build roots already use `resolve()` before construction, and the host runner resolves its source and newly created output roots. Those production implementations and `symbols.py` remain byte-for-byte unchanged.

Create `.c-provider/evidence` and a source/run/attempt/Python/temporary-path context receipt before portable tests. Retain both test streams with `tee` and the existing `set -euo pipefail`; upload the early evidence directory in the unconditional artifact step. A behavioral fixture forces failures in both the portable and host-contract commands, requiring a nonzero result and retained logs/context. Missing later artifacts cannot erase this early evidence.

The original 63-test suite reproduces one failure under a controlled symlinked `TMPDIR`. The corrected 66-test suite and 16 host-runner contract tests pass on both ordinary Linux paths and the same controlled symlinked `TMPDIR`. These are portable fixture results, not Apple execution.

## One next-run decision

A single next C-producer run is justified after independent review and parent-controlled publication of this small fixture/workflow correction. Expected observation: the portable and host-contract stages pass even when the runner temporary path has a symlink alias, then the unchanged acquisition and native gates run. Any early failure must retain its context and complete portable output.

No native source, C/Rust ABI, namespace contract, OpenSSL choice, source authentication, force-loading, complete symbol coverage, map ownership, public-header equality, offline build, final-audit requirement or runtime boundary is weakened. The original failed run is preserved; it is not a native-build failure or evidence of a rebuilt C archive. Missing tools, later source/build failures or the same unexplained symptom must be diagnosed from retained evidence, not blindly rerun. No publication or rerun is performed by this correction worker.

## Historical first C-source rebuild decision

# One-run decision: C source namespace isolation

- Current Tetherless source: 6af17537bcebfa797bf3c2659f749edd4c9d53eb
- Failed native producer: run 37446415281, attempt 1
- Verified failure report SHA-256: 1116949801b80dba4c05f371fa0cfff57ba836a6d69e936de4381dde7c3be423
- Earliest boundary: device mixed-provider C force-load link, after successful complete 382-name Rust scan and Rust/C disjointness
- Failure fingerprint: duplicate _sha512, _sha512_init, _sha512_update, _sha512_final in two members of the unchanged C provider archive
- Evidence: apple-producer-work/aarch64-apple-ios/completed/05-link-mixed_provider-c.txt and matching status JSON; pinned source declarations reveal incompatible context sizes

Hypothesis: isolating only bundled Ed25519's private SHA function identifiers removes the internal C collision while preserving both implementations, public C ABI and the complete original acceptance gates.

Discriminating change: exact 30-token/six-file source transform, authenticated full source rebuild, strict full archive export uniqueness and distinct live link-map member ownership. The new isolated producer builds only the C dependency; it does not rerun the existing Rust producer or the app.

Expected observation: all host synthetic and ASan checks succeed; both Apple C slices build with byte-identical public headers; complete C symbol sets equal the old set plus exactly four namespaced Ed25519 functions; all new global definitions are unique; actual C/Swift force-load links and live ownership maps pass in both slices; XCFramework packaging preserves tested bytes.

Unchanged assertions: no filtering/removal of duplicates, no lazy-link substitute, no mutation of the old archive, no crypto algorithm/layout change, no Rust export contract weakening, no second OpenSSL provider, no runtime activation, no device binary execution and no device acceptance claim. Subsequent Rust verification must still force-load both providers and scan the complete symbol sets.

First-run preconditions: independent candidate review; parent verifies exact branch head and publishes the isolated delta; no other current C run; existing Apple fingerprint and preinstalled Autotools match the observed contract. Missing tools stop without installation. Non-Apple tool versions are first-observed candidate evidence, not a claim of old release reproducibility.

One planned native run is justified only after this review. If the same link boundary fails, or tools/header/configuration differ, stop the full-run loop and preserve the earliest actual failure. Do not blindly retry, upgrade tools, drop dependencies, change context layouts or relax assertions. Run/job/artifact IDs and digest must be checked after completion before any C→Rust handoff. No native run has yet been requested or executed for this candidate.
