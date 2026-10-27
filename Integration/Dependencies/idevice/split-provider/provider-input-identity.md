# Selected OpenSSL input identity and link-contract requirements

Date: 2026-10-05 UTC

## Result and boundary

The selected framework/header and host archive inputs now have verified local byte identities. This closes the prior missing-input-byte evidence gap for the proposed Apple-framework and standalone host-static profiles. It does not approve or activate either profile, establish source/binary equivalence, or prove native linking, runtime configuration or Apple compatibility.

This independent review checked hashes, lengths, Git blob identities, file-mode metadata, header text and package metadata. Framework executables and host archives were handled only as opaque bytes for hashing. No binary format, architecture contents, Mach-O/CMS/signature, native execution or paused application integration was inspected. No old app artifact search or duplicate capture was performed.

## Provenance and exact inputs

Paths are relative to `/workspace/scratch/30ad10c9f5dc/`.

- Parent-owned capture run: `37339519028`, job `111862711856`, artifact `11357912777`
- Run source: `87dcec6fd14dfbbe9cdef0b36feeebe72b1a6dd0`
- Vendor: `krzyzanowskim/OpenSSL`, commit `fdc9231384f37f053dffe058fd6dfc6c5072dae5`, tree `e7c94a8efdade4b77561c7176ba7cc4865bc32ee`
- Input root: `tetherless-component-verification/37339519028/openssl-verified/`
- Parent verification document: `tetherless-component-verification/37339519028/verification.json`
  - SHA-256: `ff429fb6560121ea80a434460c4e6fb337673799168af557f5037c4f049b571a`
- Capture receipt: input-root `receipt.json`
  - SHA-256: `0bd290ce1c2313d86223ebf6f2c43082022eded5b0b20bfe07142f7458cf00d2`
- Opaque input tar: `tetherless-component-verification/37339519028/retained/openssl-inputs.tar`
  - Independently rehashed SHA-256: `8c13cbf432e6400b3699d2d9b727831e946011792d9c3bed5149b35ddd31197c`
- Existing disabled input contract used for comparison: `tetherless-native-build-tools/Integration/Dependencies/idevice/openssl-candidate/target-inputs.json`
  - SHA-256: `f564ad0a0551f976fe98d720649784905dd346d5187298cf5dc9800e1aa82bbc`

The capture receipt contains 447 unique entries totaling 40,574,701 bytes. Its commit, tree and totals match the expected parent capture. The parent reports every captured entry was checked.

This reviewer independently checked 443 scoped files totaling 40,506,667 bytes for actual size, SHA-256, Git blob hash, regular-file identity and executable/non-executable mode consistency. The four privacy/signing-resource files were intentionally not examined. No claim of reviewing their contents or admission is made.

### Apple framework payloads, opaque identities only

- `Frameworks/OpenSSL.xcframework/ios-arm64/OpenSSL.framework/OpenSSL`
  - 5,113,136 bytes; Git mode `100755`
  - Git blob: `8e5792a4b98f84a56548f8dbf7f03de8f8558e7c`
  - SHA-256: `355ff3a21cb4eb8ef86bfba202414de1a9070b3ddf8703d03cedfcacbe9e5431`
- `Frameworks/OpenSSL.xcframework/ios-arm64_x86_64-simulator/OpenSSL.framework/OpenSSL`
  - 10,425,568 bytes; Git mode `100755`
  - Git blob: `c780c5ed3b626d0f7bd4d149a781fe8dcbbe78ca`
  - SHA-256: `a25a4fab515e6e69d4b3c0dd6d09c6d80e022759a7169dbca565593d085abeaa`

These labels and paths do not independently prove payload architecture or linkage type.

### Host archive payloads, opaque identities only

- `macosx/lib/libssl.a`
  - 3,173,672 bytes; Git mode `100644`
  - Git blob: `a9191a6db4aabecab8a22c7316aac9a515f6a120`
  - SHA-256: `fb4b112f0e9144a7df58b3530e2498894dee2a9371dd21416b969eb6dc362370`
- `macosx/lib/libcrypto.a`
  - 15,711,656 bytes; Git mode `100644`
  - Git blob: `5462f1729148cf971667afc6791d72bd22673838`
  - SHA-256: `7e898e6676f079dd6c77c47de2dd64b936ee68ab3a09e13f5f89b8e297df2702`

Both host archive Git blobs and sizes match the prior input contract.

## Header and package correspondence

Each captured Apple framework has 144 verified headers. The 143 non-umbrella headers match every corresponding platform-header Git blob and length in the prior contract; the only additional header is `OpenSSL.h`. The 143 host headers also match the prior macOS contract.

