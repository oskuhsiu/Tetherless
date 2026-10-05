"""Bounded POSIX process-group supervision for helper-only native fixture CI.

Commands are trusted build tools, run without a shell. They must not detach from
this owned session/process group. No global process search or unrelated PID kill.
"""
from __future__ import annotations

import errno
import json
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import threading
import time

from apply_patch import VerificationError

COMMAND_TIMEOUT_SECONDS = 20 * 60
MAX_LOG_BYTES = 32 * 1024 * 1024
SUMMARY_TAIL_BYTES = 128 * 1024
TERM_GRACE_SECONDS = 5.0
KILL_JOIN_SECONDS = 5.0
POLL_SECONDS = 0.05


def probe_group(pgid: int) -> tuple[str, int | None]:
    """Signal permission is not existence proof: only ESRCH proves empty.

    Darwin can report EPERM while a group is transitioning through zombie-only
    membership. Keep that observation unknown until a later bounded probe can
    establish ESRCH; never map EPERM (or another OSError) to absence.
    """
    if type(pgid) is not int or pgid <= 1:
        return "unknown", errno.EINVAL
    try:
        os.killpg(pgid, 0)
        return "present", None
    except ProcessLookupError:
        return "empty", errno.ESRCH
    except OSError as exc:
        return "unknown", exc.errno


def stop_and_join(process: subprocess.Popen, term_grace: float, kill_grace: float) -> dict:
    """Bounded escalation/reaping continues through unknown group observations."""
    sent, signal_errors = [], []
    unknown_count = 0
    last_unknown_errno = None
    last_probe = ("unknown", None)

    def observe():
        nonlocal unknown_count, last_unknown_errno, last_probe
        last_probe = probe_group(process.pid)
        if last_probe[0] == "unknown":
            unknown_count += 1
            last_unknown_errno = last_probe[1]
        return last_probe[0]

    def result(reaped: bool) -> dict:
        empty = last_probe[0] == "empty"
        return {"signals": sent, "signal_errors": signal_errors,
                "direct_child_reaped": reaped, "group_empty": empty,
                "empty_evidence": "killpg_ESRCH" if empty else None,
                "unknown_probe_count": unknown_count, "last_unknown_errno": last_unknown_errno,
                "last_group_probe": {"state": last_probe[0], "errno": last_probe[1]}}

    for sig, grace in ((signal.SIGTERM, term_grace), (signal.SIGKILL, kill_grace)):
        process.poll()  # Keep reaping even if the previous group probe was EPERM.
        if observe() != "empty":
            try:
                os.killpg(process.pid, sig)
                sent.append(signal.Signals(sig).name)
            except OSError as exc:
                # ESRCH during signalling is only a transition observation;
                # re-probe and reap below. EPERM never shortcuts cleanup.
                signal_errors.append({"signal": signal.Signals(sig).name, "errno": exc.errno})
        deadline = time.monotonic() + grace
        while True:
            returncode = process.poll()
            state = observe()
            if returncode is not None and state == "empty":
                process.wait(timeout=0)
                return result(True)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(POLL_SECONDS, remaining))
    reaped = process.poll() is not None
    if reaped:
        process.wait(timeout=0)
    observe()
    return result(reaped)


