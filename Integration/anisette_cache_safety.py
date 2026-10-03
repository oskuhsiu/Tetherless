#!/usr/bin/env python3
"""Seal ODA cache generations before publication and verify before each client."""
from pathlib import Path
import hashlib
import sys

SOURCE = 'Dependencies/SideSign/Sources/Anisette/AnisetteDataManager.swift'
EXPECTED = 'd83b936e437177ba16b9664007f6a99ce7b86a2b'
ROOT = Path(__file__).parents[1]


def once(text, old, new):
    if text.count(old) != 1: raise ValueError('Unreviewed ODA cache anchor')
    return text.replace(old, new, 1)


def method(text, start, end, body):
    if text.count(start) != 1 or text.count(end) != 1: raise ValueError('Unreviewed ODA cache method')
    before, rest = text.split(start)
    _, after = rest.split(end, 1)
    return before + start + body + end + after


def patch(text):
    text = once(text, '    private var localProvider: AnisetteClient?\n', '')
    text = once(text, 'private func getClient(for mode: AnisetteMode, clientInfo: String) async throws -> AnisetteClient',
                'private func getClient(for mode: AnisetteMode, clientInfo: String) async throws -> any AnisetteClientProtocol')
    text = once(text, '        AnisetteClient.validateLibrariesExist(at: directory)',
                '        (try? AnisetteLibraryCache(directory: directory, requiredLibraries: Constants.Anisette.Libraries.requiredNames).current()) != nil')
    text = method(text, '    public var libsDir: URL {', '    public static func validateServer(', '''
        // Public location is informational. Every provider below revalidates it.
        (try? verifiedLibraries()) ?? remoteLibsDir
    }

    private func libraryCache(at directory: URL) throws -> AnisetteLibraryCache {
        try AnisetteLibraryCache(directory: directory, requiredLibraries: Constants.Anisette.Libraries.requiredNames)
    }

    private func verifiedLibraries() throws -> URL? {
        if let local = try libraryCache(at: localLibsDir).current() { return local }
        return try libraryCache(at: remoteLibsDir).current()
    }

    private func pinLibraries() throws -> AnisetteLibraryCache.PinnedGeneration? {
        // Only manager-owned slots are eligible for automatic reclamation.
        try libraryCache(at: localLibsDir).pruneUnused()
        try libraryCache(at: remoteLibsDir).pruneUnused()
        if let local = try libraryCache(at: localLibsDir).pinCurrent() { return local }
        return try libraryCache(at: remoteLibsDir).pinCurrent()
    }

    public func isReady() -> Bool { (try? verifiedLibraries()) != nil }

''')
    text = once(text, '        case .localODA(let libDir, let prov):\n', '''        case .localODA(let libDir, let prov):
            guard let pinned = try libraryCache(at: libDir).pinCurrent() else {
                throw AnisetteLibraryCacheFailure.missingLibraries
            }
''')
    text = once(text, '            let targetProvDir = prov ?? provisioningDir\n            try FileManager.default.createDirectory(at: targetProvDir, withIntermediateDirectories: true)\n            return try AnisetteClient(',
                '            let targetProvDir = prov ?? provisioningDir\n            try FileManager.default.createDirectory(at: targetProvDir, withIntermediateDirectories: true)\n            let client = try AnisetteClient(')
    # Only the pre-download local provider still has this exact resolver.
    text = once(text, '                libraryDirectoryResolver: { libDir }\n            )\n\n        case .remoteODA',
                '                libraryDirectoryResolver: { pinned.directory }\n            )\n            return LibraryPinnedAnisetteClient(client: client, generation: pinned)\n\n        case .remoteODA')
    text = once(text, '''            try FileManager.default.createDirectory(at: libsDir, withIntermediateDirectories: true)
            try FileManager.default.createDirectory(at: provisioningDir, withIntermediateDirectories: true)
            if !AnisetteClient.validateLibrariesExist(at: libsDir, requiredLibraries: Constants.Anisette.Libraries.requiredNames) {''', '''            if try verifiedLibraries() == nil {''')
    a = '        // Neither cache directories nor archive staging are touched on mismatch.'
    b = '    private func resolveZipData('
    text = method(text, a, b, '''
        let libDir = targetDirectory ?? remoteLibsDir
        // This API publishes only manager-owned slots, not arbitrary user paths.
        guard [localLibsDir.standardizedFileURL, remoteLibsDir.standardizedFileURL].contains(libDir.standardizedFileURL) else {
            throw AnisetteLibraryCacheFailure.unsafeFile
        }
        let fm = FileManager.default
        try fm.createDirectory(at: baseAnisetteDirectory, withIntermediateDirectories: true)
        let base = try baseAnisetteDirectory.resourceValues(forKeys: [.isSymbolicLinkKey, .isDirectoryKey])
        guard base.isDirectory == true, base.isSymbolicLink != true else { throw AnisetteLibraryCacheFailure.unsafeFile }
        try libraryCache(at: libDir).install(archive: zipData, expectedSHA256: expected) { archive, staging in
            var limits = ArchiveLimits()
            limits.maximumArchiveBytes = UInt64(AnisettePackageInput.maximumArchiveBytes)
            limits.maximumExpandedBytes = 256 * 1024 * 1024
            limits.maximumFileBytes = 128 * 1024 * 1024
            limits.maximumEntries = 4096
            try Task.checkCancellation()
            try SafeArchive.extract(at: archive, toDirectory: staging, limits: limits)
            try Task.checkCancellation()
        }
        // No client is cached across generations. Loading always verifies again.
    }

''')
    text = method(text, '    public func setupFromRemote(', '    private func computeSHA256(', '''serverSourceURL: URL, fallbackODAURL: URL? = nil, force: Bool = false, clientInfo: String = Constants.Anisette.defaultClientInfo) async throws {
        if !force, try libraryCache(at: remoteLibsDir).current() != nil { return }
        let odaInfo = try await fetchODAInfo(from: serverSourceURL, fallbackODAURL: fallbackODAURL)
        try await downloadAndCacheLibs(from: odaInfo, targetDirectory: remoteLibsDir, clientInfo: clientInfo)
    }

    public func ensureProviderLoaded(clientInfo: String = Constants.Anisette.defaultClientInfo) async throws -> any AnisetteClientProtocol {
        try Task.checkCancellation()
        guard let pinned = try pinLibraries() else { throw AnisetteLibraryCacheFailure.missingLibraries }
        try FileManager.default.createDirectory(at: provisioningDir, withIntermediateDirectories: true)
        let client = try AnisetteClient(provisioningDir: provisioningDir, clientInfo: clientInfo,
            userAgent: Constants.Anisette.defaultUserAgent, lookupURL: Constants.Anisette.URLs.grandSlamLookup,
            requiredLibraries: Constants.Anisette.Libraries.requiredNames, libraryDirectoryResolver: { pinned.directory })
        return LibraryPinnedAnisetteClient(client: client, generation: pinned)
    }

''')
    return text


def apply(root):
    path = root / SOURCE
    raw = path.read_bytes()
    if hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest() != EXPECTED:
        raise ValueError('Unreviewed ODA cache input')
    outputs = {path: patch(raw.decode())}
    for name in ['AnisetteLibraryCache', 'PrivateFileStore', 'LibraryCacheMaintenance']:
        target = path.parent / ('Tetherless' + name + '.swift')
        if target.exists(): raise ValueError('Unexpected generated cache destination')
        outputs[target] = (ROOT/'Sources/TetherlessCore'/ (name + '.swift')).read_text()
    wrapper = path.parent / 'LibraryPinnedAnisetteClient.swift'
    if wrapper.exists(): raise ValueError('Unexpected generated client destination')
    outputs[wrapper] = (ROOT/'Integration/Overrides/LibraryPinnedAnisetteClient.swift').read_text()
    for target, text in outputs.items(): target.write_text(text)

if __name__ == '__main__': apply(Path(sys.argv[1]))
