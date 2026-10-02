//
//  CertificateManager.swift
//  SideStore
//
//  Created by Magesh K on 1/8/26.
//  Copyright © 2026 SideStore. All rights reserved.
//

import Foundation
import SideSign
import CodeSignKit

public struct ActiveSigningCertificate: Sendable {
    public let certificate: ALTCertificate
    public let p12Data: Data
    public let password: String?
    
    public var serialNumber: String {
        certificate.serialNumber
    }

    init(certificate: ALTCertificate, p12Data: Data, password: String?) {
        self.certificate = certificate
        self.p12Data = p12Data
        self.password = password
    }
}

// Tetherless persistence override; inherited parsing/attribution retained.
public final class CertificateManager: @unchecked Sendable {
    public static let shared = CertificateManager()
    private let serialsKey = "importedCertificateSerials"
    private let metadataPrefix = "certMetadata_"
    private let metadataLock = NSRecursiveLock()
    private init() {}

    // Keychain is authoritative. Do not retain a signable object across logout
    // or another process changing the selected certificate.
    public var activeCertificate: ActiveSigningCertificate? {
        do { return try loadActiveCertificate() }
        catch {
            UserDefaults.standard.set(true, forKey: "tetherless.certificate.storageFailed")
            return nil
        }
    }
    public static func parse(_ data: Data, password: String?) throws -> ALTCertificate {
        guard !data.isEmpty, data.count <= 32_768 else { throw AuthenticationStorageFailure.invalidRecord }
        return try ALTCertificate(p12Data: data, password: password)
    }
    public static func convert(_ cert: ALTCertificate, password: String?) throws -> Data {
        if let password { return try cert.encryptedP12Data(password: password) }
        return try cert.unencryptedP12Data()
    }
    @discardableResult
    public func loadActiveCertificate() throws -> ActiveSigningCertificate? {
        try NativeCertificatePersistence.loadActive()
    }
    public func getPassword(for cert: ALTCertificate) -> String? { cert.serialNumber }
    public func getPassword(for serialNumber: String) -> String? { serialNumber }
    public func setActiveCertificate(_ cert: ALTCertificate?) throws {
        try NativeMutationGate.withSynchronousLease {
            if let cert {
                let record = try NativeCertificatePersistence.record(cert)
                try saveCertificate(cert) // Preserve the key before switching active identity.
                try NativeCertificatePersistence.saveActive(record)
            } else { try NativeCertificatePersistence.saveActive(nil) }
            UserDefaults.standard.removeObject(forKey: "tetherless.certificate.storageFailed")
        }
    }
    public func clearActiveCertificate() throws { try setActiveCertificate(nil) }
    public var activeSigningCertificateBase64Encoded: String? { nil } // No URL secret export.

