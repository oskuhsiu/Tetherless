#!/usr/bin/env python3
"""Bound ODA inputs and reject checksum failures before cache mutation."""
from pathlib import Path
import hashlib
import sys

SOURCE = 'Dependencies/SideSign/Sources/Anisette/AnisetteDataManager.swift'
EXPECTED = '8c6448563e030dd991daefec52c42fcf3dbc3a0d'
ROOT = Path(__file__).parents[1]


def once(text, old, new):
    if text.count(old) != 1: raise ValueError('Unreviewed ODA package anchor')
    return text.replace(old, new, 1)


def replace_body_prefix(text, start, end, body):
    if text.count(start) != 1: raise ValueError('Unreviewed ODA function')
    prefix, rest = text.split(start)
    if end not in rest: raise ValueError('Unreviewed ODA function boundary')
    _, tail = rest.split(end, 1)
    return prefix + start + '\n' + body + end + tail


def patch(text):
    text = once(text, '    private var isCaching: Bool = false',
                '    private let packageAdmission = AnisettePackageAdmission()')
    a = '    public func downloadAndCacheLibs(from oda: ODAInfo, targetDirectory: URL? = nil, clientInfo: String = Constants.Anisette.defaultClientInfo) async throws {'
    b = '        let tempZipURL ='
    text = replace_body_prefix(text, a, b, '''        try Task.checkCancellation()
        let admission = try packageAdmission.acquire()
        defer { admission.release() }
        let expected = try AnisettePackageInput.digest(oda.sha256)
        let zipData = try await resolveZipData(from: oda)
        try Task.checkCancellation()
        try AnisettePackageInput.verify(expected: expected, actual: computeSHA256(data: zipData))
        try Task.checkCancellation()
        // Neither cache directories nor archive staging are touched on mismatch.
        let libDir = targetDirectory ?? remoteLibsDir
        let prov = provisioningDir
        let fm = FileManager.default
        try fm.createDirectory(at: libDir, withIntermediateDirectories: true)
        try fm.createDirectory(at: prov, withIntermediateDirectories: true)

''')
    text = once(text, '        try fm.unzipArchive(at: tempZipURL, to: libDir)', '''        var limits = ArchiveLimits()
        limits.maximumArchiveBytes = UInt64(AnisettePackageInput.maximumArchiveBytes)
        limits.maximumExpandedBytes = 256 * 1024 * 1024
        limits.maximumFileBytes = 128 * 1024 * 1024
        limits.maximumEntries = 4096
        try Task.checkCancellation()
        try SafeArchive.extract(at: tempZipURL, toDirectory: libDir, limits: limits)
        try Task.checkCancellation()''')
    text = replace_body_prefix(text,
        '    private func resolveZipData(from oda: ODAInfo) async throws -> Data {',
        '    public func setupFromRemote(', '''        if let inline = oda.base64Payload {
            guard oda.url == nil else { throw AnisettePackageFailure.ambiguousPayload }
            return try AnisettePackageInput.decodeBase64(inline)
        }
        guard let raw = oda.url, raw.utf8.count <= 16_384, let url = URL(string: raw) else { throw AnisettePackageFailure.invalidPayload }
        let data = try await boundedODAPackageData(from: url, maximumBytes: AnisettePackageInput.maximumEncodedBytes)
        return try AnisettePackageInput.archive(from: data)
    }

''')
    text = replace_body_prefix(text,
        '    public func fetchServerList(from sourceURL: URL) async throws -> AnisetteServerData {',
        '        let decoder = JSONDecoder()',
        '        let data = try await boundedODAPackageData(from: sourceURL, maximumBytes: AnisettePackageInput.maximumMetadataBytes)\n\n')
    text = replace_body_prefix(text,
        '    public func fetchODAInfo(from serverSourceURL: URL, fallbackODAURL: URL? = nil) async throws -> ODAInfo {',
        '        let decoder = JSONDecoder()',
        '        let data = try await boundedODAPackageData(from: serverSourceURL, maximumBytes: AnisettePackageInput.maximumMetadataBytes)\n\n')
    text = replace_body_prefix(text,
        '    private func fetchODAData(from url: URL) async throws -> ODAInfo {',
        '    public func downloadAndCacheLibs(', '''        let data = try await boundedODAPackageData(from: url, maximumBytes: AnisettePackageInput.maximumMetadataBytes)
        return try JSONDecoder().decode(ODAInfo.self, from: data)
    }

''')
    return text


def apply(root):
    source = root / SOURCE
    raw = source.read_bytes()
    if hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() != EXPECTED:
        raise ValueError('Unreviewed Anisette package source')
    # The existing downloader is copied with only its type namespace changed.
    # Tests exercise its real URLSession callbacks in the core test suite.
    outputs = {
        source: patch(raw.decode()),
        source.parent / 'TetherlessAnisettePackageInput.swift': (ROOT/'Sources/TetherlessCore/AnisettePackageInput.swift').read_text(),
        source.parent / 'TetherlessAnisetteHTTPDownload.swift': (ROOT/'Sources/TetherlessCore/HTTPDownload.swift').read_text().replace('HTTPDownload', 'ODAHTTPDownload'),
        source.parent / 'TetherlessAnisetteTransfer.swift': (ROOT/'Integration/Overrides/AnisettePackageTransfer.swift').read_text(),
    }
    for path in outputs:
        if path != source and path.exists(): raise ValueError('Unexpected ODA generated destination')
    for path, content in outputs.items(): path.write_text(content)


if __name__ == '__main__': apply(Path(sys.argv[1]))
