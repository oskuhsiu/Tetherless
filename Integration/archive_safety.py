#!/usr/bin/env python3
"""Route every shared SideSign unzip consumer through bounded streaming IO."""
from pathlib import Path
import hashlib
import sys
import shutil
import subprocess

ZIP = 'Dependencies/SideSign/Sources/Archiver/FileManagerZip.swift'
PACKAGE = 'Dependencies/SideSign/Package.swift'
DOWNLOAD = 'SideStore/Core/Operations/StandaloneOperations/DownloadAppOperation.swift'


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Archive hardening anchor changed')
    return source.replace(old, new, 1)


def patch_zip(source):
    start = '    public func unzipArchive('
    end = '    public struct CompressionLevel:'
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError('Archiver boundaries changed')
    before, tail = source.split(start)
    _, after = tail.split(end)
    return before + '''    // Extraction deliberately has no legacy/unsafe fallback.
    public func unzipArchive(at archiveURL: URL, to directoryURL: URL, progress: Progress? = nil) throws {
        try SafeArchive.extract(at: archiveURL, toDirectory: directoryURL, progress: progress)
    }
    public func unzipAppBundle(at ipaURL: URL, to directoryURL: URL) throws -> URL {
        try SafeArchive.extractIPA(at: ipaURL, toDirectory: directoryURL)
    }
    public func unzipAppBundle(at ipaURL: URL, toDirectory directoryURL: URL) throws -> URL {
        try SafeArchive.extractIPA(at: ipaURL, toDirectory: directoryURL)
    }

''' + end + after


def patch_package(source):
    source = once(source, '\n    dependencies: [\n', '''
    dependencies: [
        .package(url: "https://github.com/weichsel/ZIPFoundation.git", exact: "0.9.20"),
''')
    return once(source, '                .product(name: "libdeflate", package: "libdeflate"),', '''                .product(name: "libdeflate", package: "libdeflate"),
                .product(name: "ZIPFoundation", package: "ZIPFoundation"),''')


def patch_download(source):
    start = '        if resourceValues.isDirectory == true {'
    end = '            // File, so assuming this is a .ipa file.'
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError('Directory-import boundaries changed')
    before, tail = source.split(start)
    _, after = tail.split(end)
    return before + '''        if resourceValues.isDirectory == true {
            // Do not let folder imports bypass the adversarial archive checks.
            throw OperationError.invalidParameters("Import an IPA, not an unpacked .app directory.")
        } else {
''' + end + after

PATCHES = {ZIP: patch_zip, PACKAGE: patch_package, DOWNLOAD: patch_download}
BLOBS = {'Dependencies/SideSign/Sources/Archiver/FileManagerZip.swift': '46c4c8912be1e37fa7c07a26deba811f8b4f9f10', 'Dependencies/SideSign/Package.swift': '89695b66f505dbe453ff6ff4b953e99d05119fd4', 'SideStore/Core/Operations/StandaloneOperations/DownloadAppOperation.swift': 'e273a1cad424244968df6fa7c0dee8cc4d8f456d'}


def apply(root: Path):
    outputs = {}
    for path, patch in PATCHES.items():
        raw = (root / path).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != BLOBS[path]:
            raise ValueError('Unreviewed archive source: ' + path)
        outputs[root / path] = patch(raw.decode())
    for path, content in outputs.items():
        path.write_text(content)
    # Identical production sources are compiled in the standalone integration
    # tests and SideSign. No duplicate decompressor or test-only extractor.
    sources = Path(__file__).parents[1] / 'Packages/TetherlessArchive/Sources/TetherlessArchive'
    for path in sources.glob('*.swift'):
        shutil.copyfile(path, root / 'Dependencies/SideSign/Sources/Archiver' / path.name)
    subprocess.run([sys.executable, str(Path(__file__).with_name("network_safety.py")), str(root)], check=True)

if __name__ == '__main__': apply(Path(sys.argv[1]))
