# App-side host pairing boundaries

This isolated source candidate adds caller-owned host transport, native call lifetime management and validation-before-promotion helpers. It does not activate wireless pairing, replace existing imports or connect onboarding/repair UI. The reviewed Rust host packet is unchanged.

Four portable source checks pass. The Debug and Release Swift runners explicitly skip because Swift is unavailable locally. Linux can run the 12 portable core fixtures; the seven Foundation/Bonjour fixtures require an Apple host. Nineteen Swift fixtures are authored, including mocked Bonjour lifecycle and actual temporary protected-store rename tests. They have not run. The native bridge also requires compilation against the new actual Cbindgen header and both Apple slices; its build condition remains disabled.

## Source ownership

Only new files are supplied. `PairingFileManager.swift`, `PrivateFileStore.swift`, the existing import/reset behavior, onboarding, startup and all wireless gates remain byte-identical. The relevant pairing manager and private-store preimages match the retained 1fc/c5e workspaces. No build flag, preparation registration or consumer call is added.

- `NativeCallLifetime` reserves a claim before native entry is queued, rejects entry after retirement, and runs cleanup once every admitted call actually returns
- `BoundedPairingHostBridge` implements the reviewed four-symbol host API behind `TETHERLESS_BOUNDED_PAIRING_HOST && canImport(IDevice)`. It owns the token/context, bounds PIN copies, joins concurrent cancel calls before free, and closes the original accepted FD after native return
- `PairingBonjourListener`, also disabled behind the native host build condition, owns one dual-stack BSD listener and a platform Bonjour publication. It returns only after the dispatch source has closed the listener, every result forwarded to the UI actor has finished, and the publisher has acknowledged stopping
- `PairingPromotion` sends exactly the normalized candidate bytes to a caller-supplied joined validator, then permits one synchronous protected commit. Cancelled or failed validation never calls commit

The bridge rejects Simulator, non-iOS, pre-iOS-27 and a non-native backend. The backend argument must come from the real selected backend, not a UI preference or a mock. It requires the exact newly compiled native API; the old packaged host API cannot substitute for it.

## One session's ownership

The future consumer must run the entire user-initiated flow inside `NativeMutationGate.withLease`. Keep that same task scope until platform publication/listener cleanup, host native return, staged-validation return and final promotion/recovery classification finish. The existing task-local mutation scope permits `PairingFileManager.savePairingFile` to borrow that lease. Do not acquire a second independent raw process lease for the commit, or move storage writes to the native worker.

Prepare the bridge on a supervised non-UI worker while retaining the lease. Publish the returned identifier and TXT metadata. The listener accepts one connection, stops advertising/listening, and transfers a `PairingAcceptedSocket`. The bridge retains that socket and its callback context before queueing C entry. Neither the consumer nor another library may read/write/shutdown it or change its flags. A single-transfer ownership token closes the original descriptor after the native duplicate has been dropped. Rejected entry closes only its own newly claimed socket; a repeated call sharing an already-transferred socket cannot close the active call's descriptor.

A cancel handler must invalidate the UI generation, call both listener cancellation and bridge cancellation, and continue awaiting their actual returns. `cancel(true)` from native remains a request. It never authorizes freeing a context or releasing the lease. Close a prepared bridge that never receives a connection by awaiting `close()`.

The six-digit PIN is copied while the native callback is active. A queued main-actor delivery rechecks bridge state. Its consumer must additionally check `promotion.acceptsPIN(for: generation)` before changing the view, because a previous view/session can be superseded while its native operation is still stopping. No PIN, host IRK, pairing record, endpoint, identifier or raw error is logged by these helpers.

The deadline stops an unfinished listener/publication, then still waits for cleanup acknowledgements. A missing OS acknowledgement can therefore leave cancellation awaiting cleanup; no timer releases the lease early. The sleep task holds only a weak listener reference and is cancelled when stopping. Actual Apple runtime behavior needs verification.

## Platform evidence and fixtures

