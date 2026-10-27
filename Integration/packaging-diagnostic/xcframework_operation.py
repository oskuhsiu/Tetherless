"""One XCFramework operation, owned and bounded by bounded_process.py.

Run only as that supervisor's session/group leader. The trusted xcodebuild child
inherits this group; this leader stays alive through its natural helper tail.
No signal handling, cleanup, deadline, session changes or process-name filtering
belong here. Only the outer supervisor can accept or terminate the operation.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

MAX_GROUP_PIDS = 128
POLL_SECONDS = 0.05
EVENT_PREFIX = 'tetherless-packaging-operation '
ENVIRONMENT_KEYS = ('PATH', 'DEVELOPER_DIR', 'HOME', 'TMPDIR')


class PackagingError(RuntimeError):
    pass


class OwnProcessGroup:
    """A bounded Darwin snapshot, including zombies, without an observer child."""

    def __init__(self):
        if sys.platform != 'darwin':
            raise PackagingError('Darwin libproc is required')
        self.pid = os.getpid()
        self.check_identity()
        # Apple's libproc.h marks this host API private/subject to change.
        # Fail closed if unavailable. Do not search libraries or invoke ps.
        self.library = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        self.list_pids = self.library.proc_listpgrppids
        self.list_pids.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        self.list_pids.restype = ctypes.c_int

    def check_identity(self):
        if (self.pid <= 1 or os.getpid() != self.pid or os.getpgrp() != self.pid
                or os.getsid(0) != self.pid):
            raise PackagingError('operation is not its owned session/group leader')

    def members(self):
        self.check_identity()
        buffer = (ctypes.c_int * MAX_GROUP_PIDS)()
        # Unlike proc_listpids, proc_listpgrppids returns a PID COUNT, not bytes.
        # Its input size is bytes. A full buffer cannot establish completeness.
        count = self.list_pids(self.pid, buffer, ctypes.sizeof(buffer))
        if count <= 0 or count >= MAX_GROUP_PIDS:
            raise PackagingError('owned group enumeration failed or saturated')
        members = set(buffer[:count])
        if len(members) != count or any(pid <= 1 for pid in members) or self.pid not in members:
            raise PackagingError('owned group enumeration has invalid identity')
        self.check_identity()
        return members


def packaging_command(paths):
    if len(paths) != 5 or any(not Path(path).is_absolute() for path in paths):
        raise PackagingError('five absolute archive/header/output paths are required')
    device_library, device_headers, simulator_library, simulator_headers, output = map(str, paths)
    return ['/usr/bin/xcodebuild', '-create-xcframework',
            '-library', device_library, '-headers', device_headers,
            '-library', simulator_library, '-headers', simulator_headers,
            '-output', output]


def packaging_environment():
    # Python may add LC_CTYPE to its own environment at startup. Never pass that
    # or another inherited variable to xcodebuild: preserve the original four.
    environment = {key: os.environ[key] for key in ENVIRONMENT_KEYS}
    if (environment['PATH'] != '/usr/bin:/bin:/usr/sbin:/sbin'
            or any(not Path(environment[key]).is_absolute() for key in ENVIRONMENT_KEYS[1:])):
        raise PackagingError('unexpected packaging environment')
    return environment


def emit(event, **fields):
    print(EVENT_PREFIX + json.dumps(dict(event=event, **fields), sort_keys=True), flush=True)


def wait_for_child_and_group(child, group):
    returncode = child.wait()  # Reap the direct xcodebuild child before drain proof.
    emit('child_reaped', pid=group.pid, child_pid=child.pid, child_returncode=returncode)
    tail_observed = False
    while group.members() != {group.pid}:
        tail_observed = True
        time.sleep(POLL_SECONDS)
    emit('group_drained', pid=group.pid, child_pid=child.pid,
         child_returncode=returncode, tail_observed=tail_observed)
    # Preserve every nonzero/signal failure; never turn a child signal into zero.
    return returncode if returncode >= 0 else 128 - returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', type=Path, nargs=5,
                        metavar='PATH', help='device archive/headers, simulator archive/headers, output')
    args = parser.parse_args(argv)
    try:
        command = packaging_command(args.paths)
        environment = packaging_environment()
        group = OwnProcessGroup()
        if group.members() != {group.pid}:
            raise PackagingError('operation group is not initially exclusive')
        child = subprocess.Popen(command, env=environment, stdin=subprocess.DEVNULL,
                                 close_fds=True)  # Inherit group, cwd and output pipes.
        emit('started', pid=group.pid, child_pid=child.pid)
        return wait_for_child_and_group(child, group)
    except Exception as error:
        # The outer supervisor sees failure and owns all remaining group cleanup.
        emit('failed', error_type=type(error).__name__)
        return 70


if __name__ == '__main__':
    raise SystemExit(main())
