// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore

private let epoch = Date(timeIntervalSince1970: 1_800_000_000)
private let digest = String(repeating: "a", count: 64)
private let components: Set<String> = ["test.app", "test.app.widget"]
private func batch() -> ProfileBatch {
    ProfileBatch(bundleID: "test.app", identityDigest: digest,
        previousExpiry: epoch.addingTimeInterval(500_000), certificateExpiry: epoch.addingTimeInterval(1_000_000),
        parts: [ProfileBatchPart(componentID: "test.app", profileID: "00000000-0000-4000-8000-000000000001",
                                bytes: Data([1]), expiry: epoch.addingTimeInterval(604_800)),
                ProfileBatchPart(componentID: "test.app.widget", profileID: "00000000-0000-4000-8000-000000000002",
                                bytes: Data([2]), expiry: epoch.addingTimeInterval(604_800))])
}
private actor SnapshotTransport: ProfileBatchTransport {
    private var count = 0
    private(set) var writes: [Data] = []
    let cancelOnReadback: Bool
    let missingExtension: Bool
    init(cancelOnReadback: Bool = false, missingExtension: Bool = false) {
        self.cancelOnReadback = cancelOnReadback; self.missingExtension = missingExtension
    }
    func readInstalledProfileBytes() throws -> [Data] {
        count += 1
        if count == 1 { return [Data([9])] }
        guard count == 2 else { throw ProfileBatchFailure.readbackMismatch }
        if cancelOnReadback { withUnsafeCurrentTask { $0?.cancel() } }
        return missingExtension ? [Data([1])] : [Data([9]), Data([2]), Data([1])]
    }
    func installProfileBytes(_ bytes: Data) { writes.append(bytes) }
    func readCount() -> Int { count }
}

@Suite("Native-consumable readback: one exact post-apply transport snapshot")
struct ProfileBatchReadbackTests {
    @Test func returnsExactVerifiedSnapshotWithoutThirdDump() async throws {
        let device = SnapshotTransport()
        let result = try await ProfileBatchExecutor.applyMissingAndReadback(batch(),
            requiredComponents: components, identityDigest: digest, transport: device, now: { epoch })
        #expect(result.installedProfiles == [Data([9]), Data([2]), Data([1])])
        #expect(result.newExpiry == epoch.addingTimeInterval(604_800))
        #expect(await device.readCount() == 2)
        #expect(await device.writes == [Data([1]), Data([2])])
    }
    @Test func cancellationDuringFinalReadCannotReturnSuccess() async throws {
        let device = SnapshotTransport(cancelOnReadback: true)
        let task = Task {
            try await ProfileBatchExecutor.applyMissingAndReadback(batch(),
                requiredComponents: components, identityDigest: digest, transport: device, now: { epoch })
        }
        await #expect(throws: CancellationError.self) { try await task.value }
        #expect(await device.readCount() == 2)
    }
    @Test func returnedReadbackCannotOmitAnExtension() async throws {
        let device = SnapshotTransport(missingExtension: true)
        await #expect(throws: ProfileBatchFailure.readbackMismatch) {
            try await ProfileBatchExecutor.applyMissingAndReadback(batch(), requiredComponents: components,
                identityDigest: digest, transport: device, now: { epoch })
        }
    }
}
