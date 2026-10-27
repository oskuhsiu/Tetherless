# Decision: read the retained owned picker archive offline

Prepared 2026-10-05. This is a diagnostic candidate, not a product correction or a native result. Publication and the one bounded analysis execution belong to the coordinating task; no execution is implied by this document.

## Fixed evidence and failed boundary

- Repository: oskuhsiu/Tetherless; historical source 3d97ef75a224a76f84ba6741da8d9a6b89f99217
- [Run 37298228388](https://github.com/oskuhsiu/Tetherless/actions/runs/37298228388), attempt 1, iOS 26.2 job 111724485744
- [Artifact 11341735733](https://github.com/oskuhsiu/Tetherless/actions/runs/37298228388/artifacts/11341735733): 76,465,711-byte ZIP, SHA-256 ac79e699970ebf98f07277855ffd824529fb826b6aba01583da4538433b742e2
- The actual product and source fixture installed. Fixture readiness passed; source-container coordinated lookup succeeded. The original XCTest passed two system cancellations, then failed its unchanged ten-second folder assertion after the observed On My iPhone cell activation. The snapshot remained on Browse Locations. No file selection/parser/store acceptance followed
- Historical MobileInstallation evidence records successful fixture install and completed LaunchServices saves. This does not prove successful Files-provider enumeration. The false documentCreationObserved manifest field is a never-updated installer default, also present in the historical passing 18.6 manifest
- The full xcresult retains the owned Simulator archive. Prior focused collection stopped before direct service logs; the broad text capture omitted the navigation interval. Do not attribute this to boot, an absent fixture, or a guessed selector

## Question and bounded observation

Hypothesis: local-root lookup/enumeration stalls or errors after the picker accepts On My iPhone navigation. It remains an unproven hypothesis. Read the retained records to distinguish explicit enumeration/error evidence from navigation/IPC-only observations. Do not launch the product, Simulator, independent control, or another full UI job.

Only the following immutable archive object may be exported:

- Owned Simulator E5EAC8DE-7B7F-481E-863A-0C3B2876A831, runtime iOS 26.2/23C54
- Logical path within xcresult diagnostics: simctl_diagnostics/E5EAC8DE-7B7F-481E-863A-0C3B2876A831/system.logarchive
- Archive ID A8B6986C-2BB8-45F8-B6EF-23650E916F85; recorded archive coverage 10:52:52–10:56:54 UTC
- Exact object reference and Info.plist hash are pinned in picker_archive.py
- The selected xcresult tree is 1,070 files / 67,535,630 bytes; its canonical tree SHA-256 is 01c5a92e41208542401cedb17698fc40bd5f7212273ce602d438e91dfd0c7a27
- The complete exported archive tree is 289 files / 160,044,778 bytes; its canonical tree SHA-256 is 494aa14e7eee4e8f273fe0bac03b0e75928ea5925bbbf9c20ae12226e8c2d2c0
- Canonical tree hash: SHA-256 of compact JSON of sorted [relative POSIX path, byte count, file SHA-256] rows. These values were derived from the digest-verified ZIP and its exact referenced object graph, without decoding runtime log messages. Largest exported object is 121,738,223 bytes; the 128-MiB per-file / 192-MiB total bounds cover the measured archive

The sole query window is 2026-10-05 10:54:58+0000 through 10:55:57+0000. It does not expand the XCTest deadline. PID22858 is the observed picker service bound to product PID21855 and org.tetherless.Tetherless.XYZ0123456 by the retained monitor rows and hierarchy. PID25024 is the LocalStorageFileProvider process observed in the same owned Simulator launchd dump. PID12472 is its fileproviderd. No predicate guesses a service executable name.

The query uses only those PIDs and an explicit allowlist of DocumentManager, DocumentManagerUICore, FileProvider, XPC, ExtensionKit, file coordination and RunningBoard subsystems. Because fileproviderd is shared, its branch also requires an explicit known local-provider, fixture-bundle or owned process reference. Other subsystems, account/APS traffic, other process IDs, and other time intervals are excluded. Redacted or unsupported records may reduce diagnostic power; they do not authorize widening the read.

## Implementation and privacy boundary

The new workflow runs only on the exact user-authorized verify/staged-pairing-native branch, with an exact repository/ref job guard and narrow new-file path triggers. Existing develop/PR workflows, acceptance assertions and product source are unchanged. Repository contents and Actions permissions are read-only; checkout does not persist credentials or fetch submodules.

The official [download-artifact v8.0.0 tag](https://github.com/actions/download-artifact/releases/tag/v8.0.0) resolves to 70fc10c6e5e1ce46ad2ea6f2b72d43f7d47b13c3, independently checked through the official GitHub tag API. Its pinned [action inputs](https://github.com/actions/download-artifact/blob/70fc10c6e5e1ce46ad2ea6f2b72d43f7d47b13c3/action.yml) support skip-decompress and digest-mismatch:error. The official action handles the ordinary ephemeral Actions token; Python never reads credentials. The script separately requires the original ZIP size and SHA before interpreting entries, and extracts only the xcresult. Every selected input byte is thereby bound to the known artifact; tree hashes add a second invariant.

Installed xcrun/xcresulttool help must advertise object export, directory type, exact ID/path/output options and the legacy flag. The [Apple Xcode 16.3 release notes](https://developer.apple.com/documentation/xcode-release-notes/xcode-16_3-release-notes) document that legacy export form. No broad diagnostics export is permitted. The exported archive must match its pinned Info.plist and complete tree before reading logs. Installed log help must advertise positional archive input, exact time filters, ndjson, UTC and predicates. The installed predicate help must explicitly identify the supported process-ID field; otherwise stop rather than invent syntax.

All Apple commands use the existing byte-pinned bounded_process.py and its exact error dependency. Help commands: 30 seconds / 64 KiB; object export: 90 seconds / 64 KiB; the one query: 90 seconds / 8 MiB, each with the supervisor's bounded TERM/KILL/join. These are offline tool bounds, not changes to original product waits. Failure, byte limits, unknown cleanup or unsupported syntax remain gaps. Help exit64 may supply observed syntax tokens but is explicitly recorded with outputComplete=false; it is never represented as complete diagnostic output.

OS privacy defaults are untouched. No private-data logging flag or configuration is enabled. Raw ZIPs, extracted xcresult/archive data, tool output and supervisor sidecars remain private temporary files and are never uploaded or committed. The private analysis scratch tree is removed only after confirmed child/group cleanup. temporaryCleanupConfirmed describes that analysis tree only; the official action’s separately downloaded original ZIP remains in unuploaded RUNNER_TEMP until the ephemeral runner is disposed of. If cleanup cannot be confirmed, do not delete a potentially active child's files; retain no public path or raw output and let the ephemeral runner dispose of its workspace.

Only report.json is uploaded. The report drops message text, paths, filenames, arbitrary domains, identifiers, addresses and payloads entirely. It retains fixed process roles, normalized timestamps, lexical event classes, whitelisted error domains/numeric codes, raw-message SHA-256 values and hashed activity IDs. The hash preserves evidence identity without publishing the message. Unknown/malformed/out-of-scope lines and event/error-code caps are explicit gaps; exceptions are never rendered as raw text.

## Interpretation and stopping condition

A timestamped enumeration request/error code tied to an owned process/activity can support the provider boundary. A matched enumeration completion before the stalled navigation would weaken the simple provider-not-ready hypothesis and focus attention on navigation/IPC handling. Explicit IPC invalidation/timeout can identify another observable boundary. Keywords alone are classified as mentions, never proven transaction outcomes, causal diagnoses or accepted import.

Missing records, redacted context, an unrecognized schema, capped output or incomplete tool/cleanup evidence cannot refute a hypothesis or establish successful enumeration. collectionComplete describes this export/query only, not proof that the OS logged every event. Even complete scoped output can be inconclusive. Stop after this one historical query and review its sanitized evidence. No automatic repeat, broader log query, UI retry or product change is authorized by this candidate.

Portable tests cover artifact/path ownership, privacy and scope filtering, exact time boundaries, explicit omission gaps, supported syntax, failure/cleanup handling, real execution of the existing process supervisor against a synthetic Python child, and exact workflow permissions/branch/upload scope. They are not Apple log decoding or product acceptance.

## Assembled-source dependency refresh

Before publication, the coordinating task assembled the reviewed native source packet with apply_patch.py SHA-256 a41e75b1903265c650c198bca05a2afc08ff053a01bcf0a56682cf95ce19c80a. The archive wrapper's previous 132a633318faa7df826997570cc122993d6ce878abf183db61ca2472ad856ce6 pin correctly refused that changed file. Replace only this exact expected digest; do not accept either digest dynamically or remove verification.

The inspected delta extends the staging helper's allowed reviewed profiles and gates alternate fixture-overlay paths in load_lock and patched_files. VerificationError is unchanged, as are imports and other import-time statements. bounded_process.py imports only that error class; it never invokes either changed staging function. Its own digest remains 7724f6c3eb7d624f49a2651b30f1d6e6bb2c47d356449cd495fad28b2dd144e4. The wrapper still loads both exact verified copies in private scratch. Rerun its 22 portable tests against the assembled packet, including the actual process-supervisor test, before publication. No archive, time window, command, privacy, acceptance or workflow setting changes in this refresh.
