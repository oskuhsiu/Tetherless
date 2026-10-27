#!/usr/bin/env python3
"""Replace split Anisette state with the verified native identity transaction."""
from pathlib import Path
import hashlib
import sys

CONFIG = 'SideStore/Core/Anisette/AnisetteConfigManager.swift'
DEVICE = 'SideStore/Core/Anisette/OnDeviceAnisetteManager.swift'
REMOTE = 'SideStore/Core/Anisette/AnisetteProvider.swift'
KEYCHAIN = 'AltStore/Core/Components/Keychain.swift'
BLOBS = {
    CONFIG: '161f608c43ec40b30f390a7e245c143796e5e2a0',
    DEVICE: '03cc650766360eb6512f2a4543c2f288b2399d11',
    REMOTE: 'bd628606d3808209159b29d5f3650118b9739401',
    KEYCHAIN: '3727e01a3a25f337fdc9826f5634db671cd65adb',
}


def once(text, old, new):
    if text.count(old) != 1: raise ValueError('Unreviewed Anisette identity anchor')
    return text.replace(old, new, 1)


def patch_config(text):
    a = '    public nonisolated var anisetteIdentifier: String? {'
    b = '    private nonisolated var configFileURL: URL {'
    if text.count(a) != 1 or text.count(b) != 1: raise ValueError('Unreviewed identity accessors')
    prefix, rest = text.split(a)
    _, tail = rest.split(b, 1)
    return prefix + '    // Identity/blob storage belongs to NativeAnisetteIdentity, not config setters.\n\n' + b + tail


def patch_device(text):
    a = '    public func fetchAnisetteData() async throws -> ALTAnisetteData {'
    if text.count(a) != 1: raise ValueError('Unreviewed device provider')
    prefix, rest = text.split(a)
    if not rest.rstrip().endswith('    }\n}'): raise ValueError('Unreviewed device provider tail')
    return prefix + a + '''
        return try await NativeAnisetteIdentity.withIdentity { identity in
            guard let identifier = identity.identifier else { throw AnisetteIdentityFailure.invalidRecord }
            let headers = await AnisetteConfigManager.shared.makeRequestHeaders()
            let sourceURLString = UserDefaults.standard.menuAnisetteList.isEmpty
                ? AnisetteServersManager.defaultSource : UserDefaults.standard.menuAnisetteList
            let sourceURL = URL(string: sourceURLString) ?? AppConstants.Anisette.defaultODAMetadataURL
            let mode = AnisetteMode.remoteODA(sourceURL: sourceURL,
                fallbackURL: AppConstants.Anisette.defaultODAMetadataURL)
            // The transaction saves and reads back a returned blob before
            // exposing headers. Storage failure cannot become provisioning success.
            return try await self.provider.fetchAnisetteData(mode: mode,
                identifier: identifier, existingAdiBlob: identity.blob, headers: headers)
        }
    }
}
'''


def patch_remote(text):
    a = '    private static func fetchRemote(handler: AnisetteServerHandler? = nil) async throws -> ALTAnisetteData {'
    text = once(text, a, a + '\n        return try await NativeAnisetteIdentity.withIdentity { identity in')
    text = once(text, '''        let existingBlob = AnisetteConfigManager.shared.anisetteAdiBlob.flatMap { Data(base64Encoded: $0) }
        let identifier = await AnisetteConfigManager.shared.resolveDeviceIdentifier()''', '''        let existingBlob = identity.blob
        guard let identifier = identity.identifier else { throw AnisetteIdentityFailure.invalidRecord }''')
    text = once(text, '''                debugLog("[AnisetteProvider] Successfully fetched Anisette data from \\(successfulServer.absoluteString)")
''', '')
    return once(text, '''        if let freshBlob = newAdiBlob {
            AnisetteConfigManager.shared.anisetteAdiBlob = freshBlob.base64EncodedString()
        }

        return anisetteData
    }
}''', '''        return (anisetteData, newAdiBlob)
        }
    }
}''')


def patch_keychain(text):
    text = once(text, '''    @KeychainItem(key: "identifier")
    public var identifier: String?
    
    @KeychainItem(key: "adiPb")
    public var adiPb: String?
''', '''    // Legacy Anisette fields are read/removed only by checked migration below.
''')
    text = once(text, '''        var keys = ["appleIDEmailAddress", "appleIDPassword", "appleIDAdsid", "appleIDXcodeToken"]
        if !keepAnisetteData { keys.append("adiPb") }''', '''        if !keepAnisetteData { try NativeAnisetteIdentity.reset(keepingIdentifier: true) }
        let keys = ["appleIDEmailAddress", "appleIDPassword", "appleIDAdsid", "appleIDXcodeToken"]''')
    text = once(text, '''    func clearAllVerified() throws {
        try self.keychain.removeAll()''', '''    func clearAllVerified() throws {
        try NativeAnisetteIdentity.reset(keepingIdentifier: false)
        try self.keychain.removeAll()''')
    a = '    public func clearSignInInfo(keepAnisetteData: Bool = true)'
    b = '// Read/write failures propagate.'
    if text.count(a) != 1 or text.count(b) != 1: raise ValueError('Unreviewed legacy cleanup')
    prefix, rest = text.split(a)
    _, tail = rest.split(b, 1)
    text = prefix + '''    public func clearSignInInfo(keepAnisetteData: Bool = true) throws {
        try NativeMutationGate.withSynchronousLease {
            try removeLegacyAuthentication(keepAnisetteData: keepAnisetteData)
        }
    }
    public func clearAll() throws {
        try NativeMutationGate.withSynchronousLease { try clearAllVerified() }
    }

    func readLegacyAnisetteVerified() throws -> LegacyAnisetteIdentity {
        func string(_ key: String, maximum: Int) throws -> String? {
            guard let data = try keychain.getData(key) else { return nil }
            guard !data.isEmpty, data.count <= maximum,
                  let value = String(data: data, encoding: .utf8) else {
                throw AnisetteIdentityFailure.invalidRecord
            }
            return value
        }
        return try LegacyAnisetteIdentity(identifier: string("identifier", maximum: 36),
            blob: string("adiPb", maximum: 43_692))
    }
    func removeLegacyAnisetteVerified() throws {
        try removeVerified(["identifier", "adiPb"])
    }
}

''' + b + tail
    return text


TRANSFORMS = {CONFIG: patch_config, DEVICE: patch_device, REMOTE: patch_remote, KEYCHAIN: patch_keychain}


def apply(root):
    originals = {}
    # Validate every input and transformation before modifying any source.
    for path, expected in BLOBS.items():
        raw = (root/path).read_bytes()
        actual = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if actual != expected: raise ValueError('Unreviewed Anisette identity source: '+path)
        originals[path] = raw.decode()
    outputs = {path: TRANSFORMS[path](text) for path, text in originals.items()}
    for path, text in outputs.items(): (root/path).write_text(text)


if __name__ == '__main__': apply(Path(sys.argv[1]))
