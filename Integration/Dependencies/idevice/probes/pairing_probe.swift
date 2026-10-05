// Compile/link only. The build recipe never executes this binary or function.
// All validation arguments are nil/zero, so even an accidental function call
// cannot carry a pairing record, endpoint, account, path or challenge.
import IDevice

@_cdecl("tetherless_swift_link_probe")
public func tetherlessSwiftLinkProbe() {
    let make: @convention(c) () -> OpaquePointer? = tetherless_pairing_validation_new
    let cancel: @convention(c) (OpaquePointer?) -> Bool = tetherless_pairing_validation_cancel
    let release: @convention(c) (OpaquePointer?) -> Void = tetherless_pairing_validation_free
    let token: OpaquePointer? = make()
    let cancelled: Bool = cancel(token)
    var client: OpaquePointer? = nil
    let timeout: UInt32 = 1
    let house: TetherlessPairingValidationResult = withUnsafeMutablePointer(to: &client) {
        tetherless_pairing_validate_house_arrest($0, token, nil, 0, nil, 0, nil, 0, timeout)
    }
    let staged: TetherlessPairingValidationResult = tetherless_pairing_validate_staged(
        nil, 0, nil, 0, token, nil, 0, nil, 0, nil, 0, timeout
    )
    _ = (cancelled, house, staged)
    release(token)
}