- All three inspected `opensslv.h` copies have SHA-256 `8cf6d4e7355d48f0ea0aa821dfb8beaf7535bb0d45f21e49cd50d7f7e09802c7` and declare version 3.6.2
- Both Apple `configuration.h` copies have SHA-256 `01aaeb2d4ea6e701dfe569f6f239557d77a2025bb383c802141f97e7804a0713`
- Host `configuration.h` has SHA-256 `97e8953d286d3a2480035ec43e869cdcc2911dd2591900bfe079ad92e0d52f01`
- These configuration headers define OPENSSL_NO_SSLKEYLOG and OPENSSL_NO_DYNAMIC_ENGINE
- Both framework module maps name module OpenSSL and umbrella header OpenSSL.h
- Package.swift selects `Frameworks/OpenSSL.xcframework`; XCFramework metadata maps the expected device/simulator identifiers to their OpenSSL.framework paths; framework metadata reports package version 3.6.2000

This establishes header-byte and declared package correspondence. It is not evidence that the opaque native payloads were built from those headers/configuration or implement the reviewed source.

## Requirements for the separately authored contract

The build owner is to author the disabled contract/tests; this reviewer will review them independently. This document is requirements and evidence, not self-approval of a new implementation.

### Standalone host fixture profile

- Use only the verified macOS 143-header tree and two archives above
- Set explicit target-prefixed OPENSSL_INCLUDE_DIR and OPENSSL_LIB_DIR, OPENSSL_LIBS=`ssl:crypto`, OPENSSL_STATIC=`1`, OPENSSL_NO_VENDOR=`1`
- Isolate its build outputs and receipts from Apple consumer builds
- Require host component and combined TLS/borrowed-adapter runtime evidence; do not treat host success as Apple-provider evidence

### Apple consumer framework profile

- Compile against the exact verified selected framework's 144-header tree, exposing both `OpenSSL/` and `openssl/` include spellings to those same bytes
- Set target-prefixed OPENSSL_LIBS to a present empty string. Omission, null and empty must not be conflated: omission defaults to ssl and crypto in the reviewed openssl-sys build script
- Set explicit verified include and existing isolated library-search directories and OPENSSL_NO_VENDOR=`1`. Prefer an empty isolated native-search directory so no sibling static archive is available for accidental selection
- An explicit OPENSSL_STATIC value controls link kind only; with an empty library list it neither adds a provider nor establishes whether the eventual framework payload is static or dynamic
- The normal final C/Swift/Rust link must resolve OpenSSL through exactly the existing selected framework; do not silently add the separate platform archives, replace the framework or substitute another provider

The source basis is retained openssl-sys 0.9.112 `build/main.rs:41-56,219-239,497-503` and `build/find_normal.rs:7-12`, as recorded in the original receipt. The callback/error source gaps are already closed by `CALLBACK_ERROR_ADDENDUM_37334149741.md`, SHA-256 `b60cc0ba6d9094437c8c797f1bc5b5fa98aaf50e7e7b4e5ed14c9b8f67e7d92a`.

### Required validation and tests

- Validate selected paths, sizes, mode metadata, Git blobs and SHA-256 inventories before use; reject missing inputs, unsafe aliases, mismatched targets and substituted header trees
- Test present-empty Apple LIBS preservation, explicit host ssl:crypto, no discovery fallback and no implicit profile activation
- Avoid inherited OpenSSL/pkg-config/compiler-search overrides; record the resolved feature graph and the exact toolchain/SDK/process build inputs
- Record openssl-sys build-script output proving no OpenSSL link-lib emission for the Apple profile and explicit static ssl/crypto emission for the host profile
- Compile header-configuration assertions using each selected include view and target compiler. Header assertions are compile evidence, not a substitute for native provider/runtime evidence
- Retain normal final-link and applicable runtime evidence identifying the actual target inputs, OpenSSL version/configuration and intended PSK behavior. No binary disassembly/admission is part of this review
- Preserve Cargo.lock, established AWS-LC/rustls defaults and the previously reviewed no-custom-global-initialization-override boundary

## Remaining gate

No helper or provider native success follows from input capture. The parent reports the helper stopped before Cargo at an inventory-representation comparison. The separately authored link contract/tests are still awaiting independent review. Native compilation/linking, runtime provider behavior and Apple compatibility remain pending.

Only this additive review document was created. Frozen acquisition manifests/source, prior receipts and the existing disabled target contract were not changed.
