// SPDX-License-Identifier: AGPL-3.0-only
// Explicit external seams for the cold-reader fixture, never app sources.
// Preferences use a test-owned plist across two OS processes, not CFPreferences.
// Directory access, process-lock acquisition and the final gateway are synthetic.
// PairingFileManager, checked storage and the pinned ordinary parser are actual.
import Foundation
import MinimuxerCommon

enum PairingColdFixture {
    static let root: URL = {
        guard let path = ProcessInfo.processInfo.environment["TETHERLESS_COLD_PAIRING_ROOT"] else {
            fatalError("test-owned fixture root required")
        }
        return URL(fileURLWithPath: path, isDirectory: true)
    }()
    static var preferencesURL: URL { root.appendingPathComponent("preferences.plist") }
    static func preferences() -> [String: Any] {
        guard FileManager.default.fileExists(atPath: preferencesURL.path) else { return [:] }
        return try! PropertyListSerialization.propertyList(from: Data(contentsOf: preferencesURL),
            options: [], format: nil) as! [String: Any]
    }
    static func set(_ value: Any?, for key: String) {
        var values = preferences(); values[key] = value
        let bytes = try! PropertyListSerialization.data(fromPropertyList: values, format: .binary, options: 0)
        try! bytes.write(to: preferencesURL, options: .atomic)
    }
}
extension FileManager {
    var applicationSupportDirectory: URL { PairingColdFixture.root.appendingPathComponent("support", isDirectory: true) }
    var documentsDirectory: URL { PairingColdFixture.root.appendingPathComponent("documents", isDirectory: true) }
}
extension UserDefaults {
    // Same optional raw-value conversion as the pinned app accessors; the
    // persistent backend is explicitly replaced to avoid ambient user defaults.
    var activePairingProtocol: PairingProtocol? {
        get { (PairingColdFixture.preferences()["activePairingProtocol"] as? String).flatMap(PairingProtocol.init(rawValue:)) }
        set { PairingColdFixture.set(newValue?.rawValue, for: "activePairingProtocol") }
    }
    var preferredPairingProtocol: PairingProtocol? {
        get { (PairingColdFixture.preferences()["preferredPairingProtocol"] as? String).flatMap(PairingProtocol.init(rawValue:)) }
        set { PairingColdFixture.set(newValue?.rawValue, for: "preferredPairingProtocol") }
    }
    var isPairingReset: Bool {
        get { PairingColdFixture.preferences()["isPairingReset"] as? Bool ?? false }
        set { PairingColdFixture.set(newValue, for: "isPairingReset") }
    }
}
enum AppConstants {
    enum Pairing {
        static let supportedExtensions = ["plist", "mobiledevicepairing", "rppairing"]
        static let lockdownPairingFileName = "lockdown.plist"
        static let remotePairingFileName = "remote.plist"
        static let legacyPairingFileName = "legacy.plist"
    }
}
// Uncalled by these fixtures. These definitions only satisfy unrelated manager
// members; they make no live protocol or wireless-session assertion.
func minimuxerPairingProtocol() -> PairingProtocol { fatalError("live gateway outside fixture") }
struct MinimuxerPairedDevice {
    let name: String
    let model: String
    let pairingFilePath: String
}
final class ProcessLease {
    static func acquire(at path: URL) throws -> ProcessLease { ProcessLease() }
    func release() {}
}
enum NativeRenewalStorage {
    static func root() throws -> URL { PairingColdFixture.root.appendingPathComponent("lease", isDirectory: true) }
    static func acquire() throws -> ProcessLease { try ProcessLease.acquire(at: root().appendingPathComponent("device-mutation.lock")) }
}
enum NativeMutationGate {}

// The actual IdeviceGateway is deliberately not compiled. This fresh receiver
// observes its input contract and calls the actual unmodified ordinary parser.
// It does not construct a native handle, start a service or simulate acceptance.
final class PairingGatewayInputSpy {
    private(set) var suppliedPreference: PairingProtocol?
    private(set) var suppliedContent: String?
    private(set) var parsed: (any PairingFile)?
    func receive(content: String, preferred: PairingProtocol?) throws {
        precondition(parsed == nil && suppliedContent == nil)
        suppliedContent = content; suppliedPreference = preferred
        parsed = try PairingFileParser.parse(content: content, preferred: preferred)
    }
}
