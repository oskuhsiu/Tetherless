// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Minimuxer

@available(iOS 17.0, tvOS 17.0, *)
struct NativeProfileTransport: ProfileBatchTransport {
    let deadline: ContinuousClock.Instant

    func checkBudget() throws {
        try Task.checkCancellation()
        guard ContinuousClock.now < deadline else { throw RenewalFailure.budgetExhausted }
    }

    func readInstalledProfileBytes() async throws -> [Data] {
        try checkBudget()
        #if targetEnvironment(simulator)
        // An upstream no-op must NEVER become deviceReadback evidence.
        throw RenewalFailure.unavailable
        #else
        let root = try NativeRenewalStorage.root()
            .appendingPathComponent("readback-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false,
                                                attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: root) }
        let dumped = try await minimuxer.core.dumpProfiles(docsPath: root.path, mode: .raw)
        try checkBudget()
        let location = URL(fileURLWithPath: dumped).standardizedFileURL
        guard location.path == root.path || location.path.hasPrefix(root.path + "/"),
              location.resolvingSymlinksInPath().path == location.path else {
            throw RenewalFailure.invalidEvidence
        }
        return try readDump(at: location)
        #endif
    }

    // DirectoryEnumerator is synchronous and must not cross an await boundary.
    // Keep it outside the async function so Swift 6's noasync contract is met.
    private func readDump(at location: URL) throws -> [Data] {
        var enumerationFailed = false
        guard let iterator = FileManager.default.enumerator(at: location,
                     includingPropertiesForKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey],
                     errorHandler: { _, _ in enumerationFailed = true; return false }) else {
            throw RenewalFailure.unavailable
        }
        var result: [Data] = []
        var total = 0
        for case let url as URL in iterator {
            let attributes = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
            guard attributes.isSymbolicLink != true else { throw RenewalFailure.invalidEvidence }
            guard attributes.isRegularFile == true else { continue }
            guard result.count < 4096, let data = try NativeRenewalStorage.read(url, maximum: 1_048_576) else {
                throw RenewalFailure.invalidEvidence
            }
            total += data.count
            guard total <= 33_554_432 else { throw RenewalFailure.invalidEvidence }
            result.append(data)
        }
        guard !enumerationFailed else { throw RenewalFailure.unavailable }
        return result
    }

    func installProfileBytes(_ bytes: Data) async throws {
        try checkBudget()
        #if targetEnvironment(simulator)
        throw RenewalFailure.unavailable
        #else
        try await minimuxer.core.installProvisioningProfile(profile: bytes)
        try checkBudget()
        #endif
    }
}
