# Current code: interrupted-renewal fix and selected-file UI test

2026-10-04. Product implementation b67a36264dd0baddf69fe65cd156b6f3ced42e58. This follow-up extends the actual UI test and its isolated test setup; product Swift stays unchanged. Develop only, main unchanged. No account, device or release handoff requested.

## Current tested behavior

The engine/runtime now retain already committed renewal results when a later app is cancelled or journal persistence fails. A per-invocation report preserves verified expiries for summaries/alarms without promoting uncommitted work. Pending operations still reconcile on the next run. The native adapter consumes the exact final ProfileBatchExecutor readback instead of dumping the device profile store again. Cancellation during final readback cannot return success.

Local baseline Debug passed 296 tests. Modified Debug passed 305 tests including six multi-app daily/interruption scenarios and three exact-readback cases, using real files/locks and scripted device responses. b67a362 macOS core run 37187683409 completed successfully with Debug and Release steps. Native Debug in 37187683426 passed; Release and Simulator details are checked separately, not inferred. Local Release commands timed out and are not claimed as completed passes.

## Actual current UI failure

Full-App run 37187683391 at b67a362 failed before product preparation: the first `simctl list devices available --json` timed out after 30 seconds. No app compilation, installation or UI assertion ran. The actual job log was inspected; this is not a failed picker or renewal assertion. The follow-up gives ONLY the initial CoreSimulator listing a 90-second bound; routine diagnosis retains 30 seconds and UI wait/action assertions are unchanged. There is no reset/retry loop and the previous failed run remains failed. A longer initialization window is not proof of the underlying service's root cause or a solved product defect.

## Real selected-file coverage added

The isolated CI runner seeds one deliberately invalid public plist in the installed app's Documents folder. It does not supply any pairing keys, credentials, readiness flags or backend responses. The actual XCTest opens Browse -> On My iPhone -> Tetherless, selects that file with semantic controls, requires a visible rejection, verifies setup cannot continue, and then performs the existing resume/consent/recovery/cold-launch assertions. Both prior system-picker cancellations remain. A later file read checks the original fixture is unchanged. The fixture manifest never claims UI success.

Four new local Python tests exercised actual fixture IO, existing-file refusal, bad readback, symlink rejection and workflow/UI contracts. Final Python suite: 178 discovered, 165 passed, 13 explicit prepared-native-preimage skips in this runtime. Native preparation separately runs the actual transform chain. Swift frontend parsed the expanded XCTest, but real XCTest compilation/execution remains pending for this follow-up; no selected-file pass is claimed.

The b67a362 source artifact 11297776949 matched outer SHA-256 35e13ec3cac552a600d29dfa9348f7d65177c31b2730115ad472c0e7978acf0e and inner TAR 40de96ab6c18dbf95070377a514e78a119f6ee89d8b1963d7ee14ccf31635726. All nine changed files matched the tested source before this follow-up. Source identity is not native/physical acceptance.

Next read the exact current native/UI results, fix actual failures rather than reciting old estimates, and continue the remaining full installer/first-sign/self-update and distribution requirements. Scripted daily renewal is not real Apple provisioning, profile installation or locked-screen scheduling. All changes are checkpointed before the longer CI run.
