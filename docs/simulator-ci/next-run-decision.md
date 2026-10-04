# One-run decision — failure-only independent UIKit recipient

- Scope: AUTO-02 / PAIR-01, discriminate provider resolution from product presentation/recipient behavior.
- Inspected product/run/attempt/job: **2ae7ebdc9a143505f8664ef5b85a61fac9347f0d / 37220011794 / 1 / 111488264234**.
- Develop parent for this change: **c6e2b27f7531622f91f78138870261ed0d73494d**.
- Read-only report SHA-256: **8bd9c3a882c559c398886c913dc0c086704dc78be481c93d5091b58027b66753**.
- First failed boundary: UI step 11. Successful original-file postcheck is not UI acceptance.

## New observed evidence

The separate source now actually launches, presents documentReady and creates its verified 241-byte file. The product still gets FileProvider -1005 / resolver -1012 at 17:28:49 UTC, with no materialized URL/delegate delivery. The complete fixed-event scan and post-selection screenshot agree. Source isolation alone did not fix it. Artifact SHA-256: c9ef4da729c008f252d164e285e9b9b482c50d07ed06bf3a8c7650b57b44d039. Existing provider logs show container lookup/preparation errors, not a confirmed product parser failure.

## One hypothesis and comparison

Hypothesis: the same system file-provider path can fail independently of Tetherless's SwiftUI/request state. Add a plain UIKit recipient in the already separate source app. Do not change Tetherless, its file types, entitlements, action or deadline. Run the control **only after** the original failure has been captured so it cannot pre-warm provider state and hide a defect. Product results remain immutable and failing even when the control succeeds.

Observe whether the independent recipient receives a file URL from one real system selection. This does not read selected contents or validate pairing. Differences remain: source-app identity and own-container access versus cross-container Tetherless access. Control failure supports a common provider/runtime boundary; control success points to remaining recipient/presentation/access differences, not automatically one confirmed cause.

## Unchanged acceptance and stop conditions

Two product cancellations, single exact semantic document tap, ten-second original outcome deadline, actual dismissal, explicit rejection, original source bytes, incomplete pairing, consent off, recovery and cold relaunch stay required. No alternative success path, manual delegate callback, arbitrary sleep, double tap, global reset or runtime switch. The control has separate bounded waits and cannot retry the product. Its result is diagnostic only.

Before publication, 33 focused tests and 16 skill tests passed; changed Swift parsed. These are not UIKit runtime evidence. Same macos-15 workflow, owned concrete destination, signing checks and toolchain-selection policy; report actual image drift rather than assume immutable labels. Existing builds still exercise the actual product. No new dependencies, privileges or workflow flags were added.

One run is justified by the previously unavailable independent comparison, not by repeating the same hypothesis. After it is dispatched, record the run ID once and hand off. If pending, do not poll or mix in installer/supply-chain work. If both recipients fail, preserve that result and isolate/review the runtime/provider rather than modify product code just to make CI green. If the control is unavailable, do not infer either outcome.

Apple API references (not claims that Apple documented this exact failure):
- https://developer.apple.com/documentation/uikit/uidocumentpickerviewcontroller/init(foropeningcontenttypes:ascopy:)
- https://developer.apple.com/documentation/uikit/uidocumentpickerdelegate/documentpicker(_:didpickdocumentsat:)
