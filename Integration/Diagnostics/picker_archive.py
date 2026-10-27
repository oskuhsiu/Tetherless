#!/usr/bin/env python3
"""Read one byte-bound historical Simulator log archive; never run Simulator/UI.

Raw input/tool output stays in a private, unuploaded temporary directory. Only
closed-vocabulary event observations, timestamps, codes and hashes are exported.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import stat
import sys
import tempfile
import zipfile

ARTIFACT_ID = 11341735733
RUN_ID = 37298228388
SOURCE_SHA = '3d97ef75a224a76f84ba6741da8d9a6b89f99217'
ZIP_SHA = 'ac79e699970ebf98f07277855ffd824529fb826b6aba01583da4538433b742e2'
ZIP_BYTES = 76465711
DEVICE = 'E5EAC8DE-7B7F-481E-863A-0C3B2876A831'
ARCHIVE_REF = '0~Xv4iZZb7_QUa5Yx9cVyJfsDDIPRnSaDfPm0lpZirnSyTt9hpcMLXsJvLIcYWBjLIex8bnfljzU-R1_7NlPWFSg=='
ARCHIVE_ID = 'A8B6986C-2BB8-45F8-B6EF-23650E916F85'
INFO_SHA = '1c000cba102c7890d0e9dc0d8bd25f7e3b239be35bdc33457ef6bc7132ace2c4'
BUNDLE = 'org.tetherless.Tetherless.XYZ0123456'
START = '2026-10-05 10:54:58+0000'
END = '2026-10-05 10:55:57+0000'
PIDS = {22858: 'documentManager', 25024: 'localStorage', 12472: 'fileprovider'}
SUPERVISOR = {
    'bounded_process.py': '7724f6c3eb7d624f49a2651b30f1d6e6bb2c47d356449cd495fad28b2dd144e4',
    'apply_patch.py': 'a41e75b1903265c650c198bca05a2afc08ff053a01bcf0a56682cf95ce19c80a',
}
MAX_LOG = 8 * 1024 * 1024
MAX_EVENTS = 20000
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
MAX_EXPORTED_FILE = 128 * 1024 * 1024
MAX_EXPORTED_TOTAL = 192 * 1024 * 1024
EXPECTED_RESULT_TREE = {'files': 1070, 'bytes': 67535630,
    'sha256': '01c5a92e41208542401cedb17698fc40bd5f7212273ce602d438e91dfd0c7a27'}
EXPECTED_ARCHIVE_TREE = {'files': 289, 'bytes': 160044778,
    'sha256': '494aa14e7eee4e8f273fe0bac03b0e75928ea5925bbbf9c20ae12226e8c2d2c0'}
SUBSYSTEMS = ('com.apple.DocumentManager', 'com.apple.DocumentManagerUICore',
              'com.apple.FileProvider', 'com.apple.xpc', 'com.apple.extensionkit',
              'com.apple.foundation.filecoordination', 'com.apple.runningboard')
DOMAINS = ('NSFileProviderErrorDomain', 'NSFileProviderInternalErrorDomain',
           'NSCocoaErrorDomain', 'NSPOSIXErrorDomain', 'NSOSStatusErrorDomain',
           'FPErrorDomain', 'FPBookmarkErrorDomain', 'FPResolverErrorDomain')
FAILURE_CODES = frozenset(('symlink', 'not_bounded_regular_file', 'file_grew', 'unsafe_zip_member',
    'artifact_identity', 'archive_member_limit', 'unsafe_zip_entry', 'archive_size_limit',
    'member_size', 'owned_identity', 'missing_result', 'tree_symlink', 'tree_limit',
    'supervisor_identity', 'unsupported_tool_syntax', 'unsupported_process_predicate',
    'report_destination', 'requires_macos', 'incomplete_tool_output', 'download_directory',
    'download_count', 'input_tree_identity', 'archive_identity', 'exported_tree_identity',
    'process_predicate_unsupported'))
CLASS_PATTERNS = {
    'navigationMention': r'\bnavigat\w*\b|\bsidebar\b|\bon my iphone\b|\broot (?:item|folder|container|node)\b',
    'enumerationMention': r'\benumerat\w*\b|\bfetch(?:ing|ed)? (?:item|children)\b|\bcontents of\b',
    'ipcMention': r'\bxpc\b|\bconnection\b|\bproxy\b|\binterrupted\b|\binvalidated\b',
    'timeoutMention': r'\btimed? ?out\b|\btimeout\b',
    'errorMention': r'\berror\b|\bfailed\b|\bfailure\b',
    'requestMention': r'\brequest\w*\b|\bbegin\w*\b|\bstart\w*\b',
    'completionMention': r'\bcomplet\w*\b|\bfinish\w*\b|\bsuccess\w*\b',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def regular(path, limit):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError('symlink')
    st = path.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
        raise ValueError('not_bounded_regular_file')
    with path.open('rb') as f:
        data = f.read(limit + 1)
    if len(data) > limit:
        raise ValueError('file_grew')
    return data


def safe_member(name):
    p = PurePosixPath(name)
    if (not name or name.startswith('/') or '\\' in name or '\x00' in name or
            any(x in ('.', '..') for x in p.parts) or str(p) != name.rstrip('/')):
        raise ValueError('unsafe_zip_member')
    return p


def extract_result(data, destination, *, expected_sha=ZIP_SHA, expected_bytes=ZIP_BYTES):
    # The exact downloaded ZIP is checked before interpreting any member. No
    # external manifest or server-provided digest can replace this reviewed pin.
    if len(data) != expected_bytes or sha(data) != expected_sha:
        raise ValueError('artifact_identity')
    destination.mkdir(mode=0o700)
    records = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        members = z.infolist()
        if len(members) > 2000:
            raise ValueError('archive_member_limit')
        seen = set()
        total = 0
        for m in members:
            p = safe_member(m.filename)
            mode = m.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if (m.filename in seen or kind not in (0, stat.S_IFREG, stat.S_IFDIR) or
                    m.flag_bits & 1 or m.file_size > MAX_FILE):
                raise ValueError('unsafe_zip_entry')
            seen.add(m.filename)
            total += m.file_size
            if total > MAX_TOTAL:
                raise ValueError('archive_size_limit')
            if m.is_dir() or p.parts[0] != 'native-ui.xcresult':
                continue
            target = destination.joinpath(*p.parts)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            raw = z.read(m)
            if len(raw) != m.file_size:
                raise ValueError('member_size')
            with target.open('xb') as f:
                f.write(raw)
            target.chmod(0o600)
            records.append([m.filename, len(raw), sha(raw)])
        owner = json.loads(z.read('native-simulator-owner.json'))
        smoke = json.loads(z.read('native-launch-evidence.json'))
        if (owner.get('id') != DEVICE or owner.get('sourceCommit') != SOURCE_SHA or
                owner.get('runtime') != 'com.apple.CoreSimulator.SimRuntime.iOS-26-2' or
                smoke.get('sourceCommit') != SOURCE_SHA or smoke.get('simulatorID') != DEVICE or
                smoke.get('bundleID') != BUNDLE):
            raise ValueError('owned_identity')
    result = destination / 'native-ui.xcresult'
    if not records or not (result / 'Info.plist').is_file():
        raise ValueError('missing_result')
    return result, tree_manifest(destination)


def tree_manifest(root, *, exported=False):
    root = Path(root).absolute()
    if any(p.is_symlink() for p in [root, *root.parents]) or not root.is_dir():
        raise ValueError('tree_symlink')
    records, pending = [], [root]
    total = 0
    directories = 1
    file_limit = MAX_EXPORTED_FILE if exported else MAX_FILE
    total_limit = MAX_EXPORTED_TOTAL if exported else MAX_TOTAL
    # Do not materialize an unbounded rglob/sort before enforcing quotas. The
    # path-row list is sorted only after bounded traversal and reads finish.
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                if entry.is_symlink():
                    raise ValueError('tree_symlink')
                path = Path(entry.path)
                if len(path.relative_to(root).parts) > 32:
                    raise ValueError('tree_limit')
                if entry.is_dir(follow_symlinks=False):
                    directories += 1
                    if directories > 1024:
                        raise ValueError('tree_limit')
                    pending.append(path)
                    continue
                if len(records) >= 2000 or entry.stat(follow_symlinks=False).st_size > total_limit - total:
                    raise ValueError('tree_limit')
                data = regular(path, min(file_limit, total_limit - total))
                total += len(data)
                records.append([path.relative_to(root).as_posix(), len(data), sha(data)])
    records.sort()
    return {'files': len(records), 'bytes': total,
            'sha256': sha(json.dumps(records, separators=(',', ':')).encode())}


def load_supervisor(root, scratch):
    folder = scratch / 'supervisor'
    folder.mkdir(mode=0o700)
    for name, expected in SUPERVISOR.items():
        data = regular(root / 'Integration/Dependencies/idevice' / name, 1024 * 1024)
        if sha(data) != expected:
            raise ValueError('supervisor_identity')
        (folder / name).write_bytes(data)
    previous = sys.modules.get('apply_patch')
    try:
        spec = importlib.util.spec_from_file_location('apply_patch', folder / 'apply_patch.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules['apply_patch'] = module
        spec.loader.exec_module(module)
        spec = importlib.util.spec_from_file_location('picker_archive_supervisor', folder / 'bounded_process.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.capture_helper_command
    finally:
        if previous is None:
            sys.modules.pop('apply_patch', None)
        else:
            sys.modules['apply_patch'] = previous


def supported(text, words):
    if not all(word in text for word in words):
        raise ValueError('unsupported_tool_syntax')


def query_predicate(field):
    if field not in ('processIdentifier', 'processID'):
        raise ValueError('unsupported_process_predicate')
    subsystem = '(' + ' OR '.join('subsystem == "' + s + '"' for s in SUBSYSTEMS) + ')'
    # Shared fileproviderd is additionally limited to explicit owned/local
    # process or fixture references. Redacted/unmatched events stay unavailable.
    binding = '(' + ' OR '.join('eventMessage CONTAINS "' + s + '"' for s in
        ('org.tetherless.testdocuments', 'com.apple.FileProvider.LocalStorage',
         ':22858', '[22858]', ':25024', '[25024]')) + ')'
    return f'(({field} == 22858 OR {field} == 25024) OR ({field} == 12472 AND {binding})) AND {subsystem}'


def scope_matches(record):
    pid = record.get('processID')
    message = record.get('eventMessage')
    if type(pid) is not int or pid not in PIDS or record.get('subsystem') not in SUBSYSTEMS or not isinstance(message, str):
        return False
    if pid == 12472 and not any(s in message for s in
        ('org.tetherless.testdocuments', 'com.apple.FileProvider.LocalStorage',
         ':22858', '[22858]', ':25024', '[25024]')):
        return False
    return True


def sanitize_events(raw):
    # ndjson is required by the installed help. Any unsupported line or event
    # leaves an explicit gap, never a fabricated empty/successful query.
    events, gaps = [], set()
    count = 0
    start, end = datetime.fromisoformat(START), datetime.fromisoformat(END)
    for line in raw.decode('utf-8', 'strict').splitlines():
        if not line.strip():
            continue
        count += 1
        if count > MAX_EVENTS:
            gaps.add('event_limit')
            break
        try:
            record = json.loads(line)
            if not isinstance(record, dict) or not scope_matches(record):
                raise ValueError('out_of_scope_or_schema')
            timestamp = datetime.fromisoformat(record['timestamp'])
            if timestamp.tzinfo is None or not start <= timestamp <= end:
                raise ValueError('out_of_window')
            message = record['eventMessage']
            if len(message.encode()) > 256 * 1024:
                raise ValueError('message_limit')
            classes = [k for k, pattern in CLASS_PATTERNS.items() if re.search(pattern, message, re.I)]
            errors = []
            for domain, code in re.findall(r'\bError Domain=([A-Za-z0-9_.-]+) Code=(-?\d{1,10})\b', message):
                if domain in DOMAINS:
                    errors.append({'domain': domain, 'code': int(code)})
                else:
                    classes.append('unlistedErrorDomain')
            if len(errors) > 16:
                gaps.add('error_code_limit')
            event = {'timestampUTC': timestamp.astimezone(timezone.utc).isoformat(),
                     'processRole': PIDS[record['processID']], 'classes': sorted(set(classes)),
                     'messageSHA256': sha(message.encode()), 'errorCodes': errors[:16],
                     'omittedErrorCodeCount': max(0, len(errors) - 16),
                     'privateMarkerPresent': '<private>' in message}
            activity = record.get('activityIdentifier')
            if type(activity) is int and 0 < activity < 2**64:
                event['activitySHA256'] = sha(str(activity).encode())
            events.append(event)
        except (ValueError, KeyError, TypeError, OverflowError):
            gaps.add('unparsed_or_out_of_scope_record')
    if not events:
        gaps.add('no_scoped_events')
    return {'events': events, 'gaps': sorted(gaps), 'inputLines': count,
            'classificationMeaning': 'lexical observations only; no inferred transaction completion or root cause'}


def analyze(download, source, output, *, runner=None, platform=None):
    output = Path(output).absolute()
    if (output.exists() or any(p.is_symlink() for p in [output, *output.parents]) or
            not output.parent.is_dir()):
        raise ValueError('report_destination')
    output.mkdir(mode=0o700)
    report = {'schema': 1, 'status': 'pending', 'stage': 'platform', 'artifactID': ARTIFACT_ID, 'runID': RUN_ID,
              'sourceCommit': SOURCE_SHA, 'zipSHA256': ZIP_SHA, 'archiveID': ARCHIVE_ID,
              'window': {'startUTC': START, 'endUTC': END}, 'phases': {}, 'gaps': [],
              'rootCauseInferred': False, 'productAccepted': False, 'rawMessagesExported': False,
              'defaultPrivacyRetained': True, 'collectionComplete': False,
              'collectionCompletenessScope': 'owned archive export and scoped query, not proof every runtime event was logged'}
    scratch = None
    safe_cleanup = True
    try:
        if (sys.platform if platform is None else platform) != 'darwin':
            raise ValueError('requires_macos')
        scratch = Path(tempfile.mkdtemp(prefix='tetherless-picker-archive-')).resolve()
        report['stage'] = 'supervisorIdentity'
        invoke = load_supervisor(Path(source).absolute(), scratch) if runner is None else runner
        env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'HOME': str(scratch), 'TMPDIR': str(scratch),
               'TZ': 'UTC', 'LANG': 'en_US.UTF-8', 'DEVELOPER_DIR': '/Applications/Xcode_26.3.app/Contents/Developer'}

        def phase(name, command, *, help_command=False, timeout=30, cap=65536):
            nonlocal safe_cleanup
            report['stage'] = name
            log = scratch / (name + '.raw')
            caught = None
            safe_cleanup = False
            try:
                invoke(command, source=scratch, env=env, log=log, timeout_seconds=timeout,
                       max_log_bytes=cap, tail_bytes=1, term_grace_seconds=5, kill_join_seconds=5)
            except Exception as error:
                caught = type(error).__name__
            status_path = log.with_name(log.name + '.status.json')
            status = json.loads(regular(status_path, 65536)) if status_path.exists() else {}
            cleanup = status.get('cleanup') or {}
            joined = cleanup.get('direct_child_reaped') is True and cleanup.get('group_empty') is True
            safe_cleanup = joined
            data = regular(log, cap) if log.exists() else b''
            allowed = status.get('returncode') in ((0, 64) if help_command else (0,))
            # A help command may deliberately exit EX_USAGE, but only its bounded,
            # joined complete pipe is acceptable; no timeout/output cap exception.
            complete = (joined and status.get('output_complete') is True and
                        status.get('output_truncated') is False and status.get('returncode') == 0 and
                        status.get('outcome') == 'success' and caught is None)
            help_usable = (help_command and joined and allowed and
                           status.get('output_truncated') is False and
                           status.get('outcome') == 'nonzero_exit' and
                           status.get('stop_reason') == 'nonzero_exit' and
                           status.get('returncode') == 64)
            acceptable = complete or help_usable
            record = {'returncode': status.get('returncode'), 'outcome': status.get('outcome'),
                      'caughtExceptionClass': caught, 'elapsedSeconds': status.get('elapsed_seconds'),
                      'timeoutSeconds': timeout, 'limitBytes': cap, 'retainedBytes': len(data),
                      'outputSHA256': sha(data), 'outputComplete': complete,
                      'helpUsageExitAcceptedForSyntaxOnly': help_usable,
                      'truncated': status.get('output_truncated'), 'joined': joined}
            report['phases'][name] = record
            if not acceptable:
                raise ValueError('incomplete_tool_output')
            return data

        report['stage'] = 'artifactIdentity'
        directory = Path(download).absolute()
        if any(p.is_symlink() for p in [directory, *directory.parents]) or not directory.is_dir():
            raise ValueError('download_directory')
        files = list(directory.iterdir())
        if len(files) != 1:
            raise ValueError('download_count')
        zip_data = regular(files[0], ZIP_BYTES)
        result, before = extract_result(zip_data, scratch / 'input')
        report['inputTree'] = before
        if before != EXPECTED_RESULT_TREE:
            raise ValueError('input_tree_identity')
        del zip_data
        help_data = phase('exportHelp', ['/usr/bin/xcrun', 'xcresulttool', 'export', 'object', '--help'], help_command=True)
        help_text = help_data.decode('utf-8', 'strict')
        supported(help_text, ('--path', '--output-path', '--id', '--type', 'directory', '--legacy'))
        archive = scratch / 'owned.logarchive'
        phase('exportOwnedArchive', ['/usr/bin/xcrun', 'xcresulttool', 'export', 'object', '--legacy',
              '--type', 'directory', '--path', str(result), '--id', ARCHIVE_REF,
              '--output-path', str(archive)], timeout=90)
        report['stage'] = 'exportedArchiveIdentity'
        info_data = regular(archive / 'Info.plist', 65536)
        info = plistlib.loads(info_data)
        if sha(info_data) != INFO_SHA or info.get('ArchiveIdentifier') != ARCHIVE_ID:
            raise ValueError('archive_identity')
        report['archiveTree'] = tree_manifest(archive, exported=True)
        if report['archiveTree'] != EXPECTED_ARCHIVE_TREE:
            raise ValueError('exported_tree_identity')
        show_help = phase('logShowHelp', ['/usr/bin/log', 'show', '--help'], help_command=True).decode('utf-8', 'strict')
        supported(show_help, ('<archive>', '--start', '--end', '--style', 'ndjson', '--timezone', '--predicate'))
        for level in ('info', 'debug'):
            if not re.search(r'--(?:\[no-\])?' + level + r'\b', show_help):
                raise ValueError('unsupported_tool_syntax')
        pred_help = phase('predicateHelp', ['/usr/bin/log', 'help', 'predicates'], help_command=True).decode('utf-8', 'strict')
        field = next((x for x in ('processIdentifier', 'processID') if re.search(r'\b' + x + r'\b', pred_help)), None)
        if field is None:
            raise ValueError('process_predicate_unsupported')
        predicate = query_predicate(field)
        report['queryPredicateSHA256'] = sha(predicate.encode())
        raw = phase('scopedArchiveQuery', ['/usr/bin/log', 'show', '--start', START,
                    '--end', END, '--style', 'ndjson', '--timezone', 'UTC', '--info', '--debug',
                    '--predicate', predicate, str(archive)], timeout=90, cap=MAX_LOG)
        report['stage'] = 'sanitizeScopedEvents'
        parsed = sanitize_events(raw)
        report.update(parsed)
        report['gaps'] = parsed['gaps']
        if tree_manifest(scratch / 'input') != before:
            report['gaps'].append('input_tree_changed')
        report['collectionComplete'] = not report['gaps']
        report['status'] = 'complete' if report['collectionComplete'] else 'gaps'
    except (KeyboardInterrupt, SystemExit):
        safe_cleanup = False
        report['status'] = 'interrupted'
        report['gaps'].append('interrupted')
    except Exception as error:
        report['status'] = 'gaps'
        # No exception text, raw tool line, file path or arbitrary identifier.
        report['gaps'].append('analysis_failed')
        report['errorClass'] = type(error).__name__
        report['failureCode'] = str(error) if type(error) is ValueError and str(error) in FAILURE_CODES else 'unclassified_failure'
    finally:
        report['temporaryCleanupScope'] = 'private_analysis_scratch_only; original download remains in ephemeral runner temp'
        report['temporaryCleanupConfirmed'] = False
        if scratch is not None and safe_cleanup:
            try:
                shutil.rmtree(scratch)
                report['temporaryCleanupConfirmed'] = True
            except OSError:
                report['gaps'].append('temporary_cleanup_failed')
                report['status'] = 'gaps'
        elif scratch is not None:
            report['gaps'].append('supervised_cleanup_unconfirmed')
            report['status'] = 'gaps'
        report['collectionComplete'] = report['collectionComplete'] and not report['gaps']
        (output / 'report.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download-dir', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = analyze(args.download_dir, args.source_root, args.output)
        print(json.dumps({'status': result['status'], 'collectionComplete': result['collectionComplete'],
                          'rootCauseInferred': False, 'productAccepted': False}))
        return 0 if result['status'] == 'complete' else 1
    except Exception:
        print('{"status":"report_setup_failed","productAccepted":false}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
