// Tetherless privacy boundary for SideSign authentication failures.
// The normal error types and numeric server codes survive; arbitrary payloads
// and NSError userInfo must not reach app logs or persisted error reports.
import Foundation

func sanitizedAuthenticationError(_ error: Error) -> Error {
    if error is CancellationError { return CancellationError() }
    if let error = error as? URLError { return URLError(error.code) }
    if let error = error as? ServerError {
        switch error {
        case .underlyingError(let code, _):
            return ServerError.underlyingError(code: code, message: "Apple authentication request failed")
        case .badServerResponse:
            return ServerError.badServerResponse(reason: "Invalid authentication response", jsonPayload: "[authentication payload omitted]")
        case .invalidResponseFormat:
            return ServerError.invalidResponseFormat(rawPayload: "[authentication payload omitted]")
        case .missingKey:
            return ServerError.missingKey(key: "required authentication field", jsonPayload: "[authentication payload omitted]")
        }
    }
    if let error = error as? DeveloperPortalError {
        switch error {
        case .incorrectCredentials: return DeveloperPortalError.incorrectCredentials()
        case .appSpecificPasswordRequired: return DeveloperPortalError.appSpecificPasswordRequired()
        case .incorrectVerificationCode: return DeveloperPortalError.incorrectVerificationCode()
        case .noTeams: return DeveloperPortalError.noTeams
        case .requiresTwoFactorAuthentication: return DeveloperPortalError.requiresTwoFactorAuthentication
        case .userCancelled: return DeveloperPortalError.userCancelled
        case .authenticationHandshakeFailed:
            return DeveloperPortalError.authenticationHandshakeFailed(cause: "Authentication handshake failed")
        case .invalidAnisetteData:
            return DeveloperPortalError.invalidAnisetteData(cause: "Local authentication data is unavailable or invalid")
        case .tooManyAttempts:
            return DeveloperPortalError.tooManyAttempts(cause: "Too many attempts. Please try again later.")
        case .invalid2FAResponse:
            return DeveloperPortalError.invalid2FAResponse(cause: "Apple rejected the verification response")
        case .accountRepairRequired:
            return DeveloperPortalError.accountRepairRequired(url: Constants.URLs.developerAccount,
                message: Constants.defaultAccountRepairMessage)
        default: break
        }
    }
    return DeveloperPortalError.unknown(cause: "Authentication could not complete")
}
