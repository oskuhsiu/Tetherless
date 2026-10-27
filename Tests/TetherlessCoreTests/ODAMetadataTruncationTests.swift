// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore

@Suite("ODA preflight differential: Foundation-generated JSON and every truncation")
struct ODAMetadataTruncationTests {
    @Test func generatedObjectsAndEveryIncompletePrefix() throws {
        // No faked decoder response: Foundation produces valid JSON bytes, then
        // the actual production preflight inspects every incomplete prefix.
        let values: [Any] = [true, false, NSNull(), 0, -12, 1.25,
            "quote\" slash\\ line\n", "臺灣🌐", ["a": [1, 2, 3]], ["nested": ["item": "\u{0000}"]]]
        var rejected = 0
        for index in 0..<500 {
            let object: [String: Any] = ["servers": [], "extension": [
                "value": values[index % values.count], "index": index,
                "nested": [values[(index + 3) % values.count]]]]
            let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
            try ODAMetadata.validateStructure(data)
            for length in 0..<data.count {
                do {
                    try ODAMetadata.validateStructure(Data(data.prefix(length)))
                    Issue.record("Incomplete JSON passed the production preflight")
                } catch is ODAMetadataFailure { rejected += 1 }
            }
        }
        // Exact serialization length can differ across Foundation platforms.
        // Require the work actually ran, without assuming one OS's escaping.
        #expect(rejected >= 30_000)
    }
}
