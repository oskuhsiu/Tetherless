#!/usr/bin/env python3
"""Close native history/source-error persistence at reviewed source boundaries."""
from pathlib import Path
import hashlib
import sys

MODEL = 'AltStore/Core/Model/LoggedError.swift'
MANAGER = 'AltStore/Managing Apps/AppManager.swift'
MY_APPS = 'AltStore/My Apps/MyAppsViewController.swift'
SOURCES = 'AltStore/Sources/SourcesViewController.swift'
OVERRIDE = Path(__file__).with_name('Overrides') / 'LoggedErrorPrivacy.swift'

# SideStore 0dd743f: model and views are raw; AppManager is after
# catalog_safety and maintenance_safety. No Core Data schema changes.
BLOBS = {MODEL: 'affb5ad682b36f60201a9c9482496d33fe1f6230',
         MANAGER: '720794f95132df8f64e2c052531470c06544f296',
         MY_APPS: '0721a46491c1872de337a71e3642d2decb39cba0',
         SOURCES: '766ad6143ab0090c575bf50fd8cbc95f4ab0e8f8'}


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unreviewed error privacy anchor')
    return text.replace(old, new, 1)


def patch_model(text):
    text = once(text, '        let nsError = error as NSError\n',
        '        let nsError = TetherlessErrorRecordPolicy.sanitized(error as NSError)\n')
    # A legacy row can contain arbitrary userInfo/domain. Its display/copy path
    # must not reconstruct or evaluate that payload. Existing disk bytes are
    # not silently purged or migrated by this read-only presentation boundary.
    text = once(text,
        '        let nsError = NSError(domain: self.domain, code: Int(self.code), userInfo: self.userInfo)',
        '        let nsError = TetherlessErrorRecordPolicy.snapshot(domain: self.domain, code: Int(self.code))')
    return text + '\n' + OVERRIDE.read_text(encoding='utf-8')


def patch_manager(text):
    # Preserve the cancellation filters above and the existing database save
    # handling below. Other error propagation/serialization is deliberately
    # unchanged: this is diagnostic persistence, never an execution decision.
    text = once(text,
        '''        // Sanitize NSError on same thread before performing background task.
        let sanitizedError = (error as NSError).sanitizedForSerialization()''',
        '''        // Capture only closed diagnostic metadata before crossing queues.
        let sanitizedError = TetherlessErrorRecordPolicy.sanitized(error as NSError)''')
    # Preserve errors[source] = error for the original live completion result.
    # Only the persisted Source.error slot receives the diagnostic snapshot.
    text = once(text, 'source.error = error.sanitizedForSerialization()',
        'source.error = TetherlessErrorRecordPolicy.sanitized(error)')
    return patch_source_merge_error(text)


def patch_source_merge_error(text):
    # This snapshot is used only for the source's persisted error field. The
    # original mergeError still supplies sourceID selection and is rethrown.
    return once(text, 'let sanitizedError = (mergeError as NSError).sanitizedForSerialization()',
        'let sanitizedError = TetherlessErrorRecordPolicy.sanitized(mergeError as NSError)')


def patch_source_views(text):
    # Both existing display actions retain Optional nil/non-nil state. Old
    # stored NSError payloads are never sent directly to the alert presenter.
    old = 'if let error = source.error\n'
    if text.count(old) != 2:
        raise ValueError('Unreviewed source error display inventory')
    return text.replace(old,
        'if let error = source.error.map(TetherlessErrorRecordPolicy.sanitized)\n')


def apply(root: Path) -> None:
    outputs = {}
    for relative, patch in [(MODEL, patch_model), (MANAGER, patch_manager),
                            (MY_APPS, patch_source_merge_error), (SOURCES, patch_source_views)]:
        raw = (root / relative).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != BLOBS[relative]:
            raise ValueError('Unreviewed error privacy source: ' + relative)
        outputs[root / relative] = patch(raw.decode('utf-8'))
    # Validate every preimage/anchor before writing any source.
    for target, replacement in outputs.items():
        target.write_text(replacement, encoding='utf-8')


if __name__ == '__main__':
    apply(Path(sys.argv[1]))
