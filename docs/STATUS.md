# Current implementation test checkpoint

2026-10-04. Development is based on the live develop head 428bd9a and its current product source, not previous progress estimates. Work stays on develop; main is unchanged. No device or credentials requested.

## Product work

- Preserve actual per-invocation renewal outcomes on thrown exits. The engine publishes its result in a synchronous defer; the runtime retains earlier durable successes when a later app is cancelled or saving fails. Pending work still reconciles before another mutation. Failed/unverified work is not promoted to success, and failures still propagate.
- Return the exact post-install profile snapshot from ProfileBatchExecutor. The native adapter validates/commits that same readback instead of dumping the entire device profile store again. The already-extended branch also uses one consistent snapshot. Required final readback remains mandatory; cancellation arriving during it cannot return success.
- Add full coordinator scenarios with real journal files/locks and a scripted device: manager plus two apps, next-day renewal, same-day duplicate, cancellation after manager success, failed second commit followed by recovery without duplicate writes, and applied-but-unverified evidence.

## Verified locally

- Current unmodified baseline: 296 Debug tests passed in this runtime.
- Modified implementation: 305 Debug tests passed, including six daily/interruption scenarios and three readback cases. The first new test expected a recovery order inconsistent with earliest-expiry scheduling; the assertion now matches that policy without changing scheduling.
- Python integration: 174 discovered, 161 passed and 13 explicit prepared-input skips in the current runtime. Three new native wiring checks ran. Prepared upstream transformation preimages must be restored or executed in native CI; skipped checks are not passes.
- Native runtime/backend Swift syntax parsing passed; not native typechecking.
- Local Release builds hit command timeouts; no completed Release pass is claimed yet. Fresh macOS/core, Simulator and unsigned native/UI CI are required for this exact implementation.

## Goal status

Daily renewal/recovery scenarios are scripted tests, not real Apple/profile installation or locked-screen execution. Full physical acceptance remains at the end. Current work closes interrupted-report correctness and redundant device reads, not all product completion conditions. Next: inspect this implementation's native/CI results and close actual selected-file outcomes and remaining install/first-sign/self-update and distribution requirements. Do not re-diagnose historical failures without current evidence.
