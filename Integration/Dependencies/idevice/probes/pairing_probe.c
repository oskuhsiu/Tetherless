// Compile/link only. Never invoked by the build recipe; contains no account data.
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "idevice.h"

_Static_assert(sizeof(TetherlessPairingValidationResult) == sizeof(uint32_t), "result ABI width");
_Static_assert(TetherlessPairingValidationOk == 0, "ok result ABI");
_Static_assert(TetherlessPairingValidationInvalidArgument == 1, "argument result ABI");
_Static_assert(TetherlessPairingValidationCancelled == 2, "cancel result ABI");
_Static_assert(TetherlessPairingValidationTimedOut == 3, "timeout result ABI");
_Static_assert(TetherlessPairingValidationProtocol == 4, "protocol result ABI");
_Static_assert(TetherlessPairingValidationIo == 5, "I/O result ABI");
_Static_assert(TetherlessPairingValidationMismatch == 6, "mismatch result ABI");
_Static_assert(TetherlessPairingValidationAlreadyUsed == 7, "used result ABI");
_Static_assert(TetherlessPairingValidationBudget == 8, "budget result ABI");

typedef TetherlessPairingValidationHandle *(*NewFn)(void);
typedef bool (*CancelFn)(const TetherlessPairingValidationHandle *);
typedef void (*FreeFn)(TetherlessPairingValidationHandle *);
typedef TetherlessPairingValidationResult (*HouseArrestFn)(
    HouseArrestClientHandle **, const TetherlessPairingValidationHandle *,
    const uint8_t *, uintptr_t, const uint8_t *, uintptr_t,
    const uint8_t *, uintptr_t, uint32_t);
typedef TetherlessPairingValidationResult (*StagedFn)(
    const uint8_t *, uintptr_t, const uint8_t *, uintptr_t,
    const TetherlessPairingValidationHandle *, const uint8_t *, uintptr_t,
    const uint8_t *, uintptr_t, const uint8_t *, uintptr_t, uint32_t);

// Typed assignments verify the generated declarations. -Werror makes a pointer
// type mismatch fatal, rather than accepting a C compatibility warning.
void tetherless_c_link_probe(void) {
    NewFn make = tetherless_pairing_validation_new;
    CancelFn cancel = tetherless_pairing_validation_cancel;
    FreeFn release = tetherless_pairing_validation_free;
    HouseArrestFn house = tetherless_pairing_validate_house_arrest;
    StagedFn staged = tetherless_pairing_validate_staged;
    TetherlessPairingValidationHandle *token = make();
    HouseArrestClientHandle *client = NULL;
    bool cancelled = cancel(token);
    TetherlessPairingValidationResult a = house(&client, token, NULL, 0, NULL, 0, NULL, 0, 1);
    TetherlessPairingValidationResult b = staged(NULL, 0, NULL, 0, token, NULL, 0, NULL, 0, NULL, 0, 1);
    (void)cancelled; (void)a; (void)b;
    release(token);
}

int main(void) { return 0; }
