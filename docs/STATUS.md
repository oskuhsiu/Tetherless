# Current checkpoint — bounded ODA metadata and non-silent fallback

Updated 2026-10-04 (Asia/Taipei). Starting develop head: cb6bd38faf939ced28c1d83270183910cceb59bd, product 582953d. This increment changes the native ODA metadata routes and adds tested schema/resource boundaries. Work remains on develop, main unpromoted. No physical-device handoff or credentials requested.

## Baseline and actual outstanding UI failure

The previously saved transfer-workspace implementation was recovered from the exact CI source archive (11279746545): ZIP SHA-256 89a7609c076fa681e21145e41caf252e5934bda81d4a9f2bc33c9fabafe243a4, inner TAR 8abd2bba57c7c235fb7f444ba419289bf0e786c776cfb99072e2968068828041 and recorded commit 582953d matched. cb6bd38 is documentation-only. Prior core/native passes remain scoped to that version.

Complete-App run **37138806001** at 582953d finished with failure, not pending: TetherlessUITests.swift:30 timed out waiting for the actual document-picker Cancel control. Setup reached the pairing page, and app stdout records Started DatabaseManager. This matches the earlier intermittent blank system-picker symptom, not proof of another App Group failure or of a cache regression. The downloaded artifact 11279718861 matched SHA-256 71c03352974cf2719b06ef6371d4991f9789a20d3dcec579d8ce18436c5bb44f. Actual test log, app stdout and diagnostic attachments were inspected. No UI assertion was removed or weakened in this increment; picker lifecycle/root-cause work remains open.

## Connected change

All three metadata routes call the same checked adapter. A raw buffer preflight validates grammar/Unicode and bounds depth, tokens, array entries, key and string lengths before Foundation builds its graph. Escaped-equivalent duplicate keys, multiple non-null package aliases, wrong field types and mixed envelopes fail explicitly. Recognized layouts and individual legacy aliases are preserved. Invalid data or unsafe references no longer silently turn into an absent ODA entry and activate fallback. One synchronous parse per process is admitted without queueing.

The adapter is compiled locally together with actual SideSign model declarations, not fake replacements. It demonstrates legitimate explicit fallback when the validated catalog lacks ODA, rejection of malformed/unsafe references without fallback, and relative-reference resolution. The native transformation requires prepared input blob df58f374bd41fc901ee5ed265429f765d33fee09 and runs after the existing cache transform. All destinations are checked before writing. See ODA_METADATA.md for deliberate compatibility and resource limits.

This does not authenticate mutable metadata, downloaded binaries or their distribution rights. The per-parse structural/string budget is not an install-wide RAM/RSS budget. Real Apple/Anisette and locked-screen behavior are not exercised.

## Local evidence before commit

- Completed Linux Swift Debug and Release: **276 tests passed each**, including all **18 new metadata tests**. Two earlier interrupted Release driver attempts are not counted; a subsequently completed invocation exited zero. The initial compile-only filter had no tests and is not counted as execution.
- Python integration: **155 passed, no skips**, using retained exact dd0b09c auth, ae9fd0a cache and 582953d metadata sources. Five new checks include the compiled actual native model/adapter path and refusal of unreviewed inputs/destination collisions.
- Prepared 582953d Debug artifact 11279303445 matched SHA-256 d848afa283f80538685ee1c997bb01891a6eab823e655accd60ae157bb790496 before its source was used. This is an input to local transformation tests, not a native build of this newer increment.
- New macOS, Simulator, native and full-App/UI CI are required for this change. Earlier successful native builds do not validate it.

## Next

1. Read this implementation's fresh CI. Preserve any compiler/test or picker failure and do not infer native execution from local syntax checks.
2. Resolve the repeated system pairing-picker presentation/cancellation failure without skipping that product path. Finish remaining native logging and callback lifetime checks.
3. Independently verify/pin library provenance and distribution rights; finish IPA/install-wide resource admission, remaining first-sign/self-update/supported-configuration tests and branding. Consolidate device acceptance only after feasible development gates.

No downloaded library execution, live Apple provisioning, real profile installation, physical protection, locked-screen unattended renewal or expiry crossing is claimed. Code and exact continuation state are saved together.
