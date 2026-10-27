/* Compile/link only. No native function or app is executed by this probe. */
#include <stdint.h>
#include "idevice.h"
#include <libimobiledevice/afc.h>
#include <libimobiledevice/lockdown.h>
#include <libimobiledevice/libimobiledevice.h>
#include <plist/plist.h>

typedef void (*RustArraySet)(tetherless_native_plist_t, tetherless_native_plist_t, uint32_t);
typedef plist_err_t (*CArraySet)(plist_t, plist_t, uint32_t);
typedef void (*RustAFCFree)(AfcClientHandle *);
typedef afc_error_t (*CAFCFree)(afc_client_t);

_Static_assert(TETHERLESS_NATIVE_PLIST_OPT_INDENT == 8, "Rust existing option unchanged");
_Static_assert(PLIST_OPT_COERCE == 16, "C-only option remains in C provider");
_Static_assert(sizeof(tetherless_native_plist_write_options_t) == sizeof(uint32_t), "Rust option width unchanged");
_Static_assert(sizeof(TetherlessPairingHostResult) == sizeof(uint32_t), "pairing ABI unchanged");

uintptr_t tetherless_mixed_provider_c_probe(void) {
    RustArraySet rust_set = tetherless_native_plist_array_set_item;
    CArraySet c_set = plist_array_set_item;
    RustAFCFree rust_afc = tetherless_native_afc_client_free;
    CAFCFree c_afc = afc_client_free;
    /* Observable addresses retain both actual provider references. No aliases,
       cross-provider node casts, dummy provider functions or calls are used. */
    return (uintptr_t)rust_set ^ (uintptr_t)c_set ^ (uintptr_t)rust_afc ^ (uintptr_t)c_afc
        ^ (uintptr_t)tetherless_native_plist_new_dict ^ (uintptr_t)plist_new_dict
        ^ (uintptr_t)tetherless_native_plist_free ^ (uintptr_t)plist_free
        ^ (uintptr_t)tetherless_native_lockdownd_client_free ^ (uintptr_t)lockdownd_client_free
        ^ (uintptr_t)tetherless_native_idevice_free ^ (uintptr_t)idevice_free;
}

int main(void) { return 0; }
