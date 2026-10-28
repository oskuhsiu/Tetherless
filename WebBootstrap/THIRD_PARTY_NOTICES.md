# Web bootstrap third-party code

This directory is an isolated component of Tetherless. Original repository licensing
is unchanged. Third-party files retain their licenses, listed below.

## Vendored executable runtime

Source: [AntonP29/SylvaSigner, full commit f7127d6857a6aaa919b7430ef73baa262fe28070](https://github.com/AntonP29/SylvaSigner/tree/f7127d6857a6aaa919b7430ef73baa262fe28070).
The unmodified `public/wasm/zsign-mobile.js` and `.wasm` are copied from that
commit. `runtime-lock.json` pins their SHA-256 bytes. Build refuses mismatches.
This verifies provenance against the retrieved commit, not a reproducible rebuild
or full binary audit. Upstream source/build recipes are available at that exact pin:

- `vendor/zsign/`: zsign commit `28a6421` with upstream's disclosed browser patches
- `scripts/build-wasm.mjs`, `scripts/build-openssl-wasm.mjs`, `scripts/toolchain.mjs`
- `docs/UPSTREAM.md`, `docs/WASM_BUILD.md`

Components: zsign (MIT), zlib and minizip (zlib-style license), OpenSSL 3.5.7
(Apache-2.0), Emscripten 6.0.0 (MIT and University of Illinois/NCSA).
Exact notices reside in `licenses/`. `public/sign-worker.js` is a simplified
adapter derived from SylvaSigner's MIT mobile worker. No Sylva UI, branding,
enterprise-certificate source, remote IPA proxy, analytics, or hosting integration
is included. The synthetic dylib fixture uses zsign's upstream MIT test binary.

## npm libraries

Runtime dependencies are exact-version pinned in `package.json`; full integrity
locks reside in `package-lock.json`. Direct runtime license texts are copied under
`licenses/npm/` and included in the static build.

- `node-forge` 1.4.2: BSD-3-Clause (selected dual-license option), P12/CMS metadata,
  CSR and local test-only/key material construction
- `@zip.js/zip.js` 2.8.26: BSD-3-Clause, bounded metadata reading
- `@plist/binary.parse` 1.1.0: BSD-3-Clause-Clear, Apple binary plist metadata

## Dependency review (2026-10-28)

The prior 2026-10-06 audit recorded a high Forge finding. The older
[GHSA-86w9-cpqp-85rv](https://github.com/advisories/GHSA-86w9-cpqp-85rv)
was superseded for remediation evidence by the maintainer's
[new advisory](https://github.com/digitalbazaar/forge/security/advisories/GHSA-2g46-22mc-6gwp):
1.4.1 fixes the issue and the pinned 1.4.2 includes that repair. Web and native
copies were upgraded together from the official package, with integrity checks.
Product CSR verification independently uses fail-closed platform WebCrypto;
Forge is not used to establish an Apple trust chain. Development Vite was also
updated to its official 8.1.6 security release.

The fresh full dependency audit in `runtime-audit.json` reports zero known
findings at 2026-10-28. This is a registry snapshot, not proof of no vulnerabilities
or production/device acceptance. Primary sources, prior metadata discrepancy,
call-path review and regression boundaries are in
[`docs/CERTIFICATE_DEPENDENCY_REVIEW.md`](../docs/CERTIFICATE_DEPENDENCY_REVIEW.md).

## Bounded binary plist adapter

`src/vendor/binary-plist.js` is derived from the npm 1.1.0 ESM file. Its original
SHA-256, patched SHA-256, npm integrity and exact source revision are recorded in
`src/vendor/vendor-notices.json`. The narrow patch adds byte/object/traversal/depth/
cycle/materialization budgets, reference-table bounds and prototype-free unique
keys; it does not claim a full format/security audit. The browser invokes it in a
cancellable module worker. Full BSD-3-Clause-Clear license is included in the
static distribution under `licenses/npm/plist-binary-BSD-Clear.txt`.
