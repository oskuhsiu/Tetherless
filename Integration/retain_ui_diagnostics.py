#!/usr/bin/env python3
"""Retain bounded app-only diagnostic excerpts; the original xcresult is kept.

An oversized log is evidence to summarize, not a product/UI failure. Excerpts
never pretend to be complete files. IO failures and unexpected types still fail.
"""
import argparse
import json
import os
import re
from pathlib import Path
import stat


# Match only an entire line emitted by the zero-payload native event API. No
# copied path, arbitrary log suffix or raw provider response enters this record.
PAIRING_EVENTS = frozenset("""requestBegan pickerCreated plistTypeAllowed plistTypeNotAllowed
selectionReceived invalidSelection cancellationReceived resultDelivered lateCallbackIgnored
coordinatorInvalidated resolutionAccepted resolutionIgnored coverDismissed dismissalUnbound
dismissalObserved dismissalIgnored
cancelFinished importStarted importSucceeded importFailed""".split())
PAIRING_PREFIX = b'[Tetherless.PairingImport] '


def pairing_lifecycle(stream, size, scan_limit=33_554_432, event_limit=256):
    if scan_limit < 1 or event_limit < 1:
        raise ValueError('Invalid lifecycle evidence limits')
    stream.seek(0)
    consumed = 0
    total = 0
    events = []
    discard_line = False
    budget = min(size, scan_limit)
    while consumed < budget:
        part = stream.readline(min(4096, budget - consumed))
        if not part:
            raise ValueError('Diagnostic changed during lifecycle scan')
        consumed += len(part)
        complete_line = part.endswith(b'\n')
        if not discard_line and complete_line and part.startswith(PAIRING_PREFIX):
            event = part[len(PAIRING_PREFIX):].removesuffix(b'\n').removesuffix(b'\r')
            try:
                value = event.decode('ascii')
            except UnicodeDecodeError:
                value = None
            if value in PAIRING_EVENTS:
                total += 1
                if len(events) < event_limit:
                    events.append(value)
        # A suffix of an oversized line must not be mistaken for a fresh event.
        discard_line = not complete_line
    return {'events': events, 'observedEventCount': total,
            'eventsTruncated': total > event_limit, 'scannedBytes': consumed,
            'scanComplete': consumed == size, 'uiResultInferred': False}



PICKER_PREFIX = b'[Tetherless.PickerTiming] '
CLOCK_FIELDS = {'schemaVersion', 'source', 'event', 'processID',
                'monotonicBeforeUS', 'unixTimeUS', 'monotonicAfterUS'}
APP_TIMING_FIELDS = {
    'hostDidAppear': {'hostWindowAttached', 'pickerWindowAttached', 'presentedControllerMatches', 'alreadyPresented'},
    'presentationAttempt': {'hostWindowAttached', 'pickerWindowAttached', 'presentedControllerMatches', 'alreadyPresented'},
    'presentationCompleted': {'hostWindowAttached', 'pickerWindowAttached', 'presentedControllerMatches', 'alreadyPresented'},
    'delegateSelection': {'pickerWindowAttached'}, 'delegateCancellation': {'pickerWindowAttached'},
    'interactiveDismissal': {'pickerWindowAttached'}, 'dismantle': {'hostWindowAttached'},
}
UI_TIMING_FIELDS = {'beforeFirstPickerTap': set(), 'firstCancelWaitStart': set(), 'firstCancelWaitEnd': {'found'}}
HOST_TIMING_FIELDS = {'hostBeforeUI': set(), 'hostAfterUI': set(), 'hostAfterCollection': set()}


def clock_record(value, source):
    """Closed numeric/Boolean/event schema; reject arbitrary payloads outright."""
    choices = {'app': APP_TIMING_FIELDS, 'uiTest': UI_TIMING_FIELDS, 'host': HOST_TIMING_FIELDS}
    if not isinstance(value, dict) or source not in choices or value.get('source') != source:
        raise ValueError('Invalid timing source')
    if not isinstance(value.get('event'), str): raise ValueError('Invalid timing event type')
    extra = choices[source].get(value.get('event'))
    if extra is None or set(value) != CLOCK_FIELDS | extra:
        raise ValueError('Unrecognized timing schema')
    if type(value['schemaVersion']) is not int or value['schemaVersion'] != 1:
        raise ValueError('Invalid timing version')
    if type(value['processID']) is not int or not 0 < value['processID'] <= 2_147_483_647:
        raise ValueError('Invalid timing process')
    for key in ('monotonicBeforeUS', 'unixTimeUS', 'monotonicAfterUS'):
        if type(value[key]) is not int or not 0 <= value[key] < 2**53:
            raise ValueError('Invalid timing clock')
    if value['monotonicAfterUS'] < value['monotonicBeforeUS']:
        raise ValueError('Clock bracket reversed')
    if not 946_684_800_000_000 <= value['unixTimeUS'] <= 4_102_444_800_000_000:
        raise ValueError('UTC clock out of reviewed range')
    if any(type(value[key]) is not bool for key in extra):
        raise ValueError('Invalid timing flag')
    return dict(value)


