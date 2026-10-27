#!/usr/bin/env python3
"""Classify one pre-identified historical picker event. No product/UI execution."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import sys
import tempfile

HELPER_SHA = 'b3272ed5743bc887a2254ef3eae7e27e95c4ce4dae0505a067acf61cf5b94b4d'
TARGET_TIME = '2026-10-05T10:55:56.651894+00:00'
TARGET_MESSAGE_SHA = 'f7547ed30e40537407357290e3b3f7caf45d9665a9c8fa5bb427986f5a11cfd2'
TARGET_ACTIVITY_SHA = '2b2a184998c7a08b7ff6ed56f6cee51dbcc2a78b49a3758886bc481ebad12246'
QUERY_START = '2026-10-05 10:55:56+0000'
QUERY_END = '2026-10-05 10:55:57+0000'
TARGET_PID = 22858
QUERY_CAP = 1024 * 1024
FORMAT_CAP = 8192
MAX_LINES = 4096
PRINTF = re.compile(r'%(?:\{[^{}\r\n]{0,160}\})?(?:[1-9]\d*\$)?[-+ #0]*(?:\d+|\*(?:[1-9]\d*\$)?)?(?:\.(?:\d+|\*(?:[1-9]\d*\$)?))?(?:hh|ll|[hlqLztj])?[@diouxXfFeEgGaAcCsSpP%]')
# Unknown words are elided even after ordinary PII/payload removal. Preserve
# useful static Apple operation vocabulary, not arbitrary formatted prose.
WORDS = frozenset(('a an the this that these those to from for of by on in into out with without and or but '
    'at as is are was were be been being not no nil null none yes true false can cannot could should would '
    'will did does do has have had while when before after during because due instead only already '
    'failed failure fail error errors timeout timed timing time out wait waiting waited pending cancelled '
    'cancel cancellation canceling cancelling finished finish finishing complete completed completion '
    'completing success successful successfully unsuccessful unable unavailable available invalid '
    'valid invalidated invalidating interrupted interrupt interruption request requested requesting '
    'response respond responding returned returning return received receiving receive sent sending send '
    'start started starting begin beginning end ended ending retry retries retrying '
    'navigate navigates navigated navigating navigation navigator transition transitions transitioning '
    'perform performed performing operation operations action actions task tasks transaction transactions '
    'enumerate enumerates enumerated enumerating enumeration enumerator fetch fetching fetched lookup '
    'resolve resolving resolved resolution bookmark bookmarks coordinate coordinated coordinating coordination '
    'connect connecting connected connection connections xpc ipc proxy service process provider fileprovider '
    'local localstorage document documents manager browser browse browsed browsing sidebar root content contents '
    'item items node nodes location locations folder folders container containers directory directories '
    'file files url urls identifier identifiers state states target source destination current previous next '
    'view controller collection list lists open opening opened select selection selected selecting load '
    'loading loaded update updated updating obtain obtaining creating create created delegate callback '
    'callbacks activity session context invalidation block blocked blocking main thread queue synchronous '
    'asynchronous dispatch dispatching seconds second milliseconds duration deadline budget limit '
    'deferred defer deferring immediately asynchronous synchronous unexpectedly expected response handler '
    'user interface ui display presented presenting presentation dismissal dismiss dismissing visible '
    'removed removing remove adding added add empty missing found find finding ready readiness lock locked '
    'read reading write writing access permission denied assertion assertionfailure exception recovery '
    'internal underlying domain code errno userinfo options metadata payload data '
    'default processactivity fpitemcollection docnodecollectiondelegate documentmanager documentmanageruicore').split())
TECHNICAL_SYMBOLS = frozenset(('NSFileCoordinator', 'NSFileProviderManager', 'NSFileProviderItem',
    'UIDocumentPickerViewController', 'DOCNodeCollectionDelegate', 'FPItemCollection',
    'DocumentManager', 'DocumentManagerUICore', 'LocalStorageFileProvider'))
ERROR_DOMAINS = frozenset(('NSFileProviderErrorDomain', 'NSFileProviderInternalErrorDomain',
    'NSCocoaErrorDomain', 'NSPOSIXErrorDomain', 'NSOSStatusErrorDomain', 'NSURLErrorDomain',
    'FPErrorDomain', 'FPBookmarkErrorDomain', 'FPResolverErrorDomain',
    'com.apple.iconServices.symbol-error'))
OPERATIONS = {
    'navigation': r'\bnavigat(?:e|es|ed|ing|ion|or)\b',
    'enumeration': r'\benumerat(?:e|es|ed|ing|ion|or)\b',
    'bookmarkResolution': r'\bbookmark\w*\b.*\bresolv\w*\b|\bresolv\w*\b.*\bbookmark\w*\b',
    'fileCoordination': r'\bcoordinat(?:e|ed|ing|ion)\b|\bNSFileCoordinator\b',
    'connection': r'\bxpc\b|\bipc\b|\bconnection\b',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bounded_regular(path, limit):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in [path, *path.parents]) or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('unsafe_file')
    with path.open('rb') as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError('file_limit')
    return value


def load_base(source, scratch):
    raw = bounded_regular(source / 'Integration/Diagnostics/picker_archive.py', 65536)
    if sha(raw) != HELPER_SHA:
        raise ValueError('helper_identity')
    frozen = scratch / 'picker_archive_base.py'
    frozen.write_bytes(raw)
    spec = importlib.util.spec_from_file_location('picker_archive_event_base', frozen)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def redact_template(value):
    if not isinstance(value, str) or not value or len(value.encode()) > FORMAT_CAP:
        return None
    if any(ord(c) < 32 and c not in '\r\n\t' for c in value):
        return None
    # Parse every printf conversion first; values never come from eventMessage.
    pieces, cursor, substitutions = [], 0, 0
    while cursor < len(value):
        if value[cursor] != '%':
            pieces.append(value[cursor]); cursor += 1; continue
        match = PRINTF.match(value, cursor)
        if match is None:
            return None
        pieces.append('%' if match.group() == '%%' else '<value>')
        substitutions += match.group() != '%%'
        cursor = match.end()
    text = ''.join(pieces)
    contractions = {"can't": 'cannot', "couldn't": 'could not', "don't": 'do not',
        "doesn't": 'does not', "didn't": 'did not', "won't": 'will not',
        "isn't": 'is not', "aren't": 'are not', "wasn't": 'was not',
        "weren't": 'were not', "hasn't": 'has not', "haven't": 'have not',
        "hadn't": 'had not', "shouldn't": 'should not', "wouldn't": 'would not'}
    for contraction, expanded in contractions.items():
        pattern = re.escape(contraction).replace("'", "['’]")
        text = re.sub(r'\b' + pattern + r'\b', expanded, text, flags=re.I)
    # Elide quoted content and object/dictionary descriptions, including nested
    # braces. These are unnecessary for the static technical operation.
    quoted, cursor = [], 0
    pairs = {'\"': '\"', "'": "'", '`': '`', '“': '”', '‘': '’'}
    while cursor < len(text):
        char = text[cursor]
        if char in ('”', '’'):
            return None
        if char not in pairs:
            quoted.append(char); cursor += 1; continue
        end = cursor + 1
        while end < len(text):
            if text[end] == '\\':
                end += 2; continue
            if text[end] == pairs[char]:
                break
            end += 1
        if end >= len(text):
            return None
        quoted.append('<value>'); cursor = end + 1
    text = ''.join(quoted)
    while re.search(r'\{[^{}]*\}', text):
        text = re.sub(r'\{[^{}]*\}', '<value>', text)
    if '{' in text or '}' in text:
        return None
    text = re.sub(r'<(?!value>)[^>]*>', '<value>', text)
    if '<' in text.replace('<value>', '') or '>' in text.replace('<value>', ''):
        return None
    text = re.sub(r'(?i)\b(?:password|passwd|secret|token|api[_-]?key|authorization|bearer|cookie|account|username|email)\s*[:=]\s*[^,;\r\n]+', '<value>', text)
    text = re.sub(r'\b[A-Za-z][A-Za-z0-9+.-]*://\S+|(?:[A-Za-z]:\\|~?/|\.{1,2}[/\\]|[A-Za-z0-9_.-]+[/\\])[^,;\r\n\)\]]+', '<value>', text)
    text = re.sub(r'\b[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', '<value>', text)
    text = re.sub(r'\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b|\b0x[0-9a-fA-F]+\b', '<value>', text)
    text = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F:]{0,32}\b', '<value>', text)
    tokens = re.findall(r'<value>|[A-Za-z_][A-Za-z0-9_]*|\d+|[^\w\s]', text)
    output, symbols = [], []
    elided = 0
    for token in tokens:
        if token == '<value>':
            output.append(token)
        elif token in TECHNICAL_SYMBOLS:
            output.append(token); symbols.append(token)
        elif token.lower() in WORDS:
            output.append(token.lower())
        elif token in '.,:;()[]=-!?/%':
            output.append(token)
        else:
            output.append('<text>'); elided += 1
    rendered = ' '.join(output)
    # Never publish even a long reconstruction. No silent truncation.
    if not rendered or len(rendered.encode()) > FORMAT_CAP:
        return None
    return {'template': rendered, 'formatSHA256': sha(value.encode()),
            'interpolatedValueCount': substitutions, 'elidedTokenCount': elided,
            'technicalSymbols': sorted(set(symbols))}


def event_details(record):
    message = record['eventMessage']
    template = redact_template(record.get('formatString'))
    errors, unknown = [], 0
    for domain, code in re.findall(r'\bError Domain=([A-Za-z0-9_.-]{1,160}) Code=(-?\d{1,10})(?=$|[\s,;)}\]])', message):
        if domain in ERROR_DOMAINS and -(2**31) <= int(code) < 2**31:
            errors.append({'domain': domain, 'code': int(code)})
        else:
            unknown += 1
    if len(errors) > 16:
        return {'status': 'inconclusive', 'reason': 'error_detail_limit'}
    text = template['template'] if template else ''
    operations = [name for name, pattern in OPERATIONS.items() if re.search(pattern, text, re.I)]
    timeout = bool(re.search(r'\btimeout\b|\btimed?\s+out\b', text, re.I))
    result = {'status': 'classified' if operations or errors else 'inconclusive',
              'reportedOperations': operations, 'timeoutExplicitInTemplate': timeout,
              'technicalErrors': errors, 'unretainedDomainCount': unknown,
              'meaning': 'technical content of this exact log event, not root cause or proof of operation completion'}
    if template is not None:
        result['staticFormat'] = template
    else:
        result['templateUnavailableOrUnsafe'] = True
    return result


def identify(raw, subsystems):
    matches, nonmatching, unsupported = [], 0, 0
    line_count = 0
    for line in raw.decode('utf-8', 'strict').splitlines():
        if not line.strip():
            continue
        line_count += 1
        if line_count > MAX_LINES:
            raise ValueError('line_limit')
        try:
            r = json.loads(line)
            if not isinstance(r, dict):
                raise ValueError('shape')
            message, activity = r.get('eventMessage'), r.get('activityIdentifier')
            timestamp = datetime.fromisoformat(r['timestamp'])
            if timestamp.tzinfo is None:
                raise ValueError('naive_timestamp')
            match = (r.get('processID') == TARGET_PID and type(r.get('processID')) is int and
                     r.get('subsystem') in subsystems and timestamp == datetime.fromisoformat(TARGET_TIME) and
                     isinstance(message, str) and sha(message.encode()) == TARGET_MESSAGE_SHA and
                     type(activity) is int and 0 < activity < 2**64 and sha(str(activity).encode()) == TARGET_ACTIVITY_SHA)
            if match:
                matches.append(r)
            else:
                nonmatching += 1
        except (ValueError, TypeError, KeyError, OverflowError):
            unsupported += 1
    # Neither nonmatching records nor malformed-line text/hashes are exported.
    result = {'queryNonblankLines': line_count, 'nonmatchingRecordCount': nonmatching,
              'unsupportedLineCount': unsupported, 'exactMatchCount': len(matches),
              'allQueryLinesParsed': unsupported == 0,
              'matchingEventObserved': len(matches) == 1,
              'eventIdentified': len(matches) == 1 and unsupported == 0}
    if len(matches) != 1:
        result.update(status='inconclusive', reason='exact_event_missing_or_ambiguous')
    else:
        details = event_details(matches[0])
        if unsupported:
            result.update(status='inconclusive', reason='unsupported_query_lines',
                          provisionalExactMatchDetails=details)
        else:
            result.update(details)
    return result


def predicate(field, subsystems):
    if field not in ('processIdentifier', 'processID'):
        raise ValueError('predicate_field')
    return f'{field} == {TARGET_PID} AND (' + ' OR '.join('subsystem == "' + s + '"' for s in subsystems) + ')'


def analyze(download, source, output, *, runner=None, base=None, platform=None):
    output = Path(output).absolute()
    if output.exists() or any(p.is_symlink() for p in [output, *output.parents]) or not output.parent.is_dir():
        raise ValueError('output_destination')
    output.mkdir(mode=0o700)
    result = {'schema': 1, 'status': 'pending', 'stage': 'platform', 'phases': {},
              'targetTimestampUTC': TARGET_TIME, 'targetMessageSHA256': TARGET_MESSAGE_SHA,
              'targetActivitySHA256': TARGET_ACTIVITY_SHA, 'helperSHA256': HELPER_SHA,
              'queryStartUTC': QUERY_START, 'queryEndUTC': QUERY_END,
              'rootCauseInferred': False, 'productAccepted': False,
              'rawMessageExported': False, 'defaultPrivacyRetained': True}
    scratch, joined = None, True
    try:
        if (sys.platform if platform is None else platform) != 'darwin':
            raise ValueError('requires_macos')
        scratch = Path(tempfile.mkdtemp(prefix='tetherless-picker-event-')).resolve()
        result['stage'] = 'helperIdentity'
        helper = load_base(Path(source).absolute(), scratch) if base is None else base
        invoke = helper.load_supervisor(Path(source).absolute(), scratch) if runner is None else runner
        result.update(artifactID=helper.ARTIFACT_ID, runID=helper.RUN_ID,
                      sourceCommit=helper.SOURCE_SHA, zipSHA256=helper.ZIP_SHA,
                      archiveID=helper.ARCHIVE_ID)
        env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'HOME': str(scratch), 'TMPDIR': str(scratch),
               'TZ': 'UTC', 'LANG': 'en_US.UTF-8', 'DEVELOPER_DIR': '/Applications/Xcode_26.3.app/Contents/Developer'}

        def phase(name, command, *, help_command=False, timeout=30, cap=65536):
            nonlocal joined
            result['stage'] = name
            log = scratch / (name + '.raw')
            caught = None
            joined = False
            try:
                invoke(command, source=scratch, env=env, log=log, timeout_seconds=timeout,
                       max_log_bytes=cap, tail_bytes=1, term_grace_seconds=5, kill_join_seconds=5)
            except Exception as error:
                caught = type(error).__name__
            sidecar = json.loads(helper.regular(log.with_name(log.name + '.status.json'), 65536))
            cleanup = sidecar.get('cleanup') or {}
            joined = cleanup.get('direct_child_reaped') is True and cleanup.get('group_empty') is True
            raw = helper.regular(log, cap)
            complete = (joined and caught is None and sidecar.get('outcome') == 'success' and
                        sidecar.get('returncode') == 0 and sidecar.get('output_complete') is True and
                        sidecar.get('output_truncated') is False)
            usage = (help_command and joined and sidecar.get('outcome') == 'nonzero_exit' and
                     sidecar.get('returncode') == 64 and sidecar.get('stop_reason') == 'nonzero_exit' and
                     sidecar.get('output_truncated') is False)
            result['phases'][name] = {'returncode': sidecar.get('returncode'),
                'outcome': sidecar.get('outcome'), 'joined': joined, 'outputComplete': complete,
                'helpUsageExitAcceptedForSyntaxOnly': usage, 'timeoutSeconds': timeout,
                'limitBytes': cap, 'retainedBytes': len(raw), 'outputSHA256': sha(raw),
                'truncated': sidecar.get('output_truncated')}
            if not complete and not usage:
                raise ValueError('incomplete_tool_output')
            return raw

        result['stage'] = 'artifactIdentity'
        download = Path(download).absolute()
        if any(p.is_symlink() for p in [download, *download.parents]) or not download.is_dir():
            raise ValueError('download_directory')
        files = list(download.iterdir())
        if len(files) != 1:
            raise ValueError('download_count')
        raw_zip = helper.regular(files[0], helper.ZIP_BYTES)
        xcresult, original_tree = helper.extract_result(raw_zip, scratch / 'input')
        del raw_zip
        if original_tree != helper.EXPECTED_RESULT_TREE:
            raise ValueError('input_tree_identity')
        result['inputTree'] = original_tree
        export_help = phase('exportHelp', ['/usr/bin/xcrun', 'xcresulttool', 'export', 'object', '--help'], help_command=True).decode()
        helper.supported(export_help, ('--path', '--output-path', '--id', '--type', 'directory', '--legacy'))
        archive = scratch / 'owned.logarchive'
        phase('exportOwnedArchive', ['/usr/bin/xcrun', 'xcresulttool', 'export', 'object', '--legacy',
            '--type', 'directory', '--path', str(xcresult), '--id', helper.ARCHIVE_REF,
            '--output-path', str(archive)], timeout=90)
        result['stage'] = 'archiveIdentity'
        info_data = helper.regular(archive / 'Info.plist', 65536)
        if sha(info_data) != helper.INFO_SHA or plistlib.loads(info_data).get('ArchiveIdentifier') != helper.ARCHIVE_ID:
            raise ValueError('archive_identity')
        archive_tree = helper.tree_manifest(archive, exported=True)
        if archive_tree != helper.EXPECTED_ARCHIVE_TREE:
            raise ValueError('export_tree_identity')
        result['archiveTree'] = archive_tree
        help_text = phase('logHelp', ['/usr/bin/log', 'show', '--help'], help_command=True).decode()
        helper.supported(help_text, ('<archive>', '--start', '--end', '--style', 'ndjson', '--timezone', '--predicate'))
        for level in ('info', 'debug'):
            if not re.search(r'--(?:\[no-\])?' + level + r'\b', help_text):
                raise ValueError('unsupported_tool_syntax')
        fields = phase('predicateHelp', ['/usr/bin/log', 'help', 'predicates'], help_command=True).decode()
        field = next((f for f in ('processIdentifier', 'processID') if re.search(r'\b' + f + r'\b', fields)), None)
        query = predicate(field, helper.SUBSYSTEMS)
        result['queryPredicateSHA256'] = sha(query.encode())
        raw = phase('exactSecondQuery', ['/usr/bin/log', 'show', '--start', QUERY_START,
            '--end', QUERY_END, '--style', 'ndjson', '--timezone', 'UTC', '--info', '--debug',
            '--predicate', query, str(archive)], timeout=90, cap=QUERY_CAP)
        result['stage'] = 'identifyAndClassifyExactEvent'
        result.update(identify(raw, helper.SUBSYSTEMS))
        if helper.tree_manifest(scratch / 'input') != original_tree:
            result.update(status='inconclusive', reason='input_tree_changed')
    except (KeyboardInterrupt, SystemExit):
        joined = False
        result.update(status='inconclusive', reason='interrupted')
    except Exception as error:
        # Error content is never an alternate route to publishing raw messages.
        result.update(status='inconclusive', reason='analysis_failure', errorClass=type(error).__name__)
    finally:
        result['temporaryCleanupConfirmed'] = False
        result['temporaryCleanupScope'] = 'private analysis scratch only; action download remains unuploaded ephemeral data'
        if scratch is not None and joined:
            try:
                shutil.rmtree(scratch)
                result['temporaryCleanupConfirmed'] = True
            except OSError:
                result.update(status='inconclusive', reason='temporary_cleanup_failed')
        elif scratch is not None:
            result.update(status='inconclusive', reason='supervised_cleanup_unconfirmed')
        (output / 'report.json').write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download-dir', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        r = analyze(args.download_dir, args.source_root, args.output)
        print(json.dumps({'status': r['status'], 'eventIdentified': r.get('eventIdentified', False),
                          'rootCauseInferred': False, 'productAccepted': False}))
        return 0 if r['status'] == 'classified' else 1
    except Exception:
        print('{"status":"report_setup_failed","productAccepted":false}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
