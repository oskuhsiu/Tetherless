// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore

@Suite("Identifier path boundaries")
struct IdentifierTests {
    @Test func pathEscapesAndMissingMainAreRejected() throws {
        for id in ["", "..", "test..app", "test/app", "/tmp/app", "test\\app", "test.app\u{0}", String(repeating: "x", count: 256)] {
            #expect(!ManagedBundleIdentifier.isSafe(id))
        }
        #expect(ManagedBundleIdentifier.isSafe("test.app-1_widget"))
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let identity = String(repeating: "a", count: 64)
        let part = ProfileBatchPart(componentID: "test.app.widget", profileID: UUID().uuidString,
                                    bytes: Data([1]), expiry: now.addingTimeInterval(600_000))
        let batch = ProfileBatch(bundleID: "test.app", identityDigest: identity, previousExpiry: now,
                                 certificateExpiry: now.addingTimeInterval(900_000), parts: [part])
        #expect(throws: ProfileBatchFailure.invalidPlan) {
            try batch.validate(requiredComponents: ["test.app.widget"], identityDigest: identity, now: now)
        }
    }
}
