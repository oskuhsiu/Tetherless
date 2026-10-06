"""Portable operation contracts; no Xcode/Rust build or Linux production route."""
import contextlib
import ctypes
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('xcframework_operation_test_subject', ROOT / 'xcframework_operation.py')
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


def load_capture():
    # Load the same pinned repository supervisor from its promoted recipe path.
    path = ROOT / 'bounded_process.py'
    expected = '7724f6c3eb7d624f49a2651b30f1d6e6bb2c47d356449cd495fad28b2dd144e4'
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise RuntimeError('supervisor source mismatch')
    spec = importlib.util.spec_from_file_location('operation_fixture_supervisor', path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module.capture_helper_command


class EnumerationTests(unittest.TestCase):
    def setUp(self):
        for name, value in [('getpid', 123), ('getpgrp', 123), ('getsid', 123)]:
            patcher = patch.object(subject.os, name, return_value=value)
            patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.object(subject.sys, 'platform', 'darwin')
        patcher.start(); self.addCleanup(patcher.stop)
        self.function = Mock()
        library = Mock(proc_listpgrppids=self.function)
        patcher = patch.object(subject.ctypes, 'CDLL', return_value=library)
        self.loader = patcher.start(); self.addCleanup(patcher.stop)
        self.group = subject.OwnProcessGroup()

    def enumerate(self, pids, count=None):
        def call(group, buffer, size):
            self.assertEqual(group, 123)
            self.assertEqual(size, subject.MAX_GROUP_PIDS * ctypes.sizeof(ctypes.c_int))
            for index, pid in enumerate(pids):
                buffer[index] = pid
            return len(pids) if count is None else count
        self.function.side_effect = call
        return self.group.members()

    def test_native_signature_and_return_value_are_pid_count_not_bytes(self):
        self.loader.assert_called_once_with('/usr/lib/libproc.dylib', use_errno=True)
        self.assertEqual(self.function.argtypes, [ctypes.c_int, ctypes.c_void_p, ctypes.c_int])
        self.assertEqual(self.function.restype, ctypes.c_int)
        self.assertEqual(self.enumerate([123, 124, 125]), {123, 124, 125})
        self.assertEqual(self.enumerate([123]), {123})

    def test_failed_empty_or_saturated_enumeration_is_not_empty(self):
        for count in [-1, 0, subject.MAX_GROUP_PIDS, subject.MAX_GROUP_PIDS + 1]:
            with self.subTest(count=count), self.assertRaises(subject.PackagingError):
                self.enumerate([123], count)
        pids = list(range(2, 2 + subject.MAX_GROUP_PIDS - 1))
        self.assertIn(123, pids)
        self.assertEqual(self.enumerate(pids), set(pids))

    def test_own_pid_required_and_invalid_or_duplicate_ids_rejected(self):
        for pids in [[124], [123, 123], [123, 0], [123, 1], [123, -4]]:
            with self.subTest(pids=pids), self.assertRaises(subject.PackagingError):
                self.enumerate(pids)

    def test_identity_change_is_rejected_before_and_after_native_call(self):
        for name in ['getpid', 'getpgrp', 'getsid']:
            with patch.object(subject.os, name, return_value=124), self.assertRaises(subject.PackagingError):
                self.group.members()
        self.function.assert_not_called()
        with patch.object(subject.os, 'getpgrp', side_effect=[123, 124]):
            with self.assertRaises(subject.PackagingError):
                self.enumerate([123])

    def test_unavailable_platform_or_native_api_fails_closed(self):
        with patch.object(subject.sys, 'platform', 'linux'), self.assertRaises(subject.PackagingError):
            subject.OwnProcessGroup()
        with patch.object(subject.ctypes, 'CDLL', side_effect=OSError('missing library')):
            with self.assertRaises(OSError): subject.OwnProcessGroup()
        with patch.object(subject.ctypes, 'CDLL', return_value=object()):
            with self.assertRaises(AttributeError): subject.OwnProcessGroup()


class OperationTests(unittest.TestCase):
    def test_fixed_argv_and_exact_four_key_child_environment(self):
        paths = ['/device.a', '/device-headers', '/simulator.a', '/simulator-headers', '/out.xcframework']
        command = subject.packaging_command(paths)
        self.assertEqual(command, ['/usr/bin/xcodebuild', '-create-xcframework',
                         '-library', paths[0], '-headers', paths[1],
                         '-library', paths[2], '-headers', paths[3], '-output', paths[4]])
        env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'DEVELOPER_DIR': '/Xcode', 'HOME': '/home', 'TMPDIR': '/tmp'}
        child = Mock(pid=124)
        child.wait.return_value = 0
        group = Mock(pid=123)
        group.members.side_effect = [{123}, {123}]
        with patch.dict(os.environ, dict(env, LC_CTYPE='C.UTF-8', SECRET='not-for-child'), clear=True), \
                patch.object(subject, 'OwnProcessGroup', return_value=group), \
                patch.object(subject.subprocess, 'Popen', return_value=child) as spawn, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(subject.main(paths), 0)
        spawn.assert_called_once_with(command, env=env, stdin=subprocess.DEVNULL, close_fds=True)
        child.wait.assert_called_once_with()
        self.assertEqual(group.members.call_count, 2)
        for bad in [paths[:4], ['relative'] + paths[1:]]:
            with self.assertRaises(subject.PackagingError): subject.packaging_command(bad)

    def test_direct_child_reaped_before_drain_and_nonzero_preserved(self):
        for code, expected in [(0, 0), (7, 7), (-15, 143)]:
            with self.subTest(code=code):
                child = Mock(pid=124)
                calls = []
                child.wait.side_effect = lambda: calls.append('reaped') or code
                group = Mock(pid=123)
                def members():
                    self.assertEqual(calls[0], 'reaped')
                    calls.append('snapshot')
                    return {123, 125} if len(calls) < 4 else {123}
                group.members.side_effect = members
                with patch.object(subject.time, 'sleep') as sleep, contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(subject.wait_for_child_and_group(child, group), expected)
                self.assertEqual(sleep.call_count, 2)
                events = [json.loads(line.removeprefix(subject.EVENT_PREFIX)) for line in output.getvalue().splitlines()]
                self.assertEqual(events[-1]['event'], 'group_drained')
                self.assertTrue(events[-1]['tail_observed'])
                self.assertEqual(events[-1]['child_returncode'], code)

    def test_enumeration_error_after_reaping_never_emits_drained(self):
        child = Mock(pid=124); child.wait.return_value = 0
        group = Mock(pid=123); group.members.side_effect = subject.PackagingError('truncated')
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(subject.PackagingError): subject.wait_for_child_and_group(child, group)
        child.wait.assert_called_once_with()
        self.assertNotIn('group_drained', output.getvalue())

    def test_main_rejects_nonexclusive_group_without_spawning(self):
        paths = ['/a', '/h', '/b', '/j', '/o']
        with patch.object(subject, 'packaging_environment', return_value={}), \
                patch.object(subject, 'OwnProcessGroup') as group, \
                patch.object(subject.subprocess, 'Popen') as spawn, \
                contextlib.redirect_stdout(io.StringIO()):
            group.return_value.pid = 123
            group.return_value.members.return_value = {123, 124}
            self.assertEqual(subject.main(paths), 70)
        spawn.assert_not_called()


