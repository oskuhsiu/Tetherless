// SPDX-License-Identifier: AGPL-3.0-only
#if canImport(CryptoKit) && canImport(Darwin)
import Foundation
import CryptoKit
import Darwin

/// Content hashing, not the inherited filename/size-only cache key. The file
/// reader rejects links/special files and bounds actual streamed bytes.
public enum BundleContentHash {
    public static func file(_ url: URL, maximum: Int64 = 536_870_912) throws -> String {
        guard url.isFileURL, maximum > 0, maximum <= 4_294_967_296 else { throw PrivateFileError.invalidName }
        let fd = open(url.path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK)
        guard fd >= 0 else { throw PrivateFileError.unavailable }
        defer { _ = close(fd) }
        var before = stat()
        guard fstat(fd, &before) == 0, (before.st_mode & S_IFMT) == S_IFREG,
              before.st_nlink == 1, before.st_size >= 0, before.st_size <= maximum else {
            throw PrivateFileError.unsafeFile
        }
        let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: false)
        var hasher = SHA256()
        var total: Int64 = 0
        while true {
            let bytes = try handle.read(upToCount: 65_536) ?? Data()
            if bytes.isEmpty { break }
            guard Int64(bytes.count) <= maximum - total else { throw PrivateFileError.tooLarge }
            total += Int64(bytes.count); hasher.update(data: bytes)
        }
        var after = stat()
        guard fstat(fd, &after) == 0, after.st_size == total, before.st_size == after.st_size,
              before.st_mtimespec.tv_sec == after.st_mtimespec.tv_sec,
              before.st_mtimespec.tv_nsec == after.st_mtimespec.tv_nsec,
              before.st_ctimespec.tv_sec == after.st_ctimespec.tv_sec,
              before.st_ctimespec.tv_nsec == after.st_ctimespec.tv_nsec else {
            throw PrivateFileError.changedDuringRead
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }
    public static func bundle(_ url: URL) throws -> String {
        var count = 0
        var bytes: Int64 = 0
        let ignored: Set<String> = ["__MACOSX", ".DS_Store", "_CodeSignature", "embedded.mobileprovision"]
        func node(_ url: URL, depth: Int) throws -> String {
            guard depth <= 32 else { throw PrivateFileError.tooLarge }
            let root = try url.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
            guard root.isDirectory == true, root.isSymbolicLink != true else { throw PrivateFileError.unsafeFile }
            let children = try FileManager.default.contentsOfDirectory(at: url,
                includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey, .fileSizeKey])
            guard children.count <= 30_000 - count else { throw PrivateFileError.tooLarge }
            count += children.count
            var hasher = SHA256()
            hasher.update(data: Data("TetherlessContentTree-v1\0".utf8))
            for child in children.sorted(by: { $0.lastPathComponent < $1.lastPathComponent }) {
                let name = child.lastPathComponent
                if ignored.contains(name) { continue }
                let values = try child.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey, .fileSizeKey])
                guard values.isSymbolicLink != true else { throw PrivateFileError.unsafeFile }
                let digest: String
                if values.isDirectory == true {
                    digest = "D" + (try node(child, depth: depth + 1))
                } else {
                    let size = Int64(values.fileSize ?? -1)
                    guard size >= 0, size <= 4_294_967_296 - bytes else { throw PrivateFileError.tooLarge }
                    bytes += size
                    digest = "F" + (try file(child))
                }
                let nameBytes = Data(name.precomposedStringWithCanonicalMapping.utf8)
                hasher.update(data: Data("\(nameBytes.count):".utf8))
                hasher.update(data: nameBytes); hasher.update(data: Data(digest.utf8))
            }
            return hasher.finalize().map { String(format: "%02x", $0) }.joined()
        }
        return try node(url, depth: 0)
    }
}
#endif
