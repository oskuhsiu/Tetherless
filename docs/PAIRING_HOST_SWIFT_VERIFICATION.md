# Standalone macOS pairing fixtures

This wrapper executes the frozen app-boundary Swift fixtures without building or linking IDevice. It uses the selected macOS Xcode toolchain and the exact source hashes embedded in the script. It does not invoke a device, publish a real Bonjour service or generate native pairing credentials.

After applying the reviewed app-boundary additions and this wrapper to the same checkout, run:

```sh
python3 Integration/verify_pairing_host_app.py --source-root . --output-root evidence/pairing-host-swift
```

The output directory must be new; its parent must already exist and have no symlink components. The wrapper verifies and copies the small fixture package plus the existing `bounded_process.py`/`apply_patch.py` supervisor inputs into owned temporary directories. It runs Debug first and Release second through `/usr/bin/xcrun --sdk macosx swift test`. Tool path and Swift version are observed afterward under the same environment. No newly invented toolchain preflight precedes fixture execution.

Each configuration must execute these 19 unique XCTest fixtures without failures: 3 native-entry lifetime tests, 9 validation/promotion tests and 7 mocked Bonjour/socket-ownership tests. The wrapper records individual fixture names and requires a successful final All-tests suite. Repeated successful package/All-tests summary lines are accepted; a duplicated fixture cannot substitute for a missing one, and a failure cannot be hidden by a later success line.

The Bonjour fixtures override publication/stop and use local socket pairs, without network discovery. The separate fixture package enables the otherwise disabled transport build condition. It does not include `BoundedPairingHostBridge.swift`, IDevice or any generated native header. Success therefore establishes Swift source/fixture behavior only, not FFI calls, native ABI, physical-device pairing, app-container validation or an activated consumer.

Each of four tool phases has a 60-second execution deadline, a 16-MiB merged log cap, and up to five seconds each for TERM and KILL cleanup. The existing hash-locked supervisor handles interruption, reaps the direct child and checks that the owned process group is empty. The maximum tool-plus-cleanup envelope is 280 seconds; allow a six-minute workflow step for staging and reporting. If a process-group join cannot be confirmed, the wrapper stops further commands, marks cleanup incomplete and retains its scratch directory rather than deleting files a descendant could still use. It never signals unrelated processes. Missing, malformed or unreadable cleanup status is treated as unconfirmed, including launch failures without affirmative join evidence. A cancellation/exit exception remains terminal even if a success sidecar was already written. Scratch-removal errors preserve a failing report and retained-path observation.

Debug and Release results are independent; a Release pass cannot mask a Debug failure. Timeout, output limit, nonzero exit, cancellation and incomplete cleanup remain non-passing states. The report and retained supervisor status distinguish them. An interrupted command stops the sequence. Source drift around any phase invalidates the observation. Original sources are never modified.

Retain only the new output directory: `report.json`, four merged stdout/stderr `.log` files, and each log's supervisor-status JSON. The report includes exact commands, compiler path/version, input and log hashes, child/group cleanup evidence, unique fixture results and repeated aggregate summaries. Build products and module caches stay outside the retained directory and are removed only after quiescence is established.

No Apple Swift command has executed locally. Eighteen portable wrapper tests pass: seventeen use clearly labeled injected supervision/results, and one loads the exact supervisor to run and join a short local Python fixture. These are wrapper checks, not Apple runtime or native ABI evidence. A separate component-workflow job can execute the Swift packet without depending on the Rust vendor/preparation step.
