#!/usr/bin/env python3
"""Narrow, hash-locked distribution and signing-material hardening."""
from __future__ import annotations
import hashlib
from pathlib import Path
import plistlib
import sys

APP_ID = 'org.tetherless.Tetherless'
BUILD = 'Build.xcconfig'
BUNDLE = 'Shared/Extensions/Bundle+AltStore.swift'
STORE = 'AltStore/Core/Model/StoreApp.swift'
EMBED = 'SideStore/Core/Operations/PipelineOperations/EmbedSigningCertOperation.swift'
RESIGN = 'SideStore/Core/Operations/PipelineOperations/ResignAppOperation.swift'
CERT = 'SideStore/Core/Certificates/CertificateManager.swift'
ROUTER = 'SideStore/DeepLinks/URLHandler.swift'
BACKUP = 'SideStore/Core/Operations/PipelineOperations/PerformBackupRestoreOperation.swift'


def once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError('Hardening anchor changed; review the pinned source')
    return source.replace(old, new, 1)


def replace_between(source: str, start: str, end: str, replacement: str) -> str:
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError('Hardening boundary changed')
    before, rest = source.split(start)
    _, after = rest.split(end)
    return before + replacement + end + after


def patch_build(source: str) -> str:
    source = once(source, 'BASE_BUNDLE_ID                                  = $(ORG_IDENTIFIER).SideStore',
                         'BASE_BUNDLE_ID                                  = ' + APP_ID)
    # Keep internal target/module names unchanged; only the product identity changes.
    source = once(source, 'MARKETING_VERSION = 0.7.0', 'MARKETING_VERSION = 0.1.0')
    return once(source, 'CURRENT_PROJECT_VERSION = 0700', 'CURRENT_PROJECT_VERSION = 0100')


def patch_bundle(source: str) -> str:
    for symbol in ('storeAppBundleIdentifier', 'appbundleIdentifier'):
        source = once(source, f'static let {symbol} = "com.SideStore.SideStore"',
                             f'static let {symbol} = "{APP_ID}"')
    return source


def patch_store(source: str) -> str:
    source = once(source, 'let placeholderDownloadURL = AppConstants.Sources.sideStoreWebsite',
                         'let placeholderDownloadURL = URL(string: "https://github.com/oskuhsiu/Tetherless/releases")!')
    source = once(source, '        app.name = "SideStore"', '        app.name = "Tetherless"')
    source = once(source, '        app.developerName = "Side Team"', '        app.developerName = "Tetherless contributors"')
    return once(source, '        app.localizedDescription = "SideStore is an alternative App Store."',
                       '        app.localizedDescription = "Independent on-device sideloading and proactive renewal, based on SideStore."')


def patch_embed(source: str) -> str:
    start = 'final class EmbedSigningCertOperation:'
    if source.count(start) != 1:
        raise ValueError('Embed operation declaration changed')
    prefix = source.split(start)[0]
    return prefix + '''// Tetherless: never hand a signing private key to an installed app.
final class EmbedSigningCertOperation: BasePipelineOperation<InstallAppOperationContext, Void>, @unchecked Sendable {
    override func execute(parentProgress: Progress?) async throws {
        try await super.executePreconditionCheck(parentProgress: parentProgress)
        guard let certificate = self.context.targetSigningCertificate,
              let data = certificate.data, let app = self.context.targetAppBundle else {
            throw OperationError.invalidParameters("Missing public signing certificate or app bundle.")
        }
        try PublicSigningMaterial.writeCertificate(data, into: app.fileURL)
        self.setProgress(100)
    }
}
'''


def patch_resign(source: str) -> str:
    start = '        if targetAppBundle.isAltStoreApp {\n'
    end = '        // Prepare app\n'
    replacement = '''        if targetAppBundle.isAltStoreApp {
            guard let certificate = self.context.targetSigningCertificate,
                  let data = certificate.data else {
                throw OperationError.invalidParameters("Missing manager signing identity.")
            }
            additionalValues[Bundle.Info.certificateID] = certificate.serialNumber
            try PublicSigningMaterial.writeCertificate(data, into: appBundle.fileURL)
        }

'''
    return replace_between(source, start, end, replacement)


