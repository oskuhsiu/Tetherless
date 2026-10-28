// SPDX-License-Identifier: AGPL-3.0-only
//! Explicit, bounded certificate operations. Private keys never enter this module.
//! The process-memory issuance guard is not durable across redeploys; recovery
//! files must therefore default to read-only reuse, never automatic reissuance.
use crate::{
    apple::{apple_error, certificate_matches_public_key},
    model::*,
};
use axum::http::StatusCode;
use base64::{Engine, engine::general_purpose::STANDARD};
use isideload::dev::{
    certificates::{CertificatesApi, DevelopmentCertificate},
    developer_session::DeveloperSession,
    device_type::DeveloperDeviceType,
    teams::{DeveloperTeam, TeamsApi},
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{HashMap, HashSet},
    future::Future,
    time::{Duration, Instant},
};
use x509_cert::{Certificate, der::Decode};

const MAX_TEAMS: usize = 128;
const MAX_CERTIFICATES: usize = 128;
const MAX_ISSUANCE_GUARDS: usize = 256;
const MAX_CONFIRMATIONS: usize = 512;
const CONFIRMATION_TTL: Duration = Duration::from_secs(300);

#[derive(Default)]
pub struct CertificateState {
    // Retain guards for the process lifetime. Never silently evict a submitted
    // operation and accidentally permit a second mutation.
    submitted: HashMap<String, Submitted>,
    revoked: HashSet<(String, String)>,
    confirmations: HashMap<String, Confirmation>,
}
struct Submitted {
    public_key: [u8; 32],
    serial: Option<String>,
}
struct Confirmation {
    session_id: String,
    team_id: String,
    certificate_id: String,
    serial: String,
    fingerprint: [u8; 32],
    created: Instant,
}
fn upstream() -> ApiError {
    ApiError(StatusCode::BAD_GATEWAY, ErrorCode::AppleRequestFailed)
}
fn uncertain() -> ApiError {
    ApiError(StatusCode::CONFLICT, ErrorCode::ProvisioningUncertain)
}
fn mismatch() -> ApiError {
    ApiError(StatusCode::CONFLICT, ErrorCode::CertificateMismatch)
}

