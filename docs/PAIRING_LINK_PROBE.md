# Packaged pairing host compile/link probe

This is a narrow prerequisite for PAIR-01, not wireless pairing implementation or acceptance. The current host and client product gates are unchanged. Imported/stored pairing, renewal, account state and protected files are unchanged.

## Why another probe is needed

The retained Debug package inspection from `d566891`, native run `37294413252`, contains all four required C declarations in the actual device and simulator `idevice.h`. It does **not** establish exported-symbol availability: Apple's selected `nm` returned 1 while reading Rust LLVM 22 `compiler_builtins` members with its older LLVM reader. The inspection correctly remained incomplete. Successful existing app linking does not prove that unused host cancellation functions resolve.

`Integration/probe_pairing_link.py` uses the selected official `xcrun` toolchain. It does not switch Xcode, install dependencies, parse archive members, ignore unresolved symbols or infer successful exports from failed `nm` output.

## Inputs and commands

Run after the existing native build has resolved package artifacts:

```sh
python3 Integration/probe_pairing_link.py \
  --artifacts-root .generated/DerivedData/SourcePackages/artifacts \
  --output-root artifacts/pairing-link-Debug
```

Use a fresh output directory for each observation/configuration. The script refuses to overwrite prior evidence, write inside the package artifact root or accept symlinked input components. Both expected arm64 slices and all observed archive/header hashes are checked before any compiler invocation. The selected archive/header are rechecked immediately before and after every compile/link command, and the entire selected package identity is checked again before reporting final success. Observed byte or metadata drift invalidates the observation:

- Header: `23e7ab332fc73788b67b441b0c128720f3ddbd2210672cbc4bcb1503b5ca8426`
- Device archive: `622e8f91aa285bf1a6076e2853da9cacb39839bfd72ad1b1b08a0902e7f33d5b`
- Simulator archive: `83e94401faf680916740ba112c630e0e52bbfc98ef0d77b53967494b63858f23`

For each slice it resolves the matching SDK and independently records C compile, C link, Swift compile and Swift link. C function-pointer types check the full declaration signatures. Swift imports the actual packaged header and compiles the callback, opaque cancellation pointer, peer pointer, record pointer and 16-byte host-IRK output call site. Linker `-u` roots force all four required native functions to resolve; the Swift call-site function is also rooted.

The only extra link inputs are the selected static archive, SDK Foundation and `-lc++`. The real gateway imports Foundation and the verified app's link command includes `-lc++`. Missing dependencies remain explicit link failures; the script does not guess extra third-party libraries or fall back to dynamic lookup. `-no_adhoc_codesign` disables automatic linker signing. No `codesign` invocation occurs.

Every command uses the existing bounded inspection runner: 60 seconds, 16 MiB per output pipe, process-group termination on timeout/truncation/error, and a wait to reap the launched process. There are four resolution/version commands, two SDK resolutions and eight compile/link commands at most. The maximum subprocess budget is 14 × 60 seconds = 840 seconds, plus bounded hashing/filesystem overhead. Use a 16-minute separately recorded CI evidence step; normal execution should be much shorter. Retain the entire output directory even on failure. It contains only the report and bounded text logs. Objects, linked executables and module caches live in a probe-owned temporary directory outside the retained artifact directory and are removed only after the compiler/linker commands have finished. Successful linked-output hashes remain in the report; dependency executables and caches are not uploaded. This step's outcome must not rewrite the app build's outcome.

Neither executable is ever launched. The C main only checks addresses; Swift main is empty. The compiled Swift probe function is not a runtime smoke test. No pairing, listener, discovery, PIN exchange, signing, device connection or persistent credentials are created.

## Reading the result

`report.json` distinguishes unsupported package identity, unsupported toolchain, unsupported SDK, input identity drift, C/Swift compilation failure and C/Swift link failure. Every launched command has its exact arguments, exit code, tool status and bounded stdout/stderr files. Exit 0 means both language probes compiled and linked for both reviewed slices; exit 1 means recorded incomplete/unsupported evidence; exit 2 means an argument/output or filesystem error prevented completion.

Success proves static typed-call compatibility and symbol resolution for that exact toolchain, SDK and artifact. It does not prove runtime ABI behavior, cancellation, joining, socket cleanup, native logging privacy, same-phone discovery, PIN presentation, background lifetime, device behavior or a complete host adapter. The optional `pairable_host_accept_with_options` is not required or linked by this probe.

## Remaining promotion blocker

AppBootManager reads a connected peer's UDID. Its wrapper can overwrite the cached Keychain UDID with that peer value. NativeRenewalBackend also reads the connected peer's identity. Neither establishes an independent current-phone identity before replacing a pairing record. A successful handshake, displayed PIN or mutable peer-derived cache is insufficient to promote a staged record as current-phone pairing.

A future implementation must retain token/context/mutation lease until real native completion, signal cancellation and join without a fabricated PIN or timer-based lease release, generation-scope every callback and validate the staged peer under a reviewed current-phone identity contract before replacing the old record. Until then, both product gates remain. The client has a separate uncancellable PIN wait and remains out of scope.

## Local verification

Focused Python tests use synthetic package identities and modeled tool outcomes to test orchestration and fail-closed reporting. A separate C signature fixture compiles/links against synthetic implementations and rejects signature drift; it never executes the result. These tests do not stand in for the official Apple C/Swift probe. No Swift/Xcode toolchain is available in the local cloud workspace, so actual Apple compile/link evidence remains pending until the parent's native CI runs it.
