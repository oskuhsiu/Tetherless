import Foundation
import Testing
@testable import TetherlessCore

@Suite("Private signing material never enters target app resources")
struct SigningMaterialTests {
    private func directory() throws -> URL {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString).appendingPathExtension("app")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        return root
    }
    @Test func removesKnownLegacyP12AndKeepsOtherApplicationAssets() throws {
        let root = try directory(); defer { try? FileManager.default.removeItem(at: root) }
        try Data("old signing material".utf8).write(to: root.appendingPathComponent("ALTCertificate.p12"))
        try Data("legitimate app asset".utf8).write(to: root.appendingPathComponent("client.p12"))
        let publicBytes = Data([0x30, 0x01, 0x00]) // Payload fixture, not a trusted X.509 certificate.
        try PublicSigningMaterial.writeCertificate(publicBytes, into: root)
        #expect(!FileManager.default.fileExists(atPath: root.appendingPathComponent("ALTCertificate.p12").path))
        #expect(try Data(contentsOf: root.appendingPathComponent("ALTCertificate.der")) == publicBytes)
        #expect(try Data(contentsOf: root.appendingPathComponent("client.p12")) == Data("legitimate app asset".utf8))
    }
    @Test func missingLegacyResourceIsNormal() throws {
        let root = try directory(); defer { try? FileManager.default.removeItem(at: root) }
        try PublicSigningMaterial.writeCertificate(Data([1]), into: root)
        #expect(FileManager.default.fileExists(atPath: root.appendingPathComponent("ALTCertificate.der").path))
    }
    @Test func symlinkDestinationDoesNotOverwriteExternalFile() throws {
        let root = try directory(); defer { try? FileManager.default.removeItem(at: root) }
        let external = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: external) }
        try Data("preserve".utf8).write(to: external)
        try FileManager.default.createSymbolicLink(at: root.appendingPathComponent("ALTCertificate.der"), withDestinationURL: external)
        try FileManager.default.createSymbolicLink(at: root.appendingPathComponent("ALTCertificate.p12"), withDestinationURL: external)
        try PublicSigningMaterial.writeCertificate(Data([1]), into: root)
        #expect(try Data(contentsOf: external) == Data("preserve".utf8))
    }
    @Test func rejectsInvalidInputBeforeRemovingExistingMaterial() throws {
        let root = try directory(); defer { try? FileManager.default.removeItem(at: root) }
        let legacy = root.appendingPathComponent("ALTCertificate.p12")
        try Data([8]).write(to: legacy)
        #expect(throws: RenewalFailure.invalidInput) { try PublicSigningMaterial.writeCertificate(Data(), into: root) }
        #expect(throws: RenewalFailure.invalidInput) { try PublicSigningMaterial.writeCertificate(Data(repeating: 0, count: 65_537), into: root) }
        #expect(try Data(contentsOf: legacy) == Data([8]))
    }
}
