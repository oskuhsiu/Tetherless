# Helper process cleanup: Darwin transition repair

## Evidence and scope

The first helper-only CI attempt, run 37320923359/job 111799478871 at Tetherless
commit `7f0f400f5e9b26e4c1e02cd9f890b23db7ca7614`, failed in portable process
fixtures before idevice source/Cargo acquisition or any Rust fixture execution.
The recorded host was macOS 15.7.9 ARM64 (24G830), image 20260907.0337.1, Python
3.14.7. The suite reported 63 tests, one failure and seven errors. Repeated stack
traces show `killpg(pgid, 0)` raising EPERM during cleanup; the old exception path
then retried cleanup and could leave the direct child unreaped.

This isolated delta changes only helper process supervision and adds regression
fixtures. It does not modify the immutable helper packet, workflow, source/profile
locks, feature selection, composite builder, native libraries or app integration.
The original 15 process/summary tests are unchanged and remain required.

## Why unknown is a separate state

Apple's published [XNU killpg1 implementation](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/kern/kern_sig.c#L1675-L1722)
filters zombie members and can return EPERM when a group exists but no eligible
member was found. That explains a possible transition consistent with the log;
it does not establish the exact internal state of the failed runner's kernel.
The cited immutable source blob is `93d9d7c614763d99b3b55e26af6db2030e4c79fc`.

A signal-permission result is not proof of process-group absence. The repaired
probe distinguishes:

- present: a successful zero-signal probe
- empty: a probe specifically returned ESRCH
- unknown: EPERM or any other unexpected OSError

Only a later ESRCH observation, together with a reaped direct child, satisfies
successful cleanup. There is no EPERM-to-empty conversion or alternate process
inspection/termination route. Persistent uncertainty remains cleanup_incomplete.

## Bounded cleanup and evidence

Unknown probes do not interrupt the TERM/KILL grace periods or direct-child
polling/reaping. Actual TERM/KILL syscall errors are retained as signal_errors and
do not abort that bounded cleanup path. Each signal is attempted at most once per
its existing stage. After a zero exit, an unknown probe stays within the original
command deadline until absence is established or the deadline expires; it is not
misclassified as a proven surviving descendant. A definite present group retains
the existing descendant-failure behavior.

The fixed 20-minute command, 32 MiB log, 128 KiB tail, five-second TERM and
five-second KILL/join limits are unchanged. Sidecars retain the original stop
reason/truncation fields and add bounded diagnostic summaries: unknown-probe count,
last unknown errno, signal errors, final probe state and explicit ESRCH evidence.
No unbounded per-poll history is collected. Existing nonzero, quota, cancellation,
missing-summary and exact-test-count checks remain in place.

## Controlled verification and remaining evidence

```sh
python3 -m unittest discover -s Integration/Dependencies/idevice/tests \
  -p test_bounded_process.py -v
python3 -m unittest discover -s Integration/Dependencies/idevice/tests \
  -p test_darwin_process_transitions.py -v
```

The unchanged 15 fixtures and eight new fixtures pass locally. New fixtures inject
errno transitions around real, short-lived owned Python subprocesses: transient
EPERM to ESRCH after successful exit; post-TERM transient EPERM; persistent probe
uncertainty; TERM denial with later KILL; and TERM/KILL denial with bounded natural
exit/reap. They verify retained evidence, direct-child reaping and failure on
persistent unknown state. The existing descendant assertions were not relaxed.

These are controlled Linux-hosted fixtures modeling the observed errno sequence.
Actual execution on the recorded macOS runner is still pending; no macOS, Rust or
native-build success is claimed by this delta. The parent owns CI publication,
execution and early-log/context retention changes.
