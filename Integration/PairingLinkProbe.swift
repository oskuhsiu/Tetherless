// SPDX-License-Identifier: AGPL-3.0-only
// Imported through the exact packaged idevice.h, never locally redeclared.
// This function is compiled and linked but is NEVER invoked by the probe.
@_cdecl("tetherless_pairing_swift_link_probe")
public func tetherlessPairingSwiftLinkProbe() {
    let token: OpaquePointer? = pairable_host_cancel_new()
    pairable_host_cancel_signal(token)
    defer { pairable_host_cancel_free(token) }

    var record: OpaquePointer?
    var peer: UnsafeMutablePointer<RpPairingPeerDeviceC>?
    var hostAltIRK = [UInt8](repeating: 0, count: 16)
    let callback: @convention(c) (UnsafePointer<CChar>?, UnsafeMutableRawPointer?) -> Void = { _, _ in }
    // The token is pre-signalled only as an extra defensive measure. Compilation
    // cannot establish cancellation behavior, and nothing executes this body.
    "Tetherless compile-link probe".withCString { name in
        hostAltIRK.withUnsafeMutableBufferPointer { bytes in
            _ = pairable_host_accept(name, nil, 0, callback, nil, token,
                                     bytes.baseAddress, &peer, &record)
        }
    }
}

@main
struct PairingLinkProbe {
    static func main() {
        // Deliberately empty. No runtime capability or pairing claim follows.
    }
}
