// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import Testing
@testable import TetherlessCore

@Suite("HTTP input policy")
struct HTTPPolicyTests {
    @Test(arguments: ["http://example.com/a.ipa", "file:///tmp/a", "ftp://example.com/a", "https://u:p@example.com/a", "https://example.com/a#fragment"])
    func rejectsUnsafeURLs(_ input: String) throws {
        let policy = try HTTPDownloadPolicy()
        #expect(throws: HTTPDownloadFailure.invalidURL) { try policy.request(for: URL(string: input)!) }
    }
    @Test func requestsDoNotCarryCredentials() throws {
        let request = try HTTPDownloadPolicy().request(for: URL(string: "https://example.com/a?signature=test")!)
        #expect(request.httpMethod == "GET")
        #expect(request.value(forHTTPHeaderField: "Authorization") == nil)
        #expect(request.value(forHTTPHeaderField: "Cookie") == nil)
        #expect(request.value(forHTTPHeaderField: "Accept-Encoding") == "identity")
    }
    @Test(arguments: [204, 206, 301, 401, 403, 404, 429, 500])
    func nonFullSuccessfulResponseRejected(_ status: Int) throws {
        let response = HTTPURLResponse(url: URL(string: "https://example.com/a")!, statusCode: status, httpVersion: nil, headerFields: nil)!
        #expect(throws: HTTPDownloadFailure.invalidResponse) { try HTTPDownloadPolicy().expectedBytes(in: response) }
    }
    @Test func headerAndActualBudgetsAreIndependent() throws {
        let policy = try HTTPDownloadPolicy(maximumBytes: 100)
        let response = HTTPURLResponse(url: URL(string: "https://example.com/a")!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Length": "101"])!
        #expect(throws: HTTPDownloadFailure.responseTooLarge) { try policy.expectedBytes(in: response) }
        #expect(try policy.adding(100, to: 0, expected: nil) == 100)
        #expect(throws: HTTPDownloadFailure.responseTooLarge) { try policy.adding(1, to: 100, expected: nil) }
        #expect(throws: HTTPDownloadFailure.incompleteBody) { try policy.adding(10, to: 0, expected: 3) }
        #expect(throws: HTTPDownloadFailure.responseTooLarge) { try policy.adding(Int.max, to: 1, expected: nil) }
    }
    @Test(arguments: ["-1", "1, 2", "+10", "n/a", "9999999999999999999999999"])
    func malformedLengthRejected(_ value: String) throws {
        let response = HTTPURLResponse(url: URL(string: "https://example.com/a")!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Length": value])!
        #expect(throws: HTTPDownloadFailure.invalidResponse) { try HTTPDownloadPolicy().expectedBytes(in: response) }
    }
    @Test func compressedAndPartialBodiesAreNotAccepted() throws {
        for headers in [["Content-Encoding": "gzip"], ["Content-Range": "bytes 0-9/100"], ["Content-Type": "multipart/x-mixed-replace"]] {
            let response = HTTPURLResponse(url: URL(string: "https://example.com/a")!, statusCode: 200, httpVersion: nil, headerFields: headers)!
            #expect(throws: HTTPDownloadFailure.invalidResponse) { try HTTPDownloadPolicy().expectedBytes(in: response) }
        }
    }
}

/// Injects HTTP response/chunks through the real URLSession callback machinery.
/// This is NOT a live internet/TLS test; file IO and cancellation are real.
private final class DownloadFixtureProtocol: URLProtocol, @unchecked Sendable {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        guard let url = request.url else { return }
        let scenario = url.pathComponents.dropFirst().first ?? "ok"
        var headers: [String: String] = [:]
        var chunks = [Data("abc".utf8), Data("def".utf8)]
        var status = 200
        switch scenario {
        case "ok": headers["Content-Length"] = "6"
        case "unknown": break
        case "largeHeader": headers["Content-Length"] = "5000"
        case "largeBody": chunks = [Data(repeating: 65, count: 60), Data(repeating: 66, count: 60)]
        case "forged": headers["Content-Length"] = "2"
        case "truncated": headers["Content-Length"] = "10"
        case "status": status = 500
        case "empty": chunks = []
        case "stall": chunks = []
        case "disconnected": break
        default: break
        }
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1", headerFields: headers)!, cacheStoragePolicy: .notAllowed)
        for data in chunks { client?.urlProtocol(self, didLoad: data) }
        if scenario == "stall" { return }
        if scenario == "disconnected" {
            client?.urlProtocol(self, didFailWithError: URLError(.networkConnectionLost))
        } else { client?.urlProtocolDidFinishLoading(self) }
    }
    override func stopLoading() {}
}

@Suite("Bounded downloader: scripted HTTP, real URLSession and files")
struct HTTPTransferTests {
    private func directory() throws -> URL {
        let dir = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        return dir
    }
    private func transfer() -> BoundedHTTPDownload {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [DownloadFixtureProtocol.self]
        return BoundedHTTPDownload(configuration: configuration)
    }
    private func source(_ scenario: String) -> URL { URL(string: "https://fixture.invalid/\(scenario)/\(UUID().uuidString)")! }
    @Test(arguments: ["ok", "unknown"])
    func streamsCompletedFile(_ scenario: String) async throws {
        let directory = try directory()
        defer { try? FileManager.default.removeItem(at: directory) }
        let downloader = transfer()
        let output = try await downloader.download(from: source(scenario), into: directory, maximumBytes: 100)
        #expect(try Data(contentsOf: output) == Data("abcdef".utf8))
        let permissions = try FileManager.default.attributesOfItem(atPath: output.path)[.posixPermissions] as? NSNumber
        #expect(permissions?.intValue == 0o600)
        await #expect(throws: HTTPDownloadFailure.alreadyStarted) {
            try await downloader.download(from: source("ok"), into: directory, maximumBytes: 100)
        }
    }
    @Test(arguments: ["largeHeader", "largeBody", "forged", "truncated", "status", "empty", "disconnected"])
    func failedTransfersDoNotPublishPartialOutput(_ scenario: String) async throws {
        let directory = try directory()
        defer { try? FileManager.default.removeItem(at: directory) }
        // A failure must not delete unrelated files in the caller-owned directory.
        let sentinel = directory.appendingPathComponent("keep")
        try Data("keep".utf8).write(to: sentinel)
        await #expect(throws: HTTPDownloadFailure.self) {
            try await transfer().download(from: source(scenario), into: directory, maximumBytes: 100)
        }
        #expect(try FileManager.default.contentsOfDirectory(atPath: directory.path) == ["keep"])
        #expect(try String(contentsOf: sentinel, encoding: .utf8) == "keep")
    }
    @Test func cancellationBeforeStartCannotHangOrCreateAFile() async throws {
        let directory = try directory()
        defer { try? FileManager.default.removeItem(at: directory) }
        let downloader = transfer()
        downloader.cancel()
        await #expect(throws: CancellationError.self) {
            try await downloader.download(from: source("ok"), into: directory)
        }
        #expect(try FileManager.default.contentsOfDirectory(atPath: directory.path).isEmpty)
    }
    @Test func swiftTaskCancellationStopsAnActiveTransfer() async throws {
        let directory = try directory()
        defer { try? FileManager.default.removeItem(at: directory) }
        let downloader = transfer()
        let task = Task { try await downloader.download(from: source("stall"), into: directory) }
        var sawFile = false
        for _ in 0..<500 {
            if !(try FileManager.default.contentsOfDirectory(atPath: directory.path)).isEmpty { sawFile = true; break }
            try await Task.sleep(for: .milliseconds(2))
        }
        task.cancel()
        await #expect(throws: CancellationError.self) { try await task.value }
        #expect(sawFile)
        #expect(try FileManager.default.contentsOfDirectory(atPath: directory.path).isEmpty)
    }
    @Test func unsafeURLRejectedBeforeCreatingOutput() async throws {
        let directory = try directory()
        defer { try? FileManager.default.removeItem(at: directory) }
        await #expect(throws: HTTPDownloadFailure.invalidURL) {
            try await transfer().download(from: URL(string: "http://fixture.invalid/ok")!, into: directory)
        }
        #expect(try FileManager.default.contentsOfDirectory(atPath: directory.path).isEmpty)
    }
    @Test func parentSymlinkCannotRedirectOutput() async throws {
        let directory = try directory()
        defer { try? FileManager.default.removeItem(at: directory) }
        let target = directory.appendingPathComponent("target")
        let alias = directory.appendingPathComponent("alias")
        try FileManager.default.createDirectory(at: target, withIntermediateDirectories: false)
        try FileManager.default.createSymbolicLink(at: alias, withDestinationURL: target)
        await #expect(throws: HTTPDownloadFailure.storageUnavailable) {
            try await transfer().download(from: source("ok"), into: alias)
        }
        #expect(try FileManager.default.contentsOfDirectory(atPath: target.path).isEmpty)
    }
}