def patch_certificates(source: str) -> str:
    source = once(source, '''        if let cert = loadEmbeddedCertificate(for: serialNumber, fallbackPassword: fallbackPassword) {
            return cert
        }
''', '''        // Tetherless does not recover private keys from app bundle resources.
        // The authorized signing identity must be present in its own Keychain.
''')
    return replace_between(source, '    private func loadEmbeddedCertificate(for serialNumber:',
                           '    // Reads the Mach-O binary contents', '')


def patch_router(source: str) -> str:
    # No URL-triggered certificate/pairing export surface in this product.
    source = replace_between(source, '        case "pairing":\n', '        default:\n            return false\n',
                             '        case "pairing", "certificate":\n            return false\n\n')
    marker = '        guard let host = components.host?.lowercased() else {'
    source = once(source, marker, '''        guard let scheme = components.scheme?.lowercased(),
              scheme == "tetherless" || scheme == "sidestore-" + Bundle.Info.activeBundleIdentifier.lowercased() else {
            return false
        }
''' + marker)
    # Incoming URLs may contain credential-shaped query values. Do not log them.
    return '\n'.join(line for line in source.split('\n') if 'debugLog(' not in line)


PATCHES = {
    BUILD: patch_build, BUNDLE: patch_bundle, STORE: patch_store,
    EMBED: patch_embed, RESIGN: patch_resign, CERT: patch_certificates,
    ROUTER: patch_router,
    BACKUP: lambda s: once(s, 'URL(string: "sidestore://")', 'URL(string: "tetherless://")'),
}
# Filled from the exact review snapshot; changed upstream content must fail closed.
BLOBS = {
    'Build.xcconfig': '3fd3b5c99379480a6ac6b25b14a1691e823f92d3',
    'Shared/Extensions/Bundle+AltStore.swift': '83062c7569390d40e7a2f69f8cbeb9ff544bd559',
    'AltStore/Core/Model/StoreApp.swift': 'd042f841e627e18498bfb1303284a0d7556c7742',
    'SideStore/Core/Operations/PipelineOperations/EmbedSigningCertOperation.swift': '9ca401f2d00d1de519b0d05991d89984c025980c',
    'SideStore/Core/Operations/PipelineOperations/ResignAppOperation.swift': '970338f82686df14d9cc42f7c069c3fb98b3b46b',
    'SideStore/Core/Certificates/CertificateManager.swift': 'c4bdf6f97d6835cba83aa4d798f5821dcad6f1e3',
    'SideStore/DeepLinks/URLHandler.swift': 'a21e2450a3a797b705905dcc53cfc594aaff0a80',
    'SideStore/Core/Operations/PipelineOperations/PerformBackupRestoreOperation.swift': 'b6f13cb9202a61771d35d7df2f61dfcf6e7723c7',
}


def harden(root: Path) -> None:
    outputs = {}
    for relative, patch in PATCHES.items():
        path = root / relative
        raw = path.read_bytes()
        digest = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if digest != BLOBS[relative]:
            raise ValueError(f'Unreviewed hardening input: {relative}')
        outputs[path] = patch(raw.decode())
    info_path = root / 'AltStore/Info.plist'
    info = plistlib.loads(info_path.read_bytes())
    for item in info.get('CFBundleURLTypes', []):
        item['CFBundleURLName'] = item.get('CFBundleURLName', '').replace('SideStore', 'Tetherless')
        item['CFBundleURLSchemes'] = ['tetherless' if s == 'sidestore' else s for s in item.get('CFBundleURLSchemes', [])]
    info['LSApplicationQueriesSchemes'] = ['tetherless', 'sidestore-$(PRODUCT_BUNDLE_IDENTIFIER)', 'localdevvpn']
    # Network APIs must use TLS except explicitly local-network communication.
    info['NSAppTransportSecurity'] = {'NSAllowsLocalNetworking': True}
    for path, source in outputs.items():
        path.write_text(source)
    info_path.write_bytes(plistlib.dumps(info, sort_keys=False))


if __name__ == '__main__':
    harden(Path(sys.argv[1]))