def picker_timing(stream, size, scan_limit=33_554_432, event_limit=128):
    if min(scan_limit, event_limit) < 1: raise ValueError('Invalid timing scan bounds')
    stream.seek(0)
    consumed = observed = invalid = 0
    records = []
    discard = False
    budget = min(size, scan_limit)
    while consumed < budget:
        part = stream.readline(min(2048, budget - consumed))
        if not part: raise ValueError('Diagnostic changed during timing scan')
        consumed += len(part)
        whole = part.endswith(b'\n')
        if not discard and whole and part.startswith(PICKER_PREFIX):
            try:
                record = clock_record(json.loads(part[len(PICKER_PREFIX):]), 'app')
                observed += 1
                if len(records) < event_limit: records.append(record)
            except (ValueError, TypeError, UnicodeError): invalid += 1
        discard = not whole
    return {'records': records, 'observedRecordCount': observed, 'invalidRecordCount': invalid,
            'recordsTruncated': observed > event_limit, 'scannedBytes': consumed,
            'scanComplete': consumed == size, 'uiResultInferred': False}


def bounded_json(path, maximum=2_097_152):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError('Unsafe timing input')
    return json.loads(path.read_text())


def clock_correlation(records):
    """Bracketed UTC-minus-monotonic offsets, never a videoPTS conversion.

    Two microseconds cover integer rounding. An empty offset intersection is
    drift/disagreement, not permission to silently align clock origins.
    """
    groups = {}
    for record in records:
        item = clock_record(record, record.get('source'))
        key = (item['source'], item['processID'])
        low = item['unixTimeUS'] - item['monotonicAfterUS'] - 2
        high = item['unixTimeUS'] - item['monotonicBeforeUS'] + 2
        groups.setdefault(key, []).append((low, high, item))
    summaries = []
    all_intervals = []
    for (source, pid), values in sorted(groups.items()):
        lower, upper = max(v[0] for v in values), min(v[1] for v in values)
        summaries.append({'source': source, 'processID': pid, 'samples': len(values),
                          'offsetLowerUS': lower, 'offsetUpperUS': upper,
                          'constantOffsetCompatible': lower <= upper,
                          'minimumOffsetDisagreementUS': max(0, lower - upper),
                          'maximumSampleBracketUS': max(v[2]['monotonicAfterUS'] - v[2]['monotonicBeforeUS'] for v in values)})
        all_intervals += [(v[0], v[1]) for v in values]
    lower = max((v[0] for v in all_intervals), default=0)
    upper = min((v[1] for v in all_intervals), default=0)
    sources = {v['source'] for v in summaries}
    compatible = len(sources) >= 2 and lower <= upper
    return {'groups': summaries, 'roundingUncertaintyUS': 2,
            'crossSourceOffsetCompatibility': 'insufficient' if len(sources) < 2 else ('compatible' if compatible else 'disagrees'),
            'sharedOffsetLowerUS': lower if compatible else None, 'sharedOffsetUpperUS': upper if compatible else None,
            'minimumCrossSourceDisagreementUS': max(0, lower - upper),
            'videoPTSMappingPerformed': False, 'rootCauseInferred': False}



