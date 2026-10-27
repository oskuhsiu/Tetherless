#ifndef TETHERLESS_PAIRING_VALIDATION_TEST_SPY_H
#define TETHERLESS_PAIRING_VALIDATION_TEST_SPY_H
// Synthetic declarations for Swift ownership tests only. This is NOT a native
// artifact header, ABI probe, device transport or cryptographic implementation.
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef struct TetherlessPairingValidationHandle TetherlessPairingValidationHandle;
typedef enum {
    TetherlessPairingValidationOk = 0,
    TetherlessPairingValidationInvalidArgument = 1,
    TetherlessPairingValidationCancelled = 2,
    TetherlessPairingValidationTimedOut = 3,
    TetherlessPairingValidationProtocol = 4,
    TetherlessPairingValidationIo = 5,
    TetherlessPairingValidationMismatch = 6,
    TetherlessPairingValidationAlreadyUsed = 7,
    TetherlessPairingValidationBudget = 8
} TetherlessPairingValidationResult;
TetherlessPairingValidationHandle *tetherless_pairing_validation_new(void);
bool tetherless_pairing_validation_cancel(const TetherlessPairingValidationHandle *handle);
void tetherless_pairing_validation_free(TetherlessPairingValidationHandle *handle);
TetherlessPairingValidationResult tetherless_pairing_validate_staged(
    const uint8_t *record, uintptr_t record_len, const uint8_t *endpoint, uintptr_t endpoint_len,
    const TetherlessPairingValidationHandle *handle, const uint8_t *bundle, uintptr_t bundle_len,
    const uint8_t *path, uintptr_t path_len, const uint8_t *expected, uintptr_t expected_len, uint32_t timeout_ms);
void tetherless_spy_reset(bool hold_return);
void tetherless_spy_release(void);
unsigned tetherless_spy_started(void);
unsigned tetherless_spy_cancels(void);
unsigned tetherless_spy_frees(void);
unsigned tetherless_spy_active(void);
unsigned tetherless_spy_invalid_input(void);
unsigned tetherless_spy_freed_while_active(void);
#endif
