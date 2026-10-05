# Verified cross-runtime document selection result

Inspected 2026-10-05. [Run 37273262340](https://github.com/oskuhsiu/Tetherless/actions/runs/37273262340), attempt 1, job 111644618374, source `9a49417dc6f6b707b94786882722ca907870fa9c`. Overall conclusion: **failure**, earliest boundary **UI**. No product acceptance or automatic retry.

Artifact 11329279200: 133,081,902 bytes, SHA-256 `3558700b84e0326ae64aae2e11a9c2bab954367bf8933bc0ec1eb7b2c788983e`, independently verified. Host: macOS 15.7.9 (24G830), macos-15-arm64 image 20260907.0337.1. Toolchain: Xcode 26.3 (17C529), Simulator SDK 26.2 (23C57), arm64. Focused preflight inventory, the single build/signature verification and device readiness passed.

## Actual observations

| Case | Cancellations | Third presentation | Source |
|---|---|---|---|
| iOS 26.2 / 23C54 | Two real cancels, one callback and dismissal each | Waiting, zero callbacks, picker still visible; unchanged ten-second assertion failed | Intact |
| iOS 18.6 / 22G86 | Two real cancels, one callback and dismissal each | One selectedFileURL callback, dismissed; XCTest passed | Intact |

Both original files remained 241 bytes with SHA-256 `8adc01ad4d6304deb1daf74335f9acc7891ed5ed442dd85c5a50a7e30b58b96b`. Both installed bundle maps matched the same frozen signed build before and after execution. All 47 uploaded bundle files and the xctestrun configuration were independently rehashed, as were full recipient stdout and required screenshot/hierarchy/result attachments. No changed selector, extra activation, permission change, replacement copy operation or extended assertion was used.

The untruncated 26.2 `document-manager.log` records the single file activation at 06:43:05.084 UTC and the service obtaining its source URL. At 06:43:09.681–.682, recipient bookmark resolution reports FileProvider -1005 / Resolver -1012 and an empty item array. The boundary precedes the UIKit recipient delegate and reproduces the earlier product failure without its SwiftUI/import parser. The separate ResolverService capture contains connection events, not those error details.

This supports a runtime-associated interaction under the same observed host and artifacts. It does not establish the underlying OS defect, a universal platform limitation, or successful product parsing, storage, login, pairing or renewal. Local-provider “bundle name unknown” warnings occur six times in **both** cases and do not distinguish the failing runtime.

## Evidence limitations remain visible

- Both device-log help probes printed usage but returned 64
- Broad recipient unified logs were truncated: 2,783,423 bytes on 26.2 and 2,480,783 on 18.6, each retaining 262,144. Full recipient stdout and required UI attachments were preserved separately
- All six 18.6 unified-log queries warned of a wall-clock adjustment. Missing individual service events there cannot establish that a service was absent
- Therefore both diagnostic cases retain `collectionComplete=false`; an 18.6 passing XCTest is not a green overall diagnostic

The next useful boundary is real-product import/parser/storage evidence on the demonstrated working delivery environment, while preserving unresolved 26.2 coverage. Investigating 26.2 should use the retained service-URL → recipient-bookmark evidence. Do not rerun solely to clear collector warnings, weaken assertions, change signing or guess new tap targets. [Core run 37273262455](https://github.com/oskuhsiu/Tetherless/actions/runs/37273262455) passed for this exact source; it is a separate evidence level.
