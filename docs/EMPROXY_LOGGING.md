# EMProxy callback privacy

The pinned Minimuxer EMProxy initializer used to decode native log messages and
forward warning/error text to its unconditional Swift debug logger. The separate
IDevice logger's Off setting does not control that callback.

The preparation transform changes only that initializer's callback. It returns
true without reading either argument, converting a C string, allocating a Swift
message or invoking a diagnostic sink. The native API defines true as handled.
Start, stop, socket, handshake, cancellation and error-return behavior are unchanged.
Existing fixed renewal evidence and application diagnostics remain available.

## Source identity

- Minimuxer commit `12be70dc2627307a16bfd2dc7a009080d5bec909`
- `Sources/EMProxyImpl.swift` Git blob `920e57694b1835b00dbd8761d34b2045bd272880`
- The retained test fixture is that exact complete source, with its original
  copyright notice. Minimuxer's AGPL-3.0 notice is retained in the existing supply
  chain materials
- Native callback contract inspected in EMProxy v0.9.3, commit
  `6e117e140ca7cff4ff106bdefa18147552a0e592`, `src/lib.rs` blob
  `4ca773dbf560f72bd83508f046391807cceda561`

Primary sources:
[Swift callback](https://github.com/SideStore/minimuxer/blob/12be70dc2627307a16bfd2dc7a009080d5bec909/Sources/EMProxyImpl.swift)
and [native handling](https://github.com/SideStore/em_proxy/blob/6e117e140ca7cff4ff106bdefa18147552a0e592/src/lib.rs).

## Verification and limits

Portable checks verify exact source identity, callback-only transformation,
preimage/anchor drift rejection, unchanged network methods and single preparation
registration. A Swift 6 spy compiles the actual transformed initializer in Debug
and Release modes, supplies nil, synthetic valid and deliberately unreadable
pointers at all representative levels, and requires true with no payload output.
It runs only where a Swift compiler exists. Full generated application compilation
and native callback/binary behavior remain separate evidence.

This does not erase prior logs, prevent another caller replacing the process-global
callback, audit all EMProxy/dependency logging, or prove binary/source equivalence.
The native library can fall back to its logger if no callback is registered or if
its CString conversion fails before invoking the callback. No broader native
logging guarantee follows from this Swift boundary. No credentials or actual
pairing material are used in these tests.
