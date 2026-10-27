// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore

@Suite("ODA JSON: real scanner/decoder, bounded structure and no silent fallback", .serialized)
struct ODAMetadataTests {
    private let sha = String(repeating: "a", count: 64)
    private func body(_ text: String) -> Data { Data(text.utf8) }
    private func package(_ fields: String) -> String { "{\"s\":\"\(sha)\",\(fields)}" }
    @Test func knownAliasesRetainPayloadAndDigest() throws {
        for key in ["l", "libraries", "data", "payload"] {
            let p = try ODAMetadata.decodePackage(body(package("\"\(key)\":\"UEsDBA==\"")))
            #expect(p.base64Payload == "UEsDBA==" && p.url == nil && p.sha256 == sha)
        }
        for key in ["s", "sha", "sha256"] {
            let p = try ODAMetadata.decodePackage(body("{\"\(key)\":\"\(sha.uppercased())\",\"url\":\"https://example.invalid/p.zip\"}"))
            #expect(p.url == "https://example.invalid/p.zip" && p.sha256 == sha)
        }
    }
    @Test func directCatalogAndRelativeReferenceAreDistinct() throws {
        let nested = "{\"servers\":[],\"oda\":\(package("\"l\":\"UEsDBA==\""))}"
        let doc = try ODAMetadata.decode(body(nested))
        #expect(!doc.isDirectPackage && doc.servers.isEmpty)
        guard case .package(let package) = doc.entry else { Issue.record("No nested package"); return }
        #expect(package.base64Payload == "UEsDBA==")
        let reference = try ODAMetadata.decode(body("{\"oda\":\"packages/oda.json\"}"))
        #expect(reference.entry == .reference("packages/oda.json"))
        let url = try ODAMetadata.resolveURL("packages/oda.json", relativeTo: URL(string: "https://example.invalid/list.json")!)
        #expect(url.absoluteString == "https://example.invalid/packages/oda.json")
        #expect(throws: ODAMetadataFailure.invalidSchema) { try ODAMetadata.decodePackage(body(nested)) }
    }
    @Test func serverListAndMissingODARemainCompatible() throws {
        for json in ["[]", "{\"servers\":[]}", "{\"oda\":null}"] {
            let result = try ODAMetadata.decode(body(json))
            #expect(result.servers.isEmpty && result.entry == nil)
        }
        let doc = try ODAMetadata.decode(body("[{\"name\":\"伺服器 🌐\",\"url\":\"https://example.invalid\",\"isHidden\":true}]"))
        #expect(doc.servers.count == 1 && doc.servers[0].isHidden)
        #expect(doc.servers[0].name == "伺服器 🌐")
    }
    @Test func relativeReferencesClampDotSegmentsAtTheAuthorityRoot() throws {
        let root = URL(string: "https://example.invalid/list.json")!
        let nested = URL(string: "https://example.invalid/catalog/v1/list.json?old=1")!
        let cases: [(String, URL, String)] = [
            ("../package.json", root, "https://example.invalid/package.json"),
            ("../../../package.json", root, "https://example.invalid/package.json"),
            ("./packages/../package.json", root, "https://example.invalid/package.json"),
            ("../package.json", nested, "https://example.invalid/catalog/package.json"),
            ("../../../../package.json", nested, "https://example.invalid/package.json"),
            ("/catalog/./../package.json", nested, "https://example.invalid/package.json"),
            ("https://other.invalid/a/../package.json", nested, "https://other.invalid/package.json"),
            ("//other.invalid/../package.json", nested, "https://other.invalid/package.json"),
            ("..", root, "https://example.invalid/"),
            ("../", root, "https://example.invalid/"),
            (".", nested, "https://example.invalid/catalog/v1/"),
            ("../packages/..", root, "https://example.invalid/"),
            ("../packages/.", root, "https://example.invalid/packages/"),
            ("../.package..json", root, "https://example.invalid/.package..json")
        ]
        for (raw, base, expected) in cases {
            let resolved = try ODAMetadata.resolveURL(raw, relativeTo: base)
            #expect(resolved.absoluteString == expected)
            #expect(resolved.baseURL == nil)
        }
    }
    @Test func pathNormalizationPreservesEscapesEmptySegmentsAndQueries() throws {
        let base = URL(string: "https://example.invalid/catalog/list.json?old=1")!
        let cases = [
            ("../../pkg%2Fname%20one.json?next=/a/../b&v=%2f%3F%23", "https://example.invalid/pkg%2Fname%20one.json?next=/a/../b&v=%2f%3F%23"),
            ("../../%2E%2E/package.json", "https://example.invalid/%2E%2E/package.json"),
            ("../../%252E%252E/package.json", "https://example.invalid/%252E%252E/package.json"),
            ("../../a//b.json?x=1&x=2", "https://example.invalid/a//b.json?x=1&x=2"),
            ("../../a//../b.json", "https://example.invalid/a/b.json"),
            ("../../package.json?", "https://example.invalid/package.json?"),
            ("?next=/a/../b&v=%2F", "https://example.invalid/catalog/list.json?next=/a/../b&v=%2F")
        ]
        for (raw, expected) in cases {
            #expect(try ODAMetadata.resolveURL(raw, relativeTo: base).absoluteString == expected)
        }
        #expect(try ODAMetadata.resolveURL("https://example.invalid").absoluteString == "https://example.invalid")
    }
    @Test func rawAndResolvedURLSizeLimitsRemainIndependent() throws {
        let prefix = "https://example.invalid/"
        let atLimit = prefix + String(repeating: "a", count: 16_384 - prefix.utf8.count)
        #expect(try ODAMetadata.resolveURL(atLimit).absoluteString == atLimit)
        for raw in [atLimit + "a", String(repeating: "a", count: 16_384)] {
            #expect(throws: ODAMetadataFailure.invalidURL) {
                try ODAMetadata.resolveURL(raw, relativeTo: URL(string: prefix)!)
            }
        }
    }
    @Test func duplicateAndEscapedEquivalentKeysRejectBeforeDecoder() {
        for json in ["{\"oda\":null,\"oda\":null}", #"{"servers":[],"serv\u0065rs":[]}"#,
                     "{\"oda\":{\"s\":\"\(sha)\",\"l\":\"AA==\",\"l\":\"BB==\"}}"] {
            #expect(throws: ODAMetadataFailure.duplicateKey) { try ODAMetadata.decode(body(json)) }
        }
    }
    @Test func multipleAliasesAndMixedEnvelopesAreNotSilentlySelected() {
        for json in [package("\"url\":\"https://example.invalid\",\"l\":\"AA==\""),
                     package("\"sha\":\"\(sha)\",\"l\":\"AA==\""),
                     package("\"l\":\"AA==\",\"oda\":null"),
                     "[{\"address\":\"https://a.invalid\",\"url\":\"https://b.invalid\"}]"] {
            #expect(throws: ODAMetadataFailure.ambiguous) { try ODAMetadata.decode(body(json)) }
        }
    }
    @Test func wrongTypesNeverBecomeEmptyOrMissing() {
        for json in ["{\"servers\":42}", "{\"servers\":[42]}", "{\"oda\":false}",
                     package("\"url\":123"), "{\"s\":42,\"l\":\"AA==\"}",
                     "[{\"address\":\"https://example.invalid\",\"isHidden\":\"false\"}]"] {
            #expect(throws: ODAMetadataFailure.invalidSchema) { try ODAMetadata.decode(body(json)) }
        }
    }
    @Test func nullAliasMayCoexistWithOneRealValue() throws {
        let result = try ODAMetadata.decodePackage(body(package("\"sha256\":null,\"url\":null,\"payload\":\"AA==\"")))
        #expect(result.base64Payload == "AA==")
    }
    @Test func unknownSmallFieldsAreBoundedButNotBreaking() throws {
        let result = try ODAMetadata.decode(body(#"{"servers":[],"future":{"a":[true,null,-1.25e+2,"a\"b\\c",{"b":"\uD83C\uDF10"}]}}"#))
        #expect(result.entry == nil)
    }
    @Test func rejectsBadGrammarAndTrailingDocuments() {
        for json in ["", "{", "[] []", "{\"servers\":[],}", "[true,]", "{\"servers\":[],\"v\":01}",
                     "{\"servers\":[],\"v\":-}", "{\"servers\":[],\"v\":1.}", "{\"servers\":[],\"v\":1e}",
                     "{\"servers\":[],\"v\":NaN}", "{\"servers\":[],\"v\":truex}", #"{"servers":[],"v":"\q"}"#] {
            #expect(throws: (any Error).self) { try ODAMetadata.decode(body(json)) }
        }
    }
    @Test func rejectsInvalidUnicodeEvenInIgnoredValues() {
        for text in [#"{"servers":[],"ignored":"\uD800"}"#, #"{"servers":[],"ignored":"\uDC00"}"#,
                     #"{"servers":[],"ignored":"\uD800\u0041"}"#] {
            #expect(throws: ODAMetadataFailure.malformed) { try ODAMetadata.decode(body(text)) }
        }
        for invalid: [UInt8] in [[0x80], [0xC0,0x80], [0xED,0xA0,0x80], [0xF4,0x90,0x80,0x80], [0xF0,0x9F]] {
            let json = body("{\"servers\":[],\"ignored\":\"") + Data(invalid) + body("\"}")
            #expect(throws: ODAMetadataFailure.malformed) { try ODAMetadata.decode(json) }
        }
    }
    @Test func exactDepthAndValueBudgetsAreEnforcedBeforeMaterialization() throws {
        var limits = ODAMetadata.Limits(); limits.depth = 3; limits.values = 4
        try ODAMetadata.validateStructure(body("[[[0]]]"), limits: limits)
        #expect(throws: ODAMetadataFailure.tooDeep) { try ODAMetadata.validateStructure(body("[[[[0]]]]"), limits: limits) }
        try ODAMetadata.validateStructure(body("[0,1,2]"), limits: limits)
        #expect(throws: ODAMetadataFailure.tooManyValues) { try ODAMetadata.validateStructure(body("[0,1,2,3]"), limits: limits) }
    }
    @Test func stringBudgetDistinguishesPayloadFromUnknownFields() throws {
        var limits = ODAMetadata.Limits(); limits.ordinaryStringBytes = 4; limits.payloadStringBytes = 8
        for json in ["{\"l\":\"12345678\"}", "{\"oda\":{\"data\":\"12345678\"}}"] {
            try ODAMetadata.validateStructure(body(json), limits: limits)
        }
        for json in ["{\"other\":\"12345\"}", "{\"l\":\"123456789\"}", "{\"x\":{\"l\":\"12345\"}}",
                     "{\"oda\":[{\"l\":\"12345\"}]}"] {
            #expect(throws: ODAMetadataFailure.stringTooLarge) { try ODAMetadata.validateStructure(body(json), limits: limits) }
        }
    }
    @Test func aggregateStringAndKeyBudgetsCannotBeBypassedWithEscapes() throws {
        var limits = ODAMetadata.Limits(); limits.allStringBytes = 8; limits.keyBytes = 2
        try ODAMetadata.validateStructure(body("{\"a\":\"1234567\"}"), limits: limits)
        #expect(throws: ODAMetadataFailure.stringTooLarge) { try ODAMetadata.validateStructure(body("{\"a\":\"1234\",\"b\":\"5678\"}"), limits: limits) }
        #expect(throws: ODAMetadataFailure.stringTooLarge) { try ODAMetadata.validateStructure(body(#"{"\u0061":0}"#), limits: limits) }
    }
    @Test func bodyArrayAndNumberLimitsApplyToIgnoredValues() throws {
        var limits = ODAMetadata.Limits(); limits.bytes = 2
        try ODAMetadata.validateStructure(body("[]"), limits: limits)
        #expect(throws: ODAMetadataFailure.tooLarge) { try ODAMetadata.validateStructure(body(" []"), limits: limits) }
        limits = ODAMetadata.Limits(); limits.arrayItems = 2
        #expect(throws: ODAMetadataFailure.tooManyValues) { try ODAMetadata.validateStructure(body("[0,1,2]"), limits: limits) }
        #expect(throws: ODAMetadataFailure.malformed) { try ODAMetadata.decode(body("{\"servers\":[],\"value\":\(String(repeating: "1", count: 65))}")) }
    }
    @Test func tooManyServersHaveAnExplicitFailure() {
        let server = "{\"url\":\"https://example.invalid\"}"
        let json = "[" + Array(repeating: server, count: 129).joined(separator: ",") + "]"
        #expect(throws: ODAMetadataFailure.tooManyServers) { try ODAMetadata.decode(body(json)) }
    }
    @Test func invalidAbsoluteAndRelativeURLsNeverUseFallback() {
        let base = URL(string:"https://example.invalid/source.json")!
        for raw in ["http://a.invalid", "file:///tmp/payload", "https://user:secret@a.invalid", "https://a.invalid/#secret", "\nhttps://a.invalid", "", "https://a.invalid/ path",
                    "../package.json#blocked", "//user@a.invalid/../package.json", "https://", "https://["] {
            #expect(throws: ODAMetadataFailure.invalidURL) { try ODAMetadata.resolveURL(raw, relativeTo: base) }
        }
    }
    @Test func errorsContainNoUntrustedSecretFields() {
        let secret = "SYNTHETIC_METADATA_SECRET_TOKEN"
        let invalid = package("\"url\":\"https://user:\(secret)@example.invalid\"")
        do { _ = try ODAMetadata.decode(body(invalid)); Issue.record("Accepted credential-bearing URL") }
        catch {
            #expect(error as? ODAMetadataFailure == .invalidURL)
            #expect(!String(reflecting: error).contains(secret))
            #expect(!error.localizedDescription.contains(secret))
            #expect(!(error as NSError).userInfo.description.contains(secret))
        }
    }
    @Test func cancellationRemainsCancellationAndReleasesDecodeAdmission() async throws {
        let data = body("{\"servers\":[]}")
        let task = Task {
            withUnsafeCurrentTask { $0?.cancel() }
            do { _ = try ODAMetadata.decode(data); Issue.record("Cancelled parse returned data") }
            catch is CancellationError { return }
            catch { Issue.record("Cancellation was converted to another error") }
        }
        await task.value
        let next = try ODAMetadata.decode(data)
        #expect(next.servers.isEmpty)
    }
}
