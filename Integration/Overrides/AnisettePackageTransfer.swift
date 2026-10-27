// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// A single in-flight public ODA transfer per container, including final read.
/// Process-killed downloads are reclaimed on the next admission, never while
/// another owner still holds the stable pool lock. No account cookies/auth.
func boundedODAPackageData(from url: URL, maximumBytes: Int) async throws -> Data {
    _ = try ODAHTTPDownloadPolicy(maximumBytes: Int64(maximumBytes)).request(for: url)
    try Task.checkCancellation()
    let pool = FileManager.default.temporaryDirectory.appendingPathComponent("tetherless-oda-transfers-v1", isDirectory: true)
    let workspace = try TransferWorkspace(pool: pool, maximumBytes: maximumBytes)
    defer { try? workspace.finish() }
    let file = try await BoundedODAHTTPDownload().download(from: url, into: workspace.directory, maximumBytes: Int64(maximumBytes))
    try Task.checkCancellation()
    let data = try workspace.readOutput(file)
    try Task.checkCancellation()
    // Do not report a successful transfer if normal cleanup failed.
    try workspace.finish()
    try Task.checkCancellation()
    return data
}
