"""Only controlled local Python subprocesses; no Cargo, Xcode, network or app tests."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apply_patch import VerificationError
from bounded_process import capture_helper_command
import bounded_process
from run_helper_tests import verify_fixture_summary

SUMMARY = "test result: ok. 18 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s\n"


@unittest.skipUnless(os.name == "posix", "process-group tests require POSIX")
class BoundedProcessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.log = self.directory / "capture.txt"

    def capture(self, code, **overrides):
        options = dict(timeout_seconds=2.0, max_log_bytes=4096, tail_bytes=256,
                       term_grace_seconds=0.2, kill_join_seconds=0.2)
        options.update(overrides)
        return capture_helper_command([sys.executable, "-u", "-c", code],
            source=self.directory, env=dict(os.environ), log=self.log, **options)

    def status(self):
        return json.loads(self.log.with_name(self.log.name + ".status.json").read_bytes())

    def wait_until(self, predicate, seconds=2.0):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("controlled fixture did not reach its expected state")

    def assert_not_running(self, pid):
        # Linux may retain an orphan zombie until PID 1 reaps it. Such a process
        # is stopped, but production correctly reports group-empty uncertainty
        # as failure rather than treating that as a successful command.
        proc_stat = Path(f"/proc/{pid}/stat")
        if proc_stat.exists():
            state = proc_stat.read_text().split(") ", 1)[1].split()[0]
            self.assertEqual(state, "Z", "fixture descendant is still running")
            return
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_stdout_and_stderr_are_visible_before_exit(self):
        result = {}
        def worker():
            try:
                result["tail"] = self.capture("import os,time; os.write(1,b'out-partial'); os.write(2,b'err-partial'); time.sleep(.7); print('done')")
            except BaseException as exc:
                result["error"] = exc
        thread = threading.Thread(target=worker)
        thread.start()
        try:
            self.wait_until(lambda: self.log.exists() and b"err-partial" in self.log.read_bytes())
            self.assertTrue(thread.is_alive(), "log was only written after process exit")
            self.assertEqual(self.log.read_bytes(), b"out-partialerr-partial")
        finally:
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertNotIn("error", result)
        self.assertIn("done", result["tail"])
        self.assertEqual(self.status()["outcome"], "success")

    def test_nonzero_exit_retains_both_streams_and_failure_status(self):
        with self.assertRaises(VerificationError):
            self.capture("import os,sys; os.write(1,b'compiler-out\\n'); os.write(2,b'compiler-error\\n'); sys.exit(7)")
        self.assertIn(b"compiler-out", self.log.read_bytes())
        self.assertIn(b"compiler-error", self.log.read_bytes())
        self.assertEqual(self.status()["outcome"], "nonzero_exit")
        self.assertEqual(self.status()["returncode"], 7)
        self.assertTrue(self.status()["cleanup"]["direct_child_reaped"])

    def test_oversized_output_fails_and_log_never_exceeds_quota(self):
        with self.assertRaises(VerificationError):
            self.capture("import os; os.write(1,b'x'*20000)", max_log_bytes=1024)
        self.assertEqual(self.log.stat().st_size, 1024)
        self.assertEqual(self.status()["outcome"], "output_limit")
        self.assertTrue(self.status()["cleanup"]["group_empty"])

    def test_quota_reason_survives_unconfirmed_cleanup(self):
        original_cleanup = bounded_process.stop_and_join
        def cleanup_then_report_uncertainty(*args):
            # Perform real group termination/reaping, then simulate the distinct
            # observation failure. This leaves no deliberately surviving child.
            result = original_cleanup(*args)
            result["group_empty"] = False
            return result
        with patch.object(bounded_process, "stop_and_join", side_effect=cleanup_then_report_uncertainty):
            with self.assertRaises(VerificationError):
                self.capture("import os; os.write(1,b'x'*20000)", max_log_bytes=1024)
        status = self.status()
        self.assertEqual(status["outcome"], "cleanup_incomplete")
        self.assertEqual(status["stop_reason"], "output_limit")
        self.assertTrue(status["output_truncated"])
        self.assertGreater(status["output_bytes_over_limit_observed"], 0)
        self.assertFalse(status["output_complete"])
        self.assertEqual(self.log.stat().st_size, 1024)

    def test_valid_looking_summary_before_quota_failure_cannot_pass(self):
        with self.assertRaises(VerificationError):
            self.capture("import os; os.write(1," + repr(SUMMARY.encode()) + "); os.write(1,b'x'*20000)", max_log_bytes=1024)
        self.assertIn(b"18 passed", self.log.read_bytes())
        self.assertEqual(self.status()["outcome"], "output_limit")

    def test_hang_is_timed_out_and_reaped(self):
        start = time.monotonic()
        with self.assertRaises(VerificationError):
            self.capture("import time; print('before-hang',flush=True); time.sleep(30)", timeout_seconds=0.2)
        self.assertLess(time.monotonic() - start, 1.5)
        self.assertEqual(self.status()["outcome"], "timeout")
        self.assertIn(b"before-hang", self.log.read_bytes())
        self.assertTrue(self.status()["cleanup"]["group_empty"])

    def test_ignored_term_escalates_to_kill_and_joins(self):
        with self.assertRaises(VerificationError):
            self.capture("import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready',flush=True); time.sleep(30)", timeout_seconds=0.2)
        self.assertEqual(self.status()["cleanup"]["signals"], ["SIGTERM", "SIGKILL"])
        self.assertEqual(self.status()["returncode"], -signal.SIGKILL)
        self.assertTrue(self.status()["cleanup"]["direct_child_reaped"])

    def test_pipe_eof_does_not_hide_a_still_running_child(self):
        with self.assertRaises(VerificationError):
            self.capture("import os,time; os.close(1); os.close(2); time.sleep(30)", timeout_seconds=0.2)
        self.assertEqual(self.status()["outcome"], "timeout")
        self.assertEqual(self.log.stat().st_size, 0)

    def test_owned_descendants_are_terminated_and_parent_reaps_them(self):
        pidfile = self.directory / "descendant.pid"
        code = """
