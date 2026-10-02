// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

public enum HTTPDownloadFailure: String, Error, LocalizedError, Sendable {
    case invalidURL, invalidLimit, alreadyStarted, invalidResponse, responseTooLarge
    case incompleteBody, tooManyRedirects, storageUnavailable, networkFailure
    public var errorDescription: String? { "Download failed: \(rawValue)." }
}

/// Validates both the initial URL and every redirect. Never accepts credentials
/// in a URL, HTTP downgrade, or a custom URL scheme handled by another app.
public struct HTTPDownloadPolicy: Sendable {
    public let maximumBytes: Int64
    public init(maximumBytes: Int64 = 1_073_741_824) throws {
        guard maximumBytes > 0, maximumBytes <= 1_073_741_824 else { throw HTTPDownloadFailure.invalidLimit }
        self.maximumBytes = maximumBytes
    }
    public func request(for url: URL) throws -> URLRequest {
        guard let parts = URLComponents(url: url, resolvingAgainstBaseURL: false),
              parts.scheme?.lowercased() == "https", let host = parts.host, !host.isEmpty,
              parts.user == nil, parts.password == nil, parts.fragment == nil,
              url.absoluteString.utf8.count <= 16_384 else { throw HTTPDownloadFailure.invalidURL }
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30)
        request.httpMethod = "GET"
        request.setValue("identity", forHTTPHeaderField: "Accept-Encoding")
        return request
    }
    public func expectedBytes(in response: URLResponse) throws -> Int64? {
        guard let http = response as? HTTPURLResponse, let url = http.url,
              http.statusCode == 200 else { throw HTTPDownloadFailure.invalidResponse }
        _ = try request(for: url)
        // An unsolicited partial body or multipart stream cannot become an IPA.
        guard http.value(forHTTPHeaderField: "Content-Range") == nil,
              http.mimeType?.lowercased().hasPrefix("multipart/") != true else {
            throw HTTPDownloadFailure.invalidResponse
        }
        if let encoding = http.value(forHTTPHeaderField: "Content-Encoding"),
           encoding.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() != "identity" {
            throw HTTPDownloadFailure.invalidResponse
        }
        guard let raw = http.value(forHTTPHeaderField: "Content-Length") else { return nil }
        let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty, value.utf8.allSatisfy({ (48...57).contains($0) }),
              let count = Int64(value) else { throw HTTPDownloadFailure.invalidResponse }
        guard count > 0 else { throw HTTPDownloadFailure.incompleteBody }
        guard count <= maximumBytes else { throw HTTPDownloadFailure.responseTooLarge }
        return count
    }
    public func adding(_ count: Int, to received: Int64, expected: Int64?) throws -> Int64 {
        guard count >= 0, received >= 0, Int64(count) <= maximumBytes,
              received <= maximumBytes - Int64(count) else { throw HTTPDownloadFailure.responseTooLarge }
        let total = received + Int64(count)
        if let expected, total > expected { throw HTTPDownloadFailure.incompleteBody }
        return total
    }
}

