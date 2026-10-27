// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif
@testable import TetherlessCore

@Suite("ODA transfer workspaces: real IO and ownership, no network")
struct TransferWorkspaceTests {
    let fm = FileManager.default
    func fixture(_ run: (URL) throws -> Void) throws {
        let parent = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try fm.createDirectory(at: parent, withIntermediateDirectories: false)
        defer { try? fm.removeItem(at: parent) }
        try run(parent.appendingPathComponent("pool"))
    }
    func output(_ directory: URL, data: Data = Data("body".utf8)) throws -> URL {
        let url = directory.appendingPathComponent("download-" + UUID().uuidString + ".part")
        try data.write(to: url)
        return url
    }
    func abandoned(_ pool: URL) throws -> URL {
        try fm.createDirectory(at: pool, withIntermediateDirectories: true)
        let url = pool.appendingPathComponent("transfer-" + UUID().uuidString)
        try fm.createDirectory(at: url, withIntermediateDirectories: false)
        return url
    }
    @Test func completedReadAndCleanupReleaseAdmissionAndKeepLockInode() throws {
        try fixture { pool in
            let first = try TransferWorkspace(pool: pool, maximumBytes: 8)
            let url = try output(first.directory)
            #expect(try first.readOutput(url) == Data("body".utf8))
            let lock = pool.appendingPathComponent("usage.lock").path
            var before = stat(); #expect(lstat(lock, &before) == 0)
            try first.finish(); try first.finish()
            #expect(!fm.fileExists(atPath: first.directory.path))
            #expect(throws: TransferWorkspaceFailure.closed) { try first.readOutput(url) }
            let second = try TransferWorkspace(pool: pool, maximumBytes: 8)
            var after = stat(); #expect(lstat(lock, &after) == 0)
            #expect(before.st_ino == after.st_ino && before.st_dev == after.st_dev)
            try second.finish()
        }
    }
    @Test func anotherOwnerCannotReclaimActiveOutput() throws {
        try fixture { pool in
            let first = try TransferWorkspace(pool: pool, maximumBytes: 8)
            let url = try output(first.directory)
            #expect(throws: LibraryCacheMaintenanceFailure.busy) { try TransferWorkspace(pool: pool, maximumBytes: 8) }
            #expect(try first.readOutput(url) == Data("body".utf8))
            try first.finish()
        }
    }
    @Test func abandonedDownloadsAreReclaimedButUnknownRootEntriesSurvive() throws {
        try fixture { pool in
            let previous = try abandoned(pool)
            _ = try output(previous)
            let other = pool.appendingPathComponent("transfer-not-a-uuid")
            try Data("keep".utf8).write(to: other)
            let empty = try abandoned(pool)
            let next = try TransferWorkspace(pool: pool, maximumBytes: 8)
            #expect(!fm.fileExists(atPath: previous.path) && !fm.fileExists(atPath: empty.path))
            #expect(try Data(contentsOf: other) == Data("keep".utf8))
            try next.finish()
        }
    }
    @Test func malformedStageStopsBeforeAnyRecognizedFileDeletion() throws {
        try fixture { pool in
            let first = try abandoned(pool); let file = try output(first)
            let bad = try abandoned(pool)
            try Data().write(to: bad.appendingPathComponent("unrecognized"))
            #expect(throws: TransferWorkspaceFailure.unsafeEntry) { try TransferWorkspace(pool: pool, maximumBytes: 8) }
            #expect(fm.fileExists(atPath: file.path))
            #expect(fm.fileExists(atPath: bad.appendingPathComponent("unrecognized").path))
        }
    }
    @Test func stageSymlinkNeverDeletesExternalContents() throws {
        try fixture { pool in
            try fm.createDirectory(at: pool, withIntermediateDirectories: false)
            let outside = pool.deletingLastPathComponent().appendingPathComponent("outside")
            try fm.createDirectory(at: outside, withIntermediateDirectories: false)
            let file = try output(outside)
            let stage = pool.appendingPathComponent("transfer-" + UUID().uuidString)
            try fm.createSymbolicLink(at: stage, withDestinationURL: outside)
            #expect(throws: TransferWorkspaceFailure.unsafeEntry) { try TransferWorkspace(pool: pool, maximumBytes: 8) }
            #expect(try Data(contentsOf: file) == Data("body".utf8))
        }
    }
    @Test func readRejectsEscapeEmptyAndOversizeFiles() throws {
        try fixture { pool in
            let workspace = try TransferWorkspace(pool: pool, maximumBytes: 3)
            let empty = try output(workspace.directory, data: Data())
            let large = try output(workspace.directory)
            let outside = try output(pool)
            #expect(throws: TransferWorkspaceFailure.invalidOutput) { try workspace.readOutput(empty) }
            #expect(throws: TransferWorkspaceFailure.invalidOutput) { try workspace.readOutput(large) }
            #expect(throws: TransferWorkspaceFailure.invalidOutput) { try workspace.readOutput(outside) }
            try workspace.finish()
            #expect(fm.fileExists(atPath: outside.path))
        }
    }
    @Test func linksAndFIFOAreNotReadOrRemoved() throws {
        for kind in 0..<3 {
            try fixture { pool in
                let workspace = try TransferWorkspace(pool: pool, maximumBytes: 8)
                let outside = try output(pool)
                let target = workspace.directory.appendingPathComponent("download-" + UUID().uuidString + ".part")
                if kind == 0 { try fm.createSymbolicLink(at: target, withDestinationURL: outside) }
                else if kind == 1 { try fm.linkItem(at: outside, to: target) }
                else { #expect(mkfifo(target.path, mode_t(0o600)) == 0) }
                #expect(throws: (any Error).self) { try workspace.readOutput(target) }
                #expect(throws: TransferWorkspaceFailure.unsafeEntry) { try workspace.finish() }
                #expect(try Data(contentsOf: outside) == Data("body".utf8))
                try fm.removeItem(at: target)
                try workspace.finish()
            }
        }
    }
    @Test func invalidLimitsDoNotCreatePoolOrLogInput() throws {
        try fixture { pool in
            for count in [0, -1, Int.max, TransferWorkspace.maximumTransferBytes + 1] {
                #expect(throws: TransferWorkspaceFailure.invalidLimit) { try TransferWorkspace(pool: pool, maximumBytes: count) }
            }
            #expect(!fm.fileExists(atPath: pool.path))
            let workspace = try TransferWorkspace(pool: pool, maximumBytes: 8)
            let secret = "SYNTHETIC_TOKEN_78F1"
            do {
                _ = try workspace.readOutput(workspace.directory.appendingPathComponent(secret))
                Issue.record("Invalid output accepted")
            } catch {
                #expect(error as? TransferWorkspaceFailure == .invalidOutput)
                #expect(!String(reflecting: error).contains(secret))
                #expect(!error.localizedDescription.contains(secret))
            }
            try workspace.finish()
        }
    }
    @Test func deallocationCleansOrdinaryAbandonedOwner() throws {
        try fixture { pool in
            var workspace: TransferWorkspace? = try TransferWorkspace(pool: pool, maximumBytes: 8)
            let directory = try #require(workspace?.directory)
            _ = try output(directory)
            workspace = nil
            #expect(!fm.fileExists(atPath: directory.path))
            let next = try TransferWorkspace(pool: pool, maximumBytes: 8)
            try next.finish()
        }
    }
    @Test func partialDeletionCanBeReclaimedAndExcessiveEntryCountsRefused() throws {
        try fixture { pool in
            let partial = try abandoned(pool); let file = try output(partial)
            try fm.removeItem(at: file)
            let next = try TransferWorkspace(pool: pool, maximumBytes: 8)
            #expect(!fm.fileExists(atPath: partial.path))
            try next.finish()
            let excess = try abandoned(pool)
            for _ in 0..<9 { _ = try output(excess) }
            #expect(throws: TransferWorkspaceFailure.capacity) { try TransferWorkspace(pool: pool, maximumBytes: 8) }
            #expect(try fm.contentsOfDirectory(atPath: excess.path).count == 9)
        }
    }
    #if os(macOS) || os(Linux)
    @Test func processDeathLeavesRecoverableOutputAndReleasesKernelOwnership() throws {
        try fixture { pool in
            let seed = try TransferWorkspace(pool: pool, maximumBytes: 8)
            try seed.finish()
            let process = Process(); process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = ["python3", "-c", "import fcntl,os,sys,uuid\np=sys.argv[1]\nf=open(p+'/usage.lock','r+')\nfcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\ns=p+'/transfer-'+str(uuid.uuid4()).upper()\nos.mkdir(s,0o700)\nwith open(s+'/download-'+str(uuid.uuid4()).upper()+'.part','wb') as out: out.write(b'partial')\nos._exit(0)", pool.path]
            try process.run(); process.waitUntilExit()
            #expect(process.terminationStatus == 0)
            let leftovers = try fm.contentsOfDirectory(atPath: pool.path).filter { $0.hasPrefix("transfer-") }
            #expect(leftovers.count == 1)
            let next = try TransferWorkspace(pool: pool, maximumBytes: 8)
            for name in leftovers { #expect(!fm.fileExists(atPath: pool.appendingPathComponent(name).path)) }
            try next.finish()
        }
    }
    @Test func independentProcessRespectsTransferLifetime() throws {
        try fixture { pool in
            let workspace = try TransferWorkspace(pool: pool, maximumBytes: 8)
            func locked() throws -> String {
                let process = Process(); process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
                process.arguments = ["python3", "-c", "import fcntl,sys\nf=open(sys.argv[1], 'r+')\ntry:\n fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);print('free')\nexcept BlockingIOError:\n print('busy')", pool.appendingPathComponent("usage.lock").path]
                let pipe = Pipe(); process.standardOutput = pipe
                try process.run(); process.waitUntilExit()
                #expect(process.terminationStatus == 0)
                return String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
            }
            #expect(try locked() == "busy\n")
            try workspace.finish()
            #expect(try locked() == "free\n")
        }
    }
    #endif
}
