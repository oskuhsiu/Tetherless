# One-run decision — separate host and simulated entitlements for the producer

- Scope: AUTO-02 / PAIR-01, repair the test-document source startup prerequisite only.
- Current source: develop `2ec72137dd76d8d63b44961d561be39fff61fb83`.
- Observed run/attempt/job: `37207927236` / 1 / `111452931419`.
- Actual read-only report: docs/simulator-ci/latest-report.json; SHA-256 `428cf183950960d63d22e9127b2c4e57abfe02e21b59375f1e97d8a8adfe0d2b`.
- Earliest failed workflow step: UI, step 11. Concrete failure: producer launch before any product UI. Step 12's missing fixture is consequent evidence, not proof of product deletion.

## Evidence

The current artifact SHA-256 is `1af4797c77483280058ad1e47112111100cf0f05b93c429a139565507725babd`. Its XCTest log fails documents.launch() at line 13. The original xcresult contains a DocumentFixture crash with CODESIGNING / 1 / Taskgated Invalid Signature and SIGKILL (Code Signature Invalid); decoded crash SHA-256 `fe150437df1f48436fd15ad32fc7cac9c0610ffe0b69e67690b703bc1f1ef9f8`. The original diagnostic selection omitted that process. The helper did not create its document, so no selection/materialization result is available.

Compare the commands from the same actual run, not a remembered generic fix: the helper embeds its iOS entitlements in __TEXT and ALSO passes that file to codesign. The working Xcode product signs with an empty host entitlement dictionary and embeds simulated entitlements separately. Static codesign --verify had passed for the old helper; it did not prove launch authorization.

Confirmed observation: taskgated signature rejection at producer startup. Evidence-backed correction: remove iOS privilege claims from the helper's host signature, retaining them only in the simulated section. Actual successful runtime after that correction remains unverified.

## One discriminating change

Generate separate empty host and unchanged simulated entitlement files. Use the host file for ad-hoc signing, preserve the simulated linker section, and inspect BOTH actual representations before installation. Keep strict signature verification and expected identity/platform checks. Record static evidence with runtimeLaunchObserved=false. Retain helper crash/stdout separately within the existing bounded diagnostic exporter.

No production Swift, producer Swift, payload, content type, picker delegate, Files source, single semantic tap, timeout, cancellation, rejection, original-byte or consent/relaunch assertions changes. No entitlements are added to the product and no security check is disabled. This corrects a test-build misconfiguration, not a product permission workaround.

## Expected observation / refutation

Require helper signature inspection -> XCTest launch -> actual documentReady -> the unchanged full product path and independent source preservation. If the helper still has a codesigning failure, preserve the new signed-bundle evidence and crash; do not reset the simulator or keep rerunning. If it starts but provider resolution still fails, that refutes the earlier source-isolation hypothesis rather than this launch prerequisite. A later callback/dismissal failure belongs to its observed boundary. No intermediate stage alone closes invalid-file acceptance.

## Environment and checks

Same declared macos-15 job, concrete owned device destination and installed-toolchain selection; no SDK/runtime upgrade or reset. Inspected failed run used macos-15-arm64 image 20260907.0337.1, macOS 15.7.9, Xcode 26.3 build 17C529, iOS 26.2 SDK/runtime and iPhone SE (3rd generation). Report any actual next-run drift rather than assuming the label is immutable.

42 focused local tests and 16 skill tests passed. These use actual files/Mach-O parsing and scripted codesign responses, not native execution. Product core and full integration suites were not rerun for this test-build-only correction. The unchanged original UI remains required. Read STATUS.md for exact evidence and limits. Before pushing, verify there is no current related active run; dispatch at most one full validation via the code commit and checkpoint its ID without polling.

Primary implementation reference for the platform distinction: https://github.com/madsmtm/embed_entitlements . The decisive project evidence is the actual Xcode build and crash above, not an assumption that every taskgated failure has this cause.
