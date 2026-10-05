// SPDX-License-Identifier: AGPL-3.0-only
// Synthetic app directories/defaults and process-acquisition seam. The fixture
// compiles the real PairingFileManager, NativePairingMutation and MutationScope.
// It proves borrowing/ownership of this seam, not real OS process-lock behavior.
import Foundation
import MinimuxerCommon

private final class FixtureState: @unchecked Sendable {
    private let lock = NSLock()
    private var active: PairingProtocol?
    private var preferred: PairingProtocol?
    private var reset = false
    func readActive() -> PairingProtocol? { lock.lock(); defer { lock.unlock() }; return active }
    func readPreferred() -> PairingProtocol? { lock.lock(); defer { lock.unlock() }; return preferred }
    func readReset() -> Bool { lock.lock(); defer { lock.unlock() }; return reset }
    func setActive(_ value: PairingProtocol?) { lock.lock(); defer { lock.unlock() }; active = value }
    func setPreferred(_ value: PairingProtocol?) { lock.lock(); defer { lock.unlock() }; preferred = value }
    func setReset(_ value: Bool) { lock.lock(); defer { lock.unlock() }; reset = value }
}
enum PairingGeneratedFixture {
    static let root: URL = {
        guard let path = ProcessInfo.processInfo.environment["TETHERLESS_PAIRING_FIXTURE_ROOT"] else {
            fatalError("fixture root must be supplied")
        }
        return URL(fileURLWithPath: path, isDirectory: true).resolvingSymlinksInPath()
    }()
    fileprivate static let state = FixtureState()
    static let lease = PairingFixtureLeaseProbe()
}
extension FileManager {
    var applicationSupportDirectory: URL { PairingGeneratedFixture.root.appendingPathComponent("support", isDirectory: true) }
    var documentsDirectory: URL { PairingGeneratedFixture.root.appendingPathComponent("documents", isDirectory: true) }
}
extension UserDefaults {
    var activePairingProtocol: PairingProtocol? {
        get { PairingGeneratedFixture.state.readActive() }
        set { PairingGeneratedFixture.state.setActive(newValue) }
    }
    var preferredPairingProtocol: PairingProtocol? {
        get { PairingGeneratedFixture.state.readPreferred() }
        set { PairingGeneratedFixture.state.setPreferred(newValue) }
    }
    var isPairingReset: Bool {
        get { PairingGeneratedFixture.state.readReset() }
        set { PairingGeneratedFixture.state.setReset(newValue) }
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
func minimuxerPairingProtocol() -> PairingProtocol { .rppairing }
enum PairingFixtureFailure: Error { case parser, busy, postWrite }
final class PairingFixtureLeaseProbe: @unchecked Sendable {
    private let mutex = NSLock()
    private var held = false
    private var acquired = 0
    private var released = 0
    var counts: (acquired: Int, released: Int, held: Bool) {
        mutex.lock(); defer { mutex.unlock() }; return (acquired, released, held)
    }
    func acquire() throws -> (@Sendable () -> Void) {
        mutex.lock(); defer { mutex.unlock() }
        guard !held else { throw PairingFixtureFailure.busy }
        held = true; acquired += 1
        return { [self] in
            mutex.lock(); defer { mutex.unlock() }
            precondition(held); held = false; released += 1
        }
    }
}
final class ProcessLease {
    private let releaseAction: @Sendable () -> Void
    private var released = false
    private init(_ release: @escaping @Sendable () -> Void) { releaseAction = release }
    static func acquire(at path: URL) throws -> ProcessLease {
        precondition(path == PairingGeneratedFixture.root.appendingPathComponent("lease/device-mutation.lock"))
        return try ProcessLease(PairingGeneratedFixture.lease.acquire())
    }
    func release() { precondition(!released); released = true; releaseAction() }
}
enum NativeRenewalStorage {
    // A test directory only. The production root/accessor is neither copied nor
    // replaced in production; this harness does not execute its implementation.
    static func root() throws -> URL { PairingGeneratedFixture.root.appendingPathComponent("lease", isDirectory: true) }
    static func acquire() throws -> ProcessLease { try ProcessLease.acquire(at: root().appendingPathComponent("device-mutation.lock")) }
}
enum NativeMutationGate {}
