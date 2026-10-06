// SPDX-License-Identifier: AGPL-3.0-only
//! This adapter calls the pinned real isideload APIs. No production mocks.
use crate::model::*;
use axum::http::StatusCode;
use base64::{Engine, engine::general_purpose::STANDARD};
use isideload::{
    SideloadError,
    dev::{
        app_groups::AppGroupsApi,
        app_ids::AppIdsApi,
        certificates::{CertificatesApi, DevelopmentCertificate},
        developer_session::DeveloperSession,
        devices::DevicesApi,
        teams::TeamsApi,
    },
};
use openssl::{
    pkcs7::{Pkcs7, Pkcs7Flags},
    stack::Stack,
    x509::store::X509StoreBuilder,
};
use x509_cert::{
    Certificate,
    der::{Decode, Encode},
};

fn profile_mismatch() -> ApiError {
    ApiError(StatusCode::BAD_GATEWAY, ErrorCode::ProfileMismatch)
}

/// Uses existing CMS and plist implementations. Signature integrity is checked;
/// no independent Apple signer-chain trust or device launch is inferred.
fn validate_profile(
    bytes: &[u8],
    team: &str,
    bundle: &str,
    udid: &str,
    certificate: &[u8],
    group: Option<&str>,
) -> ApiResult<()> {
    if bytes.is_empty() || bytes.len() > 2 * 1024 * 1024 {
        return Err(profile_mismatch());
    }
    let cms = Pkcs7::from_der(bytes).map_err(|_| profile_mismatch())?;
    let certs = Stack::new().map_err(|_| profile_mismatch())?;
    if cms
        .signers(&certs, Pkcs7Flags::empty())
        .map_err(|_| profile_mismatch())?
        .len()
        != 1
    {
        return Err(profile_mismatch());
    }
    let trust = X509StoreBuilder::new()
        .map_err(|_| profile_mismatch())?
        .build();
    let mut content = Vec::new();
    cms.verify(
        &certs,
        &trust,
        None,
        Some(&mut content),
        Pkcs7Flags::NOVERIFY | Pkcs7Flags::BINARY,
    )
    .map_err(|_| profile_mismatch())?;
    if content.len() > 2 * 1024 * 1024 {
        return Err(profile_mismatch());
    }
    let profile: plist::Dictionary = plist::from_bytes(&content).map_err(|_| profile_mismatch())?;
    validate_profile_metadata(&profile, team, bundle, udid, certificate, group)
}

fn validate_profile_metadata(
    profile: &plist::Dictionary,
    team: &str,
    bundle: &str,
    udid: &str,
    certificate: &[u8],
    group: Option<&str>,
) -> ApiResult<()> {
    let array = |key| {
        profile
            .get(key)
            .and_then(plist::Value::as_array)
            .ok_or_else(profile_mismatch)
    };
    if !array("TeamIdentifier")?
        .iter()
        .any(|v| v.as_string() == Some(team))
        || !array("ProvisionedDevices")?
            .iter()
            .any(|v| v.as_string().is_some_and(|s| s.eq_ignore_ascii_case(udid)))
        || !array("DeveloperCertificates")?
            .iter()
            .any(|v| v.as_data() == Some(certificate))
        || profile
            .get("ExpirationDate")
            .and_then(plist::Value::as_date)
            .map(std::time::SystemTime::from)
            .is_none_or(|date| date <= std::time::SystemTime::now())
    {
        return Err(profile_mismatch());
    }
    let entitlements = profile
        .get("Entitlements")
        .and_then(plist::Value::as_dictionary)
        .ok_or_else(profile_mismatch)?;
    if entitlements
        .get("com.apple.developer.team-identifier")
        .and_then(plist::Value::as_string)
        != Some(team)
    {
        return Err(profile_mismatch());
    }
    let app_id = entitlements
        .get("application-identifier")
        .and_then(plist::Value::as_string)
        .ok_or_else(profile_mismatch)?;
    if !array("ApplicationIdentifierPrefix")?
        .iter()
        .filter_map(plist::Value::as_string)
        .any(|prefix| app_id == format!("{prefix}.{bundle}"))
    {
        return Err(profile_mismatch());
    }
    if let Some(group) = group
        && !entitlements
            .get("com.apple.security.application-groups")
            .and_then(plist::Value::as_array)
            .is_some_and(|groups| groups.iter().any(|v| v.as_string() == Some(group)))
    {
        return Err(profile_mismatch());
    }
    Ok(())
}

