/* Compile/link only. Never executed on iOS or Simulator. */
#include <stdint.h>
#include <libimobiledevice/afc.h>
#include <libimobiledevice/lockdown.h>
#include <libimobiledevice/libimobiledevice.h>
#include <plist/plist.h>
#include <libimobiledevice-glue/sha.h>

extern int tetherless_c_ed25519_sha512(const unsigned char *, size_t, unsigned char *);
typedef plist_err_t (*ArraySet)(plist_t, plist_t, uint32_t);
typedef afc_error_t (*AFCFree)(afc_client_t);
_Static_assert(PLIST_OPT_COERCE == 16, "public C option unchanged");
_Static_assert(sizeof(plist_err_t) == sizeof(uint32_t), "public C result width unchanged");
uintptr_t tetherless_c_provider_probe(void) {
    ArraySet set = plist_array_set_item;
    AFCFree afc = afc_client_free;
    return (uintptr_t)set ^ (uintptr_t)afc ^ (uintptr_t)plist_new_dict ^ (uintptr_t)plist_free
        ^ (uintptr_t)lockdownd_client_free ^ (uintptr_t)idevice_free
        ^ (uintptr_t)sha512 ^ (uintptr_t)tetherless_c_ed25519_sha512;
}
int main(void) { return 0; }
