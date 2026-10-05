#!/usr/bin/env python3
"""Suppress the separately registered EMProxy native diagnostic callback."""
from pathlib import Path
import hashlib
import sys

SOURCE = 'Dependencies/minimuxer/Sources/EMProxyImpl.swift'
EXPECTED = '920e57694b1835b00dbd8761d34b2045bd272880'
OLD = '''        set_log_callback { level, msgPtr in
            guard let msgPtr = msgPtr else { return false }
            let msg = "[EMProxy] \\(String(cString: msgPtr))"
            if level <= 1 {
                verboseLog(msg)
            } else {
                debugLog(msg)
            }
            return true
        }'''
NEW = '''        // A true return marks the native diagnostic as handled. Do not
        // decode or emit its free-form payload, even when logging is enabled.
        set_log_callback { _, _ in true }'''


def patch(source: str) -> str:
    if source.count(OLD) != 1:
        raise ValueError('Unreviewed EMProxy logging callback')
    return source.replace(OLD, NEW, 1)


def apply(root: Path) -> None:
    target = root / SOURCE
    raw = target.read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if actual != EXPECTED:
        raise ValueError('Unreviewed EMProxy logging source')
    output = patch(raw.decode('utf-8'))
    target.write_text(output, encoding='utf-8')


if __name__ == '__main__':
    apply(Path(sys.argv[1]))
