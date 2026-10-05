# Native persisted-error privacy boundary

## Scope and evidence

This increment covers the native `LoggedError` history and the three reviewed
`Source.error` persistence paths at SideStore
`0dd743f75afc358b0ba4a002feb5f19474492371`. It does not certify all application
error handling, historic database contents, the console log, or device behavior.
No account, device, credential, or server response is needed for its tests.

Reviewed upstream files were retrieved through the GitHub connector at that exact
commit and their UTF-8 bytes matched Git blob hashes:

| File | Git blob SHA |
| --- | --- |
| `AltStore/Core/Model/LoggedError.swift` | `affb5ad682b36f60201a9c9482496d33fe1f6230` |
| `AltStore/Managing Apps/AppManager.swift` | `9397828fddd9c47cfa8d17e6cec1d4f0a7385bbb` |
| `Shared/Extensions/NSError+AltStore.swift` | `1b162bf07ac6bae91047beb738360e67829b5914` |
| `SideStore/Core/Operations/PipelineRunner.swift` | `a76344edcf8ed2518f52cff5b19de68fe1d0a991` |
| `AltStore/Settings/Error Log/ErrorLogViewController.swift` | `c2794596f0697b63584dc03f75375d2f6241fb0b` |
| `AltStore/Settings/Error Log/ErrorDetailsViewController.swift` | `5dc5379160cc18e6728a7c9691150c710f113814` |
| `AltStore/Core/Model/BaseEntity.swift` | `6da120b8f46249b0d5bd8b9ded1650614125866a` |
| `AltStore/Core/Model/Source.swift` | `2b9ba04e2099e2d3a79e4daa42c7808d0abda5e2` |
| `AltStore/My Apps/MyAppsViewController.swift` | `0721a46491c1872de337a71e3642d2decb39cba0` |
| `AltStore/Sources/SourcesViewController.swift` | `766ad6143ab0090c575bf50fd8cbc95f4ab0e8f8` |

The pinned source, not a historical prepared-source copy, is the preimage.

## Reachable leak

1. `PipelineRunner.swift:307` passes operation failures to `logger.log`.
2. `AppManager.swift:856-885` preserves cancellation filtering, serializes the
   remaining error, constructs `LoggedError`, and saves the Core Data context.
3. `NSError+AltStore.swift:74-115` makes values serializable, not private: it copies
   arbitrary `userInfo`, materializes localized strings, keeps secure-codable
   strings/URLs/data/containers, and recursively retains underlying errors.
4. `LoggedError.swift:72-76` stores the source domain, integer code, and entire
   resulting `userInfo`; lines 108-110 reconstruct them for display.
5. The history list reads that reconstructed error at
   `ErrorLogViewController.swift:133-138`. Copy-message/code actions read it at
   lines 274-288, and `ErrorDetailsViewController.swift:21-27` formats all details.

The reviewed history controller contains an export-button outlet, but no separate
active `LoggedError` file-export action. Its console-log action at line 222 opens
a separate log file. `BaseEntity.serialize` is a generic inherited serializer
that reads raw managed attributes (`BaseEntity.swift:30-45,74-86`); it is not a
privacy boundary. No invocation of that serializer for error-history export was
found in the reviewed call sites. A future export or direct database/KVC consumer
must use the closed snapshot rather than raw legacy attributes.

## Implemented change

`error_privacy_safety.py` validates all four exact preimages and all replacement
anchors before writing any file. It changes only:

- The `AppManager.log` diagnostic handoff, before its background queue
- The `LoggedError` initializer's error snapshot
- The `LoggedError.error` getter used for history display and copy
- The three reviewed `Source.error` persistence captures
- The two existing optional source-error reads used for display

The helper is appended to the existing compiled `LoggedError.swift`, requiring
no new project-file entry. It returns a fresh `NSError` with fixed domain
`Tetherless.LoggedError`, a code in the closed 1-13 category set, and exactly three
string fields: fixed description, fixed category group, and `failed`/`cancelled`.
Known network/filesystem errors retain bounded operational meaning such as
timeout, offline, TLS failure, invalid response, missing file, permission denied,
and storage full. Known authentication/server domains get coarse fixed groups;
unknown inputs get a fixed application-failure category.

