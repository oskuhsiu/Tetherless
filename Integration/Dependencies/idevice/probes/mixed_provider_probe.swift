// Compile/link only. No native function or app is executed by this probe.
import IDevice
import libimobiledevice

@_cdecl("tetherless_mixed_provider_swift_probe")
public func tetherlessMixedProviderSwiftProbe() -> UInt {
    let rustNew: @convention(c) () -> UnsafeMutableRawPointer? = tetherless_native_plist_new_dict
    let cNew: @convention(c) () -> UnsafeMutableRawPointer? = plist_new_dict
    let rustFree: @convention(c) (UnsafeMutableRawPointer?) -> Void = tetherless_native_plist_free
    let cFree: @convention(c) (UnsafeMutableRawPointer?) -> Void = plist_free
    let rustSet: @convention(c) (UnsafeMutableRawPointer?, UnsafeMutableRawPointer?, UInt32) -> Void = tetherless_native_plist_array_set_item
    let cSet: @convention(c) (UnsafeMutableRawPointer?, UnsafeMutableRawPointer?, UInt32) -> plist_err_t = plist_array_set_item
    let rustAFCFree: @convention(c) (OpaquePointer?) -> Void = tetherless_native_afc_client_free
    let cAFCFree: @convention(c) (OpaquePointer?) -> afc_error_t = afc_client_free
    return unsafeBitCast(rustNew, to: UInt.self) ^ unsafeBitCast(cNew, to: UInt.self)
        ^ unsafeBitCast(rustFree, to: UInt.self) ^ unsafeBitCast(cFree, to: UInt.self)
        ^ unsafeBitCast(rustSet, to: UInt.self) ^ unsafeBitCast(cSet, to: UInt.self)
        ^ unsafeBitCast(rustAFCFree, to: UInt.self) ^ unsafeBitCast(cAFCFree, to: UInt.self)
}
