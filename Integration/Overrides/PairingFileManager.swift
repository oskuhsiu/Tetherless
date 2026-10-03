// Based on SideStore PairingFileManager.swift, Copyright © 2026 SideStore.
// Tetherless protected-storage replacement. SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import UniformTypeIdentifiers
import MinimuxerCommon

public struct PairingFileMetadata: Sendable {
    public let exists: Bool
    public let size: Int64
    public let creationDate: Date?
    public let modificationDate: Date?
}

final class PairingFileManager: NSObject {
    static let shared = PairingFileManager()
    static var supportedContentTypes: [UTType] {
        AppConstants.Pairing.supportedExtensions.compactMap { UTType(filenameExtension: $0) } + [.propertyList, .xml]
    }
    var activeProtocol: PairingProtocol { minimuxerPairingProtocol() }
    var persistedActiveProtocol: PairingProtocol? {
        get { UserDefaults.standard.activePairingProtocol }
        set { UserDefaults.standard.activePairingProtocol = newValue }
    }
    var preferredProtocol: PairingProtocol? {
        get { UserDefaults.standard.preferredPairingProtocol }
        set { UserDefaults.standard.preferredPairingProtocol = newValue }
    }
    // The accessor supplies a path only. All IO goes through checked store APIs.
    nonisolated static var protectedRoot: URL {
        FileManager.default.applicationSupportDirectory.appendingPathComponent("TetherlessPairing", isDirectory: true)
    }
    nonisolated private func store() throws -> PrivateFileStore {
        _ = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        let value = try PrivateFileStore(root: Self.protectedRoot)
        try value.prepare()
        return value
    }
    nonisolated private func name(_ mode: PairingProtocol) throws -> String {
        switch mode {
        case .lockdown: return AppConstants.Pairing.lockdownPairingFileName
        case .rppairing: return AppConstants.Pairing.remotePairingFileName
        case .unknown: throw PrivateFileError.invalidContent
        }
    }
    nonisolated private func expected(_ mode: PairingProtocol?) throws -> PairingRecord.Kind? {
        switch mode {
        case .none: return nil
        case .lockdown: return .lockdown
        case .rppairing: return .remote
        case .unknown: throw PrivateFileError.invalidContent
        }
    }
    nonisolated func pairingFileURL(for mode: PairingProtocol) -> URL {
        Self.protectedRoot.appendingPathComponent((try? name(mode)) ?? "unsupported")
    }
    nonisolated func hasPairingFile(for mode: PairingProtocol) -> Bool { fetchPairingFile(for: mode) != nil }
    nonisolated func hasPairingFile() -> Bool { fetchPairingFile() != nil }
    nonisolated func metadata(for mode: PairingProtocol) -> PairingFileMetadata {
        guard let data = try? store().read(name(mode)) else {
            return PairingFileMetadata(exists: false, size: 0, creationDate: nil, modificationDate: nil)
        }
        let attrs = (try? FileManager.default.attributesOfItem(atPath: pairingFileURL(for: mode).path)) ?? [:]
        return PairingFileMetadata(exists: true, size: Int64(data.count),
                                  creationDate: attrs[.creationDate] as? Date, modificationDate: attrs[.modificationDate] as? Date)
    }
    nonisolated func fetchPairingFile(for mode: PairingProtocol) -> String? {
        try? fetchPairingFileVerified(preferred: mode)
    }
    nonisolated func fetchPairingFile(preferred: PairingProtocol? = nil) -> String? {
        try? fetchPairingFileVerified(preferred: preferred)
    }
    /// Checked callers must distinguish absent/reset data from unreadable or
    /// conflicting records. Compatibility callers above still fail closed.
    nonisolated func fetchPairingFileVerified(preferred: PairingProtocol? = nil) throws -> String? {
        guard !UserDefaults.standard.isPairingReset else { return nil }
        let value = try store()
        guard try !PairingReset.isMarked(in: value) else { return nil }
        func read(_ mode: PairingProtocol) throws -> String? {
            guard let bytes = try value.read(name(mode)) else { return nil }
            return try PairingRecord(data: bytes, expected: expected(mode)).content
        }
        if let selected = preferred ?? preferredProtocol ?? persistedActiveProtocol {
            return try read(selected)
        }
        let values = try [PairingProtocol.lockdown, .rppairing].compactMap { try read($0) }
        guard values.count <= 1 else { throw PrivateFileError.conflict }
        return values.first
    }
    @discardableResult
    nonisolated func parse(content: String, preferred: PairingProtocol? = nil) throws -> any PairingFile {
        let record = try PairingRecord(data: Data(content.utf8), expected: expected(preferred))
        return try PairingFileParser.parse(content: record.content, preferred: preferred)
    }
    @discardableResult
    func savePairingFile(contents: String, preferred: PairingProtocol? = nil) throws -> any PairingFile {
        let record = try PairingRecord(data: Data(contents.utf8), expected: expected(preferred))
        return try NativeMutationGate.withSynchronousLease { try commit(record) }
    }
    /// Internal capability: a wireless session owns the same process lease until
    /// its callback finishes. Do not call this outside that session/import scope.
    fileprivate func commit(_ record: PairingRecord) throws -> any PairingFile {
        let mode: PairingProtocol = record.kind == .remote ? .rppairing : .lockdown
        let parsed = try PairingFileParser.parse(content: record.content, preferred: mode)
        let value = try store()
        try value.write(record.xml, named: name(mode))
        guard try value.read(name(mode)) == record.xml else { throw PrivateFileError.changedDuringRead }
        try PairingReset.finishImport(in: value, name: name(mode), expected: record.xml) {
            let other: PairingProtocol = mode == .lockdown ? .rppairing : .lockdown
            try value.remove(name(other))
            for url in legacyURLs {
                if try PrivateFileStore.readExternal(url) != nil { try FileManager.default.removeItem(at: url) }
            }
        }
        persistedActiveProtocol = mode
        UserDefaults.standard.isPairingReset = false
        return parsed
    }
    func inspectPairingFile(from url: URL) throws -> (content: String, file: any PairingFile) {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        // The open-mode document picker grants a security-scoped URL. Coordinate
        // access while that grant is held, then bound and validate the snapshot.
        // Do not create an unprotected imported copy in Documents/Inbox.
        let coordinator = NSFileCoordinator(filePresenter: nil)
        var coordinationError: NSError?
        var captured: Result<Data, Error>?
        coordinator.coordinate(readingItemAt: url, options: .withoutChanges, error: &coordinationError) { coordinatedURL in
            captured = Result {
                guard let bytes = try PrivateFileStore.readExternal(coordinatedURL) else {
                    throw PrivateFileError.unavailable
                }
                return bytes
            }
        }
        guard coordinationError == nil, let captured else { throw PrivateFileError.unavailable }
        let record = try PairingRecord(data: captured.get())
        return (record.content, try parse(content: record.content))
    }
    func importPairingFile(from url: URL, preferred: PairingProtocol? = nil) throws {
        let (content, _) = try inspectPairingFile(from: url)
        _ = try savePairingFile(contents: content, preferred: preferred)
    }
    func deletePairingFile(for mode: PairingProtocol) throws {
        try NativeMutationGate.withSynchronousLease {
            try store().remove(name(mode))
            // Prevent re-importing a deleted record from a legacy bootstrap file.
            for url in legacyURLs where FileManager.default.fileExists(atPath: url.path) {
                guard let bytes = try PrivateFileStore.readExternal(url) else { continue }
                let record = try PairingRecord(data: bytes)
                if (record.kind == .remote) == (mode == .rppairing) { try FileManager.default.removeItem(at: url) }
            }
            if persistedActiveProtocol == mode { persistedActiveProtocol = nil }
        }
    }
    func resetAllPairingFiles() throws {
        try NativeMutationGate.withSynchronousLease {
            let value = try store()
            try PairingReset.begin(in: value, deleting: [name(.lockdown), name(.rppairing)])
            // Durable marker precedes deleting either current or legacy records.
            UserDefaults.standard.isPairingReset = true
            persistedActiveProtocol = nil
            preferredProtocol = nil
            for url in legacyURLs {
                if try PrivateFileStore.readExternal(url) != nil { try FileManager.default.removeItem(at: url) }
            }
        }
    }
    private var legacyURLs: [URL] {
        [AppConstants.Pairing.lockdownPairingFileName, AppConstants.Pairing.remotePairingFileName,
         AppConstants.Pairing.legacyPairingFileName].map { FileManager.default.documentsDirectory.appendingPathComponent($0) }
    }
    func migrateLegacyFiles() throws {
        guard !UserDefaults.standard.isPairingReset else { return }
        try NativeMutationGate.withSynchronousLease {
            let value = try store()
            guard try !PairingReset.isMarked(in: value) else { return }
            for source in legacyURLs {
                guard let bytes = try PrivateFileStore.readExternal(source) else { continue }
                let record = try PairingRecord(data: bytes)
                let mode: PairingProtocol = record.kind == .remote ? .rppairing : .lockdown
                try value.migrate(source, to: name(mode)) { try PairingRecord(data: $0).xml }
                if persistedActiveProtocol == nil { persistedActiveProtocol = mode }
            }
        }
    }
}

