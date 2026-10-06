# Owned XCFramework packaging discriminator

This is one isolated diagnostic, not an IDevice producer or an accepted binary artifact.

## Observed failure

At producer commit `81146b98340b2679658ba9041354b1a066b6e1a3`, both release targets and all twelve C/Swift links passed. `/usr/bin/xcodebuild -create-xcframework` returned zero and printed success. The unchanged `7724f6c3...` supervisor then observed its owned process group still present, sent SIGTERM and established ESRCH. No descendant identity was retained. No library or XCFramework bytes survived in the artifact.

`output_complete=false` is derived from the failing supervisor outcome. It does **not** independently prove that a descendant kept stdout open. A running child, an exit/reaping tail and zombie-only membership remain hypotheses, not attributed causes.

## Small discriminator and stopping condition

The runner compiles one trivial C function into separate device/simulator archives without executing them. It uses the same packaging argument structure and four-key PATH/DEVELOPER_DIR/HOME/TMPDIR environment as the failed producer. Only archive contents/names are synthetic. The original supervisor, output/cleanup rules and hash pins are unchanged.

While that one packaging call runs, a joined observer reads its existing status sidecar and samples only the recorded PGID with Darwin `ps -g`. It requests PID, PPID, state, start text and executable name, never arguments or environments. A different leader identity, malformed/out-of-group row, unjoined query, missing leader or exhausted sample budget makes the diagnostic inconclusive. It never signals observed PIDs; only the original supervisor manages its own command groups.

Packaging is bounded to 30 seconds plus the existing cleanup bounds. Each read-only query has a 0.5-second timeout and 0.25-second TERM/KILL joins; at most 256 samples, 128 rows per sample and 2,048 aggregate rows are retained. Logs are capped, and the observer is joined before reporting success. The workflow stops after this single attempt and always retains bounded evidence. A packaging failure remains a failure even if its identifying observations are useful. No Rust build or automatic retry occurs.

Sampling can miss short-lived children and says nothing about processes outside the owned group. Start text has the platform's displayed precision, not a cryptographic process identity. A passing toy package would only narrow the reproduction; it would not accept the unretained IDevice output. No supervisor relaxation, helper attribution, global process cleanup or production packaging repair is authorized by this fixture.

Darwin flag/field semantics are documented in Apple's [ps manual source](https://github.com/apple-oss-distributions/adv_cmds/blob/main/ps/ps.1): `-g` selects process groups, `-c` requests executable names, and `lstart` records the displayed start time. The sampler sets `COMMAND_MODE=unix2003` and a fixed C locale for that query only. It does not alter the packager's environment.

## Execution and evidence

Run the portable checks with `python3 -m unittest discover -s Integration/packaging-diagnostic/tests -v`. On the parent-controlled macOS job, run `run_diagnostic.py --repo-root . --work-dir .packaging-work --output .packaging-evidence/diagnostic`.

Evidence includes source/context hashes, fixed command logs and joined status sidecars, bounded per-sample logs/status, and `owned-group-observations.json`. Toy objects/archives/XCFramework remain in work and are not uploaded. There is no binary-format/signature inspection, app execution, device/account action or dependency/provider change.
