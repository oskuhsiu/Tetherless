// Compile/link only; never execute. Uses the genuine generated IDevice module.
import IDevice

@_cdecl("tetherless_result_constants_swift_probe")
public func tetherless_result_constants_swift_probe() -> UInt32 {
    let TetherlessPairingValidationResultValues: [UInt32] = [TetherlessPairingValidationOk, TetherlessPairingValidationInvalidArgument, TetherlessPairingValidationCancelled, TetherlessPairingValidationTimedOut, TetherlessPairingValidationProtocol, TetherlessPairingValidationIo, TetherlessPairingValidationMismatch, TetherlessPairingValidationAlreadyUsed, TetherlessPairingValidationBudget]
    let TetherlessPairingValidationResultValue: TetherlessPairingValidationResult = TetherlessPairingValidationOk
    switch TetherlessPairingValidationResultValue {
    case TetherlessPairingValidationOk: _ = TetherlessPairingValidationResultValues[0]
    case TetherlessPairingValidationInvalidArgument: _ = TetherlessPairingValidationResultValues[1]
    case TetherlessPairingValidationCancelled: _ = TetherlessPairingValidationResultValues[2]
    case TetherlessPairingValidationTimedOut: _ = TetherlessPairingValidationResultValues[3]
    case TetherlessPairingValidationProtocol: _ = TetherlessPairingValidationResultValues[4]
    case TetherlessPairingValidationIo: _ = TetherlessPairingValidationResultValues[5]
    case TetherlessPairingValidationMismatch: _ = TetherlessPairingValidationResultValues[6]
    case TetherlessPairingValidationAlreadyUsed: _ = TetherlessPairingValidationResultValues[7]
    case TetherlessPairingValidationBudget: _ = TetherlessPairingValidationResultValues[8]
    default: break
    }
    let TetherlessPairingHostResultValues: [UInt32] = [TetherlessPairingHostOk, TetherlessPairingHostInvalidArgument, TetherlessPairingHostCancelled, TetherlessPairingHostTimedOut, TetherlessPairingHostProtocol, TetherlessPairingHostIo, TetherlessPairingHostAlreadyUsed, TetherlessPairingHostBudget]
    let TetherlessPairingHostResultValue: TetherlessPairingHostResult = TetherlessPairingHostOk
    switch TetherlessPairingHostResultValue {
    case TetherlessPairingHostOk: _ = TetherlessPairingHostResultValues[0]
    case TetherlessPairingHostInvalidArgument: _ = TetherlessPairingHostResultValues[1]
    case TetherlessPairingHostCancelled: _ = TetherlessPairingHostResultValues[2]
    case TetherlessPairingHostTimedOut: _ = TetherlessPairingHostResultValues[3]
    case TetherlessPairingHostProtocol: _ = TetherlessPairingHostResultValues[4]
    case TetherlessPairingHostIo: _ = TetherlessPairingHostResultValues[5]
    case TetherlessPairingHostAlreadyUsed: _ = TetherlessPairingHostResultValues[6]
    case TetherlessPairingHostBudget: _ = TetherlessPairingHostResultValues[7]
    default: break
    }
    return 0
}
