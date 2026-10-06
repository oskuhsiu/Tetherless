// SPDX-License-Identifier: AGPL-3.0-only
use axum::{
    Json,
    http::StatusCode,
    response::{IntoResponse, Response},
};
use rsa::{
    RsaPublicKey,
    pkcs1v15::{Signature, VerifyingKey},
    pkcs8::DecodePublicKey,
    signature::Verifier,
    traits::PublicKeyParts,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use x509_cert::{
    der::{DecodePem, Encode},
    request::CertReq,
};

#[derive(Clone, Copy, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum ErrorCode {
    InvalidRequest,
    NotFound,
    Unauthorized,
    Busy,
    Expired,
    WrongState,
    AppleAuthenticationFailed,
    AppleRequestFailed,
    CertificateLimit,
    CertificateMismatch,
    ProfileMismatch,
    ProvisioningUncertain,
    OriginRejected,
}

#[derive(Clone, Copy, Debug)]
pub struct ApiError(pub StatusCode, pub ErrorCode);
impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (self.0, Json(serde_json::json!({"error": self.1}))).into_response()
    }
}
pub type ApiResult<T> = Result<T, ApiError>;
pub fn invalid() -> ApiError {
    ApiError(StatusCode::BAD_REQUEST, ErrorCode::InvalidRequest)
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct StartRequest {
    pub apple_id: String,
    pub password: String,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SessionView {
    pub state: &'static str,
    pub challenge: Option<Challenge>,
    pub error: Option<ErrorCode>,
}
impl SessionView {
    pub fn state(state: &'static str) -> Self {
        Self {
            state,
            challenge: None,
            error: None,
        }
    }
    pub fn failed(error: ErrorCode) -> Self {
        Self {
            state: "failed",
            challenge: None,
            error: Some(error),
        }
    }
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PhoneChoice {
    pub id: u32,
    pub last_two_digits: String,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Challenge {
    pub sms: bool,
    pub unknown: bool,
    pub retry: bool,
    pub numbers: Vec<PhoneChoice>,
    pub selected_number_id: Option<u32>,
}

#[derive(Deserialize)]
#[serde(tag = "action", rename_all = "camelCase", deny_unknown_fields)]
pub enum TwoFactorRequest {
    SubmitCode {
        code: String,
    },
    SendSms {
        #[serde(rename = "numberId")]
        number_id: u32,
    },
    SendToDevices,
    ResendCode,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct DeviceInput {
    pub udid: String,
    pub name: String,
}
#[derive(Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct AppInput {
    pub bundle_id: String,
    pub name: String,
}
#[derive(Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct AppGroupInput {
    pub identifier: String,
    pub name: String,
}
#[derive(Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ProvisionRequest {
    /// Exact action consent, displayed by the client before submitting.
    pub consent: String,
    pub team_id: String,
    pub device: DeviceInput,
    pub csr_pem: String,
    pub machine_name: String,
    pub apps: Vec<AppInput>,
    #[serde(default)]
    pub app_group: Option<AppGroupInput>,
}

impl ProvisionRequest {
    /// Only transport/metadata checks. Apple validates the CSR; this does not
    /// replace native signing admission or establish installed-app trust.
    pub fn validate(&self) -> ApiResult<Vec<u8>> {
        let required_consent = if self.app_group.is_some() {
            "register-device-app-ids-app-group-and-issue-certificate"
        } else {
            "register-device-app-ids-and-issue-certificate"
        };
        if self.consent != required_consent {
            return Err(invalid());
        }
        if let Some(group) = &self.app_group
            && (!group.identifier.starts_with("group.")
                || !valid_bundle_id(&group.identifier)
                || !safe_name(&group.name))
        {
            return Err(invalid());
        }
        if !self.team_id.bytes().all(|b| b.is_ascii_alphanumeric())
            || !(1..=64).contains(&self.team_id.len())
        {
            return Err(invalid());
        }
        if !valid_udid(&self.device.udid)
            || !safe_name(&self.device.name)
            || !safe_name(&self.machine_name)
            || !(1..=16).contains(&self.apps.len())
            || self.csr_pem.len() > 16_384
        {
            return Err(invalid());
        }
        let mut ids = HashSet::new();
        for app in &self.apps {
            if !safe_name(&app.name)
                || !valid_bundle_id(&app.bundle_id)
                || !ids.insert(&app.bundle_id)
            {
                return Err(invalid());
            }
        }
        let request = CertReq::from_pem(self.csr_pem.as_bytes()).map_err(|_| invalid())?;
        let spki = request.info.public_key.to_der().map_err(|_| invalid())?;
        let key = RsaPublicKey::from_public_key_der(&spki).map_err(|_| invalid())?;
        if key.n().bits() != 2048 || request.algorithm.oid.to_string() != "1.2.840.113549.1.1.11" {
            return Err(invalid());
        }
        let signature = Signature::try_from(request.signature.as_bytes().ok_or_else(invalid)?)
            .map_err(|_| invalid())?;
        VerifyingKey::<Sha256>::new(key)
            .verify(&request.info.to_der().map_err(|_| invalid())?, &signature)
            .map_err(|_| invalid())?;
        Ok(spki)
    }
    pub fn fingerprint(&self) -> ApiResult<[u8; 32]> {
        let bytes = serde_json::to_vec(self).map_err(|_| invalid())?;
        Ok(Sha256::digest(bytes).into())
    }
}
pub fn valid_udid(udid: &str) -> bool {
    (udid.len() == 40 && udid.bytes().all(|b| b.is_ascii_hexdigit()))
        || (udid.len() == 25
            && udid.as_bytes()[8] == b'-'
            && udid
                .bytes()
                .enumerate()
                .all(|(i, b)| i == 8 || b.is_ascii_hexdigit()))
}
pub fn safe_name(s: &str) -> bool {
    !s.trim().is_empty() && s.len() <= 128 && !s.chars().any(char::is_control)
}
pub fn valid_bundle_id(s: &str) -> bool {
    (3..=200).contains(&s.len())
        && s.contains('.')
        && s.split('.').all(|part| {
            !part.is_empty() && part.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')
        })
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProfileOutput {
    pub bundle_id: String,
    pub profile_base64: String,
    pub profile_id: String,
}
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProvisionOutput {
    pub team_id: String,
    pub certificate_der_base64: String,
    pub certificate_serial: Option<String>,
    pub certificate_reused: bool,
    pub app_group_identifier: Option<String>,
    pub profiles: Vec<ProfileOutput>,
    pub verification: &'static str,
}

#[cfg(test)]
mod tests {
    use super::*;
    use x509_cert::der::Decode;
    #[test]
    fn bundle_ids_are_explicit_not_patterns() {
        for id in ["org.example.Tetherless", "com.example.extension-1"] {
            assert!(valid_bundle_id(id));
        }
        for id in [
            "*",
            "com.*",
            "com..app",
            "com.app/evil",
            "com.app\n",
            ".app",
            "com.app.",
        ] {
            assert!(!valid_bundle_id(id));
        }
    }
    #[test]
    fn request_rejects_private_keys_and_extra_destinations() {
        assert!(
            serde_json::from_str::<StartRequest>(
                r#"{"appleId":"x","password":"x","proxy":"https://evil"}"#
            )
            .is_err()
        );
        assert!(serde_json::from_str::<ProvisionRequest>(r#"{"privateKey":"SECRET"}"#).is_err());
    }
    #[test]
    fn fixed_errors_cannot_include_upstream_secrets() {
        assert_eq!(
            serde_json::to_string(&ErrorCode::AppleAuthenticationFailed).unwrap(),
            "\"appleAuthenticationFailed\""
        );
        assert!(!safe_name("name\nsecret"));
    }
    fn synthetic_request() -> ProvisionRequest {
        ProvisionRequest {
            consent: "register-device-app-ids-and-issue-certificate".into(),
            team_id: "SYNTHETIC".into(),
            device: DeviceInput {
                udid: "0".repeat(40),
                name: "Synthetic Device".into(),
            },
            csr_pem: include_str!("../tests/fixtures/request.pem").into(),
            machine_name: "Synthetic".into(),
            apps: vec![AppInput {
                bundle_id: "org.example.synthetic".into(),
                name: "Synthetic".into(),
            }],
            app_group: None,
        }
    }
    #[test]
    fn synthetic_csr_signature_and_metadata_are_checked_offline() {
        let mut input = synthetic_request();
        let key = input.validate().unwrap();
        let cert =
            x509_cert::Certificate::from_der(include_bytes!("../tests/fixtures/certificate.der"))
                .unwrap();
        assert_eq!(
            key,
            cert.tbs_certificate
                .subject_public_key_info
                .to_der()
                .unwrap()
        );
        input.consent = "not-approved".into();
        assert!(input.validate().is_err());
    }
    #[test]
    fn synthetic_csr_rejects_broken_signature_and_duplicate_app_ids() {
        let mut input = synthetic_request();
        let mut request = CertReq::from_pem(input.csr_pem.as_bytes()).unwrap();
        request.info.subject = "CN=Tampered".parse().unwrap();
        input.csr_pem =
            x509_cert::der::EncodePem::to_pem(&request, x509_cert::der::pem::LineEnding::LF)
                .unwrap();
        assert!(input.validate().is_err());
        let mut input = synthetic_request();
        input.apps.push(AppInput {
            bundle_id: "org.example.synthetic".into(),
            name: "Duplicate".into(),
        });
        assert!(input.validate().is_err());
    }
    #[test]
    fn app_group_requires_distinct_explicit_consent_without_identifier_rewriting() {
        let mut input = synthetic_request();
        input.app_group = Some(AppGroupInput {
            identifier: "group.org.tetherless.Tetherless".into(),
            name: "Tetherless".into(),
        });
        assert!(input.validate().is_err());
        input.consent = "register-device-app-ids-app-group-and-issue-certificate".into();
        assert!(input.validate().is_ok());
        assert_eq!(
            input.app_group.unwrap().identifier,
            "group.org.tetherless.Tetherless"
        );
    }
}
