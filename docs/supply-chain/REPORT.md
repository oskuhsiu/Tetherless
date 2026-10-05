# BASE-02 and delivery supply-chain review

Baseline: `oskuhsiu/Tetherless@3dd8641e84698b97f96d53a6c53ed8c6ca4675bd`  
Checked: 2026-10-05 UTC

## Decision

**BASE-02 is open, with specific closures.** The source graph is substantially recoverable and the five prebuilt framework releases have consistent publisher metadata. That is not independent binary provenance. The remaining essential gate is the on-device authentication chain: Unicorn's combined-license permission is unresolved, and the two Apple ADI libraries have neither an independently established trust anchor nor a documented acquisition/use-rights basis in this review. No production code or trust policy was changed.

This review produced 32 source/binary component records, 509 Cargo.lock observations, 121 exact-blob-verified source/evidence files and 35 collected license/notice files. Cargo observations include optional, host, test and other-platform dependencies; they are deliberately not presented as 509 libraries inside the app. This is an engineering evidence review, not a legal clearance or final artifact SBOM.

## 1. Established source graph

The complete GitHub trees were queried with `recursive=1`, and each reported `truncated=false`. The application gitlink is SideStore `0dd743f75afc358b0ba4a002feb5f19474492371`; its two gitlinks are SideSign `6b68651697f99791ef85404b7aea1891a26a285d` and minimuxer `12be70dc2627307a16bfd2dc7a009080d5bec909`. There are no further gitlinks in those two pinned source trees. Minimuxer also contains local Common and DeviceGateway Swift packages.

The native `Package.resolved` pins 13 remote Swift packages. Their manifests were read at those exact revisions, including version-specific manifests where present. SideSign's six lock entries and minimuxer's two lock entries agree with the application's corresponding pins. ZIPFoundation `22787ffb59de99e5dc1fbfe80b19c97a904ad48d` / 0.9.20 also matches TetherlessArchive's independent lock. See `inventory.json` for every complete revision.

The native graph includes AnisetteKit, CodeSignKit, GSACryptoKit, RemotePairingKit, KeychainAccess, libdeflate, MarkdownKit, Nuke, SemanticVersion, Starscream, swift-asn1, swift-crypto and ZIPFoundation. The manifests contain branch requirements, but the supported native build passes `-onlyUsePackageVersionsFromResolvedFile`. A branch declaration does not imply that this build floats when its lock is enforced. The generated build must nevertheless preserve and record that exact lock.

`swift-crypto` records vendored BoringSSL revision `0226f30467f540a3f62ef48d453f93927da199b6`; its original license was obtained from that exact BoringSSL revision. `CryptoExtras`, used by CodeSignKit and GSACryptoKit, depends on BoringSSL even on Apple platforms. Do not drop BoringSSL from the inventory because the plain Crypto product can use system CryptoKit. Starscream's additional swift-nio-zlib-support dependency is Linux-conditional, and ZIPFoundation's CZLib alternative is non-Compression-platform conditional.

There is an upstream SideBackup build target and an embedded SideBackup.ipa build phase. The 26-byte repository resource was not readable through the text connector; it was not assumed to be a reviewed executable. The final nested IPA must be inventoried after the build. No current Roxas package or gitlink was observed; its README mention alone is historical documentation, not a new runtime dependency.

