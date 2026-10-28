#!/usr/bin/env python3
"""Explicit single-certificate quota consent and protected user exports."""
from pathlib import Path
import hashlib
import shutil
import sys
ROOT = Path(__file__).parent
HANDLER = 'SideStore/Handlers/SignInFlowHandler.swift'
EXPORTER = 'SideStore/Views/Settings/Advanced/Certificates/CertificateExporter.swift'
ROW = 'SideStore/Views/Settings/Advanced/Certificates/CertificateRowView.swift'
VIEW = 'SideStore/Views/Settings/Advanced/Certificates/CertificatesView.swift'
DETAIL = 'SideStore/Views/Settings/Advanced/Certificates/CertificateDetailView.swift'
BLOBS = {HANDLER: 'c8d2ef028c0b8f3744d47854f3e50d6b2207d19f', EXPORTER: '038c03567182fec0693034a3022171ebddfa233f',
         DETAIL: '3c7835d5abf9e68d8b1b60bcfc36a46dc86a06d4', ROW: 'b671c5d98c9306018e72d8db28b299eda91002ac', VIEW: '99e5a8dfe1dc5367767f80cfdc51c4697ee5ee3e'}

def once(source, old, new):
    if source.count(old) != 1: raise ValueError('Certificate lifecycle anchor changed: ' + old[:60])
    return source.replace(old, new, 1)

def patch_handler(source):
    start = '    @MainActor\n    func resolveRevocation('
    end = '    @MainActor\n    func resolveTeam('
    if source.count(start) != 1 or source.count(end) != 1: raise ValueError('Quota handler boundaries changed')
    a, tail = source.split(start)
    _, b = tail.split(end)
    return a + '''    @MainActor
    func resolveRevocation(certificates: [ALTX509Certificate], teamType: ALTTeamType) async throws -> RevokeDecision {
        #if os(iOS)
        guard let presenter = activePresenter, let teamID = try NativeAuthenticationStore.ready().teamID else { throw CancellationError() }
        return try await NativeCertificateQuotaPrompt.choose(certificates: certificates, teamID: teamID, presenter: presenter)
        #else
        return .keepExisting
        #endif
    }

''' + end + b

def patch_exporter(source):
    # Legacy public export remains available; private exports route through the
    # checked encrypted builder and an activity controller with bounded lifetime.
    start = '    static func shareP12('
    end = '    static func sharePrivateKeyAsPEM('
    a, tail = source.split(start); _, b = tail.split(end)
    source = a + '''    static func shareP12(_ cert: ALTCertificate, password: String, onShare: ((URL) -> Void)? = nil, onError: @escaping (String) -> Void) {
        onError("Use Auto Renewal → Signing material to save an encrypted P12 and matching profiles. No private key was exported here.")
    }

''' + end + b
    # No remaining caller should expose a bare key; remove the implementations
    # too rather than relying only on hiding a menu.
    a, tail = source.split('    static func sharePrivateKeyAsPEM(')
    _, b = tail.split('    private static func share(data:')
    return a + '    private static func share(data:' + b

def patch_row(source):
    start = '            if let signable = viewModel.getSignableCertificate(for: cert.serialNumber) {'
    a, tail = source.split(start, 1)
    block, b = tail.split('            Divider()', 1)
    if 'CertificateExporter.copyPrivateKey' not in block: raise ValueError('Private export menu changed')
    return a + '            Text("Use encrypted P12 export to back up the private key.")\n\n            Divider()' + b

def patch_view(source):
    source = once(source, '                    CertificateExporter.shareP12(signable, password: exportPasswordInput, onShare: { viewModel.shareURL = $0 }) { viewModel.errorMessage = $0 }',
                  '                    CertificateExporter.shareP12(signable, password: exportPasswordInput, onShare: { viewModel.shareURL = $0 }) { viewModel.errorMessage = $0 }\n                    exportPasswordInput = ""')
    # Match only the export prompt Cancel, not every cancellation in this view.
    return once(source, '''            SwiftUI.Button("Cancel", role: .cancel) {}
        } message: {
            Text("Set a password to encrypt the exported .p12 certificate file.")''', '''            SwiftUI.Button("Cancel", role: .cancel) { exportPasswordInput = "" }
        } message: {
            Text("Use a new password of at least 12 characters. Keep it separately; anyone with the P12 and password can sign with this identity.")''')

def patch_detail(source):
    start = '                if let privateKey = signableCert?.privateKey {'
    end = '                if let certData = certificate.data {'
    if source.count(start) != 1: raise ValueError('Private key display changed')
    a, tail = source.split(start)
    _, b = tail.split(end, 1)
    return a + '                Text("Back up signing material with an encrypted P12; private keys are not displayed or copied to the clipboard.")\n\n' + end + b

PATCHES = {HANDLER: patch_handler, EXPORTER: patch_exporter, ROW: patch_row, VIEW: patch_view, DETAIL: patch_detail}
def package_crypto(root):
    source = root / 'SideStore/TetherlessNative/SigningCrypto'
    destination = root / 'TetherlessSigningResources'
    if not source.is_dir() or destination.exists(): raise ValueError('Native crypto resource input missing or already packaged')
    names = ['TetherlessForge.min.js', 'TetherlessSigningCrypto.js', 'TetherlessCryptoEnvironment.js', 'node-forge-LICENSE.txt']
    bridge = (ROOT / 'Native/NativeEncryptedP12.swift').read_text()
    for name in names[:3]:
        raw = (source / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() not in bridge: raise ValueError('Unpinned native crypto resource: ' + name)
    project = root / 'AltStore.xcodeproj/project.pbxproj'
    text = project.read_text()
    build_refs, file_refs, members = [], [], []
    for name in names:
        file_id = hashlib.sha1(('tetherless-crypto-file:' + name).encode()).hexdigest()[:24].upper()
        build_id = hashlib.sha1(('tetherless-crypto-build:' + name).encode()).hexdigest()[:24].upper()
        if file_id in text or build_id in text: raise ValueError('Native crypto resource already present')
        file_refs.append(f'\t\t{file_id} /* {name} */ = {{isa = PBXFileReference; lastKnownFileType = text; path = "TetherlessSigningResources/{name}"; sourceTree = SOURCE_ROOT; }};')
        build_refs.append(f'\t\t{build_id} /* {name} in Resources */ = {{isa = PBXBuildFile; fileRef = {file_id} /* {name} */; }};')
        members.append(f'\t\t\t\t{build_id} /* {name} in Resources */,')
    text = once(text, '/* End PBXBuildFile section */', '\n'.join(build_refs) + '\n/* End PBXBuildFile section */')
    text = once(text, '/* End PBXFileReference section */', '\n'.join(file_refs) + '\n/* End PBXFileReference section */')
    anchor = '\t\t\t\tA84596F62F7DC4C90000B8CD /* SideStore.conf in Resources */,'
    text = once(text, anchor, anchor + '\n' + '\n'.join(members))
    # Move outside the synchronized source group, so resources are included
    # exactly once, explicitly in the main app (never extension) resource phase.
    shutil.move(str(source), str(destination))
    project.write_text(text)

def apply(root):
    changes = {}
    for path, digest in BLOBS.items():
        raw = (root / path).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != digest: raise ValueError('Unreviewed certificate lifecycle source: ' + path)
        changes[root / path] = PATCHES[path](raw.decode())
    package_crypto(root)
    for path, source in changes.items(): path.write_text(source)
if __name__ == '__main__': apply(Path(sys.argv[1]))