def temporal_enclosure(host_records, sample_records):
    """All compared UTC intervals carry their full sampled bracket uncertainty.

    Out-of-window or boundary-uncertain samples are evidence gaps. This does
    not assert a shared monotonic origin or align any video presentation time.
    """
    host = [clock_record(x, 'host') for x in host_records]
    result = {'valid': False, 'gaps': [], 'roundingUncertaintyUS': 2,
              'basis': 'recorded UTC with full monotonic bracket uncertainty', 'outsideSamples': []}
    if ([x['event'] for x in host] != list(HOST_TIMING_FIELDS) or
            host[1]['processID'] != host[2]['processID']):
        result['gaps'].append('hostStageSequenceInvalid'); return result
    def bounds(value):
        uncertainty = value['monotonicAfterUS'] - value['monotonicBeforeUS'] + 2
        return value['unixTimeUS'] - uncertainty, value['unixTimeUS'] + uncertainty
    if any(a['monotonicAfterUS'] > b['monotonicBeforeUS'] + 2 or bounds(a)[0] > bounds(b)[1]
           for a, b in zip(host, host[1:])):
        result['gaps'].append('hostStageClockOrderInvalid'); return result
    lower, upper = bounds(host[0])[0], bounds(host[1])[1]
    if lower > upper:
        result['gaps'].append('hostUIWindowInvalid'); return result
    result.update(windowLowerUnixUS=lower, windowUpperUnixUS=upper)
    for value in sample_records:
        sample = clock_record(value, value.get('source'))
        low, high = bounds(sample)
        if low < lower or high > upper:
            result['outsideSamples'].append({'source': sample['source'], 'event': sample['event'],
                'processID': sample['processID'], 'lowerUnixUS': low, 'upperUnixUS': high})
    if result['outsideSamples']: result['gaps'].append('sampleOutsideHostUIWindow')
    result['valid'] = not result['gaps']
    return result


def correlate_picker_timing(timing, diagnostics, attachments, output):
    if output.exists() or output.is_symlink(): raise FileExistsError('Timing correlation already exists')
    report = {'schemaVersion': 1, 'status': 'incomplete', 'gaps': [], 'appRecords': [],
              'uiRecords': [], 'hostRecords': [], 'uiResultInferred': False,
              'videoPTSMappingPerformed': False, 'rootCauseInferred': False}
    try:
        baseline = bounded_json(timing/'baseline.json', 65_536)
        collected = bounded_json(timing/'collection.json', 65_536)
        identity = baseline['identity']
        if identity != collected.get('identity'): raise ValueError('Timing run identity mismatch')
        report['identity'] = identity
        report['hostRecords'] = [clock_record(baseline['clock'], 'host')] + [clock_record(x, 'host') for x in collected['clocks']]
        report['collectionStatus'] = collected.get('status')
        if collected.get('status') != 'complete': report['gaps'].append('collectorIncomplete')
        retained = bounded_json(diagnostics/'manifest.json')
        for entry in retained['files']:
            if entry.get('kind') != 'stdout': continue
            scan = entry.get('pickerTiming')
            if scan is None:
                report['gaps'].append('appTimingScanMissing'); continue
            if not scan['scanComplete'] or scan['recordsTruncated'] or scan['invalidRecordCount']:
                report['gaps'].append('appTimingScanIncomplete')
            report['appRecords'] += [clock_record(x, 'app') for x in scan['records']]
        if len(report['appRecords']) > 256: raise ValueError('Excessive retained app timing records')
        manifest = bounded_json(attachments/'manifest.json')
        candidates = []
        for group in manifest:
            if group.get('testIdentifier') != 'TetherlessUITests/testFirstSetupAndLocalNavigation()': continue
            for entry in group.get('attachments', []):
                if not entry.get('suggestedHumanReadableName', '').startswith('picker-clock-first-presentation'): continue
                if entry.get('deviceId') != identity['simulatorID']:
                    raise ValueError('Timing attachment belongs to another device')
                name = entry.get('exportedFileName', '')
                if not re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9]+)?', name):
                    raise ValueError('Unsafe timing attachment name')
                candidates.append(attachments/name)
        if len(candidates) != 1: raise ValueError('Expected exactly one first-picker clock attachment')
        values = bounded_json(candidates[0], 4096)
        if not isinstance(values, list) or len(values) != 3: raise ValueError('Invalid XCTest clock count')
        report['uiRecords'] = [clock_record(x, 'uiTest') for x in values]
        if ([x['event'] for x in report['uiRecords']] != list(UI_TIMING_FIELDS) or
                len({x['processID'] for x in report['uiRecords']}) != 1):
            raise ValueError('XCTest clock identity/order changed')
        if any(a['monotonicAfterUS'] > b['monotonicBeforeUS'] for a,b in zip(report['uiRecords'],report['uiRecords'][1:])):
            raise ValueError('XCTest clock order reversed')
        start, end = report['uiRecords'][1:]
        report['originalCancelWait'] = {'found': end['found'], 'configuredTimeoutSeconds': 10,
            'durationLowerUS': end['monotonicBeforeUS'] - start['monotonicAfterUS'],
            'durationUpperUS': end['monotonicAfterUS'] - start['monotonicBeforeUS']}
        enclosure = temporal_enclosure(report['hostRecords'], report['appRecords'] + report['uiRecords'])
        report['temporalEnclosure'] = enclosure
        report['gaps'].extend(enclosure['gaps'])
        records = report['hostRecords'] + report['appRecords'] + report['uiRecords']
        report['correlation'] = clock_correlation(records)
        app_pids = {x['processID'] for x in report['appRecords']}
        services = collected.get('observedServices', [])
        report['observedServices'] = services
        if services and any(x['appPID'] not in app_pids for x in services):
            report['gaps'].append('serviceAppClockNotObserved')
        report['appTimingEventsObserved'] = bool(report['appRecords'])
        report['status'] = 'complete' if not report['gaps'] else 'gaps'
    except (OSError, ValueError, TypeError, KeyError) as error:
        report['status'] = 'gaps'; report['gaps'].append(type(error).__name__)
    output.write_text(json.dumps(report, indent=2) + '\n')
    return report