/// A wireless handshake has its own private staging directory, never Documents.
/// The callback captures the session strongly, preserving the lease until the
/// library is done. No raw pairing file is automatically presented to Share.
final class NativePairingSession: @unchecked Sendable {
    let directory: URL
    private let lease: ProcessLease
    init() throws {
        lease = try NativeRenewalStorage.acquire()
        _ = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        let parent = PairingFileManager.protectedRoot
        try PrivateFileStore(root: parent).prepare()
        directory = parent.appendingPathComponent("incoming-" + UUID().uuidString, isDirectory: true)
        try PrivateFileStore(root: directory).prepare()
    }
    func importResult(_ device: MinimuxerPairedDevice) throws -> MinimuxerPairedDevice {
        let source = URL(fileURLWithPath: device.pairingFilePath).standardizedFileURL
        guard source.deletingLastPathComponent() == directory.standardizedFileURL else { throw PrivateFileError.unsafeFile }
        guard let bytes = try PrivateFileStore.readExternal(source) else { throw PrivateFileError.unavailable }
        let record = try PairingRecord(data: bytes, expected: .remote)
        _ = try PairingFileManager.shared.commit(record)
        PairingFileManager.shared.preferredProtocol = .rppairing
        return MinimuxerPairedDevice(name: device.name, model: device.model,
            pairingFilePath: PairingFileManager.shared.pairingFileURL(for: .rppairing).path)
    }
    deinit {
        // Only this session's random, protected staging directory is removed.
        try? FileManager.default.removeItem(at: directory)
        lease.release()
    }
}
