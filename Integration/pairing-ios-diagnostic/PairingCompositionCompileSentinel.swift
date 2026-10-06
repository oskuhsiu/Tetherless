// Tetherless diagnostic compile sentinel (new source, October 2026).
// SPDX-License-Identifier: AGPL-3.0-only
// Appended only to the owned diagnostic copy. Never called or activated.
#if !TETHERLESS_PAIRING_COMPOSITION_COMPILE_CHECK
#error("Diagnostic compilation requires TETHERLESS_PAIRING_COMPOSITION_COMPILE_CHECK")
#endif
#if !TETHERLESS_BOUNDED_PAIRING_HOST || !TETHERLESS_STAGED_PAIRING_VALIDATION
#error("Diagnostic compilation requires both pairing implementation conditions")
#endif
#if !os(iOS) || targetEnvironment(simulator) || targetEnvironment(macCatalyst) || !arch(arm64)
#error("Diagnostic composition requires an arm64 iOS device target")
#endif
#if !canImport(IDevice) || !canImport(IdeviceGateway)
#error("Diagnostic composition requires the bound IDevice and IdeviceGateway modules")
#else
import IDevice
import IdeviceGateway

@available(iOS 17.0, *)
@MainActor private func tetherlessPairingCompositionCompileSentinel(
    model: PairingSetupModel,
    host: BoundedPairingHostBridge,
    validator: NativeStagedPairingValidator,
    listener: PairingBonjourListener,
    resolver: PairingEndpointResolver,
    endpoint: PairingNumericEndpoint,
    challenge: PairingValidationChallenge,
    lifetime: NativeCallLifetime,
    cancellation: PairingCancellationController,
    promotion: PairingPromotion
) {
    // Type-check the new scalar host/validation ABI and real imported entry
    // points. Taking references does not execute any native or app operation.
    let hostResult: TetherlessPairingHostResult = TetherlessPairingHostOk
    let validationResult: TetherlessPairingValidationResult = TetherlessPairingValidationOk
    let _: UInt32 = hostResult
    let _: UInt32 = validationResult
    _ = TetherlessPairingHostAdvertisement.self
    _ = tetherless_pairing_host_prepare
    _ = tetherless_pairing_host_accept_fd
    _ = tetherless_pairing_host_cancel
    _ = tetherless_pairing_host_free
    _ = tetherless_pairing_validation_new
    _ = tetherless_pairing_validate_staged
    _ = tetherless_pairing_validation_cancel
    _ = tetherless_pairing_validation_free
    _ = IdeviceGateway.self
    _ = host.accept
    _ = host.close
    _ = validator.validate
    _ = validator.close
    _ = listener.acceptOne
    _ = resolver.resolve
    _ = (endpoint, challenge, lifetime, cancellation, promotion)
    _ = model.start
    _ = model.cancel
    _ = model.reconcileCancellation
    _ = PairingSetupModel.supported
    _ = PairingSetupRequest()
    _ = PairingSetupView(finished: { _ in })
    _ = PairingValidationBudget.timeoutMilliseconds(remainingMilliseconds: 1_000, endpointsRemaining: 2)
    _ = OnboardingView.self
    _ = WirelessPairView.self
}
#endif