No runtime domain, arbitrary integer, original description, userInfo key/value,
URL, data, nested error, account field, or server message is copied into this
snapshot. Classification consults only domain and code; it does not invoke
localized-description getters, domain value providers, recursive serialization,
or regex redaction. Repeated sanitization and spoofed records in the fixed domain
are reconstructed from the closed category set, never trusted as already safe.

Dates, operation enum, local app name/bundle identifier, app relationships,
Core Data properties/schema, cancellation filtering, original error propagation,
and save failure handling remain unchanged. This deliberately reduces detail in
history; the caller's live error object and execution decisions are unchanged.

## Required integration order

The parent must add one invocation of `error_privacy_safety.py` in
`network_safety.py`, immediately after the existing `maintenance_safety.py` call.
This patch does not edit that parent-owned file.

`AppManager.swift` hashes through the existing preparation sequence are:

1. Raw pinned input: `9397828fddd9c47cfa8d17e6cec1d4f0a7385bbb`
2. After `catalog_safety`: `ae9ed3e39d77aebda142b1dae716769967ac2259`
3. After `maintenance_safety`, this patch's required input:
   `720794f95132df8f64e2c052531470c06544f296`
4. After the complete history/source patch: see the output hashes accompanying
   the patch artifact; the earlier history-only output hash is superseded

Later unrelated transforms do not currently change the four owned sources. Validate
the complete preparation chain and its invocation count when wiring this in.

## Verification and limitations

- Ten focused Python tests passed against the verified pinned preimages
- Python compilation passed for the transform and test module
- The actual Swift 6 debug/release helper and secure-archive round-trip test is
  included but was **not executed** because this executor has no `swiftc`
- The full integration suite ran 247 tests: 214 passed, 29 skipped, and four
  existing tests errored solely because `swiftc` was unavailable; it is not a
  full passing suite
- `swift test`, `swift test -c release`, native app compilation, Core Data
  save/refetch, Simulator history UI/copy, and device behavior remain unverified
  here. The helper-only archive test does not substitute for these stages

The Swift harness uses only synthetic canaries, nested errors/URLs/data, extreme
integer codes, poisoned free-form getters, all closed categories, idempotence,
secure archive/unarchive, and nil-preserving source-error mapping. It asserts
the original error remains unchanged. Source tests cover preimage mismatch,
no partial writes on any changed/missing later input, reapplication refusal,
unchanged schema/relationships/decisions, and legacy getter behavior. Exact
file reconstruction outside the approved substitutions protects live source
error results, sourceID selection, rethrows, success/failure state and UI actions.

**Legacy records remain unchanged on disk.** Their reviewed history display/copy
and source-error display paths use a fresh closed snapshot, but stored userInfo/domain still
exists until separately authorized, deliberately tested maintenance/migration.
There is no purge, schema migration, or claim of retroactive disk sanitization.

## Included Source.error boundary

`Source.error` is an independently persisted transformable NSError
(`AltStore/Core/Model/Source.swift:66`, blob
`2b9ba04e2099e2d3a79e4daa42c7808d0abda5e2`). Three reviewed writes can retain the
same free-form metadata before this patch:

- `AppManager.swift:319`: source refresh failure
- `AppManager.swift:411-418`: merge failure copied to the affected source
- `AltStore/My Apps/MyAppsViewController.swift:1863-1870`: merge failure copied
  from the foreground update path; raw blob
  `0721a46491c1872de337a71e3642d2decb39cba0`

`AltStore/Sources/SourcesViewController.swift:168-173,229-239` reads this stored
error for the warning action and display. Its raw blob is
`766ad6143ab0090c575bf50fd8cbc95f4ab0e8f8`.

The complete transform reuses the same policy at exactly those three persistence
writes and maps each of the two optional display reads through
`TetherlessErrorRecordPolicy.sanitized`. The source-error optional state is
unchanged; `errors[source] = error`, both original merge-error rethrows, sourceID
selection, refresh success handling and context save/error paths are retained.
The general `sanitizedForSerialization` helper is unchanged: other callers depend
on its typed payload for merge error propagation.

All source changes are included in this single transform; its AppManager input
remains the post-maintenance hash above. The two view-controller preimages are
raw pinned files and were also found byte-identical in the historical prepared
source. This closes future writes and the reviewed display paths for old source
errors, not legacy disk bytes or hypothetical new call sites. Native Core Data
and source-screen verification remain pending.
