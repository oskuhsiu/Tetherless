// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore

@Suite("Post-extraction dependency downloads cannot bypass IPA validation")
struct DependencyManifestTests {
    @Test func emptyAndAbsentAreAllowed() throws {
        for object: [String: Any] in [[:], ["ALTDependencies": []]] {
            for format: PropertyListSerialization.PropertyListFormat in [.xml, .binary] {
                try DependencyManifestPolicy.validate(PropertyListSerialization.data(fromPropertyList: object, format: format, options: 0))
            }
        }
    }
    @Test(arguments: ["../../outside", "Info.plist", "bin", "Resources/file"])
    func remoteInjectionAlwaysRequiresSelfContainedIPA(_ path: String) throws {
        let data = try PropertyListSerialization.data(fromPropertyList: ["ALTDependencies": [["path": path, "downloadURL": "https://fixture.invalid/secret"]]], format: .xml, options: 0)
        #expect(throws: DependencyManifestFailure.remoteDependenciesUnsupported) { try DependencyManifestPolicy.validate(data) }
    }
    @Test func malformedOrOversizedCannotBecomeEmpty() throws {
        for data in [Data(), Data(repeating: 65, count: 262_145), Data("<!DOCTYPE plist [<!ENTITY a 'boom'>]><plist><dict/></plist>".utf8)] {
            #expect(throws: DependencyManifestFailure.invalidManifest) { try DependencyManifestPolicy.validate(data) }
        }
        let data = try PropertyListSerialization.data(fromPropertyList: ["ALTDependencies": "none"], format: .binary, options: 0)
        #expect(throws: DependencyManifestFailure.invalidManifest) { try DependencyManifestPolicy.validate(data) }
    }
}
