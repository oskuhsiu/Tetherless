"""Exact diagnostic-copy-only SideStore linker settings; sibling targets unchanged."""
from __future__ import annotations
import hashlib
import re

PROJECT_PATH = 'AltStore.xcodeproj/project.pbxproj'
PROJECT_SHA256 = '62d1d4e41d6b0169cc5edead9588f11f4cb18f09ad876e7a45f2d95e979d7980'
PROJECT_GIT_BLOB = 'a511c447bd71311bffb6d116a3cb0025a75561d4'
APP_C_ROOTS = frozenset({'_plist_free', '_idevice_free'})
APP_RUST_ROOTS = frozenset({'_tetherless_pairing_host_prepare', '_tetherless_pairing_validate_staged',
                            '_tetherless_native_plist_free', '_tetherless_native_idevice_free'})
C_SYSTEM_FRAMEWORKS = frozenset({'CoreFoundation', 'SystemConfiguration'})
CONFIGURATIONS = {'Debug': 'BFD2477F2284B9A700981D42', 'Release': 'BFD247802284B9A700981D42'}
FLAGS_PREIMAGE = '\t\t\t\tOTHER_LDFLAGS = (\n\t\t\t\t\t"$(inherited)",\n\t\t\t\t\t"-Xlinker",\n\t\t\t\t\t"-w",\n\t\t\t\t);'


def patch_project(original: bytes) -> bytes:
    if (hashlib.sha256(original).hexdigest() != PROJECT_SHA256
            or hashlib.sha1(b'blob ' + str(len(original)).encode() + b'\0' + original).hexdigest() != PROJECT_GIT_BLOB):
        raise ValueError('diagnostic project is not the complete pinned prepared preimage')
    text = original.decode()
    flags = [flag for name in sorted(C_SYSTEM_FRAMEWORKS) for flag in ('-framework', name)]
    flags += ['-Wl,-u,' + name for name in sorted(APP_C_ROOTS | APP_RUST_ROOTS)]
    additions = ''.join('\t\t\t\t\t"' + flag + '",\n' for flag in flags)
    replacement = FLAGS_PREIMAGE[:-len('\t\t\t\t);')] + additions + '\t\t\t\t);'
    for name, identity in CONFIGURATIONS.items():
        pattern = re.escape('\t\t' + identity + ' /* ' + name + ' */ = {\n') + r'.*?^\t\t};'
        matches = list(re.finditer(pattern, text, re.M | re.S))
        if len(matches) != 1 or matches[0].group().count(FLAGS_PREIMAGE) != 1:
            raise ValueError('exact SideStore linker configuration differs: ' + name)
        block = matches[0].group()
        if 'isa = XCBuildConfiguration;' not in block or '\t\t\tname = ' + name + ';' not in block:
            raise ValueError('SideStore configuration identity differs')
        text = text[:matches[0].start()] + block.replace(FLAGS_PREIMAGE, replacement, 1) + text[matches[0].end():]
    return text.encode()
