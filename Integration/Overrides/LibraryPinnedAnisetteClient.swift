// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import AnisetteKit

/// The upstream resolver is consumed only during initialization; capturing a
/// pin in that closure would NOT protect later provisioning. Keep ownership in
/// the actual returned client and through every asynchronous call instead.
final class LibraryPinnedAnisetteClient: AnisetteClientProtocol {
    private let client: any AnisetteClientProtocol
    private let generation: AnisetteLibraryCache.PinnedGeneration

    init(client: any AnisetteClientProtocol, generation: AnisetteLibraryCache.PinnedGeneration) {
        self.client = client
        self.generation = generation
    }

    func getAnisetteData(identifier: UUID, storage: ProvisioningStorage,
                         headers: AnisetteRequestHeaders?) async throws -> (headers: [String: String], newBlob: Data?) {
        let lifetime = generation
        defer { withExtendedLifetime(lifetime) {} }
        return try await client.getAnisetteData(identifier: identifier, storage: storage, headers: headers)
    }
}
