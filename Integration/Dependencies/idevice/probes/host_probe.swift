// Compile/link only. No account, peer, listener or valid handle is supplied.
// The build must force-link this symbol and never execute the output.
import IDevice

@_cdecl("tetherless_host_swift_link_probe")
public func tetherlessHostSwiftLinkProbe() {
    let prepare: @convention(c) (UnsafePointer<UInt8>?, UInt, UnsafePointer<UInt8>?, UInt,
        UnsafeMutablePointer<OpaquePointer?>?, UnsafeMutablePointer<TetherlessPairingHostAdvertisement>?)
        -> TetherlessPairingHostResult = tetherless_pairing_host_prepare
    let cancel: @convention(c) (OpaquePointer?) -> Bool = tetherless_pairing_host_cancel
    let release: @convention(c) (OpaquePointer?) -> Void = tetherless_pairing_host_free
    let callback: @convention(c) (UnsafePointer<UInt8>?, UInt, UnsafeMutableRawPointer?) -> Void = { _, _, _ in }
    let a = prepare(nil, 0, nil, 0, nil, nil)
    let b = cancel(nil)
    let c: TetherlessPairingHostResult = tetherless_pairing_host_accept_fd(
        nil, -1, 1, callback, nil, nil, 0, nil
    )
    release(nil)
    _ = (a, b, c)
}
