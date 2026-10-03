#!/usr/bin/env python3
"""Post-archive, hash-locked native HTTP download and dependency boundary."""
from pathlib import Path
import hashlib
import sys
import subprocess

DOWNLOAD = 'SideStore/Core/Operations/StandaloneOperations/DownloadAppOperation.swift'

def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Network patch anchor changed')
    return source.replace(old, new, 1)

def patch_download(source):
    source = once(source, '    private let session = URLSession(configuration: .default)',
                         '    private let boundedDownload = BoundedHTTPDownload()')
    source = once(source, '    private var activeDownloadTask: URLSessionDownloadTask?\n', '')
    source = once(source, '        self.activeDownloadTask?.cancel()', '        self.boundedDownload.cancel()')
    source = once(source, 'guard let sourceURL = self.sourceURL else {', 'guard let sourceURL = app.url else {')
    start = '    func downloadFile(from downloadURL: URL) async throws -> URL {'
    if source.count(start) != 1:
        raise ValueError('Download boundary changed')
    # No private legacy delegate/dependency downloader remains reachable.
    return source.split(start)[0] + '''    func downloadFile(from downloadURL: URL) async throws -> URL {
        if self.isCancelled { throw OperationError.cancelled }
        let store = try PrivateFileStore(root: self.temporaryDirectory)
        try store.prepare()
        let fileURL = try await boundedDownload.download(from: downloadURL, into: store.root)
        if self.isCancelled {
            try? FileManager.default.removeItem(at: fileURL)
            throw OperationError.cancelled
        }
        self.setProgress(75)
        return fileURL
    }

    private func downloadDependencies(for appBundle: ALTApplication) async throws -> Set<URL> {
        guard let data = try PrivateFileStore.readExternal(appBundle.bundle.altstorePlistURL, maximum: 262_144) else { return [] }
        try DependencyManifestPolicy.validate(data)
        return []
    }
}
'''

# Input is the exact pinned upstream file AFTER archive_safety.patch_download.
BLOBS = {DOWNLOAD: '11693de2c9bb14b02b8ef4a520ae9113b8851eaf'}

def apply(root: Path):
    for path, expected in BLOBS.items():
        file = root / path
        raw = file.read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != expected:
            raise ValueError('Unreviewed prepared network source: ' + path)
        file.write_text(patch_download(raw.decode()))
    subprocess.run([sys.executable, str(Path(__file__).with_name("auth_safety.py")), str(root)], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name("manager_update.py")), str(root)], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name("certificate_safety.py")), str(root)], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name("certificate_issuance.py")), str(root)], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name("onboarding.py")), str(root)], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name("launch_safety.py")), str(root)], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name("catalog_safety.py")), str(root)], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name("authentication_privacy.py")), str(root)], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name("anisette_package_safety.py")), str(root)], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name("anisette_identity_safety.py")), str(root)], check=True)

if __name__ == '__main__': apply(Path(sys.argv[1]))