pub(crate) trait CertificateDirectory {
    fn teams(&mut self) -> impl Future<Output = ApiResult<Vec<DeveloperTeam>>> + Send;
    fn certificates(
        &mut self,
        team: &DeveloperTeam,
    ) -> impl Future<Output = ApiResult<Vec<DevelopmentCertificate>>> + Send;
    fn require_device(
        &mut self,
        team: &DeveloperTeam,
        udid: &str,
    ) -> impl Future<Output = ApiResult<()>> + Send;
    fn submit(
        &mut self,
        team: &DeveloperTeam,
        csr: &str,
        name: &str,
    ) -> impl Future<Output = ApiResult<()>> + Send;
    fn revoke(
        &mut self,
        team: &DeveloperTeam,
        serial: &str,
    ) -> impl Future<Output = ApiResult<()>> + Send;
}
impl CertificateDirectory for DeveloperSession {
    async fn teams(&mut self) -> ApiResult<Vec<DeveloperTeam>> {
        self.list_teams().await.map_err(apple_error)
    }
    async fn certificates(
        &mut self,
        team: &DeveloperTeam,
    ) -> ApiResult<Vec<DevelopmentCertificate>> {
        self.list_ios_certs(team).await.map_err(apple_error)
    }
    async fn require_device(&mut self, team: &DeveloperTeam, udid: &str) -> ApiResult<()> {
        crate::devices::require_existing(self, team, udid).await
    }
    async fn submit(&mut self, team: &DeveloperTeam, csr: &str, name: &str) -> ApiResult<()> {
        self.submit_development_csr(
            team,
            csr.into(),
            name.into(),
            Some(DeveloperDeviceType::Ios),
        )
        .await
        .map(|_| ())
        .map_err(apple_error)
    }
    async fn revoke(&mut self, team: &DeveloperTeam, serial: &str) -> ApiResult<()> {
        self.revoke_development_cert(team, serial, Some(DeveloperDeviceType::Ios))
            .await
            .map_err(apple_error)
    }
}
pub(crate) async fn owned_team(
    dev: &mut impl CertificateDirectory,
    id: &str,
) -> ApiResult<DeveloperTeam> {
    if !valid_team_id(id) {
        return Err(invalid());
    }
    let teams = dev.teams().await?;
    if teams.len() > MAX_TEAMS {
        return Err(upstream());
    }
    teams
        .into_iter()
        .find(|t| t.team_id == id)
        .ok_or_else(invalid)
}
async fn bounded_certificates(
    dev: &mut impl CertificateDirectory,
    team: &DeveloperTeam,
) -> ApiResult<Vec<DevelopmentCertificate>> {
    let certs = dev.certificates(team).await?;
    if certs.len() > MAX_CERTIFICATES
        || certs.iter().any(|c| {
            c.cert_content
                .as_ref()
                .is_some_and(|b| b.as_ref().len() > 32 * 1024)
        })
    {
        return Err(upstream());
    }
    Ok(certs)
}
pub(crate) fn matching_unique<'a>(
    certs: &'a [DevelopmentCertificate],
    public_key: &[u8],
) -> ApiResult<Option<&'a DevelopmentCertificate>> {
    // Also called directly by the profiles-only stage; it must not bypass
    // catalog limits just because certificate preparation ran earlier.
    if certs.len() > MAX_CERTIFICATES
        || certs.iter().any(|c| {
            c.cert_content
                .as_ref()
                .is_some_and(|b| b.as_ref().len() > 32 * 1024)
        })
    {
        return Err(upstream());
    }
    let matches: Vec<_> = certs
        .iter()
        .filter(|cert| {
            cert.cert_content
                .as_ref()
                .is_some_and(|bytes| certificate_matches_public_key(bytes.as_ref(), public_key))
        })
        .collect();
    if matches.len() > 1 {
        return Err(mismatch());
    }
    Ok(matches.first().copied())
}
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CertificateOutput {
    pub team_id: String,
    pub certificate_der_base64: String,
    pub certificate_serial: Option<String>,
    pub certificate_reused: bool,
}
fn output(
    team_id: &str,
    certificate: &DevelopmentCertificate,
    reused: bool,
) -> ApiResult<CertificateOutput> {
    let der = certificate.cert_content.as_ref().ok_or_else(mismatch)?;
    let parsed = Certificate::from_der(der.as_ref()).map_err(|_| mismatch())?;
    let now = std::time::SystemTime::now();
    if parsed.tbs_certificate.validity.not_after.to_system_time() <= now
        || parsed.tbs_certificate.validity.not_before.to_system_time() > now
    {
        return Err(mismatch());
    }
    Ok(CertificateOutput {
        team_id: team_id.into(),
        certificate_der_base64: STANDARD.encode(der.as_ref()),
        certificate_serial: safe_optional(certificate.serial_number.clone()),
        certificate_reused: reused,
    })
}
pub async fn prepare(
    dev: &mut impl CertificateDirectory,
    state: &mut CertificateState,
    input: &ProvisionRequest,
    public_key: &[u8],
) -> ApiResult<CertificateOutput> {
    let team = owned_team(dev, &input.team_id).await?;
    if input.device.existing_only {
        dev.require_device(&team, &input.device.udid).await?;
    }
    let certs = bounded_certificates(dev, &team).await?;
    if let Some(existing) = matching_unique(&certs, public_key)? {
        let result = output(&team.team_id, existing, true)?;
        if let Some(submitted) = state.submitted.get_mut(&team.team_id) {
            if submitted.public_key == <[u8; 32]>::from(Sha256::digest(public_key)) {
                submitted.serial = result.certificate_serial.clone();
            }
        }
        return Ok(result);
    }
    if input.certificate_intent == CertificateIntent::ReuseOnly {
        return Err(ApiError(
            StatusCode::CONFLICT,
            ErrorCode::CertificateMissing,
        ));
    }
    // A different tab/key must not manufacture another certificate after any
    // uncertain submission for this Team. Exact chosen revocation can clear it.
    if state.submitted.contains_key(&team.team_id) {
        return Err(uncertain());
    }
    if state.submitted.len() >= MAX_ISSUANCE_GUARDS {
        return Err(ApiError(StatusCode::SERVICE_UNAVAILABLE, ErrorCode::Busy));
    }
    state.submitted.insert(
        team.team_id.clone(),
        Submitted {
            public_key: Sha256::digest(public_key).into(),
            serial: None,
        },
    ); // write-ahead, including timeout/cancellation
    if let Err(error) = dev.submit(&team, &input.csr_pem, &input.machine_name).await {
        // A typed capacity rejection is not an ambiguous transport result. It
        // reports that THIS submission was rejected (not that no earlier CSR
        // exists). Remove only the guard inserted immediately above. No retry
        // occurs here; a new explicit action/revocation is required in the UI.
        if matches!(error, ApiError(_, ErrorCode::CertificateLimit)) {
            state.submitted.remove(&team.team_id);
        }
        return Err(error);
    }
    let issued = bounded_certificates(dev, &team).await?;
    let cert = matching_unique(&issued, public_key)?.ok_or_else(uncertain)?;
    let result = output(&team.team_id, cert, false)?;
    if let Some(submitted) = state.submitted.get_mut(&team.team_id) {
        submitted.serial = result.certificate_serial.clone();
    }
    Ok(result)
}
fn safe_optional(s: Option<String>) -> Option<String> {
    s.filter(|s| safe_name(s))
}
fn identifier(s: &str) -> bool {
    !s.is_empty() && s.len() <= 128 && s.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')
}
fn fingerprint(cert: &DevelopmentCertificate) -> ApiResult<[u8; 32]> {
    // Exact public record, including DER, detects changed/replaced selection.
    Ok(Sha256::digest(serde_json::to_vec(cert).map_err(|_| upstream())?).into())
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CertificateMetadata {
    id: Option<String>,
    serial: Option<String>,
    name: Option<String>,
    machine_name: Option<String>,
    expires_at: Option<String>,
    status: Option<String>,
    confirmation_token: Option<String>,
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CertificateCatalog {
    team_id: String,
    certificates: Vec<CertificateMetadata>,
}
pub async fn list(
    dev: &mut impl CertificateDirectory,
    state: &mut CertificateState,
    session_id: &str,
    team_id: &str,
) -> ApiResult<CertificateCatalog> {
    let team = owned_team(dev, team_id).await?;
    let certs = bounded_certificates(dev, &team).await?;
    state.confirmations.retain(|_, c| {
        c.created.elapsed() < CONFIRMATION_TTL
            && !(c.session_id == session_id && c.team_id == team_id)
    });
    let mut seen_ids = HashSet::new();
    let mut seen_serials = HashSet::new();
    let mut result = Vec::with_capacity(certs.len());
    for cert in certs {
        let id = cert.certificate_id.clone().filter(|s| identifier(s));
        let serial = cert.serial_number.clone().filter(|s| identifier(s));
        let mut confirmation_token = None;
        if let (Some(id), Some(serial)) = (&id, &serial) {
            if !seen_ids.insert(id.clone()) || !seen_serials.insert(serial.clone()) {
                return Err(upstream());
            }
            if state.confirmations.len() < MAX_CONFIRMATIONS {
                let token = uuid::Uuid::new_v4().to_string();
                state.confirmations.insert(
                    token.clone(),
                    Confirmation {
                        session_id: session_id.into(),
                        team_id: team_id.into(),
                        certificate_id: id.clone(),
                        serial: serial.clone(),
                        fingerprint: fingerprint(&cert)?,
                        created: Instant::now(),
                    },
                );
                confirmation_token = Some(token);
            }
        }
        result.push(CertificateMetadata {
            id,
            serial,
            name: safe_optional(cert.name),
            machine_name: safe_optional(cert.machine_name),
            expires_at: cert.expiration_date.map(|d| d.to_xml_format()),
            status: safe_optional(cert.status),
            confirmation_token,
        });
    }
    Ok(CertificateCatalog {
        team_id: team_id.into(),
        certificates: result,
    })
}
#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RevokeRequest {
    pub certificate_id: String,
    pub certificate_serial: String,
    pub confirmation_token: String,
    pub consent: String,
}
impl RevokeRequest {
    pub fn validate(&self) -> ApiResult<()> {
        if self.consent != "revoke-selected-development-certificate"
            || !identifier(&self.certificate_id)
            || !identifier(&self.certificate_serial)
            || uuid::Uuid::parse_str(&self.confirmation_token).is_err()
        {
            return Err(invalid());
        }
        Ok(())
    }
}
pub async fn revoke(
    dev: &mut impl CertificateDirectory,
    state: &mut CertificateState,
    session_id: &str,
    team_id: &str,
    input: &RevokeRequest,
) -> ApiResult<()> {
    input.validate()?;
    let confirmation = state
        .confirmations
        .get(&input.confirmation_token)
        .ok_or_else(mismatch)?;
    if confirmation.session_id != session_id
        || confirmation.team_id != team_id
        || confirmation.certificate_id != input.certificate_id
        || confirmation.serial != input.certificate_serial
        || confirmation.created.elapsed() >= CONFIRMATION_TTL
    {
        return Err(mismatch());
    }
    let expected = confirmation.fingerprint;
    let team = owned_team(dev, team_id).await?;
    let certs = bounded_certificates(dev, &team).await?;
    if certs
        .iter()
        .filter(|c| c.serial_number.as_deref() == Some(&input.certificate_serial))
        .count()
        != 1
        || certs
            .iter()
            .filter(|c| c.certificate_id.as_deref() == Some(&input.certificate_id))
            .count()
            != 1
    {
        return Err(mismatch());
    }
    let cert = certs
        .iter()
        .find(|c| {
            c.certificate_id.as_deref() == Some(&input.certificate_id)
                && c.serial_number.as_deref() == Some(&input.certificate_serial)
        })
        .ok_or_else(mismatch)?;
    if fingerprint(cert)? != expected {
        return Err(mismatch());
    }
    // Consume BEFORE mutation: an ambiguous transport response must never replay.
    state.confirmations.remove(&input.confirmation_token);
    let revocation = (team_id.to_string(), input.certificate_serial.clone());
    if state.revoked.contains(&revocation) {
        return Err(uncertain());
    }
    if state.revoked.len() >= MAX_ISSUANCE_GUARDS {
        return Err(ApiError(StatusCode::SERVICE_UNAVAILABLE, ErrorCode::Busy));
    }
    state.revoked.insert(revocation);
    dev.revoke(&team, &input.certificate_serial).await?;
    let remaining = bounded_certificates(dev, &team).await?;
    if remaining
        .iter()
        .any(|c| c.serial_number.as_deref() == Some(&input.certificate_serial))
    {
        return Err(uncertain());
    }
    // Revoking an unrelated certificate must not clear an uncertain CSR guard.
    if state
        .submitted
        .get(team_id)
        .is_some_and(|s| s.serial.as_deref() == Some(&input.certificate_serial))
    {
        state.submitted.remove(team_id);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    };
    use x509_cert::der::Encode;
    struct Fake {
        certs: Vec<DevelopmentCertificate>,
        submitted: Arc<AtomicUsize>,
        revoked: usize,
        reads: usize,
        reject_read: bool,
        fail_submit: bool,
        capacity_reject: bool,
        pending_submit: bool,
        fail_revoke: bool,
        leave_after_revoke: bool,
        owned: bool,
    }
    impl Default for Fake {
        fn default() -> Self {
            Self {
                certs: vec![],
                submitted: Arc::new(AtomicUsize::new(0)),
                revoked: 0,
                reads: 0,
                reject_read: false,
                fail_submit: false,
                capacity_reject: false,
                pending_submit: false,
                fail_revoke: false,
                leave_after_revoke: false,
                owned: true,
            }
        }
    }
    fn cert() -> DevelopmentCertificate {
        DevelopmentCertificate {
            certificate_id: Some("SYNTHETICID".into()),
            serial_number: Some("ABC123".into()),
            name: Some("Synthetic certificate".into()),
            machine_name: Some("Synthetic machine".into()),
            cert_content: Some(
                include_bytes!("../tests/fixtures/certificate.der")
                    .to_vec()
                    .into(),
            ),
            certificate_platform: Some("ios".into()),
            machine_id: None,
            certificate_type: None,
            status: None,
            status_code: None,
            expiration_date: None,
        }
    }
    fn request() -> ProvisionRequest {
        serde_json::from_value(serde_json::json!({
            "consent":"register-device-app-ids-and-issue-certificate", "teamId":"SYNTHETIC", "certificateIntent":"createOrReuse",
            "device":{"udid":"0000000000000000000000000000000000000000","name":"Synthetic"},
            "csrPem":include_str!("../tests/fixtures/request.pem"), "machineName":"Synthetic", "apps":[{"bundleId":"org.example.synthetic","name":"Synthetic"}]
        })).unwrap()
    }
    fn key() -> Vec<u8> {
        Certificate::from_der(include_bytes!("../tests/fixtures/certificate.der"))
            .unwrap()
            .tbs_certificate
            .subject_public_key_info
            .to_der()
            .unwrap()
    }
    impl CertificateDirectory for Fake {
        async fn teams(&mut self) -> ApiResult<Vec<DeveloperTeam>> {
            Ok(if self.owned {
                vec![DeveloperTeam {
                    team_id: "SYNTHETIC".into(),
                    name: None,
                    r#type: None,
                    status: None,
                }]
            } else {
                vec![]
            })
        }
        async fn certificates(
            &mut self,
            _: &DeveloperTeam,
        ) -> ApiResult<Vec<DevelopmentCertificate>> {
            self.reads += 1;
            if self.reject_read {
                Err(upstream())
            } else {
                Ok(self.certs.clone())
            }
        }
        async fn require_device(&mut self, _: &DeveloperTeam, _: &str) -> ApiResult<()> {
            Ok(())
        }
        async fn submit(&mut self, _: &DeveloperTeam, _: &str, _: &str) -> ApiResult<()> {
            self.submitted.fetch_add(1, Ordering::SeqCst);
            if self.pending_submit {
                return std::future::pending().await;
            }
            if self.capacity_reject {
                return Err(ApiError(StatusCode::CONFLICT, ErrorCode::CertificateLimit));
            }
            if self.fail_submit {
                return Err(upstream());
            }
            self.certs.push(cert());
            Ok(())
        }
        async fn revoke(&mut self, _: &DeveloperTeam, _: &str) -> ApiResult<()> {
            self.revoked += 1;
            if self.fail_revoke {
                return Err(upstream());
            }
            if !self.leave_after_revoke {
                self.certs.clear();
            }
            Ok(())
        }
    }
    fn revoke_input(catalog: &CertificateCatalog) -> RevokeRequest {
        let c = &catalog.certificates[0];
        RevokeRequest {
            certificate_id: c.id.clone().unwrap(),
            certificate_serial: c.serial.clone().unwrap(),
            confirmation_token: c.confirmation_token.clone().unwrap(),
            consent: "revoke-selected-development-certificate".into(),
        }
    }
    #[tokio::test]
    async fn certificate_is_returned_before_any_profile_step_and_same_key_is_reused() {
        let mut dev = Fake::default();
        let mut state = CertificateState::default();
        let output = prepare(&mut dev, &mut state, &request(), &key())
            .await
            .unwrap();
        assert!(!output.certificate_reused);
        assert_eq!(
            output.certificate_der_base64,
            STANDARD.encode(include_bytes!("../tests/fixtures/certificate.der"))
        );
        // A later profiles failure cannot remove the public cert/private-key backup;
        // a new session restores the same public key and reads the existing cert.
        let output = prepare(&mut dev, &mut state, &request(), &key())
            .await
            .unwrap();
        assert!(output.certificate_reused);
        assert_eq!(dev.submitted.load(Ordering::SeqCst), 1);
        assert_eq!(dev.revoked, 0);
    }
    #[tokio::test]
    async fn reuse_only_missing_and_read_error_never_issue() {
        let mut dev = Fake::default();
        let mut state = CertificateState::default();
        let mut input = request();
        input.certificate_intent = CertificateIntent::ReuseOnly;
        assert!(matches!(
            prepare(&mut dev, &mut state, &input, &key()).await,
            Err(ApiError(_, ErrorCode::CertificateMissing))
        ));
        dev.reject_read = true;
        input.certificate_intent = CertificateIntent::CreateOrReuse;
        assert!(prepare(&mut dev, &mut state, &input, &key()).await.is_err());
        assert_eq!(dev.submitted.load(Ordering::SeqCst), 0);
        assert!(state.submitted.is_empty());
    }
    #[tokio::test]
    async fn uncertain_submit_blocks_same_and_different_keys_across_sessions() {
        let mut dev = Fake {
            fail_submit: true,
            ..Default::default()
        };
        let mut state = CertificateState::default();
        assert!(
            prepare(&mut dev, &mut state, &request(), &key())
                .await
                .is_err()
        );
        for key in [key(), vec![1, 2, 3]] {
            assert!(matches!(
                prepare(&mut dev, &mut state, &request(), &key).await,
                Err(ApiError(_, ErrorCode::ProvisioningUncertain))
            ));
        }
        assert_eq!(dev.submitted.load(Ordering::SeqCst), 1);
        // Apple eventually returns the accepted certificate: readback recovers.
        dev.certs.push(cert());
        let output = prepare(&mut dev, &mut state, &request(), &key())
            .await
            .unwrap();
        assert!(output.certificate_reused);
        assert_eq!(dev.submitted.load(Ordering::SeqCst), 1);
    }
    #[tokio::test]
    async fn cancellation_after_submission_keeps_write_ahead_guard() {
        let mut dev = Fake {
            pending_submit: true,
            ..Default::default()
        };
        let mut state = CertificateState::default();
        let input = request();
        let key = key();
        assert!(
            tokio::time::timeout(
                Duration::from_millis(1),
                prepare(&mut dev, &mut state, &input, &key)
            )
            .await
            .is_err()
        );
        dev.pending_submit = false;
        assert!(matches!(
            prepare(&mut dev, &mut state, &input, &key).await,
            Err(ApiError(_, ErrorCode::ProvisioningUncertain))
        ));
        assert_eq!(dev.submitted.load(Ordering::SeqCst), 1);
    }
    #[test]
    fn profile_stage_matching_applies_the_same_certificate_bounds() {
        assert!(matching_unique(&vec![cert(); MAX_CERTIFICATES + 1], &key()).is_err());
        let mut oversized = cert();
        oversized.cert_content = Some(vec![0; 32 * 1024 + 1].into());
        assert!(matching_unique(&[oversized], &key()).is_err());
    }
    #[tokio::test]
    async fn duplicate_key_is_ambiguous_not_permission_to_issue() {
        let mut dev = Fake {
            certs: vec![cert(), cert()],
            ..Default::default()
        };
        let mut state = CertificateState::default();
        assert!(matches!(
            prepare(&mut dev, &mut state, &request(), &key()).await,
            Err(ApiError(_, ErrorCode::CertificateMismatch))
        ));
        assert_eq!(dev.submitted.load(Ordering::SeqCst), 0);
    }
    #[tokio::test]
    async fn account_team_is_checked_before_all_certificate_operations() {
        let mut dev = Fake {
            owned: false,
            ..Default::default()
        };
        let mut state = CertificateState::default();
        assert!(
            prepare(&mut dev, &mut state, &request(), &key())
                .await
                .is_err()
        );
        assert!(
            list(&mut dev, &mut state, "session", "SYNTHETIC")
                .await
                .is_err()
        );
        assert_eq!(dev.reads, 0);
        assert_eq!(dev.submitted.load(Ordering::SeqCst), 0);
    }
    #[tokio::test]
    async fn revoke_requires_exact_session_team_serial_fresh_record_and_one_shot_confirmation() {
        let mut dev = Fake {
            certs: vec![cert()],
            ..Default::default()
        };
        let mut state = CertificateState::default();
        let catalog = list(&mut dev, &mut state, "session", "SYNTHETIC")
            .await
            .unwrap();
        let mut input = revoke_input(&catalog);
        assert!(
            revoke(&mut dev, &mut state, "other", "SYNTHETIC", &input)
                .await
                .is_err()
        );
        assert!(
            revoke(&mut dev, &mut state, "session", "OTHER", &input)
                .await
                .is_err()
        );
        input.certificate_serial = "OTHER".into();
        assert!(
            revoke(&mut dev, &mut state, "session", "SYNTHETIC", &input)
                .await
                .is_err()
        );
        input.certificate_serial = "ABC123".into();
        dev.certs[0].name = Some("Replaced".into());
        assert!(
            revoke(&mut dev, &mut state, "session", "SYNTHETIC", &input)
                .await
                .is_err()
        );
        dev.certs[0] = cert();
        assert_eq!(dev.revoked, 0);
        revoke(&mut dev, &mut state, "session", "SYNTHETIC", &input)
            .await
            .unwrap();
        assert!(
            revoke(&mut dev, &mut state, "session", "SYNTHETIC", &input)
                .await
                .is_err()
        );
        assert_eq!(dev.revoked, 1);
    }
    #[tokio::test]
    async fn uncertain_revoke_cannot_be_replayed_even_with_fresh_confirmation() {
        let mut dev = Fake {
            certs: vec![cert()],
            fail_revoke: true,
            ..Default::default()
        };
        let mut state = CertificateState::default();
        for _ in 0..2 {
            let input = revoke_input(
                &list(&mut dev, &mut state, "session", "SYNTHETIC")
                    .await
                    .unwrap(),
            );
            assert!(
                revoke(&mut dev, &mut state, "session", "SYNTHETIC", &input)
                    .await
                    .is_err()
            );
        }
        assert_eq!(dev.revoked, 1);
        assert_eq!(dev.submitted.load(Ordering::SeqCst), 0);
    }
    #[tokio::test]
    async fn unrelated_revocation_does_not_unlock_uncertain_issuance() {
        let mut dev = Fake {
            certs: vec![cert()],
            ..Default::default()
        };
        let mut state = CertificateState::default();
        state.submitted.insert(
            "SYNTHETIC".into(),
            Submitted {
                public_key: [0; 32],
                serial: None,
            },
        );
        let input = revoke_input(
            &list(&mut dev, &mut state, "session", "SYNTHETIC")
                .await
                .unwrap(),
        );
        revoke(&mut dev, &mut state, "session", "SYNTHETIC", &input)
            .await
            .unwrap();
        assert!(state.submitted.contains_key("SYNTHETIC"));
        assert!(matches!(
            prepare(&mut dev, &mut state, &request(), &key()).await,
            Err(ApiError(_, ErrorCode::ProvisioningUncertain))
        ));
        assert_eq!(dev.submitted.load(Ordering::SeqCst), 0);
    }
    #[tokio::test]
    async fn explicit_quota_rejection_can_recover_after_user_revokes_old_certificate() {
        let mut dev = Fake {
            capacity_reject: true,
            ..Default::default()
        };
        let mut state = CertificateState::default();
        assert!(matches!(
            prepare(&mut dev, &mut state, &request(), &key()).await,
            Err(ApiError(_, ErrorCode::CertificateLimit))
        ));
        assert!(!state.submitted.contains_key("SYNTHETIC"));
        // A selected old certificate can then be revoked explicitly, not by prepare.
        dev.certs.push(cert());
        let input = revoke_input(
            &list(&mut dev, &mut state, "session", "SYNTHETIC")
                .await
                .unwrap(),
        );
        revoke(&mut dev, &mut state, "session", "SYNTHETIC", &input)
            .await
            .unwrap();
        dev.capacity_reject = false;
        prepare(&mut dev, &mut state, &request(), &key())
            .await
            .unwrap();
        assert_eq!(dev.submitted.load(Ordering::SeqCst), 2);
        assert_eq!(dev.revoked, 1);
    }
    #[tokio::test]
    async fn exact_confirmed_revocation_readback_allows_explicit_new_issuance() {
        let mut dev = Fake::default();
        let mut state = CertificateState::default();
        prepare(&mut dev, &mut state, &request(), &key())
            .await
            .unwrap();
        let input = revoke_input(
            &list(&mut dev, &mut state, "session", "SYNTHETIC")
                .await
                .unwrap(),
        );
        revoke(&mut dev, &mut state, "session", "SYNTHETIC", &input)
            .await
            .unwrap();
        assert!(!state.submitted.contains_key("SYNTHETIC"));
        assert_eq!(dev.submitted.load(Ordering::SeqCst), 1); // revoke never generates
        prepare(&mut dev, &mut state, &request(), &key())
            .await
            .unwrap();
        assert_eq!(dev.submitted.load(Ordering::SeqCst), 2);
    }
    #[tokio::test]
    async fn catalog_is_minimal_bounded_and_duplicate_identifiers_fail_closed() {
        let mut dev = Fake {
            certs: vec![cert()],
            ..Default::default()
        };
        let mut state = CertificateState::default();
        let catalog = list(&mut dev, &mut state, "session", "SYNTHETIC")
            .await
            .unwrap();
        let body = serde_json::to_string(&catalog).unwrap();
        for forbidden in ["certContent", "privateKey", "machineId", "statusCode"] {
            assert!(!body.contains(forbidden));
        }
        let mut second = cert();
        second.certificate_id = Some("OTHER".into());
        dev.certs.push(second);
        assert!(
            list(&mut dev, &mut state, "session", "SYNTHETIC")
                .await
                .is_err()
        );
        dev.certs = vec![cert(); MAX_CERTIFICATES + 1];
        assert!(
            list(&mut dev, &mut state, "session", "SYNTHETIC")
                .await
                .is_err()
        );
    }
    #[tokio::test]
    async fn simultaneous_sessions_with_stale_directories_submit_only_once() {
        let state = Arc::new(tokio::sync::Mutex::new(CertificateState::default()));
        let submitted = Arc::new(AtomicUsize::new(0));
        let barrier = Arc::new(tokio::sync::Barrier::new(2));
        let mut tasks = Vec::new();
        for _ in 0..2 {
            let state = state.clone();
            let submitted = submitted.clone();
            let barrier = barrier.clone();
            tasks.push(tokio::spawn(async move {
                let mut dev = Fake {
                    submitted,
                    ..Default::default()
                };
                barrier.wait().await;
                let mut state = state.lock().await;
                prepare(&mut dev, &mut state, &request(), &key())
                    .await
                    .is_ok()
            }));
        }
        let mut successes = 0;
        for task in tasks {
            if task.await.unwrap() {
                successes += 1;
            }
        }
        assert_eq!(successes, 1);
        assert_eq!(submitted.load(Ordering::SeqCst), 1);
    }
    #[tokio::test]
    async fn restarting_process_does_not_turn_imported_recovery_into_creation() {
        let mut dev = Fake {
            fail_submit: true,
            ..Default::default()
        };
        let mut state = CertificateState::default();
        assert!(
            prepare(&mut dev, &mut state, &request(), &key())
                .await
                .is_err()
        );
        let mut restarted = CertificateState::default();
        let mut recovery = request();
        recovery.certificate_intent = CertificateIntent::ReuseOnly;
        assert!(matches!(
            prepare(&mut dev, &mut restarted, &recovery, &key()).await,
            Err(ApiError(_, ErrorCode::CertificateMissing))
        ));
        assert_eq!(dev.submitted.load(Ordering::SeqCst), 1);
    }
    #[tokio::test]
    async fn unconfirmed_revocation_and_missing_or_changed_record_never_mutate() {
        let mut dev = Fake {
            certs: vec![cert()],
            ..Default::default()
        };
        let mut state = CertificateState::default();
        let mut input = revoke_input(
            &list(&mut dev, &mut state, "session", "SYNTHETIC")
                .await
                .unwrap(),
        );
        input.consent = "yes".into();
        assert!(
            revoke(&mut dev, &mut state, "session", "SYNTHETIC", &input)
                .await
                .is_err()
        );
        input.consent = "revoke-selected-development-certificate".into();
        dev.certs.clear();
        assert!(
            revoke(&mut dev, &mut state, "session", "SYNTHETIC", &input)
                .await
                .is_err()
        );
        dev.certs = vec![cert(), cert()];
        assert!(
            revoke(&mut dev, &mut state, "session", "SYNTHETIC", &input)
                .await
                .is_err()
        );
        assert_eq!(dev.revoked, 0);
    }
    #[tokio::test]
    async fn full_guard_table_refuses_creation_instead_of_evicting_uncertain_work() {
        let mut dev = Fake::default();
        let mut state = CertificateState::default();
        for i in 0..MAX_ISSUANCE_GUARDS {
            state.submitted.insert(
                format!("TEAM{i}"),
                Submitted {
                    public_key: [0; 32],
                    serial: None,
                },
            );
        }
        assert!(matches!(
            prepare(&mut dev, &mut state, &request(), &key()).await,
            Err(ApiError(_, ErrorCode::Busy))
        ));
        assert_eq!(state.submitted.len(), MAX_ISSUANCE_GUARDS);
        assert_eq!(dev.submitted.load(Ordering::SeqCst), 0);
    }
    #[tokio::test]
    async fn expired_confirmation_cannot_mutate() {
        let mut dev = Fake {
            certs: vec![cert()],
            ..Default::default()
        };
        let mut state = CertificateState::default();
        let input = revoke_input(
            &list(&mut dev, &mut state, "session", "SYNTHETIC")
                .await
                .unwrap(),
        );
        state
            .confirmations
            .get_mut(&input.confirmation_token)
            .unwrap()
            .created = Instant::now() - CONFIRMATION_TTL;
        assert!(
            revoke(&mut dev, &mut state, "session", "SYNTHETIC", &input)
                .await
                .is_err()
        );
        assert_eq!(dev.revoked, 0);
    }
}