@unittest.skipUnless(os.name == 'posix', 'controlled process fixtures require POSIX')
class SupervisedFixtures(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.log = self.work / 'operation.txt'
        self.capture = load_capture()

    def run_fixture(self, body, **overrides):
        code = 'import os,sys,subprocess,time\nsys.path.insert(0,' + repr(str(ROOT)) + ')\nimport xcframework_operation as operation\n' + body
        options = dict(timeout_seconds=2, max_log_bytes=8192, term_grace_seconds=.3, kill_join_seconds=.3)
        options.update(overrides)
        return self.capture([sys.executable, '-I', '-c', code], source=self.work,
                            env=dict(os.environ), log=self.log, **options)

    def status(self):
        return json.loads(self.log.with_name(self.log.name + '.status.json').read_bytes())

    def test_real_child_and_same_group_tail_drain_before_wrapper_exit(self):
        # A test-only second direct child models a naturally reaped group tail.
        # It avoids unreaped Linux PID-1 orphans and does not emulate Darwin API.
        output = self.run_fixture("""
child = subprocess.Popen([sys.executable, '-c', 'raise SystemExit(0)'])
tail = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(.3)'])
class Group:
    pid = os.getpid()
    def members(self):
        assert child.returncode == 0
        assert os.getpgrp() == self.pid
        if tail.poll() is None:
            assert os.getpgid(tail.pid) == self.pid
            return {self.pid, tail.pid}
        tail.wait()
        return {self.pid}
raise SystemExit(operation.wait_for_child_and_group(child, Group()))
""")
        self.assertIn('"tail_observed": true', output)
        status = self.status()
        self.assertEqual(status['outcome'], 'success')
        self.assertEqual(status['cleanup']['signals'], [])
        self.assertEqual(status['cleanup']['empty_evidence'], 'killpg_ESRCH')

    def test_real_nonzero_child_remains_failure(self):
        with self.assertRaises(Exception):
            self.run_fixture("""
child = subprocess.Popen([sys.executable, '-c', 'raise SystemExit(7)'])
class Group:
    pid = os.getpid()
    def members(self): return {self.pid}
raise SystemExit(operation.wait_for_child_and_group(child, Group()))
""")
        status = self.status()
        self.assertEqual(status['outcome'], 'nonzero_exit')
        self.assertEqual(status['returncode'], 7)
        self.assertTrue(status['cleanup']['group_empty'])

    def test_stalled_drain_is_still_bounded_by_original_timeout(self):
        with self.assertRaises(Exception):
            self.run_fixture("""
child = subprocess.Popen([sys.executable, '-c', 'raise SystemExit(0)'])
class Group:
    pid = os.getpid()
    def members(self): return {self.pid, 999999}
raise SystemExit(operation.wait_for_child_and_group(child, Group()))
""", timeout_seconds=.3)
        status = self.status()
        self.assertEqual(status['outcome'], 'timeout')
        self.assertEqual(status['cleanup']['signals'], ['SIGTERM'])
        self.assertTrue(status['cleanup']['direct_child_reaped'])
        self.assertTrue(status['cleanup']['group_empty'])
        self.assertNotIn('group_drained', self.log.read_text())

    def test_native_enumeration_failure_after_real_child_is_outer_failure(self):
        # Inject the native function only. Exercise main(), its real child wait,
        # actual count validation and unchanged outer failure classification.
        for count in [0, -1, subject.MAX_GROUP_PIDS]:
            self.log = self.work / ('enumeration-' + str(count) + '.txt')
            with self.subTest(count=count), self.assertRaises(Exception):
                self.run_fixture("""
from unittest.mock import patch
real_spawn = subprocess.Popen
def fixture_spawn(command, **kwargs):
    assert command[0:2] == ['/usr/bin/xcodebuild', '-create-xcframework']
    return real_spawn([sys.executable, '-c', 'raise SystemExit(0)'], **kwargs)
class NativeFunction:
    calls = 0
    def __call__(self, group, buffer, size):
        self.calls += 1
        buffer[0] = os.getpid()
        return 1 if self.calls == 1 else %d
class Library:
    proc_listpgrppids = NativeFunction()
environment = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'DEVELOPER_DIR': '/Xcode', 'HOME': '/home', 'TMPDIR': '/tmp'}
with patch.object(operation.sys, 'platform', 'darwin'), patch.object(operation.ctypes, 'CDLL', return_value=Library()), patch.object(operation.subprocess, 'Popen', side_effect=fixture_spawn), patch.dict(os.environ, environment, clear=True):
    raise SystemExit(operation.main(['/a', '/h', '/b', '/j', '/o']))
""" % count)
            status = self.status()
            self.assertEqual(status['outcome'], 'nonzero_exit')
            self.assertEqual(status['returncode'], 70)
            self.assertTrue(status['cleanup']['group_empty'])
            self.assertIn('child_reaped', self.log.read_text())
            self.assertNotIn('group_drained', self.log.read_text())

    def test_external_cancellation_retains_original_interrupted_outcome(self):
        runner = self.work / 'supervisor.py'
        code = """
import os,sys,subprocess
sys.path.insert(0, %r)
import xcframework_operation as operation
child = subprocess.Popen([sys.executable, '-c', 'raise SystemExit(0)'])
class Group:
    pid = os.getpid()
    def members(self): return {self.pid, 999999}
raise SystemExit(operation.wait_for_child_and_group(child, Group()))
""" % str(ROOT)
        runner.write_text("import importlib.util,os,sys\nfrom pathlib import Path\n"
            "spec=importlib.util.spec_from_file_location('operation_fixture_tests'," + repr(str(Path(__file__).resolve())) + ");module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)\n"
            "capture=module.load_capture()\n"
            "try:\n capture([sys.executable,'-I','-c'," + repr(code) + "],source=Path(" + repr(str(self.work)) + "),env=dict(os.environ),log=Path(" + repr(str(self.log)) + "),timeout_seconds=5,term_grace_seconds=.3,kill_join_seconds=.3)\n"
            "except Exception:\n sys.exit(7)\n")
        process = subprocess.Popen([sys.executable, '-I', str(runner)])
        try:
            deadline = time.monotonic() + 3
            while not (self.log.exists() and 'child_reaped' in self.log.read_text()):
                if process.poll() is not None or time.monotonic() >= deadline:
                    self.fail('controlled operation did not become ready')
                time.sleep(.01)
            process.send_signal(signal.SIGTERM)
            self.assertEqual(process.wait(timeout=3), 7)
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=2)
        status = self.status()
        self.assertEqual(status['outcome'], 'interrupted')
        self.assertEqual(status['interrupted_by'], signal.SIGTERM)
        self.assertTrue(status['cleanup']['group_empty'])
        self.assertEqual(status['cleanup']['signals'], ['SIGTERM'])


if __name__ == '__main__':
    unittest.main()
