// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore

private let epoch = Date(timeIntervalSince1970: 1_800_000_000)
private let digest = String(repeating: "a", count: 64)
private let components: Set<String> = ["test.app", "test.app.widget"]
private func part(_ id: String, _ value: UInt8, expiry: TimeInterval = 604_800) -> ProfileBatchPart {
    ProfileBatchPart(componentID: id, profileID: "00000000-0000-4000-8000-\(String(format: "%012d", Int(value)))",
                     bytes: Data([value]), expiry: epoch.addingTimeInterval(expiry))
}
private func batch(_ parts: [ProfileBatchPart]? = nil, certificateExpiry: TimeInterval = 1_000_000) -> ProfileBatch {
    ProfileBatch(bundleID: "test.app", identityDigest: digest,
                 previousExpiry: epoch.addingTimeInterval(500_000),
                 certificateExpiry: epoch.addingTimeInterval(certificateExpiry),
                 parts: parts ?? [part("test.app.widget", 2), part("test.app", 1)])
}
private actor Device: ProfileBatchTransport {
    var installed: [Data]
    var writes: [Data] = []
    var reads = 0
    var failOnWrite: Int?
    var dropWrites = false
    var failReads = false
    init(installed: [Data] = [], failOnWrite: Int? = nil, dropWrites: Bool = false, failReads: Bool = false) {
        self.installed = installed; self.failOnWrite = failOnWrite
        self.dropWrites = dropWrites; self.failReads = failReads
    }
    func readInstalledProfileBytes() throws -> [Data] {
        reads += 1
        if failReads { throw ProfileBatchFailure.readbackMismatch }
        return installed
    }
    func installProfileBytes(_ bytes: Data) throws {
        if let failOnWrite, writes.count == failOnWrite {
            self.failOnWrite = nil
            throw ProfileBatchFailure.readbackMismatch
        }
        writes.append(bytes)
        if !dropWrites { installed.append(bytes) }
    }
}

@Suite("Prepared profile batches (scripted transport, not iOS evidence)")
struct ProfileBatchTests {
    @Test func mainFirstAndReadbackRequired() async throws {
        let device = Device()
        let expiry = try await ProfileBatchExecutor.applyMissing(batch(), requiredComponents: components,
                         identityDigest: digest, transport: device, now: { epoch })
        #expect(expiry == epoch.addingTimeInterval(604_800))
        #expect(await device.writes == [Data([1]), Data([2])])
        #expect(await device.reads == 2)
    }
    @Test func resumeOnlyMissingAfterPartialFailure() async throws {
        let device = Device(failOnWrite: 1)
        await #expect(throws: ProfileBatchFailure.self) {
            try await ProfileBatchExecutor.applyMissing(batch(), requiredComponents: components,
                         identityDigest: digest, transport: device, now: { epoch })
        }
        _ = try await ProfileBatchExecutor.applyMissing(batch(), requiredComponents: components,
                         identityDigest: digest, transport: device, now: { epoch })
        #expect(await device.writes == [Data([1]), Data([2])])
    }
    @Test func installedBatchIsReconciledWithoutWriting() async throws {
        let device = Device(installed: [Data([1]), Data([2])])
        _ = try await ProfileBatchExecutor.applyMissing(batch(), requiredComponents: components,
                         identityDigest: digest, transport: device, now: { epoch })
        #expect(await device.writes.isEmpty)
        #expect(await device.reads == 2)
    }
    @Test func transportSuccessWithoutMatchingReadbackFails() async {
        let device = Device(dropWrites: true)
        await #expect(throws: ProfileBatchFailure.readbackMismatch) {
            try await ProfileBatchExecutor.applyMissing(batch(), requiredComponents: components,
                         identityDigest: digest, transport: device, now: { epoch })
        }
    }
    @Test func failedInitialReadbackNeverWrites() async {
        let device = Device(failReads: true)
        await #expect(throws: ProfileBatchFailure.self) {
            try await ProfileBatchExecutor.applyMissing(batch(), requiredComponents: components,
                         identityDigest: digest, transport: device, now: { epoch })
        }
        #expect(await device.writes.isEmpty)
    }
    @Test func missingExtensionRejectedBeforeAnyWrite() async {
        let device = Device()
        await #expect(throws: ProfileBatchFailure.invalidPlan) {
            try await ProfileBatchExecutor.applyMissing(batch([part("test.app", 1)]), requiredComponents: components,
                         identityDigest: digest, transport: device, now: { epoch })
        }
        #expect(await device.writes.isEmpty)
        #expect(await device.reads == 0)
    }
    @Test func changedIdentityRejectedBeforeReadback() async {
        let device = Device()
        await #expect(throws: ProfileBatchFailure.identityChanged) {
            try await ProfileBatchExecutor.applyMissing(batch(), requiredComponents: components,
                         identityDigest: String(repeating: "b", count: 64), transport: device, now: { epoch })
        }
        #expect(await device.reads == 0)
    }
    @Test func certificateCapsExpiry() async throws {
        let expiry = try await ProfileBatchExecutor.applyMissing(batch(certificateExpiry: 550_000), requiredComponents: components,
                         identityDigest: digest, transport: Device(), now: { epoch })
        #expect(expiry == epoch.addingTimeInterval(550_000))
    }
    @Test func unchangedExtensionPreventsFalseSuccess() throws {
        #expect(throws: ProfileBatchFailure.expiredPlan) {
            try batch([part("test.app", 1), part("test.app.widget", 2, expiry: 500_000)])
                .validate(requiredComponents: components, identityDigest: digest, now: epoch)
        }
    }
    @Test func changedBytesWithSameIDAreNotReadbackEvidence() async throws {
        let device = Device(installed: [Data([9]), Data([2])])
        _ = try await ProfileBatchExecutor.applyMissing(batch(), requiredComponents: components,
                         identityDigest: digest, transport: device, now: { epoch })
        #expect(await device.writes == [Data([1])])
    }
    @Test func duplicateAndOversizedPayloadsRejected() {
        #expect(throws: ProfileBatchFailure.invalidPlan) {
            try batch([part("test.app", 1), part("test.app.widget", 1)])
                .validate(requiredComponents: components, identityDigest: digest, now: epoch)
        }
        #expect(throws: ProfileBatchFailure.invalidPlan) {
            let big = ProfileBatchPart(componentID: "test.app", profileID: UUID().uuidString,
                          bytes: Data(repeating: 1, count: 1_048_577), expiry: epoch.addingTimeInterval(604_800))
            try batch([big, part("test.app.widget", 2)])
                .validate(requiredComponents: components, identityDigest: digest, now: epoch)
        }
    }
    @Test func persistedBatchRoundTripsWithoutChangingBytes() throws {
        let original = batch()
        #expect(try JSONDecoder().decode(ProfileBatch.self, from: JSONEncoder().encode(original)) == original)
    }
}