fn apple_error(report: rootcause::Report) -> ApiError {
    // Never format a report: upstream messages may carry private server data.
    let capacity = report.iter_reports().any(|node| {
        matches!(
            node.downcast_current_context::<SideloadError>(),
            Some(SideloadError::DeveloperError(7460, _))
        )
    });
    if capacity {
        ApiError(StatusCode::CONFLICT, ErrorCode::CertificateLimit)
    } else {
        ApiError(StatusCode::BAD_GATEWAY, ErrorCode::AppleRequestFailed)
    }
}

fn matching_certificate<'a>(
    certs: &'a [DevelopmentCertificate],
    public_key: &[u8],
) -> Option<&'a DevelopmentCertificate> {
    certs.iter().find(|cert| {
        cert.cert_content
            .as_ref()
            .is_some_and(|bytes| certificate_matches_public_key(bytes.as_ref(), public_key))
    })
}

fn certificate_matches_public_key(bytes: &[u8], public_key: &[u8]) -> bool {
    Certificate::from_der(bytes)
        .ok()
        .and_then(|parsed| parsed.tbs_certificate.subject_public_key_info.to_der().ok())
        .is_some_and(|key| key == public_key)
}

pub async fn provision(
    dev: &mut DeveloperSession,
    input: &ProvisionRequest,
    public_key: &[u8],
) -> ApiResult<ProvisionOutput> {
    let teams = dev.list_teams().await.map_err(apple_error)?;
    let team = teams
        .into_iter()
        .find(|t| t.team_id == input.team_id)
        .ok_or_else(invalid)?;
    // Existing-only intent is checked before ANY certificate/App ID/device mutation.
    // Re-read the selected authenticated team's directory; never silently register,
    // enable, or substitute a missing/disabled/unknown device.
    if input.device.existing_only {
        crate::devices::require_existing(dev, &team, &input.device.udid).await?;
    }
    // Read and reuse an account-owned certificate with the CSR's exact public key.
    // Calling CertificateIdentity::retrieve would introduce key persistence and
    // optional revocation. This service intentionally never calls that API.
    let certificates = dev.list_ios_certs(&team).await.map_err(apple_error)?;
    let (certificate, reused) =
        if let Some(existing) = matching_certificate(&certificates, public_key) {
            (existing.clone(), true)
        } else {
            // Exactly one issuance submission per accepted provisioning request.
            // There is no automatic network retry or certificate revocation.
            let request = dev
                .submit_development_csr(
                    &team,
                    input.csr_pem.clone(),
                    input.machine_name.clone(),
                    None,
                )
                .await
                .map_err(apple_error)?;
            let issued = dev.list_ios_certs(&team).await.map_err(apple_error)?;
            let certificate = issued
                .into_iter()
                .find(|c| c.certificate_id.as_deref() == Some(request.cert_request_id.as_str()))
                .ok_or(ApiError(
                    StatusCode::BAD_GATEWAY,
                    ErrorCode::ProvisioningUncertain,
                ))?;
            (certificate, false)
        };
    let der = certificate.cert_content.as_ref().ok_or(ApiError(
        StatusCode::BAD_GATEWAY,
        ErrorCode::CertificateMismatch,
    ))?;
    let parsed = Certificate::from_der(der.as_ref())
        .map_err(|_| ApiError(StatusCode::BAD_GATEWAY, ErrorCode::CertificateMismatch))?;
    if parsed
        .tbs_certificate
        .subject_public_key_info
        .to_der()
        .map_err(|_| invalid())?
        != public_key
    {
        return Err(ApiError(
            StatusCode::BAD_GATEWAY,
            ErrorCode::CertificateMismatch,
        ));
    }
    let now = std::time::SystemTime::now();
    if parsed.tbs_certificate.validity.not_after.to_system_time() <= now
        || parsed.tbs_certificate.validity.not_before.to_system_time() > now
    {
        return Err(ApiError(
            StatusCode::BAD_GATEWAY,
            ErrorCode::CertificateMismatch,
        ));
    }
    if !input.device.existing_only {
        let devices = dev.list_devices(&team, None).await.map_err(apple_error)?;
        if !devices.iter().any(|d| d.device_number == input.device.udid) {
            dev.add_device(&team, &input.device.name, &input.device.udid, None)
                .await
                .map_err(apple_error)?;
        }
    }
    let existing = dev.list_app_ids(&team, None).await.map_err(apple_error)?;
    let app_group = if let Some(requested) = &input.app_group {
        let groups = dev
            .list_app_groups(&team, None)
            .await
            .map_err(apple_error)?;
        let group = if let Some(group) = groups
            .into_iter()
            .find(|g| g.identifier == requested.identifier)
        {
            group
        } else {
            dev.add_app_group(&team, &requested.name, &requested.identifier, None)
                .await
                .map_err(apple_error)?
        };
        if group.identifier != requested.identifier || group.application_group.is_empty() {
            return Err(ApiError(
                StatusCode::BAD_GATEWAY,
                ErrorCode::AppleRequestFailed,
            ));
        }
        Some(group)
    } else {
        None
    };
    let mut profiles = Vec::with_capacity(input.apps.len());
    for app in &input.apps {
        let mut app_id = match existing
            .app_ids
            .iter()
            .find(|id| id.identifier == app.bundle_id)
        {
            Some(existing) => existing.clone(),
            None => dev
                .add_app_id(&team, &app.name, &app.bundle_id, None)
                .await
                .map_err(apple_error)?,
        };
        if let Some(group) = &app_group {
            if app_id
                .features
                .get("APG3427HIY")
                .and_then(plist::Value::as_boolean)
                != Some(true)
            {
                // The upstream convenience getter errors on a missing feature.
                // Explicitly set Boolean true while preserving existing features.
                let mut features = app_id.features.clone();
                features.insert("APG3427HIY".into(), plist::Value::Boolean(true));
                app_id = dev
                    .update_app_id(&team, &app_id, features, None)
                    .await
                    .map_err(apple_error)?;
                if app_id
                    .features
                    .get("APG3427HIY")
                    .and_then(plist::Value::as_boolean)
                    != Some(true)
                {
                    return Err(ApiError(
                        StatusCode::BAD_GATEWAY,
                        ErrorCode::AppleRequestFailed,
                    ));
                }
            }
            dev.assign_app_group(&team, group, &app_id, None)
                .await
                .map_err(apple_error)?;
        }
        let profile = dev
            .download_team_provisioning_profile(&team, &app_id, None)
            .await
            .map_err(apple_error)?;
        if profile.app_id_id != app_id.app_id_id
            || profile.encoded_profile.as_ref().is_empty()
            || profile.encoded_profile.as_ref().len() > 2 * 1024 * 1024
        {
            return Err(ApiError(
                StatusCode::BAD_GATEWAY,
                ErrorCode::AppleRequestFailed,
            ));
        }
        let profile_bytes = profile.encoded_profile.as_ref().to_vec();
        let expected_team = team.team_id.clone();
        let expected_bundle = app.bundle_id.clone();
        let expected_udid = input.device.udid.clone();
        let expected_der = der.as_ref().to_vec();
        let expected_group = input.app_group.as_ref().map(|g| g.identifier.clone());
        crate::enrollment::parse_bounded(move || {
            validate_profile(
                &profile_bytes,
                &expected_team,
                &expected_bundle,
                &expected_udid,
                &expected_der,
                expected_group.as_deref(),
            )
        })
        .await?;
        profiles.push(ProfileOutput {
            bundle_id: app.bundle_id.clone(),
            profile_base64: STANDARD.encode(profile.encoded_profile.as_ref()),
            profile_id: profile.provisioning_profile_id,
        });
    }
    Ok(ProvisionOutput {
        team_id: team.team_id,
        certificate_der_base64: STANDARD.encode(der.as_ref()),
        certificate_serial: certificate.serial_number.clone(),
        certificate_reused: reused,
        app_group_identifier: app_group.map(|group| group.identifier),
        profiles,
        // These bytes are Apple's response. No device installation, CMS trust,
        // entitlement compatibility or physical launch is claimed here.
        verification: "cmsSignatureAndMetadataOnly",
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn synthetic_profile() -> plist::Dictionary {
        let mut profile = plist::Dictionary::new();
        for (key, value) in [
            ("TeamIdentifier", "SYNTHETIC"),
            ("ApplicationIdentifierPrefix", "SYNTHETIC"),
            (
                "ProvisionedDevices",
                "0000000000000000000000000000000000000000",
            ),
        ] {
            profile.insert(
                key.into(),
                plist::Value::Array(vec![plist::Value::String(value.into())]),
            );
        }
        profile.insert(
            "DeveloperCertificates".into(),
            plist::Value::Array(vec![plist::Value::Data(
                include_bytes!("../tests/fixtures/certificate.der").to_vec(),
            )]),
        );
        profile.insert(
            "ExpirationDate".into(),
            plist::Value::Date(
                (std::time::SystemTime::now() + std::time::Duration::from_secs(600)).into(),
            ),
        );
        let mut entitlements = plist::Dictionary::new();
        entitlements.insert(
            "application-identifier".into(),
            plist::Value::String("SYNTHETIC.org.example.synthetic".into()),
        );
        entitlements.insert(
            "com.apple.developer.team-identifier".into(),
            plist::Value::String("SYNTHETIC".into()),
        );
        entitlements.insert(
            "com.apple.security.application-groups".into(),
            plist::Value::Array(vec![plist::Value::String(
                "group.org.example.synthetic".into(),
            )]),
        );
        profile.insert(
            "Entitlements".into(),
            plist::Value::Dictionary(entitlements),
        );
        profile
    }
    #[test]
    fn synthetic_profile_requires_exact_team_bundle_udid_key_and_group() {
        let profile = synthetic_profile();
        let validate = |p: &plist::Dictionary| {
            validate_profile_metadata(
                p,
                "SYNTHETIC",
                "org.example.synthetic",
                "0000000000000000000000000000000000000000",
                include_bytes!("../tests/fixtures/certificate.der"),
                Some("group.org.example.synthetic"),
            )
        };
        assert!(validate(&profile).is_ok());
        for missing in [
            "TeamIdentifier",
            "ApplicationIdentifierPrefix",
            "ProvisionedDevices",
            "DeveloperCertificates",
            "ExpirationDate",
            "Entitlements",
        ] {
            let mut wrong = profile.clone();
            wrong.remove(missing);
            assert!(validate(&wrong).is_err(), "{missing}");
        }
        for key in [
            "application-identifier",
            "com.apple.developer.team-identifier",
            "com.apple.security.application-groups",
        ] {
            let mut wrong = profile.clone();
            wrong
                .get_mut("Entitlements")
                .unwrap()
                .as_dictionary_mut()
                .unwrap()
                .remove(key);
            assert!(validate(&wrong).is_err(), "{key}");
        }
        assert!(
            validate_profile_metadata(
                &profile,
                "SYNTHETIC",
                "org.example.wrong",
                "0000000000000000000000000000000000000000",
                include_bytes!("../tests/fixtures/certificate.der"),
                Some("group.org.example.synthetic")
            )
            .is_err()
        );
        let mut expired = profile.clone();
        expired.insert(
            "ExpirationDate".into(),
            plist::Value::Date(std::time::UNIX_EPOCH.into()),
        );
        assert!(validate(&expired).is_err());
        assert!(
            validate_profile(
                b"unsigned data",
                "SYNTHETIC",
                "org.example.synthetic",
                "0000000000000000000000000000000000000000",
                include_bytes!("../tests/fixtures/certificate.der"),
                None
            )
            .is_err()
        );
    }
    #[test]
    fn synthetic_public_certificate_matches_only_its_original_csr_key() {
        let cert =
            Certificate::from_der(include_bytes!("../tests/fixtures/certificate.der")).unwrap();
        let key = cert
            .tbs_certificate
            .subject_public_key_info
            .to_der()
            .unwrap();
        assert!(certificate_matches_public_key(
            include_bytes!("../tests/fixtures/certificate.der"),
            &key
        ));
        assert!(!certificate_matches_public_key(
            include_bytes!("../tests/fixtures/other-certificate.der"),
            &key
        ));
        assert!(!certificate_matches_public_key(b"invalid", &key));
    }
}