    public func saveCertificate(_ cert: ALTCertificate) throws {
        try NativeMutationGate.withSynchronousLease {
            let record = try NativeCertificatePersistence.record(cert)
            try Keychain.shared.writeImportedCertificateVerified(record.p12, serial: cert.serialNumber)
            remember(cert.x509)
        }
    }
    /// A public certificate observation must NEVER replace an existing P12.
    /// The public-only namespace is atomic and independent of the active signer.
    public func saveX509Certificate(_ cert: ALTX509Certificate) throws {
        guard let bytes = cert.data, !bytes.isEmpty, bytes.count <= 32_768 else {
            throw AuthenticationStorageFailure.invalidRecord
        }
        try Keychain.shared.writePublicCertificateVerified(bytes, serial: cert.serialNumber)
        remember(cert)
    }
    public func getLocalCertificateVerified(serialNumber: String) throws -> ALTCertificate? {
        if let active = try loadActiveCertificate(), active.serialNumber.caseInsensitiveCompare(serialNumber) == .orderedSame {
            return active.certificate
        }
        guard let record = try Keychain.shared.readCachedSigningIdentityVerified(serial: serialNumber) else { return nil }
        var cert = try Self.parse(record.p12, password: record.password)
        guard cert.serialNumber.caseInsensitiveCompare(serialNumber) == .orderedSame, !cert.privateKey.isEmpty else {
            throw AuthenticationStorageFailure.invalidRecord
        }
        if let metadata = getCertificateMetadata(for: serialNumber) {
            cert.machineIdentifier = metadata["machineIdentifier"]
            cert.machineName = metadata["machineName"]
            cert.requesterEmail = metadata["requesterEmail"]
        }
        return cert
    }
    public func getLocalCertificate(serialNumber: String) -> ALTCertificate? {
        do { return try getLocalCertificateVerified(serialNumber: serialNumber) }
        catch { UserDefaults.standard.set(true, forKey: "tetherless.certificate.storageFailed"); return nil }
    }
    public func getLocalX509Certificate(serialNumber: String) -> ALTX509Certificate? {
        do {
            if let cert = try getLocalCertificateVerified(serialNumber: serialNumber) { return cert.x509 }
            guard let bytes = try Keychain.shared.readPublicCertificateVerified(serial: serialNumber),
                  var cert = ALTX509Certificate(data: bytes),
                  cert.serialNumber.caseInsensitiveCompare(serialNumber) == .orderedSame else { return nil }
            if let metadata = getCertificateMetadata(for: serialNumber) {
                cert.machineIdentifier = metadata["machineIdentifier"]
                cert.machineName = metadata["machineName"]
                cert.requesterEmail = metadata["requesterEmail"]
            }
            return cert
        } catch { UserDefaults.standard.set(true, forKey: "tetherless.certificate.storageFailed"); return nil }
    }
    public func getAllLocalCertificates() -> [ALTCertificate] {
        getImportedCertificateSerials().compactMap { getLocalCertificate(serialNumber: $0) }
    }
    public func getAllLocalX509Certificates() -> [ALTX509Certificate] {
        getImportedCertificateSerials().compactMap { getLocalX509Certificate(serialNumber: $0) }
    }
    public func deleteCertificate(serialNumber: String) throws {
        try NativeMutationGate.withSynchronousLease {
            if try loadActiveCertificate()?.serialNumber.caseInsensitiveCompare(serialNumber) == .orderedSame {
                try clearActiveCertificate()
            }
            try Keychain.shared.removeCachedCertificateVerified(serial: serialNumber, includePublic: true)
            metadataLock.lock(); defer { metadataLock.unlock() }
            setCertificateMetadata(nil, for: serialNumber)
            setImportedCertificateSerials(getImportedCertificateSerials().filter { $0 != serialNumber })
        }
    }
    public func removePrivateKey(for cert: ALTX509Certificate) throws {
        try NativeMutationGate.withSynchronousLease {
            try saveX509Certificate(cert)
            if try loadActiveCertificate()?.serialNumber.caseInsensitiveCompare(cert.serialNumber) == .orderedSame {
                try clearActiveCertificate()
            }
            try Keychain.shared.removeCachedCertificateVerified(serial: cert.serialNumber, includePublic: false)
        }
    }
    public func getSignableCertificate(for serialNumber: String = "", fallbackPassword: String? = nil) -> ALTCertificate? {
        getLocalCertificate(serialNumber: serialNumber)
    }

    // Reads the Mach-O binary contents of an app bundle to extract its leaf signing certificate.
    private func readBinaryCertificate(at url: URL) -> ALTX509Certificate? {
        let executableURL: URL
        if url.pathExtension == "app" {
            guard let execURL = ALTApplication(fileURL: url)?.executableURL else {
                debugLog("[CertificateManager] readBinaryCertificate: Failed to locate executable in bundle: \(url.path)")
                return nil
            }
            executableURL = execURL
        } else {
            executableURL = url
        }
        
        guard let parser = try? MachOParser(url: executableURL) else {
            debugLog("[CertificateManager] readBinaryCertificate: Failed to parse Mach-O at \(executableURL.path)")
            return nil
        }
        
        let certChain = parser.x509Certificates()

        debugLog("[CertificateManager] readBinaryCertificate: Found \(certChain.count) certificate(s) in Mach-O chain.")
        
        for (index, x509Cert) in certChain.enumerated() {
            guard let derData = x509Cert.data else { continue }
            let details = parseCertificate(derData: derData)
            
            // Filter out Root & Intermediate CA certificates
            let subjectDN = details.subject
            let isFilteredOut = subjectDN.contains("Root") || subjectDN.contains("Authority") || subjectDN.contains("Relations")
            
            verboseLog("""
            [CertificateManager] readBinaryCertificate: Certificate [\(index)]:
              - Subject: '\(details.subject)'
              - Issuer: '\(details.issuer)'
              - Serial Hex: '\(details.serialHex)'
              - Valid From: \(details.validFrom?.description ?? "N/A")
              - Valid Until: \(details.validUntil?.description ?? "N/A")
              - Filtered Out: \(isFilteredOut)
              - Parsed ALTX509Certificate: Success (serial: \(x509Cert.serialNumber))
            """)
            
            if isFilteredOut {
                continue
            }
            
            debugLog("[CertificateManager] readBinaryCertificate: Extracted leaf signing certificate from Mach-O (\(executableURL.lastPathComponent))")
            return x509Cert
        }
        return nil
    }