import os,signal,subprocess,sys,time
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
open(%r, 'w').write(str(child.pid))
def stop(signum, frame):
    child.wait(timeout=1)
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
print('parent-and-child-ready', flush=True)
time.sleep(30)
""" % str(pidfile)
        with self.assertRaises(VerificationError):
            self.capture(code, timeout_seconds=0.3, term_grace_seconds=0.5)
        pid = int(pidfile.read_text())
        self.assert_not_running(pid)
        self.assertTrue(self.status()["cleanup"]["group_empty"])
        self.assertTrue(self.status()["cleanup"]["direct_child_reaped"])

    def check_descendant_outlives_parent(self, close_pipe):
        pidfile = self.directory / "descendant.pid"
        child_code = "import time; time.sleep(30)"
        redirection = ", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL" if close_pipe else ""
        code = ("import os,subprocess,sys; child=subprocess.Popen([sys.executable,'-c'," + repr(child_code) + "]" +
                redirection + "); open(" + repr(str(pidfile)) + ",'w').write(str(child.pid)); print('parent-exiting',flush=True); os._exit(0)")
        start = time.monotonic()
        with self.assertRaises(VerificationError):
            self.capture(code)
        self.assertLess(time.monotonic() - start, 1.5)
        self.assert_not_running(int(pidfile.read_text()))
        self.assertIn(self.status()["outcome"], ("descendants_outlived_command", "cleanup_incomplete"))
        self.assertTrue(self.status()["cleanup"]["direct_child_reaped"])

    def test_parent_exit_with_descendant_holding_pipe_is_failure(self):
        self.check_descendant_outlives_parent(close_pipe=False)

    def test_parent_exit_with_descendant_closing_pipe_is_failure(self):
        self.check_descendant_outlives_parent(close_pipe=True)

    def test_success_returns_bounded_tail_containing_final_summary(self):
        output = self.capture("import os; os.write(1,b'x'*2000+b'\\n'+" + repr(SUMMARY.encode()) + ")")
        self.assertLessEqual(len(output.encode()), 256)
        self.assertTrue(output.endswith(SUMMARY))
        self.assertEqual(verify_fixture_summary(output, {"filter": "fixture", "expected_passed": 18}), 18)
        self.assertGreater(self.log.stat().st_size, len(output))

    def test_external_term_stops_owned_group_and_retains_evidence(self):
        script = self.directory / "runner.py"
        script.write_text("import sys,os\nfrom pathlib import Path\nsys.path.insert(0," + repr(str(ROOT)) + ")\n"
            "from bounded_process import capture_helper_command\nfrom apply_patch import VerificationError\n"
            "try:\n capture_helper_command([sys.executable,'-u','-c',\"import time; print('interrupt-ready',flush=True); time.sleep(30)\"],"
            "source=Path(" + repr(str(self.directory)) + "),env=dict(os.environ),log=Path(" + repr(str(self.log)) + "),"
            "timeout_seconds=5,term_grace_seconds=.2,kill_join_seconds=.2)\n"
            "except VerificationError:\n sys.exit(7)\n")
        runner = subprocess.Popen([sys.executable, str(script)])
        try:
            self.wait_until(lambda: self.log.exists() and b"interrupt-ready" in self.log.read_bytes())
            runner.send_signal(signal.SIGTERM)
            self.assertEqual(runner.wait(timeout=3), 7)
        finally:
            if runner.poll() is None:
                runner.kill()
                runner.wait(timeout=2)
        self.assertEqual(self.status()["outcome"], "interrupted")
        self.assertEqual(self.status()["interrupted_by"], signal.SIGTERM)
        self.assertTrue(self.status()["cleanup"]["group_empty"])

    def test_invalid_limits_or_existing_log_are_rejected_before_spawn(self):
        with self.assertRaises(VerificationError):
            self.capture("raise Exception('must not execute')", timeout_seconds=float("nan"))
        self.log.write_bytes(b"existing evidence")
        with self.assertRaises(VerificationError):
            self.capture("raise Exception('must not execute')")
        self.assertEqual(self.log.read_bytes(), b"existing evidence")


class FixtureSummaryTests(unittest.TestCase):
    def test_exact_summary_is_required(self):
        suite = {"filter": "fixture", "expected_passed": 18}
        self.assertEqual(verify_fixture_summary(SUMMARY, suite), 18)
        for output in ("", SUMMARY.replace("18 passed", "0 passed"), SUMMARY.replace("0 failed", "1 failed"),
                       SUMMARY.replace("0 ignored", "1 ignored"), SUMMARY.replace("ok.", "FAILED."), SUMMARY + SUMMARY):
            with self.subTest(output=output), self.assertRaises(VerificationError):
                verify_fixture_summary(output, suite)


if __name__ == '__main__':
    unittest.main()
