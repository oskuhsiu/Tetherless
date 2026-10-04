// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

/// Coordinate only the short source-to-snapshot copy, not signing or extraction.
/// Cloud/file-provider permission is released after the private input is ready.
enum NativeIPAInput {
    static func snapshot(from source: URL, to destination: URL, external: Bool,
                         check: @escaping () throws -> Void = { try Task.checkCancellation() }) throws {
        guard external else {
            try IPAInputSnapshot.create(from: source, at: destination, check: check)
            return
        }
        let scoped = source.startAccessingSecurityScopedResource()
        defer { if scoped { source.stopAccessingSecurityScopedResource() } }
        let coordinator = NSFileCoordinator(filePresenter: nil)
        var coordinationError: NSError?
        var copied: Result<Void, Error>?
        coordinator.coordinate(readingItemAt: source, options: .withoutChanges, error: &coordinationError) { authorized in
            copied = Result { try IPAInputSnapshot.create(from: authorized, at: destination, check: check) }
        }
        guard coordinationError == nil, let copied else {
            // If the accessor already copied successfully but coordination failed,
            // this private output is not an accepted input. The install context
            // owns its cleanup; no untrusted source is modified.
            throw IPAInputFailure.unavailable
        }
        try copied.get()
    }
}