Primary source: [pinned native lock](https://github.com/SideStore/SideStore/blob/0dd743f75afc358b0ba4a002feb5f19474492371/AltStore.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved), [SideSign manifest](https://github.com/SideStore/SideSign/blob/6b68651697f99791ef85404b7aea1891a26a285d/Package.swift), [minimuxer manifest](https://github.com/SideStore/minimuxer/blob/12be70dc2627307a16bfd2dc7a009080d5bec909/Package.swift)

## 2. Binary inventory and evidence quality

| Input | Release / source commit | Expected archive SHA-256 |
|---|---|---|
| EMProxy | v0.9.3 / `6e117e140ca7cff4ff106bdefa18147552a0e592` | `3998789c38d09b55e488d46e31897affc7bbcb9c244d7a9d5b2d5cf6afd916c3` |
| IDevice | v0.1.68-ss-3e55c84 / `3e55c8486b2057e40c1f74aaaa1155c82341cf76` | `445702d53942597deb4cdec2c4122d16a3f4ac124ce26cd75b68dab3dad92416` |
| libimobiledevice | 1.4.0-ss-0f88f7b / `0f88f7bbd1aa9713d8c8c2255df31f2b25ff9d8a` | `7ccbdd56b074807461fc43d2e32ba92f20df2501a6c14cf9f64a917e7f3fe6e7` |
| Unicorn | 2.1.4-xcf-a53ddc9 / `a53ddc9ac6d65b24936d4a37917333fcd816cfd0` | `52e4ac9e2d704c4941adc2c381df8706aabf673dc843611a90b33ad349d562db` |
| OpenSSL | 3.6.2000 / `fdc9231384f37f053dffe058fd6dfc6c5072dae5` | `37846a8bd302cb2443eff47f1045ab844d0cd40bf82cc6159cfad9aa5c3eff9e` |

Each manifest checksum matches the corresponding GitHub release asset digest. Each resolved producer commit is marked verified by GitHub. The first four have successful CI runs on that exact commit: [EMProxy 32957789452](https://github.com/SideStore/em_proxy/actions/runs/32957789452), [IDevice 35451211928](https://github.com/SideStore/idevice/actions/runs/35451211928), [libimobiledevice 32954800108](https://github.com/SideStore/libimobiledevice-xcframework/actions/runs/32954800108), [Unicorn 35347118050](https://github.com/mahee96/unicorn/actions/runs/35347118050). The OpenSSL commit's returned run is Pages deployment, not a framework build. The complete responses are retained under `evidence/`.

These checks authenticate neither the archive contents against independently rebuilt source nor the full producer's dependency closure. No archive bytes were downloaded here, no per-slice hashes/link maps were checked, and no build attestation was verified. A signed source commit does not sign a later release asset. GitHub asset digest agreement is useful integrity evidence, but remains on the same publisher-controlled channel.

Concrete producer weaknesses:

- The [libimobiledevice build recipe](https://github.com/SideStore/libimobiledevice-xcframework/blob/0f88f7bbd1aa9713d8c8c2255df31f2b25ff9d8a/justfile) downloads OpenSSL 3.6.2000 with curl and unzips it without checking its hash, then combines its static objects with the other libraries. The outer libimobiledevice hash does not retrospectively authenticate that input
- EMProxy and IDevice commit Cargo.lock files, but their selected Apple recipes call cargo build without `--locked`. This does not prove the release drifted; it means the recipe lacks a fail-closed lockfile constraint. Exact iOS target/features/toolchain and actual linked crates remain to be established
- Producer workflows use floating action tags, installed tool versions and `macos-latest`. Rebuilding must record or constrain those inputs. Do not execute inherited curl-to-shell recipes as a shortcut
- OpenSSL's wrapper Makefile identifies upstream 3.6.2. The upstream annotated tag resolves to `fe686e15d84334b284f883118ed92f64b409b3aa`; its GitHub signature status is unknown_key. Its source checksum download is not an independently anchored signature verification. The wrapper's signing-identity requirement is not a reason to request the user's signing credentials; an unsigned reviewed framework build recipe is the appropriate candidate closure

The libimobiledevice producer has exact source gitlinks for libplist `32428ab…`, libimobiledevice-glue `da770a7…` and libusbmuxd `93eb168…`, plus vendored ed25519 and Stanford SRP-derived code and OpenSSL. Their complete pins and notices are in the inventory. IDevice's C++ example plist_ffi gitlink is separate from the registry plist_ffi 0.1.6 in Cargo.lock; they must not be conflated.

## 3. Reachability and feasible dependency removal

**Unicorn and ADI are essential in the current design.** NativeRenewalBackend requires on-device Anisette and uses OnDeviceAnisetteManager when obtaining authentication headers. [AnisetteClient](https://github.com/mahee96/AnisetteKit/blob/db8b41022697b6c19be8a5f01a1ce834145a2a26/Sources/AnisetteClient.swift) chooses UnicornAnisetteDataProvider on iOS; that provider executes the two local ADI libraries. This is not an excluded JIT/debug feature. Removing Unicorn without replacing the provider breaks mobile-only login/reauthentication.

**libimobiledevice is removable in principle, but not already excluded.** [MinimuxerWrapper](https://github.com/SideStore/SideStore/blob/0dd743f75afc358b0ba4a002feb5f19474492371/SideStore/Core/DeviceApi/MinimuxerWrapper.swift) defaults to `.idevice`, reads the saved backend and applies it. [MinimuxerApi](https://github.com/SideStore/minimuxer/blob/12be70dc2627307a16bfd2dc7a009080d5bec909/Sources/MinimuxerApi.swift) imports both gateways and constructs either. Both products are unconditional package dependencies. NativeProfileTransport calls the selected gateway for profile installation/readback, and foreground install paths use the same facade.

The smallest removal candidate is a reviewed IDevice-only variant: remove LibimobiledeviceGateway's product dependency, associated import/factory branch and backend-selection UI; migrate or explicitly reject old saved alternative selections; remove RemotePairingKit/OpenSSL only after confirming no remaining production import. CodeSignKit and GSACryptoKit's OpenSSL targets are test-only, so those test references need not imply runtime shipping. Preserve IDevice's pairing, install and profile capabilities and verify generated native build plus linker map. Hiding a settings row or disabling hot-swap alone does not remove the binary. This is a recommendation, not an implemented closure.

EMProxy is also an unconditional package target, but is runtime-conditional on enableEMPforWireguard. A LocalDevVPN-only product might exclude it after a separate route decision and build graph review. It was not silently removed from the present product inventory.

## 4. License findings and obligations

- Tetherless declares AGPL-3.0-only for original code and explicitly describes its SideStore derivative status. The snapshot has no standalone root LICENSE. Add a full license and durable notice bundle; retain upstream attribution, source headers and modification notices
- SideStore/minimuxer include AGPLv3 texts. SideSign README declares GPLv3, but its complete pinned tree has no LICENSE file. Supply the GPLv3 text with attribution; do not label it unlicensed or MIT solely because the file is absent
- AnisetteKit, CodeSignKit and GSACryptoKit include AGPLv3 texts and README distribution commentary, including App Store prohibition. Retain those exact texts and document a distribution-specific conclusion. This sideload-only scope does not require deciding whether an App Store release would be lawful. Do not assert those extra statements are all standard AGPL requirements
- MIT components require their copyright/permission notices. Apache components require their license and applicable notices/modification attribution. Collected originals are under `licenses/`; not all binary-producer Cargo licenses are yet collected
- libimobiledevice and its C library family carry LGPL obligations; static linkage requires a deliberate source/relinking compliance choice and usable corresponding material. A filename or a general AGPL label is insufficient
- LocalDevVPN is an external helper with a custom StosVPN license, prominent attribution and an anti-rebranding clause. Preserve its name and official installation path rather than repackaging it. StikPair's custom MIT Non-Commercial license is a reference-only constraint, not an MIT dependency grant

### Unicorn: reviewed grants, still unresolved

Do not derive a GPLv2-only conclusion just from GitHub's license detector. At the exact fork revision:

| Evidence | Observed grant |
|---|---|
| README and Cargo.toml | GPLv2 / deprecated GPL-2.0 declaration |
| root uc.c | copyright header, no explicit later-version grant |
| include/unicorn/unicorn.h | LGPL2 notice |
| qemu/target/arm/translate.c | LGPL version 2 or later |
| qemu/LICENSE | QEMU overall GPLv2; files without notices GPLv2 or later; individual file terms govern |
| COPYING | generic GPLv2 text with an unfilled example notice; not a project-specific later-version grant |

The upstream [2016 license clarification issue](https://github.com/unicorn-engine/unicorn/issues/634) and [2022 SPDX issue](https://github.com/unicorn-engine/unicorn/issues/1642) do not establish an unambiguous project-wide later-version grant. The first member response says LGPL would require proof concerning the remaining QEMU code. These comments are evidence of uncertainty, not permission obtained for Tetherless.

Smallest closure: inspect the actual AArch64/TCI compiled source list and all applicable file-level grants, including the wrapper and fork modifications; document the basis permitting the exact combined AGPLv3 app. If a required file is GPLv2-only, a compatible replacement or rights-holder permission is needed. The present audit does not prove that such a file is in the linked slice, nor establish a compatible grant for all of it. GPLv2-only and GPLv3 differ materially; a later-version election requires an applicable grant. [FSF GPLv3 guide](https://www.gnu.org/licenses/quick-guide-gplv3.html)

## 5. ADI: technical provenance and rights are separate

The pinned app defaults to `https://servers.sidestore.io/servers.json` for metadata and `https://zzz.haus/oda.json` as fallback. Tetherless enforces a metadata-provided archive hash and seals/revalidates local cache generations. Those are real integrity improvements. A malicious authorized metadata origin can still supply its own payload/hash; local receipts do not independently authenticate Apple as publisher.

The [upstream discussion](https://github.com/orgs/SideStore/discussions/1457) identifies the same domain, records an author's claim that libraries match an Apple-signed APK, and has maintainers acknowledge the temporary hosting and intended future user preparation flow. This review did not independently reproduce the commenter's comparison. Do not promote that comment to verified executable provenance.

**No ADI binaries are being proposed for inclusion in Tetherless's distributable.** Runtime acquisition by the user from an authenticated Apple package would avoid distributing those bytes in our app and reduce third-party-ODA trust. It is a different technical and rights analysis, not automatically an approved use.

The direct-CDN candidate `https://apps.mzstatic.com/content/android-apple-music-apk/applemusic.apk` is recorded in [omnisette-server's README](https://github.com/SideStore/omnisette-server/blob/243933525a0d7204d6a117b074ee2c97b2da67d9/README.md). This tool could not retrieve the APK, and current [Apple support](https://support.apple.com/en-ie/109340) directs users to Google Play or named regional stores. No current APK bytes, package version, authenticated signer fingerprint, whole-package digest or per-library digests were established here.

Feasible technical design after acquiring an independently trusted sample:

1. Download or locally select the original Apple APK with a bounded, explicit source flow; do not treat a repacked ODA archive as publisher evidence
2. Validate the APK signature and whole signed content, with an independently anchored Apple signing-key fingerprint and explicit rotation policy. A self-signed certificate's subject string is not that anchor. Use a reviewed verifier; merely reading META-INF or a certificate is not signature validation. [Android APK v2 verification](https://source.android.com/docs/security/features/apksigning/v2)
3. Extract only the two exact arm64-v8a library paths into a private bounded staging area; reject duplicate/path/link/size/architecture anomalies. Record source package/version/hash, verified signer, exact file hashes and review manifest ID
4. Make the app's independently reviewed manifest authoritative at cache admission and every provider load. Server-list JSON may locate content but must not authorize new code. Preserve the prior admitted generation on error

For a smaller implementation, independently review one official package and compile its exact file hashes into the app; this still needs the trusted sample and rights basis. Unknown packages must fail visibly, not acquire trust from user confirmation or a matching metadata hash. The existing loader does not verify APK signatures; this design requires implementation and adversarial tests.

Rights gap: Apple's publicly available [Apple Music Android agreement](https://www.apple.com/legal/sla/docs/AppleMusic.pdf), dated 2016 in that document, describes use on compatible Android devices and restricts redistribution. It does not establish permission here for extraction and execution in a different iOS app. Exact current-package terms, applicable exceptions or permission remain unestablished. No terms were accepted. A user obtaining the APK, an Apple signature, or a private deployment does not itself answer that distinct question.

The draft admission policy is **not installed and contains no fabricated approved ADI entry**. Installing an empty allowlist and calling authentication complete would be a product regression. Until usable authenticated input and the rights decision exist, expose a real delivery blocker and keep independent development moving.

## 6. Smallest closure plan

| Gate | Concrete closure | Needs device/secrets? |
|---|---|---|
| Notice/source packaging | Adopt reviewed inventory and full notice bundle; add GPLv3 text for SideSign; preserve attribution; publish complete exact corresponding source with binary | No |
| Alternative C binary | Either verified rebuilt libimobiledevice chain, or reviewed IDevice-only native product graph with migration, build and link-map proof | No |
| Required binary provenance | Rebuild or verify attestations for exact EMProxy/IDevice/Unicorn and retained OpenSSL inputs; record tools, locks/features, per-slice hashes and source archive | No |
| Cargo completeness | Resolve producer's iOS target/features, preserve Cargo.lock without changes, collect per-crate licenses/notices; distinguish build-only from linked inputs | No |
| Unicorn compatibility | Complete compiled-file grant review, then choose compatible licensing/replacement/permission path if needed | No device; external permission would need separate authority |
| ADI trust and use basis | Obtain authenticated official package evidence; establish signer/hash anchor and documented acquisition/use basis; implement/test admission with a usable eligible package | No account secrets; rights cannot be fabricated by tests |
| Final delivery | Generate final IPA inventory, nested IPA/framework list, SBOM, source archive digest, lock/toolchain manifest and notices from the same candidate SHA | No device for packaging; physical acceptance stays separate |

Current `package_unsigned.py` records source commit and IPA digest but not all dependency pins, binary evidence, source/notice bundle identity, toolchain or a final inventory. The native prepared-source archive intentionally excludes frameworks and several source/build extensions; the top-level source artifact omits submodule bodies. These are useful diagnostics, not a complete corresponding-source distribution. Fourteen-day CI retention is not a durable release channel.

The recommended next code increment is a narrow packaging/inventory gate plus the reviewed optional-gateway reduction, if product scope accepts that backend choice. It should report unresolved essential entries rather than convert metadata consistency into trusted provenance. No official release, main promotion, external contact or device request is justified by this audit alone.

## Verification and limitations

Every collected source text was re-hashed with Git's blob algorithm against the connector-returned blob SHA. An added tool-serialization newline was removed only when doing so restored the exact expected blob; all 121 now match. The inventory verification script also validates document parsing, unique component IDs, graph endpoints, five manifest/release digest matches, all 509 lock observations and license-copy hashes.

Not performed: final binary/entitlement/code-signature scan, independent rebuild, source-file-wide malware audit, vulnerability database scan, final SPDX external-schema validation, exact compiled Rust/C graph, APK extraction/signature verification or legal rights clearance. The earlier prepared-source artifact was used only to orient call-chain inspection; decisive dependency/manifest evidence was fetched at the pinned upstream revisions and current Tetherless source was read locally.