Apple documents [NetServiceDidStop](https://developer.apple.com/documentation/foundation/netservicedelegate/netservicedidstop(_:)) as the notification that publication/resolution stopped, and [didNotPublish](https://developer.apple.com/documentation/foundation/netservicedelegate/netservice(_:didnotpublish:)) as a failed publication. A started publisher receives an explicit stop request even after publication fails, and the operation awaits DidStop. A source cancellation acknowledgement also waits for any accepted socket still held in a forwarded actor callback. Apple's [publication guide](https://developer.apple.com/library/archive/documentation/Networking/Conceptual/NSNetServiceProgGuide/Articles/PublishingServices.html) explains both the default run-loop schedule and the stop callback. The listener removes the initial default-mode schedule before using common mode, then removes its explicit schedule on completion. NetService is deprecated but exposes platform publication of an independently owned BSD port.

The injected Bonjour fixtures override publication and stop methods and use local socket pairs. They do not advertise or contact peers. They cover both acknowledgement orders, a stop acknowledgement overtaking queued accepted-socket delivery, cancellation while stopping, duplicate socket transfer, failed publication, TXT failure before publication and cancellation before start. The Bonjour fixtures live under `Integration/fixtures`, so ordinary core tests do not depend on native-target source membership. Real Bonjour/local-network permission behavior, required application usage-description/service declarations, foreground/background interruption and socket interoperability remain unverified.

## Promotion and stored-record reuse

The validator receives the exact `PairingRecord.xml` that will be committed, bounded to 4096 bytes. It must authenticate the staged record against the current app container without promoting it first, and it must return only after all owned native work has joined. The helper does not infer this property from syntactic parsing, peer UDID, displayed PIN or a test closure.

Capture the current target record under the lease before validation. After validation, compare it again before committing. Final cancellation check and the synchronous commit claim occur without an actor suspension. If cancellation wins first, commit is never called. If commit wins first, a subsequent cancel reports false because it cannot reverse rename.

Use the existing protected save/import method for the final commit and read the same target through checked storage APIs. A failure with an unchanged readable target is `unchangedFailure`. If rename may have happened, readback changed or readback is unavailable, the result is `recoveryRequired`; do not automatically retry or report that the old record was retained. A committed record still needs the caller's ordinary connection/readiness checks. Existing stored-record startup/reuse behavior is unchanged.

The tests inject both pre-rename and post-rename failures into a real temporary `PrivateFileStore`. They verify that the old bytes survive pre-rename failure and that post-rename failure is reported as requiring recovery. No stronger cross-file/defaults atomicity or remote peer rollback is claimed.

## Remaining composition and activation requirements

The following remain separate work, not working functionality supplied by this packet:

1. Execute the 19 Swift fixtures in Debug/Release and compile the platform listener/bridge against the official SDK and exact generated host header. Exercise the real native bridge with a native-call spy, including false/late/repeated cancellation
2. Compile/run the frozen host20 and staged acquisition29 native fixtures and the actual C/Swift ABI probes; add a complete successful synthetic peer transcript before a functional host-safe claim
3. Bind the staged validator to its separate single-use token, numeric endpoint and actual app bundle. Own an independent random filename and 32-byte protected, backup-excluded challenge file until validation joins, then delete only that owned file. No challenge file or endpoint resolver is implemented here
4. Compose the flow inside the existing mutation lease, use the existing protected record store, and connect generation-scoped PIN UI/onboarding/repair only after native capability and lifecycle evidence passes
5. Verify first approved setup and stored-record reuse in the consolidated device acceptance pass. Container possession is not hardware attestation and cannot exclude a compromised or relaying peer

The Python runner creates a small separate package and enables the transport's build condition only in that fixture package. The bridge and IDevice library are not part of the fixture package. It reuses the existing 60-second/16-MiB process-group runner for each Swift configuration, reaping children before deleting its owned temporary package. It uses only the small required core files plus the platform listener and synthetic tests. The absent compiler is recorded as skipped, never passed. No CI, publication, account or device action was performed for this candidate.
