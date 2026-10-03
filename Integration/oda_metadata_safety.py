#!/usr/bin/env python3
"""Bound and validate ODA JSON before any native decoder or fallback choice."""
from pathlib import Path
import hashlib
import sys

ROOT = Path(__file__).parents[1]
SOURCE = 'Dependencies/SideSign/Sources/Anisette/AnisetteDataManager.swift'
EXPECTED = 'df58f374bd41fc901ee5ed265429f765d33fee09'


def patch(text):
    start = '    public func fetchServerList(from sourceURL: URL) async throws -> AnisetteServerData {'
    end = '    public func downloadAndCacheLibs('
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError('Unreviewed ODA metadata boundaries')
    prefix, rest = text.split(start)
    _, suffix = rest.split(end, 1)
    return prefix + '''    public func fetchServerList(from sourceURL: URL) async throws -> AnisetteServerData {
        let data = try await boundedODAPackageData(from: sourceURL, maximumBytes: AnisettePackageInput.maximumMetadataBytes)
        return try ValidatedODAMetadata.servers(data, source: sourceURL)
    }

    public func fetchODAInfo(from serverSourceURL: URL, fallbackODAURL: URL? = nil) async throws -> ODAInfo {
        let data = try await boundedODAPackageData(from: serverSourceURL, maximumBytes: AnisettePackageInput.maximumMetadataBytes)
        switch try ValidatedODAMetadata.select(data, source: serverSourceURL, fallback: fallbackODAURL) {
        case .package(let package): return package
        case .reference(let url): return try await fetchODAData(from: url)
        }
    }

    private func fetchODAData(from url: URL) async throws -> ODAInfo {
        let data = try await boundedODAPackageData(from: url, maximumBytes: AnisettePackageInput.maximumMetadataBytes)
        return try ValidatedODAMetadata.package(data)
    }

''' + end + suffix


def apply(root):
    source = root / SOURCE
    raw = source.read_bytes()
    if hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() != EXPECTED:
        raise ValueError('Unreviewed prepared ODA metadata input')
    outputs = {
        source: patch(raw.decode()),
        source.parent / 'TetherlessODAMetadata.swift': (ROOT/'Sources/TetherlessCore/ODAMetadata.swift').read_text(),
        source.parent / 'ValidatedODAMetadata.swift': (ROOT/'Integration/Overrides/ValidatedODAMetadata.swift').read_text(),
    }
    # Validate all destinations before the first write; no partial replacement on drift.
    for path in outputs:
        if path != source and path.exists(): raise ValueError('Unexpected metadata destination')
    for path, text in outputs.items(): path.write_text(text)

if __name__ == '__main__': apply(Path(sys.argv[1]))