/// One-shot, ephemeral transfer. Data is bounded BEFORE each file write, even
/// with absent/forged Content-Length. An incomplete file is never returned.
/// Caller owns an already-created, private directory and removes successful
/// output when done. Failure/cancellation removes only this instance's file.
public final class BoundedHTTPDownload: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    private let mutex = NSLock()
    private var started = false
    private var cancelled = false
    private var finished = false
    private var continuation: CheckedContinuation<URL, Error>?
    private var session: URLSession?
    private var file: FileHandle?
    private var output: URL?
    private var policy: HTTPDownloadPolicy?
    private var expected: Int64?
    private var received: Int64 = 0
    private var acceptedResponse = false
    private var redirects = 0
    private let configuration: URLSessionConfiguration

    public override convenience init() { self.init(configuration: .ephemeral) }
    // Test-only URLProtocol injection; release callers use the public initializer.
    init(configuration: URLSessionConfiguration) {
        self.configuration = configuration.copy() as! URLSessionConfiguration
        super.init()
    }
    public func download(from url: URL, into directory: URL,
                         maximumBytes: Int64 = 1_073_741_824) async throws -> URL {
        let result: URL = try await withTaskCancellationHandler {
            try Task.checkCancellation()
            return try await withCheckedThrowingContinuation { continuation in
                begin(url: url, directory: directory, maximumBytes: maximumBytes, continuation: continuation)
            }
        } onCancel: { self.cancel() }
        // Cancellation may arrive just after the last delegate callback.
        if Task.isCancelled {
            try? FileManager.default.removeItem(at: result)
            throw CancellationError()
        }
        return result
    }
    public func cancel() {
        mutex.lock()
        cancelled = true
        mutex.unlock()
        finish(.failure(CancellationError()))
    }
    private func begin(url: URL, directory: URL, maximumBytes: Int64,
                       continuation: CheckedContinuation<URL, Error>) {
        mutex.lock()
        if started { mutex.unlock(); continuation.resume(throwing: HTTPDownloadFailure.alreadyStarted); return }
        started = true
        if cancelled { mutex.unlock(); continuation.resume(throwing: CancellationError()); return }
        self.continuation = continuation
        do {
            let policy = try HTTPDownloadPolicy(maximumBytes: maximumBytes)
            let request = try policy.request(for: url)
            guard directory.isFileURL else { throw HTTPDownloadFailure.storageUnavailable }
            let directoryFD = open(directory.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
            guard directoryFD >= 0 else { throw HTTPDownloadFailure.storageUnavailable }
            defer { _ = close(directoryFD) }
            let name = "download-" + UUID().uuidString + ".part"
            let descriptor = openat(directoryFD, name, O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW | O_CLOEXEC, mode_t(0o600))
            guard descriptor >= 0 else { throw HTTPDownloadFailure.storageUnavailable }
            let output = directory.appendingPathComponent(name)
            self.output = output
            self.file = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
            #if os(iOS) || os(tvOS)
            try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: output.path)
            #endif
            self.policy = policy
            // No shared cookies, auth cache, URL cache, automatic credential use,
            // resume data or persistent background transfer state.
            configuration.urlCache = nil
            configuration.httpCookieStorage = nil
            configuration.urlCredentialStorage = nil
            configuration.httpShouldSetCookies = false
            configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
            configuration.timeoutIntervalForRequest = 30
            configuration.timeoutIntervalForResource = 600
            configuration.httpMaximumConnectionsPerHost = 1
            let queue = OperationQueue()
            queue.maxConcurrentOperationCount = 1
            let session = URLSession(configuration: configuration, delegate: self, delegateQueue: queue)
            self.session = session
            let task = session.dataTask(with: request)
            mutex.unlock()
            // invalidateAndCancel also cancels a task not resumed yet.
            task.resume()
        } catch {
            mutex.unlock()
            finish(.failure(error is HTTPDownloadFailure ? error : HTTPDownloadFailure.storageUnavailable))
        }
    }
    public func urlSession(_ session: URLSession, dataTask: URLSessionDataTask,
                           didReceive response: URLResponse,
                           completionHandler: @escaping @Sendable (URLSession.ResponseDisposition) -> Void) {
        mutex.lock()
        do {
            guard !finished, let policy else { mutex.unlock(); completionHandler(.cancel); return }
            guard !acceptedResponse else { throw HTTPDownloadFailure.invalidResponse }
            expected = try policy.expectedBytes(in: response)
            acceptedResponse = true
            mutex.unlock()
            completionHandler(.allow)
        } catch {
            mutex.unlock()
            finish(.failure(error))
            completionHandler(.cancel)
        }
    }
    public func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        mutex.lock()
        guard !finished else { mutex.unlock(); return }
        do {
            guard acceptedResponse, let policy, let file else { throw HTTPDownloadFailure.invalidResponse }
            let total = try policy.adding(data.count, to: received, expected: expected)
            try file.write(contentsOf: data)
            received = total
            mutex.unlock()
        } catch {
            mutex.unlock()
            finish(.failure(error is HTTPDownloadFailure ? error : HTTPDownloadFailure.storageUnavailable))
        }
    }
    public func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if error != nil { finish(.failure(HTTPDownloadFailure.networkFailure)); return }
        mutex.lock()
        guard !finished else { mutex.unlock(); return }
        let complete = acceptedResponse && received > 0 && (expected == nil || expected == received)
        let destination = output
        mutex.unlock()
        if complete, let destination { finish(.success(destination)) }
        else { finish(.failure(HTTPDownloadFailure.incompleteBody)) }
    }
    public func urlSession(_ session: URLSession, task: URLSessionTask,
                           willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                           completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        mutex.lock()
        do {
            guard !finished, let policy else { mutex.unlock(); completionHandler(nil); return }
            guard redirects < 5 else { throw HTTPDownloadFailure.tooManyRedirects }
            guard !acceptedResponse, let url = request.url else { throw HTTPDownloadFailure.invalidResponse }
            // Reconstruct GET rather than forwarding cookies or authorization
            // to an attacker-selected redirect origin.
            let next = try policy.request(for: url)
            redirects += 1
            mutex.unlock()
            completionHandler(next)
        } catch {
            mutex.unlock()
            finish(.failure(error))
            completionHandler(nil)
        }
    }
    public func urlSession(_ session: URLSession, task: URLSessionTask,
                           didReceive challenge: URLAuthenticationChallenge,
                           completionHandler: @escaping @Sendable (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        #if canImport(Darwin)
        if challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust {
            completionHandler(.performDefaultHandling, nil)
            return
        }
        #endif
        // Public IPA downloads must not ask for Apple credentials, client keys
        // or reuse another session's HTTP authentication.
        completionHandler(.cancelAuthenticationChallenge, nil)
    }
    private func finish(_ proposed: Result<URL, Error>) {
        mutex.lock()
        guard started, !finished else { mutex.unlock(); return }
        finished = true
        var result = proposed
        if cancelled { result = .failure(CancellationError()) }
        if case .success = result {
            do { try file?.synchronize(); try file?.close() }
            catch { result = .failure(HTTPDownloadFailure.storageUnavailable) }
        }
        if case .failure = result {
            try? file?.close()
            if let output { try? FileManager.default.removeItem(at: output) }
        }
        file = nil
        let continuation = self.continuation
        self.continuation = nil
        let session = self.session
        self.session = nil
        mutex.unlock()
        session?.invalidateAndCancel()
        continuation?.resume(with: result)
    }
}
