// SPDX-License-Identifier: AGPL-3.0-only
//! A deliberately lossy, non-logging boundary. Never format an upstream report:
//! its contexts, attachments, URLs and messages can contain account secrets.
use isideload::SideloadError;
use serde::Serialize;

#[derive(Clone, Copy, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum LoginStage {
    AccountSetup,
    AppleLogin,
    DeveloperToken,
    Task,
}

#[derive(Clone, Copy, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum LoginFailureKind {
    AppleRejected,
    AnisetteUnavailable,
    HttpRejected,
    NetworkTimeout,
    NetworkConnect,
    NetworkFailure,
    Unknown,
    TaskFailed,
}

#[derive(Clone, Copy, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LoginDiagnostic {
    pub stage: LoginStage,
    pub kind: LoginFailureKind,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub apple_code: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub http_status: Option<u16>,
}

impl LoginDiagnostic {
    pub fn new(stage: LoginStage, kind: LoginFailureKind) -> Self {
        Self {
            stage,
            kind,
            apple_code: None,
            http_status: None,
        }
    }
}

fn network_diagnostic(stage: LoginStage, error: &reqwest::Error) -> LoginDiagnostic {
    let kind = if error.status().is_some() {
        LoginFailureKind::HttpRejected
    } else if error.is_timeout() {
        LoginFailureKind::NetworkTimeout
    } else if error.is_connect() {
        LoginFailureKind::NetworkConnect
    } else {
        LoginFailureKind::NetworkFailure
    };
    LoginDiagnostic {
        http_status: error.status().map(|status| status.as_u16()),
        ..LoginDiagnostic::new(stage, kind)
    }
}

pub fn classify(stage: LoginStage, report: rootcause::Report) -> LoginDiagnostic {
    // Type inspection only. Do not inspect/format string contexts or attachments,
    // even as a fallback. Unknown is preferable to exposing private server data.
    for node in report.iter_reports() {
        if let Some(error) = node.downcast_current_context::<SideloadError>() {
            match error {
                SideloadError::AuthWithMessage(code, _) => {
                    return LoginDiagnostic {
                        apple_code: Some(*code),
                        ..LoginDiagnostic::new(stage, LoginFailureKind::AppleRejected)
                    };
                }
                SideloadError::AnisetteNotProvisioned => {
                    return LoginDiagnostic::new(stage, LoginFailureKind::AnisetteUnavailable);
                }
                _ => {}
            }
        }
        if let Some(error) = node.downcast_current_context::<reqwest::Error>() {
            return network_diagnostic(stage, error);
        }
        if let Some(reqwest_middleware::Error::Reqwest(error)) =
            node.downcast_current_context::<reqwest_middleware::Error>()
        {
            return network_diagnostic(stage, error);
        }
    }
    LoginDiagnostic::new(stage, LoginFailureKind::Unknown)
}

#[cfg(test)]
mod tests {
    use super::*;
    use rootcause::prelude::*;

    #[test]
    fn apple_code_is_retained_but_message_context_and_attachment_are_not() {
        let report = report!(SideloadError::AuthWithMessage(
            -21669,
            "SYNTHETIC_PRIVATE_MESSAGE".into()
        ))
        .context("SYNTHETIC_PRIVATE_CONTEXT")
        .attach("SYNTHETIC_PRIVATE_ATTACHMENT");
        let result = serde_json::to_value(classify(LoginStage::AppleLogin, report.into())).unwrap();
        assert_eq!(
            result,
            serde_json::json!({
                "stage": "appleLogin", "kind": "appleRejected", "appleCode": -21669,
            })
        );
    }

    #[test]
    fn unknown_reports_are_not_string_matched_or_exposed() {
        let report =
            report!("SYNTHETIC_PASSWORD http status 403 Apple blocked").attach("SYNTHETIC_TOKEN");
        assert_eq!(
            serde_json::to_value(classify(LoginStage::DeveloperToken, report)).unwrap(),
            serde_json::json!({"stage": "developerToken", "kind": "unknown"})
        );
    }

    #[test]
    fn anisette_error_is_a_fixed_category() {
        assert_eq!(
            serde_json::to_value(classify(
                LoginStage::AppleLogin,
                report!(SideloadError::AnisetteNotProvisioned).into()
            ))
            .unwrap(),
            serde_json::json!({"stage": "appleLogin", "kind": "anisetteUnavailable"})
        );
    }

    #[test]
    fn synthetic_http_error_never_exposes_url_or_claims_ip_block() {
        // Construct a response in memory: no HTTP request, DNS or Apple contact.
        let response = axum::http::Response::builder()
            .status(403)
            .body("")
            .unwrap();
        let error = reqwest::Response::from(response)
            .error_for_status()
            .unwrap_err()
            .with_url(
                "https://synthetic.invalid/private?token=SYNTHETIC_TOKEN"
                    .parse()
                    .unwrap(),
            );
        assert_eq!(
            serde_json::to_value(classify(
                LoginStage::AccountSetup,
                report!(reqwest_middleware::Error::Reqwest(error)).into()
            ))
            .unwrap(),
            serde_json::json!({"stage": "accountSetup", "kind": "httpRejected", "httpStatus": 403})
        );
    }
}
