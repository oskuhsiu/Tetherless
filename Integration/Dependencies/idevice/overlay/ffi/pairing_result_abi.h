/* Tetherless fixed-width pairing result declarations. */
#include <stdint.h>
typedef uint32_t TetherlessPairingValidationResult;
#define TetherlessPairingValidationOk ((uint32_t)0)
#define TetherlessPairingValidationInvalidArgument ((uint32_t)1)
#define TetherlessPairingValidationCancelled ((uint32_t)2)
#define TetherlessPairingValidationTimedOut ((uint32_t)3)
#define TetherlessPairingValidationProtocol ((uint32_t)4)
#define TetherlessPairingValidationIo ((uint32_t)5)
#define TetherlessPairingValidationMismatch ((uint32_t)6)
#define TetherlessPairingValidationAlreadyUsed ((uint32_t)7)
#define TetherlessPairingValidationBudget ((uint32_t)8)
typedef uint32_t TetherlessPairingHostResult;
#define TetherlessPairingHostOk ((uint32_t)0)
#define TetherlessPairingHostInvalidArgument ((uint32_t)1)
#define TetherlessPairingHostCancelled ((uint32_t)2)
#define TetherlessPairingHostTimedOut ((uint32_t)3)
#define TetherlessPairingHostProtocol ((uint32_t)4)
#define TetherlessPairingHostIo ((uint32_t)5)
#define TetherlessPairingHostAlreadyUsed ((uint32_t)7)
#define TetherlessPairingHostBudget ((uint32_t)8)
/* End Tetherless fixed-width pairing result declarations. */
