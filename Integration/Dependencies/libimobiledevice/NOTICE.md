# Source and license notices

This is an independent Tetherless derivation of SideStore's libimobiledevice XCFramework sources, not an official SideStore release. Preserve the original authorship, copyright and license notices.

The matching-source archive includes complete unchanged original source trees plus the exact namespacing recipe. The only cryptographic source changes are the six-file, four-function identifier transform documented in namespace-contract.json. Algorithm bodies, context layouts and the public C headers are unchanged.

Original source and corresponding license material:

- SideStore/libimobiledevice-xcframework, commit 0f88f7bbd1aa9713d8c8c2255df31f2b25ff9d8a: COPYING, COPYING.LESSER, AUTHORS, source-file notices and 3rd_party/README.md
- Bundled Ed25519: 3rd_party/ed25519/LICENSE and source-file notices, preserved verbatim
- Bundled SRP: 3rd_party/libsrp6a-sha512/LICENSE and source-file notices, preserved verbatim
- libimobiledevice/libplist, commit 32428abacb909988e8e960a8845a6430b17b6a60: COPYING, COPYING.LESSER and source-file notices
- libimobiledevice/libimobiledevice-glue, commit da770a7687f35fbb981db4d7b47b1b032cd5c2c7: COPYING and source-file notices; the SHA implementations retain LibTomCrypt notices
- libimobiledevice/libusbmuxd, commit 93eb168bf6b07472d17781328c21df0c60300524: COPYING and source-file notices

The selected krzyzanowskim/OpenSSL framework at fdc9231384f37f053dffe058fd6dfc6c5072dae5 remains a separate external input. Its authenticated LICENSE.txt and provider contract accompany input evidence; this C artifact does not bundle it or claim source/binary equivalence. Any downstream redistribution must preserve applicable dependency licenses and corresponding-source/relinking obligations; this test-only artifact is not a release-admission decision.
