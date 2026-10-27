#!/usr/bin/env python3
"""Close the separate native app's free-form logging sink, not its UI errors."""
from pathlib import Path
import hashlib
import sys

SOURCE = 'SideStore/Core/Logging/SideStoreLogging.swift'
EXPECTED = '4ef9e3a0c861583c171664f651999d8ebbbee4ec'
OVERRIDE = Path(__file__).with_name('Overrides') / 'SideStoreLogging.swift'
OPERATIONS = 'SideStore/Core/Logging/OperationLogging.swift'
OPERATIONS_EXPECTED = '5dc8e6e0d42ad1b17f0f2634c1902327d5b96f15'
OPERATIONS_OVERRIDE = OVERRIDE.with_name('OperationLogging.swift')
BLOBS = {SOURCE: EXPECTED, OPERATIONS: OPERATIONS_EXPECTED}
OVERRIDES = {SOURCE: OVERRIDE, OPERATIONS: OPERATIONS_OVERRIDE}


def apply(root: Path) -> None:
    outputs = {}
    for relative, expected in BLOBS.items():
        target = root / relative
        raw = target.read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != expected:
            raise ValueError('Unreviewed native logging source: ' + relative)
        outputs[target] = OVERRIDES[relative].read_text(encoding='utf-8')
    for target, replacement in outputs.items():
        target.write_text(replacement, encoding='utf-8')


if __name__ == '__main__':
    apply(Path(sys.argv[1]))
