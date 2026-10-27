// SPDX-License-Identifier: AGPL-3.0-only
// Synthetic credentials only. Each read command follows a fully exited writer.
// No startup, real gateway, device, account or network operations are executed.
import Foundation
import MinimuxerCommon

@main struct PairingColdReadMain {
    static let privateKey = Data((0..<32).map { UInt8($0) })
    static let publicKey = Data((32..<64).map { UInt8($0) })
    static let identifier = "synthetic-controller-cold-reader"
    static let remoteName = AppConstants.Pairing.remotePairingFileName
    static let lockdownName = AppConstants.Pairing.lockdownPairingFileName
    static var remoteFields: [String: Any] {
        ["identifier": identifier, "private_key": privateKey, "public_key": publicKey,
         "alt_irk": Data(repeating: 3, count: 16), "generated_by": "synthetic-paired-fixture"]
    }
    static var lockdownFields: [String: Any] {
        var values: [String: Any] = [:]
        for key in ["WiFiMACAddress", "SystemBUID", "HostID", "UDID"] { values[key] = "synthetic-lockdown-only" }
        for key in ["RootPrivateKey", "HostPrivateKey", "RootCertificate", "EscrowBag", "HostCertificate", "DeviceCertificate"] {
            values[key] = Data([7])
        }
        return values
    }
    static func data(_ fields: [String: Any], format: PropertyListSerialization.PropertyListFormat = .xml) throws -> Data {
        try PropertyListSerialization.data(fromPropertyList: fields, format: format, options: 0)
    }
    static func check(_ condition: Bool) { precondition(condition, "cold pairing fixture assertion failed") }
    static func fails(_ body: () throws -> Void) {
        do { try body(); preconditionFailure("expected rejection") } catch {}
    }
    static func checkedStore() throws -> PrivateFileStore {
        let store = try PrivateFileStore(root: PairingFileManager.protectedRoot)
        try store.prepare(); return store
    }
    static func assertIdentity(_ parsed: any PairingFile, input: String) {
        guard let remote = parsed as? RPPairingFile else { preconditionFailure("remote protocol required") }
        precondition(remote.mode == .rppairing)
        precondition(remote.identifier == identifier)
        precondition(remote.privateKey == privateKey && remote.publicKey == publicKey)
        precondition(remote.rawContent == input && remote.rawData == Data(input.utf8))
        precondition(remote.plist["alt_irk"] as? Data == Data(repeating: 3, count: 16))
        precondition(remote.plist["generated_by"] as? String == "synthetic-paired-fixture")
    }
    @MainActor static func write(_ scenario: String) throws {
        // The launcher creates a distinct empty root for every writer/reader pair.
        for part in ["support", "documents", "lease"] {
            try FileManager.default.createDirectory(at: PairingColdFixture.root.appendingPathComponent(part), withIntermediateDirectories: true)
        }
        let manager = PairingFileManager()
        _ = try manager.savePairingFile(contents: String(decoding: data(lockdownFields), as: UTF8.self), preferred: .lockdown)
        let record = try PairingRecord(data: data(remoteFields, format: .binary), expected: .remote)
        _ = try manager.saveValidatedRemotePairingRecord(record)
        manager.preferredProtocol = .rppairing
        let store = try checkedStore()
        // Exact-save remains independent of semantic ordinary-read assertions.
        check(try store.read(remoteName) == record.xml)
        check(try store.read(lockdownName) != nil)
        if scenario == "binary_normalization" { try store.write(data(remoteFields, format: .binary), named: remoteName) }
        if scenario == "xml_representation" {
            let varied = record.content.replacingOccurrences(of: "<dict>", with: "<!-- synthetic representation -->\n<dict>")
            try store.write(Data(varied.utf8), named: remoteName)
        }
        print("pairing_cold_fixture written=" + scenario)
    }
    @MainActor static func read(_ scenario: String) throws {
        let manager = PairingFileManager() // New process, new manager, no old gateway object.
        let store = try checkedStore()
        precondition(manager.preferredProtocol == .rppairing && manager.persistedActiveProtocol == .rppairing)
        check(try store.read(lockdownName) != nil)
        switch scenario {
        case "remote_identity", "binary_normalization", "xml_representation":
            guard let content = try manager.fetchPairingFileVerified() else { preconditionFailure("selected remote missing") }
            let gateway = PairingGatewayInputSpy()
            precondition(gateway.parsed == nil && gateway.suppliedContent == nil)
            try gateway.receive(content: content, preferred: manager.preferredProtocol)
            precondition(gateway.suppliedPreference == .rppairing)
            assertIdentity(gateway.parsed!, input: content)
            if scenario == "binary_normalization" {
                check(try store.read(remoteName)!.starts(with: Data("bplist00".utf8)))
                precondition(content.hasPrefix("<?xml"))
            }
            // No comparison of fetched XML formatting with the saved record.
        case "selection_precedence":
            manager.persistedActiveProtocol = .lockdown
            let preferred = try manager.fetchPairingFileVerified()!
            assertIdentity(try PairingFileParser.parse(content: preferred), input: preferred)
            let explicit = try manager.fetchPairingFileVerified(preferred: .lockdown)!
            check(try PairingFileParser.parse(content: explicit, preferred: .lockdown).mode == .lockdown)
            manager.preferredProtocol = nil
            let active = try manager.fetchPairingFileVerified()!
            check(try PairingFileParser.parse(content: active, preferred: .lockdown).mode == .lockdown)
            manager.persistedActiveProtocol = nil
            fails { _ = try manager.fetchPairingFileVerified() }
            precondition(manager.fetchPairingFile() == nil)
            try store.remove(lockdownName)
            let sole = try manager.fetchPairingFileVerified()!
            assertIdentity(try PairingFileParser.parse(content: sole), input: sole)
        case "missing_selected":
            try store.remove(remoteName)
            check(try manager.fetchPairingFileVerified() == nil)
            precondition(manager.fetchPairingFile() == nil)
            check(try store.read(lockdownName) != nil)
        case "corrupt_or_wrong_selected":
            for bytes in [Data("not a plist".utf8), try data(lockdownFields)] {
                try store.write(bytes, named: remoteName)
                fails { _ = try manager.fetchPairingFileVerified() }
                precondition(manager.fetchPairingFile() == nil)
                check(try store.read(lockdownName) != nil)
            }
        case "invalid_preference":
            manager.preferredProtocol = .unknown
            fails { _ = try manager.fetchPairingFileVerified() }
            precondition(manager.fetchPairingFile() == nil)
            fails { _ = try manager.fetchPairingFileVerified(preferred: .unknown) }
            // A raw value outside the enum is deliberately nil in the existing
            // app accessors, and therefore uses persistedActiveProtocol.
            PairingColdFixture.set("unrecognized-raw-value", for: "preferredPairingProtocol")
            precondition(manager.preferredProtocol == nil)
            let selected = try manager.fetchPairingFileVerified()!
            assertIdentity(try PairingFileParser.parse(content: selected), input: selected)
        case "reset_suppression":
            UserDefaults.standard.isPairingReset = true
            check(try manager.fetchPairingFileVerified() == nil)
            UserDefaults.standard.isPairingReset = false
            try store.write(Data([1]), named: PairingReset.marker)
            check(try manager.fetchPairingFileVerified() == nil)
            precondition(manager.fetchPairingFile() == nil)
            check(try store.read(remoteName) != nil && store.read(lockdownName) != nil)
        case "strict_ordinary_parser":
            let remote = try manager.fetchPairingFileVerified()!
            let lockdown = String(decoding: try data(lockdownFields), as: UTF8.self)
            fails { _ = try PairingFileParser.parse(content: remote, preferred: .lockdown) }
            fails { _ = try PairingFileParser.parse(content: lockdown, preferred: .rppairing) }
            fails { _ = try PairingFileParser.parse(content: remote, preferred: .unknown) }
            var both = remoteFields; both.merge(lockdownFields) { _, other in other }
            let mixed = String(decoding: try data(both), as: UTF8.self)
            fails { _ = try PairingFileParser.parse(content: mixed) }
            fails { _ = try PairingRecord(data: Data(mixed.utf8)) }
            let gateway = PairingGatewayInputSpy()
            try gateway.receive(content: remote, preferred: .rppairing)
            assertIdentity(gateway.parsed!, input: remote)
        default: preconditionFailure("unknown fixture scenario")
        }
        print("pairing_cold_fixture passed=" + scenario)
    }
    @MainActor static func main() throws {
        precondition(CommandLine.arguments.count == 3)
        let mode = CommandLine.arguments[1], scenario = CommandLine.arguments[2]
        if mode == "write" { try write(scenario) }
        else { precondition(mode == "read"); try read(scenario) }
    }
}
