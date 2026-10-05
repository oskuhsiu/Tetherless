// Compile/link only; never execute. Real generated-header scalar/ICE contract.
#include <stdint.h>
#include "idevice.h"
_Static_assert(sizeof(TetherlessPairingValidationResult) == 4, "result must remain 32 bits");
_Static_assert(((TetherlessPairingValidationResult)-1) > 0, "result must remain unsigned");
_Static_assert(TetherlessPairingValidationOk == 0, "result discriminant");
_Static_assert(_Generic(TetherlessPairingValidationOk, uint32_t: 1, default: 0), "constant scalar type");
_Static_assert(TetherlessPairingValidationInvalidArgument == 1, "result discriminant");
_Static_assert(_Generic(TetherlessPairingValidationInvalidArgument, uint32_t: 1, default: 0), "constant scalar type");
_Static_assert(TetherlessPairingValidationCancelled == 2, "result discriminant");
_Static_assert(_Generic(TetherlessPairingValidationCancelled, uint32_t: 1, default: 0), "constant scalar type");
_Static_assert(TetherlessPairingValidationTimedOut == 3, "result discriminant");
_Static_assert(_Generic(TetherlessPairingValidationTimedOut, uint32_t: 1, default: 0), "constant scalar type");
_Static_assert(TetherlessPairingValidationProtocol == 4, "result discriminant");
_Static_assert(_Generic(TetherlessPairingValidationProtocol, uint32_t: 1, default: 0), "constant scalar type");
_Static_assert(TetherlessPairingValidationIo == 5, "result discriminant");
_Static_assert(_Generic(TetherlessPairingValidationIo, uint32_t: 1, default: 0), "constant scalar type");
_Static_assert(TetherlessPairingValidationMismatch == 6, "result discriminant");
_Static_assert(_Generic(TetherlessPairingValidationMismatch, uint32_t: 1, default: 0), "constant scalar type");
_Static_assert(TetherlessPairingValidationAlreadyUsed == 7, "result discriminant");
_Static_assert(_Generic(TetherlessPairingValidationAlreadyUsed, uint32_t: 1, default: 0), "constant scalar type");
_Static_assert(TetherlessPairingValidationBudget == 8, "result discriminant");
_Static_assert(_Generic(TetherlessPairingValidationBudget, uint32_t: 1, default: 0), "constant scalar type");
static uint32_t check_TetherlessPairingValidationResult(TetherlessPairingValidationResult value) {
    switch (value) {
    case TetherlessPairingValidationOk: return 0;
    case TetherlessPairingValidationInvalidArgument: return 1;
    case TetherlessPairingValidationCancelled: return 2;
    case TetherlessPairingValidationTimedOut: return 3;
    case TetherlessPairingValidationProtocol: return 4;
    case TetherlessPairingValidationIo: return 5;
    case TetherlessPairingValidationMismatch: return 6;
    case TetherlessPairingValidationAlreadyUsed: return 7;
    case TetherlessPairingValidationBudget: return 8;
    default: return UINT32_MAX;
    }
}
_Static_assert(sizeof(TetherlessPairingHostResult) == 4, "result must remain 32 bits");
_Static_assert(((TetherlessPairingHostResult)-1) > 0, "result must remain unsigned");
_Static_assert(TetherlessPairingHostOk == 0, "result discriminant");
_Static_assert(_Generic(TetherlessPairingHostOk, uint32_t: 1, default: 0), "constant scalar type");
_Static_assert(TetherlessPairingHostInvalidArgument == 1, "result discriminant");
_Static_assert(_Generic(TetherlessPairingHostInvalidArgument, uint32_t: 1, default: 0), "constant scalar type");
_Static_assert(TetherlessPairingHostCancelled == 2, "result discriminant");
_Static_assert(_Generic(TetherlessPairingHostCancelled, uint32_t: 1, default: 0), "constant scalar type");
_Static_assert(TetherlessPairingHostTimedOut == 3, "result discriminant");
_Static_assert(_Generic(TetherlessPairingHostTimedOut, uint32_t: 1, default: 0), "constant scalar type");
_Static_assert(TetherlessPairingHostProtocol == 4, "result discriminant");
_Static_assert(_Generic(TetherlessPairingHostProtocol, uint32_t: 1, default: 0), "constant scalar type");
_Static_assert(TetherlessPairingHostIo == 5, "result discriminant");
_Static_assert(_Generic(TetherlessPairingHostIo, uint32_t: 1, default: 0), "constant scalar type");
_Static_assert(TetherlessPairingHostAlreadyUsed == 7, "result discriminant");
_Static_assert(_Generic(TetherlessPairingHostAlreadyUsed, uint32_t: 1, default: 0), "constant scalar type");
_Static_assert(TetherlessPairingHostBudget == 8, "result discriminant");
_Static_assert(_Generic(TetherlessPairingHostBudget, uint32_t: 1, default: 0), "constant scalar type");
static uint32_t check_TetherlessPairingHostResult(TetherlessPairingHostResult value) {
    switch (value) {
    case TetherlessPairingHostOk: return 0;
    case TetherlessPairingHostInvalidArgument: return 1;
    case TetherlessPairingHostCancelled: return 2;
    case TetherlessPairingHostTimedOut: return 3;
    case TetherlessPairingHostProtocol: return 4;
    case TetherlessPairingHostIo: return 5;
    case TetherlessPairingHostAlreadyUsed: return 7;
    case TetherlessPairingHostBudget: return 8;
    default: return UINT32_MAX;
    }
}
uint32_t tetherless_result_constants_c_probe(void) {
    return check_TetherlessPairingValidationResult(TetherlessPairingValidationOk)
        + check_TetherlessPairingHostResult(TetherlessPairingHostOk);
}
int main(void) { return 0; }
