// SPDX-License-Identifier: AGPL-3.0-only
// Production native cleanup method + production transfer ownership, real files.
// No URLSession/Apple file-coordination/device behavior is claimed here.
import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

enum OperationError: Error { case cacheClearError(errors: [String]) }
enum Injected: Error { case cancellation }

final class CacheClearProbe {
    let progress = Progress(totalUnitCount: 100)
    func setProgress(_ value: Int64) { progress.completedUnitCount = value }
    func debugLog(_ text: @autoclosure () -> String) {}
    func verboseLog(_ text: @autoclosure () -> String) {}
    func clear(_ directory: URL, check: () throws -> Void = {}) throws {
        try clearTempDirItems(at: directory, coordinatorError: nil, check: check)
    }
CLEANUP_METHOD_HERE
}

@main struct Main {
    static func exists(_ url: URL) -> Bool { FileManager.default.fileExists(atPath: url.path) }
    static func identity(_ url: URL) throws -> (UInt64, UInt64) {
        var info = stat()
        guard lstat(url.path, &info) == 0 else { throw CocoaError(.fileReadUnknown) }
        return (UInt64(info.st_dev), UInt64(info.st_ino))
    }
    static func main() throws {
        let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        let negativeControl = CommandLine.arguments.count > 2 && CommandLine.arguments[2] == "negative"
        let pool = root.appendingPathComponent("tetherless-oda-transfers-v1", isDirectory: true)
        let workspace = try TransferWorkspace(pool: pool, maximumBytes: 32)
        let file = workspace.directory.appendingPathComponent("download-" + UUID().uuidString + ".part")
        let bytes = Data("in-flight transfer".utf8)
        try bytes.write(to: file)
        let lock = pool.appendingPathComponent("usage.lock")
        let before = try identity(lock)
        let unknown = pool.appendingPathComponent("owner-metadata")
        try Data("preserve".utf8).write(to: unknown)

        let ordinary = root.appendingPathComponent("ordinary.tmp")
        try Data("remove".utf8).write(to: ordinary)
        let similarlyNamed = root.appendingPathComponent("tetherless-oda-transfers-v1-old", isDirectory: true)
        try FileManager.default.createDirectory(at: similarlyNamed, withIntermediateDirectories: false)
        try Data("remove".utf8).write(to: similarlyNamed.appendingPathComponent("nested.tmp"))
        let hidden = root.appendingPathComponent(".hidden-unrelated")
        try Data("keep original hidden-file semantics".utf8).write(to: hidden)

        try CacheClearProbe().clear(root)
        precondition(!exists(ordinary) && !exists(similarlyNamed))
        precondition(exists(hidden))

        if negativeControl {
            precondition(!exists(file) && !exists(lock), "negative control did not reproduce deleted active pool")
            // The old inode is still flock-owned, but deletion permits a second
            // descriptor to create a new inode and enter the same named pool.
            let competing = try TransferWorkspace(pool: pool, maximumBytes: 32)
            let replacement = try identity(lock)
            precondition(before.0 != replacement.0 || before.1 != replacement.1)
            try competing.finish()
            print("negative control reproduced active-pool deletion and replacement lock")
            return
        }

        let retained = try workspace.readOutput(file)
        precondition(retained == bytes && exists(unknown))
        let after = try identity(lock)
        precondition(before.0 == after.0 && before.1 == after.1)
        do {
            let other = try TransferWorkspace(pool: pool, maximumBytes: 32)
            try other.finish()
            preconditionFailure("generic cleanup permitted competing ownership")
        } catch LibraryCacheMaintenanceFailure.busy {}

        let cancelledFile = root.appendingPathComponent("cancelled-cleanup.tmp")
        try Data("keep".utf8).write(to: cancelledFile)
        do {
            try CacheClearProbe().clear(root, check: { throw Injected.cancellation })
            preconditionFailure("cancelled cleanup succeeded")
        } catch Injected.cancellation {}
        precondition(exists(cancelledFile) && exists(file))
        let afterCancellation = try identity(lock)
        precondition(afterCancellation.0 == before.0 && afterCancellation.1 == before.1)

        try workspace.finish()
        precondition(!exists(file) && exists(lock))
        let abandoned = pool.appendingPathComponent("transfer-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: abandoned, withIntermediateDirectories: false)
        let abandonedOutput = abandoned.appendingPathComponent("download-" + UUID().uuidString + ".part")
        try Data("interrupted".utf8).write(to: abandonedOutput)
        try CacheClearProbe().clear(root)
        precondition(exists(abandonedOutput) && exists(lock) && exists(unknown))
        precondition(!exists(cancelledFile))
        // Only normal TransferWorkspace admission reclaims recognized stages.
        let next = try TransferWorkspace(pool: pool, maximumBytes: 32)
        precondition(!exists(abandoned) && exists(unknown))
        let finalIdentity = try identity(lock)
        precondition(finalIdentity.0 == before.0 && finalIdentity.1 == before.1)
        try next.finish()
        print("ODA pool survives generic cleanup; active ownership and stable inode preserved")
    }
}
