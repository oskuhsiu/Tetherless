# Same-host document-provider runtime comparison

Status: standalone diagnostic implementation; **not native-validated and not a product fix**. Do not replace the full-app iOS 26.2 acceptance gate with this experiment. `productAccepted` remains false in every result.

## Why this experiment exists

The original full-app run [37247923030, attempt 1](https://github.com/oskuhsiu/Tetherless/actions/runs/37247923030) tested source `89c157dbc6acd3c16eb31a32bdc6d73af6c40f57`. Build, signature checks, boot, installation, launch and public-document creation passed. After two real system cancellations, the single file activation reached DocumentManager at 00:47:49 UTC; product stdout then recorded FileProvider `-1005`, Resolver `-1012` and an empty URL array. No product import outcome arrived within ten seconds. An independent UIKit control also remained waiting, but it selected its own app's document and its stdout was not retained. The product's error codes cannot be attributed to that control.

The original 241-byte file remained intact. The broad service query omitted about 1.8 MB, including selection-time context; APS noise dominated its retained lines, and exact processes `ResolverService` and `LocalStorageFileProvider` were missing from its predicate. Original UI artifact SHA-256: `7edc964fe50816aac025f1a4cd6d43a3f2c644339ed35ba4902fab4553165f81`.

Hypothesis: delivery through the local document provider differs between installed iOS 26.2 and iOS 18.6 under a fixed host, compiled apps, signatures, source fixture and UI interaction. This is a discriminating standalone experiment, not another full-app retry or an assertion that Apple is at fault.

## Frozen conditions

- One `macos-15` job, arm64, installed `/Applications/Xcode_26.3.app/Contents/Developer`, Xcode **26.3 / 17C529**, Simulator SDK **26.2**. The compiler/SDK/architecture contract is enforced before building
- Both exact runtime identifiers and versions must already be available: `com.apple.CoreSimulator.SimRuntime.iOS-26-2` and `com.apple.CoreSimulator.SimRuntime.iOS-18-6`. Their runtime build versions and complete inventory are recorded. No download, alternative runtime or toolchain fallback
- Actual macOS 15 version/build, runner architecture, ImageOS and ImageVersion are retained. This pair shares one actual host; the new host image is **not asserted equal to the historical failing host**. A mutable runner label is not an image pin
- Two newly created, separately owned `iPhone SE (3rd generation)` devices. Allocation happens only after both runtimes pass preflight; both devices remain shutdown during compilation. Existing ownership, readiness, bounded capture and shutdown helpers are reused with separate case working directories. No shared reset, device deletion or permission change
- The existing `DocumentFixtureApp.swift`, its `build_inputs`, target, host-signing command, actual-signature inspector and exact payload are reused. Producer identity: `org.tetherless.testdocuments`. Its source is not edited and its optional same-container picker is never opened here
- Separate recipient identity: `org.tetherless.Tetherless.RuntimeRecipient`. Its `LSSupportsOpeningDocumentsInPlace=true` matches the actual product’s receiver declaration; `UIFileSharingEnabled` is absent and it never writes Documents or publishes the source. This removes a plausible receiver-semantics confound, not a demonstrated cause or a claim that the key is required for callback delivery. It has no source payload, product import code or selected-file read. Only fixed callback/dismissal observations are saved privately in its cache
- Producer is compiled/signed once. Recipient and UI test runner are built/signed by one `build-for-testing`, explicitly targeting arm64. The generated xctestrun is reused unchanged by one `test-without-building` per runtime. No rebuild or resign is performed between cases
- All files in all three signed bundles and the xctestrun are hashed before either case and checked before/after each. Installed bundle contents must match those original hashes too. A tool-induced modification invalidates the comparison rather than being silently accepted
- Producer and recipient signatures are inspected through the existing helpers. The Xcode-generated runner is a prebuilt toolchain executable, so its actual codesign verification, host entitlements and thin arm64 architecture are retained separately; the product-specific linked-identity parser is not misapplied to it

Runtime order is iOS 26.2 then iOS 18.6, sequentially, shutting down the first owned device before starting the second. Host/order effects are not randomized; a difference is runtime-associated evidence, not proof of a unique root cause.

## The native observation

XCTest launches the ordinary producer, waits for its coordinated document creation, and terminates it. It then launches the separate UIKit recipient and performs:

1. Two distinct system picker presentations with the real system Cancel button
2. A third presentation using `.propertyList` and `.xml`, `asCopy: false`, single selection and visible extensions
3. The same reviewed semantic navigation/cell selector as the product test, including exactly one activation of `Tetherless-Invalid-Pairing.plist`
4. One ten-second wait for the terminal dismissal observation, followed by exact `selectedFileURL`, counts `1,1,1`, no protocol violation, real picker disappearance and enabled/hittable open-button assertions

The delegate retains earlier picker identities so duplicate or late callbacks are counted, not discarded. If UIKit has already detached a cancelled picker before calling its delegate, the recipient records that actual state synchronously. Otherwise it checks actual presentation state in the ordinary dismissal completion. There are no artificial callbacks, selector alternatives, coordinate taps, sleeps, retries, extended outcome deadlines or copy-mode substitutions.

The payload SHA-256 must remain `8adc01ad4d6304deb1daf74335f9acc7891ed5ed442dd85c5a50a7e30b58b96b`. Source verification runs independently after **every attempted case, including a failed UI command**. A never-created/unavailable source is an explicit gap; it is never reported as preserved. Callback receipt is deliberately separate from byte access, parsing and product acceptance.

## Evidence and failure handling

Output is under `.generated/document-picker-runtime/`:

- `evidence/preflight/manifest.json` and `commands.json`: initial incomplete record, all bounded probe outputs/statuses/timestamps, accepted/refused environment and full runtime inventory. Missing executables, timeouts and nonzero exits still leave partial evidence before any build
- `evidence/build/`: complete build logs, actual signature/architecture inspections and full artifact hash maps
- `evidence/iOS-26-2/` and `evidence/iOS-18-6/`: separate owner, readiness evidence, complete xcodebuild stdout, xcresult, screenshots/accessibility hierarchies, recipient observation, source verification, installed-artifact hashes and independent case result
- Each case retains the **entire** `xcresulttool export diagnostics` and attachments output. A stdout inventory records paths, full byte counts and SHA-256 without excerpting. The exact recipient stdout must be nonempty. The export manifest must bind a valid final PNG, nonempty accessibility hierarchy and well-formed selection result to this test and device; missing/empty/corrupt evidence fails explicitly. Collection read errors stay in the case result and do not prevent the other runtime
- Six focused queries cover `ResolverService`, `LocalStorageFileProvider`, DocumentManager/DocumentManagerUICore, all recipient messages (including errors), `fileproviderd` and `filecoordinationd`. Each uses the fixed case start/end window in UTC and excludes `com.apple.apsd` noise. Existing bounded capture records original/retained byte counts, head/tail offsets, truncation, command status and timestamps separately. Installed tool help is retained before those queries
- `evidence/comparison.json`: both independent cases and overall diagnostic status. The second runtime is attempted even if the first UI fails, unless an environment/immutable-artifact/cleanup boundary prevents meaningful continuation

Read `selectionObserved`, `sourceVerification`, immutable/installed artifact checks, `testCommand`, `collectionComplete` and `recipientStdoutRetained` separately. A selected callback does not excuse missing evidence. Query/export failures or truncation prevent `diagnosticPassed`; they do not rewrite the callback observation or hide the original XCTest failure. Cleanup can only shut down a live device matching a saved ownership record.

## Trigger and interpretation

The new workflow is triggered only by a `develop` push touching this directory or `.github/workflows/document-picker-runtime.yml`. It has read-only contents permission, existing pinned checkout/upload action SHAs and its own concurrency group. It does not modify or trigger the existing path-filtered full-app workflows; the unfiltered core workflow still runs independently. Avoid a PR for this diagnostic because existing unrelated PR triggers are broader. Review and checkpoint first; this directory does not dispatch anything itself.

- Both deliveries stall: iOS 26.2 alone is insufficient to explain the shared failure; inspect the retained common provider/fixture/signing evidence rather than rotating runtimes
- Only iOS 18.6 delivers: supports a runtime-associated difference under this exact host and artifact set; iOS 26.2 and the full product remain unresolved
- Both deliver: the standalone path works in this environment; the product's original failing path is still unaccepted
- Environment/build/installation/readiness/artifact/evidence failure: no runtime-selection conclusion from that case; preserve its precise boundary, do not blindly rerun

No result establishes pairing parsing, successful renewal, Apple login, signing authorization or physical-device behavior.

## Portable checks and remaining native gate

From the repository root:

```sh
python3 -m unittest discover -s Diagnostics/document-picker-runtime/tests -v
python3 -m py_compile Diagnostics/document-picker-runtime/run.py \
  Diagnostics/document-picker-runtime/tests/test_runtime_comparison.py
```

The portable suite uses explicitly scripted tool responses only in its tests, plus a real subprocess output/error retention check. It covers exact selection rejection, compiler/image drift, partial failed-probe manifests, immutable artifacts, once-only callback admission, source verification after failed UI, missing/empty stdout, missing/empty/corrupt attachments, collection read errors and failed/truncated commands, both-case continuation and isolated trigger/native-source contracts. These tests do not execute UIKit, Xcode or Simulator.

Before the first native run, the independent review must accept this focused source, workflow and decision. Native project lint, Swift type checking, signing, generated-runner structure, both runtime launches, actual cancellation ordering, file-provider delivery, export completeness and installed bundle identity remain to be verified on the pinned macOS toolchain. A Linux shell without `swiftc` cannot establish those gates. Do not weaken a failed gate or claim this is an already-tested native reproduction.

Command-model references: [Apple build-for-testing/test-without-building](https://developer.apple.com/library/archive/technotes/tn2339/_index.html), [Apple test build reuse](https://developer.apple.com/videos/play/wwdc2019/413/), [GitHub runner image identity](https://github.com/actions/runner-images).
