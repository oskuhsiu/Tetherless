// Compile/link only. Never execute this binary or probe function.
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "idevice.h"

_Static_assert(sizeof(TetherlessPairingHostResult) == sizeof(uint32_t), "host result ABI width");
_Static_assert(TetherlessPairingHostOk == 0, "host success ABI");
_Static_assert(TetherlessPairingHostInvalidArgument == 1, "host argument ABI");
_Static_assert(TetherlessPairingHostCancelled == 2, "host cancellation ABI");
_Static_assert(TetherlessPairingHostTimedOut == 3, "host deadline ABI");
_Static_assert(TetherlessPairingHostProtocol == 4, "host protocol ABI");
_Static_assert(TetherlessPairingHostIo == 5, "host I/O ABI");
_Static_assert(TetherlessPairingHostAlreadyUsed == 7, "host one-shot ABI");
_Static_assert(TetherlessPairingHostBudget == 8, "host budget ABI");
_Static_assert(sizeof(((TetherlessPairingHostAdvertisement *)0)->identifier) == 64, "host identifier cap");
_Static_assert(sizeof(((TetherlessPairingHostAdvertisement *)0)->txt_plist) == 2048, "host TXT cap");
_Static_assert(sizeof(((TetherlessPairingHostAdvertisement *)0)->host_alt_irk) == 16, "host IRK size");

_Static_assert(sizeof(((TetherlessPairingHostAdvertisement *)0)->identifier_len) == sizeof(uintptr_t), "identifier length width");
_Static_assert(sizeof(((TetherlessPairingHostAdvertisement *)0)->txt_plist_len) == sizeof(uintptr_t), "TXT length width");
_Static_assert(offsetof(TetherlessPairingHostAdvertisement, identifier) == 0, "identifier offset");
_Static_assert(offsetof(TetherlessPairingHostAdvertisement, identifier_len) == 64, "identifier length offset");
_Static_assert(offsetof(TetherlessPairingHostAdvertisement, txt_plist) == 64 + sizeof(uintptr_t), "TXT offset");
_Static_assert(offsetof(TetherlessPairingHostAdvertisement, txt_plist_len) == 2112 + sizeof(uintptr_t), "TXT length offset");
_Static_assert(offsetof(TetherlessPairingHostAdvertisement, host_alt_irk) == 2112 + 2 * sizeof(uintptr_t), "host IRK offset");
_Static_assert(sizeof(TetherlessPairingHostAdvertisement) == 2128 + 2 * sizeof(uintptr_t), "advertisement size");
_Static_assert(_Alignof(TetherlessPairingHostAdvertisement) == _Alignof(uintptr_t), "advertisement alignment");

typedef TetherlessPairingHostResult (*PrepareFn)(const uint8_t *, uintptr_t, const uint8_t *, uintptr_t,
    TetherlessPairingHostHandle **, TetherlessPairingHostAdvertisement *);
typedef bool (*CancelFn)(const TetherlessPairingHostHandle *);
typedef void (*FreeFn)(TetherlessPairingHostHandle *);
typedef TetherlessPairingHostResult (*AcceptFdFn)(const TetherlessPairingHostHandle *, int32_t, uint32_t,
    TetherlessPairingHostPinCallback, void *, uint8_t *, uintptr_t, uintptr_t *);

void tetherless_host_c_link_probe(void) {
    PrepareFn prepare = tetherless_pairing_host_prepare;
    CancelFn cancel = tetherless_pairing_host_cancel;
    FreeFn release = tetherless_pairing_host_free;
    AcceptFdFn accept = tetherless_pairing_host_accept_fd;
    TetherlessPairingHostResult a = prepare(NULL, 0, NULL, 0, NULL, NULL);
    bool b = cancel(NULL);
    TetherlessPairingHostResult c = accept(NULL, -1, 1, NULL, NULL, NULL, 0, NULL);
    release(NULL);
    (void)a; (void)b; (void)c;
}
int main(void) { return 0; }
