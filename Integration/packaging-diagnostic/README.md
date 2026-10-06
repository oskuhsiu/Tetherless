# Owned XCFramework packaging discriminator

This is one isolated diagnostic, not an IDevice producer or an accepted binary artifact.

## Observed failure

At producer commit `81146b98340b2679658ba9041354b1a066b6e1a3`, both release targets and all twelve C/Swift links passed. `/usr/bin/xcodebuild -create-xcframework` returned zero and printed success. The unchanged `7724f6c3...` supervisor then observed its owned process group still present, sent SIGTERM and established ESRCH. No descendant identity was retained. No library or XCFramework bytes survived in the artifact.

`output_complete=false` is derived from the failing supervisor outcome. It does **not** independently prove that a descendant kept stdout open. In that original run, a running child, an exit/reaping tail and zombie-only membership were hypotheses, not attributed causes.

## Small discriminator and stopping condition

The runner compiles one trivial C function into separate device/simulator archives without executing them. The operation leader invokes xcodebuild with the same packaging argument structure and four-key PATH/DEVELOPER_DIR/HOME/TMPDIR environment as the failed producer. Only archive contents/names are synthetic. The original supervisor, output/cleanup rules and hash pins are unchanged.

While that one packaging call runs, a joined observer reads its existing status sidecar and samples only the recorded PGID with Darwin `ps -g`. It requests PID, PPID, state, start text and executable name, never arguments or environments. A different leader identity, malformed/out-of-group row, unjoined query, missing leader or exhausted sample budget makes the diagnostic inconclusive. It never signals observed PIDs; only the original supervisor manages its own command groups.

Packaging is bounded to 30 seconds plus the existing cleanup bounds. Each read-only query has a 0.5-second timeout and 0.25-second TERM/KILL joins; at most 256 samples, 128 rows per sample and 2,048 aggregate rows are retained. Logs are capped, and the observer is joined before reporting success. The workflow stops after this single attempt and always retains bounded evidence. A packaging failure remains a failure even if its identifying observations are useful. No Rust build or automatic retry occurs.

Sampling can miss short-lived children and says nothing about processes outside the owned group. Start text has the platform's displayed precision, not a cryptographic process identity. A passing toy package would only narrow the reproduction; it would not accept the unretained IDevice output. No supervisor relaxation, global process cleanup or production packaging repair is performed by this fixture.

Darwin flag/field semantics are documented in Apple's [ps manual source](https://github.com/apple-oss-distributions/adv_cmds/blob/main/ps/ps.1): `-g` selects process groups, `-c` requests executable names, and `lstart` records the displayed start time. The sampler sets `COMMAND_MODE=unix2003` and a fixed C locale for that query only. It does not alter the packager's environment.

## Execution and evidence

Run the portable checks with `python3 -m unittest discover -s Integration/packaging-diagnostic/tests -v`. On the parent-controlled macOS job, run `run_diagnostic.py --repo-root . --work-dir .packaging-work --output .packaging-evidence/diagnostic`.

Evidence includes source/context hashes, fixed command logs and joined status sidecars, bounded per-sample logs/status, and `owned-group-observations.json`. Toy objects/archives/XCFramework remain in work and are not uploaded. There is no binary-format/signature inspection, app execution, device/account action or dependency/provider change.

## Operation-owned lifetime verification

The unchanged diagnostic at `bba685049ad471be2953d46bd7acad2a070dc60a`, run `37396649973` / job `112054126526`, reproduced the failure. Its xcodebuild leader 13038 exited zero; sampled xcrun PIDs 13071/13072 were sleeping with PPID 1, while xcodebuild PIDs 13077/13078 were runnable. All belonged to PGID 13038. No sampled member was a zombie. The original supervisor correctly failed and cleaned that group. The retained artifact is 11382304546 (SHA-256 `08c594312e0bcfcff42c00098dec193206a6ba95acdc79b8a187a9596ca71a10`). Those observations and failures remain historical evidence, not successful builds.

The only operation change is `xcframework_operation.py`. The original supervisor launches this Python process as its session/group leader. It launches a single fixed xcodebuild packaging command in the same group, reaps that direct child, then stays alive until a complete group snapshot contains only its own PID. Every other member counts, including zombies. It exits with the child's nonzero result (or a nonzero signal-derived result), or fails closed on enumeration/identity errors. The supervisor still owns the original deadline, output bounds, cancellation, TERM/KILL cleanup, direct-child reaping and ESRCH-only empty-group acceptance. The wrapper installs no handlers, changes no session/group, launches no observer, and has no cleanup or timeout policy of its own.

The wrapper reconstructs exactly the four child environment keys, discarding Python's possible startup LC_CTYPE addition. It logs only three bounded lifecycle events on normal completion. The existing joined metadata sampler remains diagnostic-only, outside the packaging group.

### Darwin API contract inspected before implementation

Apple's [libproc implementation](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/libsyscall/wrappers/libproc/libproc.c#L45-L86) shows that proc_listpgrppids takes a byte-sized buffer but returns a PID count. Its underlying proc_listpids can map a syscall error to zero. The [kernel implementation](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/kern/proc_info.c#L361-L485) filters PROC_PGRP_ONLY, visits both allproc and zombproc, and stops at buffer capacity. A null-buffer sizing call is system-wide, so this wrapper does not use one. A single fixed 128-int buffer is used per poll. Zero/error, saturation (including exactly 128 legitimate members), duplicate/invalid PIDs, a missing own PID, or a changed live leader identity is inconclusive and fails; none means empty. Counts 1 through 127 are accepted when identities are valid. No byte-count divisibility assumption is applied to the returned count.

Apple's [header](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/libsyscall/wrappers/libproc/libproc.h#L41-L94) declares the function from macOS 10.7 but labels this API family private and subject to change. This is a host build helper, not shipped application code. A missing library/symbol or changed API behavior must fail closed; the real macOS tiny attempt is required evidence, not replaced by portable mocks. Sources inspected 2026-10-06 at Apple's xnu-12377.1.9 commit `f6217f891ac0bb64f3d375211650a4c1ff8ca1ea`; this source contract is not an assertion about the runner's precise kernel version.

### Verification boundary and later integration

Portable tests cover the real PID-count contract, bounded saturation, own identity, fail-closed enumeration, exact argv/environment, nonzero/signal propagation, and unchanged outer timeout/cancellation. A real local subprocess fixture retains the operation leader through a same-group child's natural tail and requires original supervisor success without cleanup signals. Its test-only second direct child is reaped by the fixture; it does not claim to reproduce Darwin orphan adoption, and no Linux production enumerator or subreaper is added.

The macOS runner performs the one actual tiny packaging operation with the original 30-second limit, requires supervisor success with a reaped leader, ESRCH and no cleanup signals, then checks both expected XCFramework platform entries and exact copied toy archive/header bytes. It does not inspect Mach-O, signing or certificates. `tiny-package-verification.json` is written only after these checks pass. This does not accept or salvage IDevice output.

Keep this stage under Integration/packaging-diagnostic so it cannot trigger the Rust producer. Only after the tiny attempt passes and independent review approves may a separate production change copy the exact reviewed operation module into the native recipe, invoke it through the unchanged supervisor with five absolute archive/header/output paths, and propagate the new source pins coherently. No production caller, recipe, profile, consumer or supervisor is modified here.
