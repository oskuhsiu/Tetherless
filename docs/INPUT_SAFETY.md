# Pairing records and untrusted IPA inputs

Implementation checkpoint: `318faaefb116a60dee86c5cddccfd9df4c865719` (2026-10-02). Pairing/archive implementation is carried forward; HTTP boundaries were added in `4c24758`.
This describes implemented boundaries, not an independent audit or proof of device acceptance.

## Pairing storage and migration

Pairing records are stored under Application Support/TetherlessPairing, not the user-facing Documents folder. The shared `PrivateFileStore` uses a flat, bounded namespace, 0700 directories, 0600 files, no-follow descriptor reads and regular-file/link-count checks. Records are limited to 1 MiB; malformed, mixed-protocol, unsupported or excessively nested plists fail closed. Binary plists are normalized to XML for the inherited parser. Type validation is not cryptographic validation or a successful pairing handshake.

Replacement writes use a fresh protected file, flush it, then rename it over the previous record and flush the directory. A failure before promotion preserves the existing record. The legacy migration checks both the normalized destination and the original source again before removing the old file; conflicting protected records are not overwritten. Bootstrap tools may still initially provide one of the known legacy files in Documents. The app migrates those files on its maintenance path before the old maintenance-counter check. Cold boot also attempts migration under the shared lease before declaring a protected record missing, because database maintenance and boot run independently. It does not ask a desktop bootstrap tool to know a new private directory.

Full reset persists `reset.marker` before removing records. A partially failed reset or restart cannot silently reactivate legacy data; fetch and migration honor that marker. A newly imported record must be saved and read back, then any reset leftovers must be removed before clearing it. A failed cleanup leaves the marker in place; an ordinary replacement does not delete the other protocol. Single-protocol deletion and recovery from an incomplete legacy-file cleanup still require lifecycle integration tests; do not generalize the full-reset transaction guarantee to every deletion path.

Import, reset, maintenance and protocol-switch call sites use the same mutation lease as renewal. Wireless pairing owns a lease for its callback session, writes into a protected random staging directory, uses a fixed filename rather than a device-provided name and imports through the validated store. It does not automatically open a share sheet for pairing secrets. Empty or cancelled PIN input no longer becomes `000000`.

On iOS, Data Protection is requested before secret bytes are written. The directory is excluded from backups. The actual protection class, behavior before first unlock and lifecycle of the underlying wireless library require consolidated device acceptance. The iOS Simulator returned no protection class in our first assertion; that hardware-specific test remains explicitly skipped on Simulator, not reported as passed. Independent backup-exclusion, file-permission and IO tests remain enabled there.

## IPA extraction

`Packages/TetherlessArchive` contains the production extractor. The preparation script copies those exact Swift sources into SideSign and redirects the shared unzip APIs to it. Host and simulator package tests therefore exercise the same extractor, not a separate mock implementation. ZIPFoundation is pinned to 0.9.20 / `22787ffb59de99e5dc1fbfe80b19c97a904ad48d`.

The extractor snapshots a regular input file into private staging, checks the complete ZIP32 central directory against local headers and data descriptors, then validates all output paths before extracting. Supported compression methods are stored and deflate. A truncated iterator result cannot be accepted as a valid prefix of an archive. CRC values, including zero, are checked. Actual streamed output is counted independently of the archive's declared sizes.

Traversal, absolute paths, duplicate/case-colliding or normalization-colliding paths, file/directory conflicts, links and special files are rejected. Extraction occurs in a fresh tree. Existing destination files are never overwritten. IPA import publishes a single validated Payload/*.app only after extraction and metadata checks succeed. Generic multi-root extraction does not claim an atomic all-or-nothing directory merge across process termination; it only removes its own newly published paths on a caught error.

Main and nested app/extension/framework metadata have bounded Info.plist parsing, filesystem-safe bundle identifiers and single-component executable names. Custom XML entities are rejected. Unpacked .app imports are disabled rather than allowed to bypass archive validation. Resource-only bundles may omit an executable.

### Deliberate v1 limits

| Boundary | Maximum / policy |
| --- | --- |
| Input archive | 1 GiB (1,073,741,824 bytes) |
| Total expanded data | 4 GiB (4,294,967,296 bytes) |
| Individual expanded file | 512 MiB (536,870,912 bytes) |
| Entries | 30,000 |
| Central directory | 16 MiB |
| Path | 4,096 UTF-8 bytes, depth 32, component 255 bytes |
| Info.plist | 1 MiB |
| Unsupported archive features | ZIP64, multidisk, encryption, symlinks/special files |
| Unsupported input path | Unpacked .app directory import |

These restrictions may reject a legitimate large or unusual IPA. There is no automatic unsafe fallback. Compatibility expansion requires explicit code and adversarial tests, not disabling the checks. These extraction limits are separate from the implemented streaming HTTP transfer limit below.

## Remote IPA downloads

The native download operation now uses the shared `BoundedHTTPDownload`. It accepts HTTPS GET URLs without embedded credentials and checks every redirect, reconstructing requests rather than carrying authorization or cookies to another origin. At most five redirects are followed. Responses must be full HTTP 200 bodies, not partial/multipart or transport-compressed responses. Declared Content-Length and actual streamed bytes are independently bounded to 1 GiB, and a declared length must match the final body. An absent length is allowed only within the streamed budget.

An ephemeral URLSession has no shared credential, cookie or cache store. Public IPA downloads cannot prompt for account credentials or client keys. Failed/cancelled transfers remove their own temporary file, never unrelated caller data; incomplete files are never returned as complete input. The caller owns the private directory and successful file lifecycle. Request/resource timeouts are bounded, but this is not a complete global memory/disk reservation system.

A supported-version fallback uses the selected app version's URL, not the original incompatible version's URL. URLProtocol tests exercise actual URLSession callbacks and file IO with scripted responses; they are not live TLS/CDN integration tests.

## No post-extraction dependency injection

`AltStore.plist` may describe remote `ALTDependencies`. The inherited downloader could write those resources after archive validation. V1 now accepts only an absent or empty dependency list; malformed, oversized or nonempty manifests fail with a self-contained-IPA requirement. No additional resource is downloaded, and no legacy unsafe fallback runs. This intentionally rejects legitimate IPA packages requiring this feature.

## Verification and remaining work

The core tests use real temporary files for replacement failure, migration conflicts, links, FIFOs, permissions, backup exclusion and reset-marker recovery. Pairing fixtures contain synthetic bytes, never real account or device secrets.

The archive tests build real ZIP files independently of the preflight parser, plus actual deflated content. They cover successful extraction, path collisions, CRC corruption, local/central mismatch, encrypted trailing entries, forged expanded sizes, cancelled work, destination preservation, malformed metadata and nested executable escapes. A compressed expansion test forges the declared size and confirms that the streaming consumer stops before publishing output.

Still required before the complete product is a candidate: aggregate disk/memory reservation and cross-operation resource budgeting, abandoned staging cleanup after process termination, native wireless callback/bootstrap lifecycle tests, remaining authentication/maintenance mutation and log auditing, and unsupported-entitlement/Mach-O/signature parser review. Safe extraction does not certify the IPA's behavior or independently attest CMS signatures or iOS launch authorization. See STATUS.md for exact executed checks, skips and revisions.