    public func getSigningCertificate(at url: URL) -> ALTX509Certificate? {
        verboseLog("[CertificateManager] Step 1 (Mach-O): Checking \(url.path)...")
        if let binaryX509 = readBinaryCertificate(at: url) {
            debugLog("[CertificateManager] getSigningCertificate: Loaded signing certificate from Mach-O \(url.path) (serial: \(binaryX509.serialNumber)).")
            return binaryX509
        } else {
            verboseLog("[CertificateManager] Step 1 (Mach-O): No valid leaf certificate extracted from Mach-O at \(url.path).")
            return nil
        }
    }

    public func getSigningCertificate(for app: InstalledAppProtocol) -> ALTX509Certificate? {
        let bundleID = app.bundleIdentifier
        let isSelf = app.resignedBundleIdentifier.isAltStoreAppID || app.bundleIdentifier.isAltStoreAppID

        verboseLog("[CertificateManager] getSigningCertificate started for app: \(app.name), isSelf: \(isSelf), bundleID: \(bundleID)")

        // STEP 1: Mach-O Binary Check (Only for SideStore itself)
        if isSelf {
            return self.getSigningCertificate(at: Bundle.Info.activeBundleURL)
        }

        // STEP 2: App Group Cached Certificate Check (For third-party apps)
        let certURL = app.signingCertificateURL
        verboseLog("[CertificateManager] Step 2 (App Group Cached Cert): Checking \(certURL.path)...")

        if FileManager.default.fileExists(atPath: certURL.path) {
            if let derData = try? Data(contentsOf: certURL), let cert = ALTX509Certificate(data: derData) {
                debugLog("[CertificateManager] getSigningCertificate: Loaded cached signing certificate from App Group \(certURL.path) (serial: \(cert.serialNumber))")
                return cert
            } else {
                verboseLog("[CertificateManager] Step 2 (App Group Cached Cert): File exists at \(certURL.path) but failed to parse.")
            }
        }
        verboseLog("[CertificateManager] Step 2 (App Group Cached Cert): No cached certificate found in App Group at \(certURL.path).")

        return nil
    }

    public func isCertificateLocallyCached(serialNumber: String) -> Bool {
        getLocalX509Certificate(serialNumber: serialNumber) != nil
    }
    private func remember(_ cert: ALTX509Certificate) {
        metadataLock.lock(); defer { metadataLock.unlock() }
        var serials = getImportedCertificateSerials()
        if !serials.contains(cert.serialNumber) { serials.append(cert.serialNumber) }
        setImportedCertificateSerials(serials)
        var metadata = getCertificateMetadata(for: cert.serialNumber) ?? [:]
        metadata["name"] = cert.name; metadata["serialNumber"] = cert.serialNumber
        if let value = cert.machineIdentifier { metadata["machineIdentifier"] = value }
        if let value = cert.machineName { metadata["machineName"] = value }
        if let value = cert.requesterEmail { metadata["requesterEmail"] = value }
        setCertificateMetadata(metadata, for: cert.serialNumber)
    }
}

private extension CertificateManager {
    func getImportedCertificateSerials() -> [String] {
        UserDefaults.standard.stringArray(forKey: serialsKey) ?? []
    }
    func setImportedCertificateSerials(_ serials: [String]) {
        UserDefaults.standard.set(serials, forKey: serialsKey)
    }
    func getCertificateMetadata(for serial: String) -> [String: String]? {
        UserDefaults.standard.dictionary(forKey: metadataPrefix + serial) as? [String: String]
    }
    func setCertificateMetadata(_ metadata: [String: String]?, for serial: String) {
        if let metadata { UserDefaults.standard.set(metadata, forKey: metadataPrefix + serial) }
        else { UserDefaults.standard.removeObject(forKey: metadataPrefix + serial) }
    }
}
