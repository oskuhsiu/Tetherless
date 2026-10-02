#!/usr/bin/env python3
"""Split CSR generation from submission; route native creation through recovery."""
from pathlib import Path
import hashlib
import sys

PORTAL = 'SideStore/Core/Auth/DeveloperPortalProxy.swift'
CERTIFICATES = 'Dependencies/SideSign/Sources/DeveloperPortal/Certificates.swift'

def once(source, old, new):
    if source.count(old) != 1: raise ValueError('Certificate issuance anchor drift: ' + old[:60])
    return source.replace(old, new, 1)

def patch_certificates(source):
    start = '        let csrString = String(decoding: certRequest.csrData, as: UTF8.self)'
    source = once(source, start, '''        let cert = try await submitCertificateRequest(csrData: certRequest.csrData,
            machineName: machineName, machineIdentifier: UUID().uuidString.uppercased(),
            type: type, to: team, session: session)
        return KeyStore(certificate: cert, privateKey: certRequest.privateKey)
    }

    // Tetherless: no key generation here. The caller durably owns the exact
    // CSR/private key before dispatch. A stable machine ID is correlation, NOT
    // a claim that Apple's endpoint offers idempotent request semantics.
    func submitCertificateRequest(csrData: Data, machineName: String, machineIdentifier: String,
                                  type: CertificateType, to team: Team, session: Session) async throws -> X509Certificate {
        guard !csrData.isEmpty, csrData.count <= 8192, !machineName.isEmpty,
              machineName.utf8.count <= 128, UUID(uuidString: machineIdentifier) != nil,
              !(team.type == .free && type.isPaidOnly) else {
            throw DeveloperPortalError.invalidParameters(cause: "Invalid prepared certificate request.")
        }
        let csrString = String(decoding: csrData, as: UTF8.self)''')
    source = once(source, '            "machineId": UUID().uuidString.uppercased()', '            "machineId": machineIdentifier')
    # Only the original trailing return moves to public-certificate-only.
    marker = '        verboseLog("[SideSign] SerialNumber: \\(cert.serialNumber)")\n        return KeyStore(certificate: cert, privateKey: certRequest.privateKey)'
    source = once(source, marker, '        return cert')
    return source

def patch_portal(source):
    source = once(source, '''            let created = try await ALTAppleAPI.shared.addCertificate(machineName: machineName, type: type, to: team, session: session)
            // Preserve the returned key BEFORE any extra portal fetch or caller cancellation.
            // A failure here propagates; it must not become "created successfully".
            try CertificateManager.shared.saveCertificate(created)
            return created''', '''            guard let created = try await NativeCertificateIssuance.perform(machineName: machineName, type: type,
                team: team, session: session, allowNew: true) else { throw CertificateIssuanceFailure.invalidRecord }
            return created''')
    return once(source, '    @discardableResult\n    public func revokeCertificate(', '''    public func recoverPendingCertificate(type: CertificateType = .development, team: ALTTeam? = nil) async throws -> ALTCertificate? {
        try await NativeMutationGate.withLease {
            let session = try await self.getSession()
            let team = try await self.getTeam(team)
            return try await NativeCertificateIssuance.perform(machineName: "Tetherless", type: type,
                team: team, session: session, allowNew: false)
        }
    }

    @discardableResult
    public func revokeCertificate(''')

PATCHES = {PORTAL: patch_portal, CERTIFICATES: patch_certificates}
BLOBS = {'SideStore/Core/Auth/DeveloperPortalProxy.swift': '3db4f94ddd0f0f112591c9b998d1ac12f6f3c3f5', 'Dependencies/SideSign/Sources/DeveloperPortal/Certificates.swift': '6127e16f8a265471e01ed8d03d6ba4a496caddb0'}  # Populated from the already-reviewed 1ef23cf prepared artifact.

def apply(root: Path):
    outputs = {}
    for path, patch in PATCHES.items():
        raw = (root/path).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != BLOBS[path]: raise ValueError('Unreviewed issuance source: ' + path)
        outputs[root/path] = patch(raw.decode())
    for path, content in outputs.items(): path.write_text(content)

if __name__ == '__main__': apply(Path(sys.argv[1]))
