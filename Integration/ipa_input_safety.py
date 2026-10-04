#!/usr/bin/env python3
"""Snapshot IPA once before extraction; do not reread an external mutable source."""
from pathlib import Path
import hashlib
import sys

SOURCE = 'SideStore/Core/Operations/StandaloneOperations/DownloadAppOperation.swift'
EXPECTED = '99e33a7b94fb26707d81d3dab7d25e68254c93ad'


def patch(text):
    start = '    func downloadIPA(from sourceURL: URL) async throws -> ALTApplication {'
    end = '    func downloadFile(from downloadURL: URL) async throws -> URL {'
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError('IPA input boundaries changed')
    before, rest = text.split(start)
    _, after = rest.split(end, 1)
    return before + '''    func downloadIPA(from sourceURL: URL) async throws -> ALTApplication {
        if self.isCancelled { throw OperationError.cancelled }
        let fileURL: URL
        if sourceURL.isFileURL { fileURL = sourceURL }
        else { fileURL = try await downloadFile(from: sourceURL) }
        defer {
            if !sourceURL.isFileURL { try? FileManager.default.removeItem(at: fileURL) }
        }
        let input = self.context.temporaryDirectory.appendingPathComponent("App.ipa")
        // Create once. Validation, installation metadata and later cached IPA
        // all refer to these same bytes, never a second read of the source URL.
        try NativeIPAInput.snapshot(from: fileURL, to: input, external: sourceURL.isFileURL) {
            try Task.checkCancellation()
            if self.isCancelled { throw CancellationError() }
        }
        var accepted = false
        defer { if !accepted { try? FileManager.default.removeItem(at: input) } }
        try Task.checkCancellation()
        if self.isCancelled { throw OperationError.cancelled }
        try PrivateFileStore(root: self.temporaryDirectory).prepare()
        let appURL = try FileManager.default.unzipAppBundle(at: input, toDirectory: self.temporaryDirectory)
        guard let application = ALTApplication(fileURL: appURL) else { throw IPAInputFailure.unsafeFile }
        try Task.checkCancellation()
        if self.isCancelled { throw OperationError.cancelled }
        self.context.ipaURL = input
        self.setProgress(75)
        accepted = true
        return application
    }

''' + end + after


def apply(root):
    path = root / SOURCE
    raw = path.read_bytes()
    digest = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if digest != EXPECTED:
        raise ValueError('Unreviewed prepared IPA input source')
    path.write_text(patch(raw.decode()))


if __name__ == '__main__': apply(Path(sys.argv[1]))