def capture_helper_command(command: list[str], *, source: Path, env: dict, log: Path,
                           timeout_seconds: float = COMMAND_TIMEOUT_SECONDS,
                           max_log_bytes: int = MAX_LOG_BYTES,
                           tail_bytes: int = SUMMARY_TAIL_BYTES,
                           term_grace_seconds: float = TERM_GRACE_SECONDS,
                           kill_join_seconds: float = KILL_JOIN_SECONDS) -> str:
    """Stream merged output to disk; return only a bounded final summary tail.

    Every quota, duration, nonzero-exit, signal or descendant-cleanup failure raises.
    A sidecar status JSON and already-written log bytes survive those failures.
    """
    if os.name != "posix":
        raise VerificationError("helper process supervision requires POSIX process groups")
    if not command or not all(isinstance(part, str) for part in command):
        raise VerificationError("invalid supervised command")
    for value in (timeout_seconds, term_grace_seconds, kill_join_seconds):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise VerificationError("process duration/cleanup limits must be finite and positive")
    if type(max_log_bytes) is not int or max_log_bytes <= 0 or type(tail_bytes) is not int or tail_bytes <= 0:
        raise VerificationError("process output limits must be positive integers")
    tail_bytes = min(tail_bytes, max_log_bytes)
    log.parent.mkdir(parents=True, exist_ok=True)
    status_path = log.with_name(log.name + ".status.json")
    if log.exists() or log.is_symlink() or status_path.exists() or status_path.is_symlink():
        raise VerificationError("supervised output paths must be new")
    start = time.monotonic()
    status = {"schema": 1, "outcome": "starting", "command": command,
              "timeout_seconds": timeout_seconds, "max_log_bytes": max_log_bytes,
              "summary_tail_bytes": tail_bytes, "term_grace_seconds": term_grace_seconds,
              "kill_join_seconds": kill_join_seconds, "log_bytes": 0,
              "stop_reason": None, "output_truncated": False, "output_bytes_over_limit_observed": 0,
              "post_exit_unknown_probe_count": 0, "post_exit_last_unknown_errno": None}
    status_path.write_text(json.dumps(status, sort_keys=True, indent=2) + "\n")
    interrupted = []
    previous_handlers = {}
    process = None
    selector = selectors.DefaultSelector()
    tail = bytearray()
    outcome = "internal_failure"
    cleanup = None
    caught = None
    eof = False

    def interrupted_handler(signum, _frame):
        # Do not throw through cleanup. Repeated cancellation still gets one
        # bounded cleanup path. The main-loop selector wakes at most 50ms later.
        if not interrupted:
            interrupted.append(signum)

    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, interrupted_handler)

    try:
        # Unbuffered file writes make evidence available while compilation is
        # still running, even without a newline or a normal compiler exit.
        with log.open("xb", buffering=0) as stream:
            def consume(data: bytes) -> bool:
                remaining = max_log_bytes - status["log_bytes"]
                kept = data[:remaining]
                if kept:
                    if stream.write(kept) != len(kept):
                        raise OSError("short write while retaining helper compiler output")
                    status["log_bytes"] += len(kept)
                    tail.extend(kept)
                    if len(tail) > tail_bytes:
                        del tail[:-tail_bytes]
                if len(data) > remaining:
                    status["output_truncated"] = True
                    status["output_bytes_over_limit_observed"] += len(data) - remaining
                    status["stop_reason"] = status["stop_reason"] or "output_limit"
                    return False
                return True

            process = subprocess.Popen(command, cwd=source, env=env, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       start_new_session=True, close_fds=True, bufsize=0)
            assert process.stdout is not None
            fd = process.stdout.fileno()
            os.set_blocking(fd, False)
            selector.register(fd, selectors.EVENT_READ)
            status.update({"outcome": "running", "pid": process.pid, "process_group": process.pid})
            status_path.write_text(json.dumps(status, sort_keys=True, indent=2) + "\n")
            try:
                while True:
                    if interrupted:
                        outcome = "interrupted"
                        break
                    remaining = timeout_seconds - (time.monotonic() - start)
                    if remaining <= 0:
                        outcome = "timeout"
                        break
                    for _key, _mask in selector.select(min(POLL_SECONDS, remaining)):
                        try:
                            data = os.read(fd, min(65536, max_log_bytes - status["log_bytes"] + 1))
                        except BlockingIOError:
                            continue
                        if not data:
                            selector.unregister(fd)
                            eof = True
                        elif not consume(data):
                            outcome = "output_limit"
                            break
                    if outcome == "output_limit":
                        break
                    returncode = process.poll()
                    if returncode is not None:
                        if returncode != 0:
                            outcome = "nonzero_exit"
                            break
                        group_state, group_errno = probe_group(process.pid)
                        if group_state == "present":
                            outcome = "descendants_outlived_command"
                            break
                        if group_state == "unknown":
                            status["post_exit_unknown_probe_count"] += 1
                            status["post_exit_last_unknown_errno"] = group_errno
                            continue
                        if eof:
                            outcome = "success"
                            break
            finally:
                if outcome != "success" and status["stop_reason"] is None:
                    status["stop_reason"] = outcome
                # Always reap/stop the owned group, including exceptions caused
                # by failed log writes or an external KeyboardInterrupt.
                cleanup = stop_and_join(process, term_grace_seconds, kill_join_seconds)
                # Preserve remaining pipe bytes after exit/escalation, without
                # ever waiting for an inherited pipe or exceeding the disk cap.
                drain_deadline = time.monotonic() + POLL_SECONDS
                while not eof and time.monotonic() < drain_deadline:
                    try:
                        data = os.read(fd, min(65536, max_log_bytes - status["log_bytes"] + 1))
                    except BlockingIOError:
                        break
                    if not data:
                        eof = True
                        break
                    if not consume(data):
                        outcome = "output_limit"
                        break
                process.stdout.close()
                os.fsync(stream.fileno())
    except BaseException as exc:
        caught = exc
        status["stop_reason"] = status["stop_reason"] or "supervision_error"
        if process is not None and cleanup is None:
            cleanup = stop_and_join(process, term_grace_seconds, kill_join_seconds)
    finally:
        selector.close()
        if process is not None and process.stdout is not None:
            process.stdout.close()
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
        if caught is not None:
            outcome = "supervision_error"
        if cleanup is not None and (not cleanup["direct_child_reaped"] or not cleanup["group_empty"]):
            outcome = "cleanup_incomplete"
        if interrupted and outcome == "success":
            outcome = "interrupted"
        if interrupted and status["stop_reason"] is None:
            status["stop_reason"] = "interrupted"
        status.update({"outcome": outcome, "elapsed_seconds": time.monotonic() - start,
                       "returncode": process.returncode if process is not None else None,
                       "cleanup": cleanup, "interrupted_by": interrupted[0] if interrupted else None,
                       "error_type": type(caught).__name__ if caught is not None else None,
                       "output_complete": outcome == "success" and not status["output_truncated"]})
        status_path.write_text(json.dumps(status, sort_keys=True, indent=2) + "\n")
    if caught is not None:
        raise caught
    if outcome != "success":
        raise VerificationError(f"helper command failed ({outcome}); retained log: {log}; status: {status_path}")
    return tail.decode("utf-8", errors="replace")