def kind(path):
    if path.name.startswith('StandardOutputAndStandardError-org.tetherless.testdocuments'):
        return 'fixture-stdout'
    if path.name.startswith('DocumentFixture-') and path.suffix in {'.ips', '.crash'}:
        return 'fixture-crash'
    if path.name.startswith('StandardOutputAndStandardError-org.tetherless.Tetherless'):
        return 'stdout'
    if path.name.startswith('SideStore-') and path.suffix in {'.ips', '.crash'}:
        return 'crash'
    return None


def retain(root: Path, destination: Path, limit=2_097_152):
    if limit < 2 or root.is_symlink() or not root.is_dir():
        raise ValueError('Invalid diagnostic selection input')
    selected = sorted(p for p in root.rglob('*') if kind(p) and not p.is_dir())
    if len(selected) > 20:
        raise ValueError('Unexpected diagnostic count')
    destination.mkdir(exist_ok=False)
    manifest = {'schemaVersion': 1, 'originalResultRetained': 'native-ui.xcresult',
                'uiResultInferred': False, 'files': []}
    for index, path in enumerate(selected):
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError('Unexpected diagnostic file type')
            size = before.st_size
            ranges = [(0, size)] if size <= limit else [(0, limit // 2), (size - (limit - limit // 2), limit - limit // 2)]
            entry = {'kind': kind(path), 'originalBytes': size, 'truncated': size > limit,
                     'omittedBytes': max(0, size - limit), 'parts': []}
            for part, (offset, length) in enumerate(ranges):
                stream.seek(offset)
                data = stream.read(length)
                if len(data) != length:
                    raise ValueError('Diagnostic changed during selection')
                name = f'{index:02d}-{kind(path)}-{part}.txt'
                (destination / name).write_bytes(data)
                entry['parts'].append({'file': name, 'offset': offset, 'bytes': length})
            if kind(path) == 'stdout':
                entry['pairingLifecycle'] = pairing_lifecycle(stream, size)
                entry['pickerTiming'] = picker_timing(stream, size)
            after = os.fstat(stream.fileno())
            if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
                raise ValueError('Diagnostic changed during selection')
            manifest['files'].append(entry)
    manifest['truncatedFiles'] = sum(item['truncated'] for item in manifest['files'])
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--correlate-picker', type=Path, metavar='ATTACHMENTS')
    parser.add_argument('--timing-report', type=Path)
    args = parser.parse_args()
    if args.correlate_picker is not None:
        if args.timing_report is None: parser.error('--timing-report is required for correlation')
        result = correlate_picker_timing(args.source, args.destination, args.correlate_picker, args.timing_report)
        print('Picker timing evidence:', result['status'], '; UI result not inferred.')
        if result['status'] != 'complete': raise SystemExit(1)
    else:
        if args.timing_report is not None: parser.error('--timing-report requires --correlate-picker')
        result = retain(args.source, args.destination)
        print('Retained', len(result['files']), 'app diagnostics;', result['truncatedFiles'],
              'explicitly truncated. Original xcresult unchanged; UI result not inferred.')
