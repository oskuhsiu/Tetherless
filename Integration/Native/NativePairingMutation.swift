// SPDX-License-Identifier: AGPL-3.0-only
import Foundation

extension NativeMutationGate {
    static func withSynchronousLease<T>(_ body: () throws -> T) throws -> T {
        let path = try NativeRenewalStorage.root().appendingPathComponent("device-mutation.lock")
        return try MutationScope.withSynchronousLease(identity: path.path, acquire: {
            let lease = try ProcessLease.acquire(at: path)
            return { lease.release() }
        }, body: body)
    }

}
