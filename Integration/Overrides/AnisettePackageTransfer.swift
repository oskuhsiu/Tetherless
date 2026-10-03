// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// Public library/metadata downloads never borrow account cookies or auth.
/// A fresh private workspace is removed on success/failure/cancellation.
func boundedODAPackageData(from url: URL, maximumBytes: Int) async throws -> Data {
    _ = try ODAHTTPDownloadPolicy(maximumBytes: Int64(maximumBytes)).request(for: url)
    try Task.checkCancellation()
    let fm = FileManager.default
    let directory = fm.temporaryDirectory.appendingPathComponent("tetherless-oda-" + UUID().uuidString, isDirectory: true)
    try fm.createDirectory(at: directory, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
    defer { try? fm.removeItem(at: directory) }
    #if os(iOS) || os(tvOS)
    try fm.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: directory.path)
    #endif
    let file = try await BoundedODAHTTPDownload().download(from: url, into: directory, maximumBytes: Int64(maximumBytes))
    try Task.checkCancellation()
    // Downloader bounds every write. Independently limit the final read too.
    let handle = try FileHandle(forReadingFrom: file)
    defer { try? handle.close() }
    let data = try handle.read(upToCount: maximumBytes + 1) ?? Data()
    guard !data.isEmpty, data.count <= maximumBytes else { throw AnisettePackageFailure.payloadTooLarge }
    try Task.checkCancellation()
    return data
}
