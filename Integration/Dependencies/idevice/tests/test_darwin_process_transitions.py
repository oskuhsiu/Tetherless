"""Controlled POSIX fixtures plus injected Darwin errno transitions; no native builds."""
import errno
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bounded_process
from apply_patch import VerificationError


@unittest.skipUnless(os.name == "posix", "owned process-group fixtures require POSIX")
class DarwinGroupTransitionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.log = self.directory / "capture.txt"
        self.real_killpg = os.killpg

    def capture(self, code, **limits):
        options = dict(timeout_seconds=1.0, max_log_bytes=4096, tail_bytes=256,
                       term_grace_seconds=0.15, kill_join_seconds=0.3)
        options.update(limits)
        return bounded_process.capture_helper_command([sys.executable, "-u", "-c", code],
            source=self.directory, env=dict(os.environ), log=self.log, **options)

    def status(self):
        return json.loads(self.log.with_name(self.log.name + ".status.json").read_bytes())

    def test_probe_permission_failure_is_unknown_never_empty(self):
        for code in (errno.EPERM, errno.EACCES, errno.EINVAL):
            with self.subTest(errno=code), patch.object(bounded_process.os, "killpg", side_effect=OSError(code, "fixture")):
                self.assertEqual(bounded_process.probe_group(12345), ("unknown", code))

    def test_only_esrch_is_positive_empty_evidence(self):
        with patch.object(bounded_process.os, "killpg", side_effect=ProcessLookupError(errno.ESRCH, "fixture")):
            self.assertEqual(bounded_process.probe_group(12345), ("empty", errno.ESRCH))
        with patch.object(bounded_process.os, "killpg", return_value=None):
            self.assertEqual(bounded_process.probe_group(12345), ("present", None))

    def test_invalid_group_ids_never_signal(self):
        with patch.object(bounded_process.os, "killpg") as kill:
            for pgid in (-1, 0, 1, None):
                self.assertEqual(bounded_process.probe_group(pgid), ("unknown", errno.EINVAL))
            kill.assert_not_called()

    def test_successful_exit_waits_through_transient_eperm_to_esrch(self):
        unknown = 2
        def transition(pgid, sig):
            nonlocal unknown
            if sig == 0 and unknown:
                unknown -= 1
                raise PermissionError(errno.EPERM, "controlled Darwin transition")
            return self.real_killpg(pgid, sig)
        with patch.object(bounded_process.os, "killpg", side_effect=transition):
            output = self.capture("print('complete-final-output')")
        self.assertIn("complete-final-output", output)
        status = self.status()
        self.assertEqual(status["outcome"], "success")
        self.assertEqual(status["post_exit_unknown_probe_count"], 2)
        self.assertEqual(status["post_exit_last_unknown_errno"], errno.EPERM)
        self.assertTrue(status["cleanup"]["direct_child_reaped"])
        self.assertTrue(status["cleanup"]["group_empty"])
        self.assertEqual(status["cleanup"]["empty_evidence"], "killpg_ESRCH")

    def test_cleanup_reaps_through_transient_post_term_probe_eperm(self):
        sent_term, unknown = False, 2
        def transition(pgid, sig):
            nonlocal sent_term, unknown
            if sig == signal.SIGTERM:
                sent_term = True
            if sig == 0 and sent_term and unknown:
                unknown -= 1
                raise PermissionError(errno.EPERM, "controlled zombie-only transition")
            return self.real_killpg(pgid, sig)
        with patch.object(bounded_process.os, "killpg", side_effect=transition):
            with self.assertRaises(VerificationError):
                self.capture("import time; print('compiler-before-timeout'); time.sleep(30)", timeout_seconds=0.2)
        status = self.status()
        self.assertEqual(status["outcome"], "timeout")
        self.assertEqual(status["stop_reason"], "timeout")
        self.assertEqual(status["cleanup"]["unknown_probe_count"], 2)
        self.assertEqual(status["cleanup"]["last_unknown_errno"], errno.EPERM)
        self.assertTrue(status["cleanup"]["direct_child_reaped"])
        self.assertTrue(status["cleanup"]["group_empty"])
        self.assertIn(b"compiler-before-timeout", self.log.read_bytes())

    def test_persistent_probe_eperm_retains_evidence_reaps_and_fails_closed(self):
        def uncertain(pgid, sig):
            if sig == 0:
                raise PermissionError(errno.EPERM, "controlled persistent uncertainty")
            return self.real_killpg(pgid, sig)
        start = time.monotonic()
        with patch.object(bounded_process.os, "killpg", side_effect=uncertain):
            with self.assertRaises(VerificationError):
                self.capture("print('successful-child-is-not-group-absence-proof')", timeout_seconds=0.1)
        self.assertLess(time.monotonic() - start, 1.5)
        status = self.status()
        self.assertEqual(status["outcome"], "cleanup_incomplete")
        self.assertFalse(status["cleanup"]["group_empty"])
        self.assertIsNone(status["cleanup"]["empty_evidence"])
        self.assertTrue(status["cleanup"]["direct_child_reaped"])
        self.assertEqual(status["returncode"], 0)
        self.assertGreater(status["cleanup"]["unknown_probe_count"], 0)
        self.assertFalse(status["output_complete"])
        self.assertIn(b"successful-child", self.log.read_bytes())

    def test_term_eperm_is_recorded_and_kill_still_reaps(self):
        def denied_term(pgid, sig):
            if sig == signal.SIGTERM:
                raise PermissionError(errno.EPERM, "controlled denied TERM")
            return self.real_killpg(pgid, sig)
        with patch.object(bounded_process.os, "killpg", side_effect=denied_term):
            with self.assertRaises(VerificationError):
                self.capture("import time; print('compiler-start'); time.sleep(30)", timeout_seconds=0.2)
        cleanup = self.status()["cleanup"]
        self.assertEqual(cleanup["signal_errors"], [{"signal": "SIGTERM", "errno": errno.EPERM}])
        self.assertEqual(cleanup["signals"], ["SIGKILL"])
        self.assertTrue(cleanup["direct_child_reaped"])
        self.assertTrue(cleanup["group_empty"])
        self.assertEqual(self.status()["returncode"], -signal.SIGKILL)

    def test_term_and_kill_eperm_do_not_skip_natural_exit_reap(self):
        def denied_signals(pgid, sig):
            if sig in (signal.SIGTERM, signal.SIGKILL):
                raise PermissionError(errno.EPERM, "controlled denied signal")
            return self.real_killpg(pgid, sig)
        with patch.object(bounded_process.os, "killpg", side_effect=denied_signals):
            with self.assertRaises(VerificationError):
                self.capture("import time; print('short-lived-fixture'); time.sleep(.4)",
                             timeout_seconds=0.1, term_grace_seconds=0.1, kill_join_seconds=0.7)
        status = self.status()
        self.assertEqual(status["outcome"], "timeout")
        self.assertEqual(status["cleanup"]["signal_errors"], [
            {"signal": "SIGTERM", "errno": errno.EPERM}, {"signal": "SIGKILL", "errno": errno.EPERM}])
        self.assertTrue(status["cleanup"]["direct_child_reaped"])
        self.assertTrue(status["cleanup"]["group_empty"])
        self.assertEqual(status["returncode"], 0)


if __name__ == "__main__":
    unittest.main()
