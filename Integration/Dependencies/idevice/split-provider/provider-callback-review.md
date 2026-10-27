# PSK callback and error-conversion source addendum

Date: 2026-10-05 UTC

## Outcome

The two selected-source gaps identified in the prior registry review are closed for the staged acquisition path. No new blocking source concern was found in the authenticated PSK callback trampoline or SSL-to-I/O error conversion. The prior bridge/owned-write source conclusion remains valid.

This is source evidence only. No Rust fixtures or native tests ran, and no target-provider, final-link or device-compatibility acceptance is granted. The parent reports the new run stopped during preparation on separate packaged configuration handling.

## Immutable baseline and new provenance

Paths are relative to `/workspace/scratch/30ad10c9f5dc/`.

- Prior receipt, preserved unchanged: `tetherless-openssl-registry-review/REVIEW_RECEIPT.md`
  - SHA-256: `15728c544e0625cfd5fd56356e4984f287438c5bc2e3626b5cc00e4a27fd5d2d`
- Frozen candidate manifest, preserved unchanged: `tetherless-contributory-acquisition/source_manifest.json`
  - SHA-256: `8eabd1496f2944178ed7897e25f4ef11640b049229b3e20dfe03580df8e93e07`
  - All five candidate overlay hashes reverified
- New retained source manifest: `tetherless-component-verification/37334149741/retained/review-sources/review-source-manifest.json`
  - SHA-256: `06d2e896c1739c3fc667c8873f94967b0623f80b7a3c542572889aed89fbc4f8`
  - Parent-controlled run: `37334149741`
  - Parent-reported verified ZIP SHA-256: `4ec950881fa9765554be351401ae9f30c47a27eb60316b7414bbb256357e443e`; the ZIP was not independently reopened in this addendum
- Pinned Cargo.lock SHA-256: `3c1a7710f0cd02f9100e91b97c9f8abc6546f115f7f3255551c990628aea0e16`

The four relevant package archive SHA-256 identities were rechecked against that lock:

- openssl 0.10.76: `951c002c75e16ea2c65b8c7e4d3d51d5530d8dfa7d060b4776828c88cfb18ecf`
- openssl-sys 0.9.112: `57d55af3b3e226502be1526dfdba67ab0e9c96fc293004e79576b2b9edb0dbdb`
- tokio-openssl 0.6.5: `59df6849caa43bb7567f9a36f863c447d95a11d5903c9cc334ba32576a27eadd`
- jktcp 0.1.7: `4d3b9e59938be47d261173086c65a9352fe048951bc502109e7595b70b60cd98`

All four relevant per-package checksum manifests match the aggregate manifest. All 27 retained files for these packages match their SHA-256 entries, totaling 420,215 bytes. The previous 25 files are byte-identical to the earlier retained inputs. Other packages listed in the expanded aggregate manifest are outside this addendum's source-review scope.

New files, under the new retained `review-sources/openssl-0.10.76/` directory:

- `src/ssl/callbacks.rs`: 18,480 bytes; SHA-256 `63d04641a08f2069631eb0a76175429a4093c63dd7e0bf2a289d8400700a3124`
- `src/ssl/error.rs`: 5,756 bytes; SHA-256 `f39ac3e1037a35ae5cccbf5cf5976044614a6368c9ffe3f1b96bead63c0c4231`

As in the original receipt, this verifies the retained selected files and their linkage to parent-controlled archive extraction; it is not an independent rehash or complete audit of every archive file.

## PSK trampoline findings

Registry-relative references below are in openssl 0.10.76.

- `src/ssl/callbacks.rs:55-95`: raw_client_psk retrieves the context-owned callback, borrows the native identity and PSK buffers using their supplied capacities, invokes the callback synchronously and returns its length as u32. A Rust callback error is placed on the OpenSSL error queue and returns zero. No background task or deferred callback ownership is introduced.
- The staged callback in candidate `idevice/src/remote_pairing/tunnel.rs:204-210,233-235` first requires a nonempty identity buffer and at least 32 output bytes. It then writes the empty identity terminator and exactly 32 PSK bytes. Its only return lengths are zero and 32, so the trampoline's usize-to-u32 conversion cannot truncate this result and the native output capacity cannot be exceeded.
- The staged callback ignores the server hint and performs no allocation, formatting or logging. The trampoline creates a borrowed view of the native C-string hint; safety still depends on the selected OpenSSL implementation satisfying its C callback contract, as with the other native buffer inputs.
- `callbacks.rs:97-134` has equivalent output-capacity plumbing for the server callback used by synthetic fixtures. Those fixtures check the expected empty identity and sufficient output space before their fixed-size copy.
- The PSK trampoline does not catch panics and uses an internal expectation that its registered callback exists. The current staged callback has no input-driven panic path after its explicit size checks. This is not a general panic-recovery or allocation-failure guarantee. Future callback changes must preserve the non-panicking, bounded behavior.

## Callback lifetime and destruction

- `src/ssl/mod.rs:1339-1356` stores the Send+Sync+'static callback in context ex-data before registering the native trampoline.
- `src/ssl/mod.rs:1562-1577,1795-1820` owns callback data in a Box and registers the matching type-specific free hook. `src/ssl/mod.rs:569-580` synchronously reconstructs and drops that Box during ex-data cleanup.
- `src/ssl/mod.rs:2297-2306` constructs SSL and retains an owned context reference in session ex-data. This is consistent with the context and callback remaining live for the TLS session and with the previously reviewed SSL/BIO destruction order.

No lifetime escape or detached cleanup was found for this use. Ordinary Box destruction is not a promise of secret-memory zeroization; none is claimed here.

## Error conversion and privacy

- `src/ssl/error.rs:64-87`: into_io_error returns the stored I/O cause only when the cause is actually an I/O error. Otherwise it returns the SSL error unchanged. It does not turn an SSL authentication failure into success or invent a retryable I/O cause.
- Combined with the previously reviewed `src/ssl/mod.rs:3886-3908,3960-3977` and tokio-openssl bridge, actual WouldBlock I/O continues to Pending; other SSL errors remain failures. Handshake WANT_READ/WANT_WRITE processing remains as documented in the prior receipt.
- `src/ssl/error.rs:100-121` can format underlying error details when callers request Display; it does not itself send or log them. The staged handshake uses fixed rejection mapping at candidate `tunnel.rs:247-257`, the composite uses a fixed protocol result at `ffi/src/staged_acquisition.rs:176-183`, and the owned adapter reduces transport failures to fixed error kinds/messages. This inspected path does not expose the binding's detailed error formatting.

## Unchanged remaining gates

This addendum closes the specifically missing callbacks.rs/error.rs review items. It does not claim a complete audit of all Rust binding or native OpenSSL source.

The prior source-backed, separate host-static and proposed Apple single-framework link profiles remain proposals requiring their recorded verification. Exact target library/framework/header bytes, one-provider final C/Swift/Rust linking, runtime engine/configuration and PSK behavior, native logging behavior, combined OpenSSL/borrowed-adapter fixtures and Apple compatibility remain outstanding. No equivalence is inferred from version labels or package resolution.

The prior global-initialization correction also remains: the safe binding performs standard OpenSSL initialization; the route adds no custom initialization override. No ambient/global configuration change was made or authorized.

Only this additive documentation file was created. The prior receipt and frozen acquisition files remain unchanged. No binaries, paused admission/integration areas, CI operations, external writes, installs or shell network access were inspected or used.
