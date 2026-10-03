// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif
@testable import TetherlessCore

@Suite("Cache reclamation: real no-follow IO and shared/exclusive descriptors")
struct LibraryCacheMaintenanceTests {
    private let fm = FileManager.default
    private enum Injected: Error { case unreadable }
    private func fixture(_ run: (URL) throws -> Void) throws {
        let root = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try fm.createDirectory(at: root, withIntermediateDirectories: false)
        defer { try? fm.removeItem(at: root) }
        try run(root)
    }
    private func directory(_ root: URL, _ prefix: String) throws -> URL {
        let url = root.appendingPathComponent(prefix + UUID().uuidString)
        try fm.createDirectory(at: url.appendingPathComponent("payload"), withIntermediateDirectories: true)
        try Data("synthetic payload".utf8).write(to: url.appendingPathComponent("payload/item"))
        return url
    }
    @Test func sharedOwnersDeferCleanupWithoutReadingOrDeleting() throws {
        try fixture { root in
            let old = try directory(root, "version-")
            var first: LibraryCacheUsage? = try LibraryCacheUsage.acquire(in: root)
            var second: LibraryCacheUsage? = try LibraryCacheUsage.acquire(in: root)
            #expect(first != nil && second != nil)
            #expect(try !LibraryCacheMaintenance.reclaim(in: root) { Issue.record("Read while pinned"); return nil })
            #expect(fm.fileExists(atPath: old.path))
            first = nil
            #expect(try !LibraryCacheMaintenance.reclaim(in: root) { nil })
            second = nil
            #expect(try LibraryCacheMaintenance.reclaim(in: root) { nil })
            #expect(!fm.fileExists(atPath: old.path))
        }
    }
    @Test func preservesCurrentReceiptLockAndUnknownNames() throws {
        try fixture { root in
            let current = try directory(root, "version-")
            let old = try directory(root, "version-")
            let stage = try directory(root, "stage-")
            let partialReceipt = root.appendingPathComponent(".staging-" + UUID().uuidString)
            try Data("incomplete".utf8).write(to: partialReceipt)
            let receipt = root.appendingPathComponent("current.json")
            try Data("receipt fixture".utf8).write(to: receipt)
            let unrelated = root.appendingPathComponent("version-not-a-uuid")
            try Data("preserve".utf8).write(to: unrelated)
            #expect(try LibraryCacheMaintenance.reclaim(in: root) { current.lastPathComponent })
            #expect(fm.fileExists(atPath: current.path))
            #expect(!fm.fileExists(atPath: old.path) && !fm.fileExists(atPath: stage.path))
            #expect(!fm.fileExists(atPath: partialReceipt.path))
            #expect(try Data(contentsOf: receipt) == Data("receipt fixture".utf8))
            #expect(fm.fileExists(atPath: unrelated.path) && fm.fileExists(atPath: root.appendingPathComponent("usage.lock").path))
        }
    }
    @Test func failedReceiptValidationNeverDeletesCandidates() throws {
        try fixture { root in
            let old = try directory(root, "version-")
            #expect(throws: Injected.unreadable) {
                try LibraryCacheMaintenance.reclaim(in: root) { throw Injected.unreadable }
            }
            #expect(fm.fileExists(atPath: old.path))
            #expect(throws: LibraryCacheMaintenanceFailure.unsafeFile) {
                try LibraryCacheMaintenance.reclaim(in: root) { "../../not-a-generation" }
            }
            #expect(fm.fileExists(atPath: old.path))
        }
    }
    @Test func linksAndSpecialFilesFailPreflightBeforeAnyRemoval() throws {
        for kind in 0..<3 {
            try fixture { root in
                let good = try directory(root, "stage-")
                let bad = try directory(root, "stage-")
                let outside = root.appendingPathComponent("outside")
                try Data("keep".utf8).write(to: outside)
                let target = bad.appendingPathComponent("unsafe")
                if kind == 0 { try fm.createSymbolicLink(at: target, withDestinationURL: outside) }
                else if kind == 1 { try fm.linkItem(at: outside, to: target) }
                else { #expect(mkfifo(target.path, 0o600) == 0) }
                #expect(throws: LibraryCacheMaintenanceFailure.unsafeFile) {
                    try LibraryCacheMaintenance.reclaim(in: root) { nil }
                }
                #expect(fm.fileExists(atPath: good.appendingPathComponent("payload/item").path))
                #expect(try Data(contentsOf: outside) == Data("keep".utf8))
            }
        }
    }
    @Test func lockSymlinkAndHardlinkAreRejected() throws {
        try fixture { root in
            let other = root.appendingPathComponent("other")
            let lock = root.appendingPathComponent("usage.lock")
            try Data().write(to: other)
            try fm.createSymbolicLink(at: lock, withDestinationURL: other)
            #expect(throws: LibraryCacheMaintenanceFailure.unsafeFile) { try LibraryCacheUsage.acquire(in: root) }
            try fm.removeItem(at: lock); try fm.linkItem(at: other, to: lock)
            #expect(throws: LibraryCacheMaintenanceFailure.unsafeFile) { try LibraryCacheUsage.acquire(in: root) }
        }
    }
    @Test func exclusiveOwnerRejectsNewReaderAndNeverReplacesLockInode() throws {
        try fixture { root in
            let path = root.appendingPathComponent("usage.lock").path
            var writer: LibraryCacheUsage? = try LibraryCacheUsage.acquire(in: root, exclusive: true)
            #expect(writer != nil)
            var before = stat(); #expect(lstat(path, &before) == 0)
            #expect(throws: LibraryCacheMaintenanceFailure.busy) { try LibraryCacheUsage.acquire(in: root) }
            writer = nil
            #expect(try LibraryCacheMaintenance.reclaim(in: root) { nil })
            var after = stat(); #expect(lstat(path, &after) == 0)
            #expect(before.st_dev == after.st_dev && before.st_ino == after.st_ino)
        }
    }
    @Test func partialAbandonedTreeCanBeReclaimedAgain() throws {
        try fixture { root in
            let stage = try directory(root, "stage-")
            try fm.removeItem(at: stage.appendingPathComponent("payload/item"))
            #expect(try LibraryCacheMaintenance.reclaim(in: root) { nil })
            #expect(try LibraryCacheMaintenance.reclaim(in: root) { nil })
            #expect(!fm.fileExists(atPath: stage.path))
        }
    }
    @Test func asynchronousOwnerRetainsTheRealUsageDescriptor() async throws {
        let root = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try fm.createDirectory(at: root, withIntermediateDirectories: false)
        defer { try? fm.removeItem(at: root) }
        let usage = try LibraryCacheUsage.acquire(in: root)
        let task = Task { [usage] in
            defer { withExtendedLifetime(usage) {} }
            try await Task.sleep(for: .milliseconds(30))
            return try LibraryCacheMaintenance.reclaim(in: root) { nil }
        }
        #expect(try await !task.value)
        withExtendedLifetime(usage) {}
    }
    #if os(macOS) || os(Linux)
    @Test func independentProcessCannotTakeExclusiveOwnershipWhilePinned() throws {
        try fixture { root in
            func attempt() throws -> String {
                let process = Process(); process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
                process.arguments = ["python3", "-c", "import fcntl,sys\nf=open(sys.argv[1], 'r+')\ntry:\n fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);print('acquired')\nexcept BlockingIOError:\n print('busy')", root.appendingPathComponent("usage.lock").path]
                let output = Pipe(); process.standardOutput = output
                try process.run(); process.waitUntilExit()
                #expect(process.terminationStatus == 0)
                return String(decoding: output.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
            }
            var usage: LibraryCacheUsage? = try LibraryCacheUsage.acquire(in: root)
            #expect(usage != nil)
            #expect(try attempt() == "busy\n")
            usage = nil
            #expect(try attempt() == "acquired\n")
        }
    }
    #endif

}
