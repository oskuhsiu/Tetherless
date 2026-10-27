# Component supervision decision after the first macOS run

## Observed failure

Source `7f0f400f5e9b26e4c1e02cd9f890b23db7ca7614`,
[run 37320923359](https://github.com/oskuhsiu/Tetherless/actions/runs/37320923359),
job `111799478871`, attempt 1, failed in the portable process-supervision tests.
The 63 tests reported one failure and seven errors. Prerequisite checks found
arm64 macOS, the selected Xcode directory, rustup, cmake, ninja and Python.

The observed runner was macOS 15.7.9/24G830, image
`macos-15-arm64` version `20260907.0337.1`, with Python 3.14.7. Repeated tracebacks
show `os.killpg(pgid, 0)` raising EPERM inside `stop_and_join`, including a second
cleanup attempt. Some subprocess objects then reported that a child was still
running. These are failures in CI supervision before source acquisition, Cargo,
Rust compilation or native fixtures. No component or application acceptance passed.

The workflow wrote its run-context file only after the failing tests. Its existing
always-upload step therefore found no artifact files. The full GitHub job log was
retrieved and retained; missing artifacts are not a successful cleanup result.

## Discriminating repair

The [Apple XNU killpg1 implementation](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/kern/kern_sig.c#L1675-L1722)
skips zombie members and can return EPERM during a group transition. That source
supports treating a permission result as unknown rather than throwing out of
cleanup. It does not establish the actual kernel state of this CI run.

The narrow supervision repair must preserve that uncertainty, continue bounded
owned-group handling and direct-child reaping, and require both a reaped child
and a later ESRCH observation before claiming an empty group. Persistent EPERM
must remain `cleanup_incomplete`. No privilege escalation, global process scan,
foreign-group signaling, test skip or false empty-group fallback is permitted.
Regression tests must cover transient and persistent permission errors, signal
errors, original failure-cause preservation and retained status evidence.

The separate workflow change writes whitelisted run context before its checks
and tees the portable test output into the existing artifact path. `pipefail`
continues to propagate a failed unittest command. No credentials/environment dump,
extra source archive or compiled product is uploaded by this repair.

## Next-run acceptance

After independent review and portable tests of the final repair, one new
component run should distinguish the corrected cleanup behavior on the same
runner contract, then reach source verification and the original 18 helper plus
25 RSD Rust fixture filters. Both outcomes must be inspected independently.

The fixture counts, source/Cargo.lock hashes, command quotas, original test
assertions, workflow deadlines, exact-branch app-job exclusion and application/UI
acceptance remain unchanged. Host generation, composite acquisition, OpenSSL,
application activation and physical-device acceptance are outside this repair.
A repeated unresolved supervision failure requires its new evidence to be
examined before another run; this record is not permission for blind retries.
