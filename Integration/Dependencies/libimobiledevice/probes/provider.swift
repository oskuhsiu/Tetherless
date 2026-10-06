// Compile/link only. Never executed on iOS or Simulator.
import libimobiledevice
@_cdecl("tetherless_c_provider_swift_probe")
public func tetherlessCProviderSwiftProbe() -> UInt {
    let new: @convention(c) () -> UnsafeMutableRawPointer? = plist_new_dict
    let free: @convention(c) (UnsafeMutableRawPointer?) -> Void = plist_free
    let set: @convention(c) (UnsafeMutableRawPointer?, UnsafeMutableRawPointer?, UInt32) -> plist_err_t = plist_array_set_item
    let afc: @convention(c) (OpaquePointer?) -> afc_error_t = afc_client_free
    return unsafeBitCast(new, to: UInt.self) ^ unsafeBitCast(free, to: UInt.self)
        ^ unsafeBitCast(set, to: UInt.self) ^ unsafeBitCast(afc, to: UInt.self)
}
