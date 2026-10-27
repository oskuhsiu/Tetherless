// SPDX-License-Identifier: AGPL-3.0-only
//! One-time device metadata collection, not MDM enrollment or device attestation.
use crate::{App, model::*};
use axum::{
    Json,
    body::Bytes,
    extract::{Path, State},
    http::{HeaderMap, HeaderValue, StatusCode, header},
    response::{IntoResponse, Response},
};
use openssl::{
    pkcs7::{Pkcs7, Pkcs7Flags},
    stack::Stack,
    x509::store::X509StoreBuilder,
};
use plist::{Dictionary, Value};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::{
    sync::{Arc, LazyLock},
    time::{Duration, Instant},
};
use subtle::ConstantTimeEq;
use tokio::sync::{Mutex, Semaphore};
use uuid::Uuid;
use zeroize::Zeroizing;

pub const ENROLLMENT_TTL: Duration = Duration::from_secs(600);
const MAX_ENROLLMENTS: usize = 16;
const MAX_CALLBACK_BYTES: usize = 32 * 1024;
static PARSERS: LazyLock<Arc<Semaphore>> = LazyLock::new(|| Arc::new(Semaphore::new(2)));

pub struct Enrollment {
    pub created: Instant,
    token: Zeroizing<String>,
    download_ticket: Zeroizing<String>,
    challenge: Zeroizing<String>,
    state: Mutex<EnrollmentState>,
}
#[derive(Default)]
struct EnrollmentState {
    device: Option<DeviceMetadata>,
    attempts: u8,
    cancelled: bool,
}
#[derive(Clone, Serialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct DeviceMetadata {
    pub udid: String,
    pub product: Option<String>,
    pub version: Option<String>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CreateRequest {
    consent: String,
}
#[derive(Deserialize)]
struct CallbackData {
    #[serde(rename = "UDID")]
    udid: String,
    #[serde(rename = "CHALLENGE")]
    challenge: String,
    #[serde(rename = "PRODUCT")]
    product: Option<String>,
    #[serde(rename = "VERSION")]
    version: Option<String>,
}

fn secret() -> String {
    format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple())
}
fn expired() -> ApiError {
    ApiError(StatusCode::GONE, ErrorCode::Expired)
}

pub async fn create(
    State(app): State<Arc<App>>,
    Json(input): Json<CreateRequest>,
) -> ApiResult<Response> {
    if input.consent != "collect-device-udid" || !app.allowed_origin.starts_with("https://") {
        return Err(invalid());
    }
    let mut last = app.last_enrollment_start.lock().await;
    if last.is_some_and(|t| t.elapsed() < Duration::from_secs(5)) {
        return Err(ApiError(StatusCode::TOO_MANY_REQUESTS, ErrorCode::Busy));
    }
    let mut map = app.enrollments.write().await;
    if map.len() >= MAX_ENROLLMENTS {
        return Err(ApiError(StatusCode::TOO_MANY_REQUESTS, ErrorCode::Busy));
    }
    let id = Uuid::new_v4().to_string();
    let token = secret();
    let ticket = secret();
    let profile_url = format!(
        "{}/v1/device-enrollments/{}/profile/{}.mobileconfig",
        app.allowed_origin, id, ticket
    );
    map.insert(
        id.clone(),
        Arc::new(Enrollment {
            created: Instant::now(),
            token: Zeroizing::new(token.clone()),
            download_ticket: Zeroizing::new(ticket),
            challenge: Zeroizing::new(secret()),
            state: Mutex::new(EnrollmentState::default()),
        }),
    );
    *last = Some(Instant::now());
    let cookie = cookie(&id, &token, false)?;
    Ok((StatusCode::CREATED, [(header::SET_COOKIE,cookie)], Json(json!({"enrollmentId":id,"profileUrl":profile_url,"expiresInSeconds":ENROLLMENT_TTL.as_secs(),"verification":"untrustedDeviceMetadata"}))).into_response())
}

fn cookie(id: &str, token: &str, delete: bool) -> ApiResult<HeaderValue> {
    HeaderValue::from_str(&format!("__Secure-tetherless-enrollment={}; Path=/v1/device-enrollments/{}; Max-Age={}; Secure; HttpOnly; SameSite=Lax", token, id,
        if delete { 0 } else { ENROLLMENT_TTL.as_secs() })).map_err(|_| invalid())
}

async fn entry(app: &App, id: &str) -> ApiResult<Arc<Enrollment>> {
    let record = app
        .enrollments
        .read()
        .await
        .get(id)
        .cloned()
        .ok_or(ApiError(StatusCode::NOT_FOUND, ErrorCode::NotFound))?;
    if record.created.elapsed() >= ENROLLMENT_TTL || record.state.lock().await.cancelled {
        return Err(expired());
    }
    Ok(record)
}
fn authorized(record: &Enrollment, headers: &HeaderMap) -> ApiResult<()> {
    let token = headers
        .get(header::COOKIE)
        .and_then(|h| h.to_str().ok())
        .and_then(|h| {
            h.split(';')
                .map(str::trim)
                .find_map(|s| s.strip_prefix("__Secure-tetherless-enrollment="))
        })
        .unwrap_or("");
    if !bool::from(record.token.as_bytes().ct_eq(token.as_bytes())) {
        return Err(ApiError(StatusCode::UNAUTHORIZED, ErrorCode::Unauthorized));
    }
    Ok(())
}

pub async fn status(
    State(app): State<Arc<App>>,
    Path(id): Path<String>,
    headers: HeaderMap,
) -> ApiResult<Json<serde_json::Value>> {
    let record = entry(&app, &id).await?;
    authorized(&record, &headers)?;
    let state = record.state.lock().await;
    Ok(Json(
        json!({"state":if state.device.is_some(){"received"}else{"awaitingDevice"},"device":state.device,"verification":"untrustedDeviceMetadata"}),
    ))
}
pub async fn cancel(
    State(app): State<Arc<App>>,
    Path(id): Path<String>,
    headers: HeaderMap,
) -> ApiResult<Response> {
    let record = entry(&app, &id).await?;
    authorized(&record, &headers)?;
    record.state.lock().await.cancelled = true;
    app.enrollments.write().await.remove(&id);
    Ok((
        StatusCode::NO_CONTENT,
        [(header::SET_COOKIE, cookie(&id, "", true)?)],
    )
        .into_response())
}

pub async fn profile(
    State(app): State<Arc<App>>,
    Path((id, ticket)): Path<(String, String)>,
) -> ApiResult<Response> {
    let record = entry(&app, &id).await?;
    let expected = format!("{}.mobileconfig", record.download_ticket.as_str());
    if !bool::from(expected.as_bytes().ct_eq(ticket.as_bytes())) {
        return Err(ApiError(StatusCode::NOT_FOUND, ErrorCode::NotFound));
    }
    if record.state.lock().await.device.is_some() {
        return Err(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState));
    }
    let callback_url = format!(
        "{}/v1/device-enrollments/{}/callback",
        app.allowed_origin, id
    );
    let bytes = mobileconfig(&callback_url, record.challenge.as_str())?;
    Ok((
        [
            (header::CONTENT_TYPE, "application/x-apple-aspen-config"),
            (
                header::CONTENT_DISPOSITION,
                "attachment; filename=\"Tetherless-Device-ID.mobileconfig\"",
            ),
        ],
        bytes,
    )
        .into_response())
}

fn mobileconfig(callback: &str, challenge: &str) -> ApiResult<Vec<u8>> {
    let mut content = Dictionary::new();
    content.insert("URL".into(), Value::String(callback.into()));
    content.insert("Challenge".into(), Value::String(challenge.into()));
    content.insert(
        "DeviceAttributes".into(),
        Value::Array(
            ["UDID", "PRODUCT", "VERSION"]
                .into_iter()
                .map(|s| Value::String(s.into()))
                .collect(),
        ),
    );
    let mut profile = Dictionary::new();
    for (key, value) in [
        ("PayloadType", "Profile Service"),
        ("PayloadIdentifier", "org.tetherless.bootstrap.device-id"),
        ("PayloadDisplayName", "Tetherless Device ID"),
        (
            "PayloadDescription",
            "Send this device's UDID, product model and iOS version to the Tetherless bootstrap service. This does not enroll in device management or register the device with Apple.",
        ),
        ("PayloadOrganization", "Tetherless"),
    ] {
        profile.insert(key.into(), Value::String(value.into()));
    }
    profile.insert(
        "PayloadUUID".into(),
        Value::String(Uuid::new_v4().to_string()),
    );
    profile.insert("PayloadVersion".into(), Value::Integer(1.into()));
    profile.insert("PayloadContent".into(), Value::Dictionary(content));
    let mut bytes = Vec::new();
    plist::to_writer_xml(&mut bytes, &profile).map_err(|_| invalid())?;
    Ok(bytes)
}

/// CMS signature integrity only. NOVERIFY deliberately skips signer-chain trust;
/// the returned values must remain untrusted device metadata. NOSIGS is never set.
fn extract_callback(body: &[u8], challenge: &str) -> ApiResult<DeviceMetadata> {
    if body.is_empty() || body.len() > MAX_CALLBACK_BYTES {
        return Err(invalid());
    }
    let cms = Pkcs7::from_der(body).map_err(|_| invalid())?;
    let certificates = Stack::new().map_err(|_| invalid())?;
    if cms
        .signers(&certificates, Pkcs7Flags::empty())
        .map_err(|_| invalid())?
        .len()
        != 1
    {
        return Err(invalid());
    }
    let store = X509StoreBuilder::new().map_err(|_| invalid())?.build();
    let mut output = Vec::new();
    cms.verify(
        &certificates,
        &store,
        None,
        Some(&mut output),
        Pkcs7Flags::NOVERIFY | Pkcs7Flags::BINARY,
    )
    .map_err(|_| invalid())?;
    if output.len() > 8192 {
        return Err(invalid());
    }
    let data: CallbackData = plist::from_bytes(&output).map_err(|_| invalid())?;
    if !bool::from(data.challenge.as_bytes().ct_eq(challenge.as_bytes()))
        || !crate::model::valid_udid(&data.udid)
    {
        return Err(invalid());
    }
    for field in [&data.product, &data.version].into_iter().flatten() {
        if field.is_empty() || field.len() > 64 || field.chars().any(char::is_control) {
            return Err(invalid());
        }
    }
    Ok(DeviceMetadata {
        udid: data.udid,
        product: data.product,
        version: data.version,
    })
}

pub async fn callback(
    State(app): State<Arc<App>>,
    Path(id): Path<String>,
    headers: HeaderMap,
    body: Bytes,
) -> ApiResult<Response> {
    let mime = headers
        .get(header::CONTENT_TYPE)
        .and_then(|h| h.to_str().ok())
        .unwrap_or("")
        .split(';')
        .next()
        .unwrap_or("")
        .trim();
    if !matches!(
        mime,
        "application/pkcs7-signature" | "application/pkcs7-mime" | "application/x-pkcs7-signature"
    ) {
        return Err(invalid());
    }
    let record = entry(&app, &id).await?;
    {
        let mut state = record.state.lock().await;
        if state.device.is_some() || state.attempts >= 5 {
            return Err(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState));
        }
        state.attempts += 1;
    }
    let challenge = record.challenge.to_string();
    let device = parse_bounded(move || extract_callback(&body, &challenge)).await?;
    let mut state = record.state.lock().await;
    if state.cancelled || record.created.elapsed() >= ENROLLMENT_TTL {
        return Err(expired());
    }
    if state.device.is_some() {
        return Err(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState));
    }
    state.device = Some(device);
    // No metadata in URL, no open redirect, no configuration/MDM payload returned.
    let location = HeaderValue::from_str(&format!("{}/#device-collected", app.allowed_origin))
        .map_err(|_| invalid())?;
    Ok((
        StatusCode::MOVED_PERMANENTLY,
        [(header::LOCATION, location)],
    )
        .into_response())
}

async fn bounded_parser<T: Send + 'static>(
    semaphore: Arc<Semaphore>,
    work: impl FnOnce() -> ApiResult<T> + Send + 'static,
) -> ApiResult<T> {
    let permit = semaphore
        .try_acquire_owned()
        .map_err(|_| ApiError(StatusCode::TOO_MANY_REQUESTS, ErrorCode::Busy))?;
    tokio::task::spawn_blocking(move || {
        // The actual blocking task owns capacity until it exits, including when
        // its HTTP/async caller is cancelled or disconnected.
        let _permit = permit;
        work()
    })
    .await
    .map_err(|_| invalid())?
}

pub(crate) async fn parse_bounded<T: Send + 'static>(
    work: impl FnOnce() -> ApiResult<T> + Send + 'static,
) -> ApiResult<T> {
    bounded_parser(PARSERS.clone(), work).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use openssl::{
        asn1::Asn1Time,
        hash::MessageDigest,
        pkey::PKey,
        rsa::Rsa,
        x509::{X509, X509NameBuilder},
    };
    fn signed_metadata(challenge: &str) -> Vec<u8> {
        let key = PKey::from_rsa(Rsa::generate(2048).unwrap()).unwrap();
        let mut name = X509NameBuilder::new().unwrap();
        name.append_entry_by_text("CN", "Synthetic callback; not Apple")
            .unwrap();
        let name = name.build();
        let mut cert = X509::builder().unwrap();
        cert.set_version(2).unwrap();
        cert.set_subject_name(&name).unwrap();
        cert.set_issuer_name(&name).unwrap();
        cert.set_pubkey(&key).unwrap();
        cert.set_not_before(&Asn1Time::days_from_now(0).unwrap())
            .unwrap();
        cert.set_not_after(&Asn1Time::days_from_now(1).unwrap())
            .unwrap();
        cert.sign(&key, MessageDigest::sha256()).unwrap();
        let cert = cert.build();
        let mut content = Dictionary::new();
        content.insert("UDID".into(), Value::String("0".repeat(40)));
        content.insert("CHALLENGE".into(), Value::String(challenge.into()));
        content.insert("PRODUCT".into(), Value::String("Synthetic1,1".into()));
        let mut bytes = Vec::new();
        plist::to_writer_xml(&mut bytes, &content).unwrap();
        Pkcs7::sign(
            &cert,
            &key,
            &Stack::new().unwrap(),
            &bytes,
            Pkcs7Flags::BINARY,
        )
        .unwrap()
        .to_der()
        .unwrap()
    }
    #[test]
    fn profile_requests_only_approved_metadata_and_exact_challenge() {
        let bytes = mobileconfig("https://example.com/callback", "synthetic-challenge").unwrap();
        let root: Dictionary = plist::from_bytes(&bytes).unwrap();
        assert_eq!(root["PayloadType"].as_string(), Some("Profile Service"));
        let content = root["PayloadContent"].as_dictionary().unwrap();
        assert_eq!(
            content["Challenge"].as_string(),
            Some("synthetic-challenge")
        );
        assert_eq!(content["DeviceAttributes"].as_array().unwrap().len(), 3);
        let text = String::from_utf8(bytes).unwrap();
        for absent in ["IMEI", "SERIAL", "com.apple.mdm", "com.apple.security.scep"] {
            assert!(!text.contains(absent));
        }
    }
    #[test]
    fn cms_signature_and_nonce_are_checked_but_device_is_not_attested() {
        let bytes = signed_metadata("right");
        let data = extract_callback(&bytes, "right").unwrap();
        assert_eq!(data.udid, "0".repeat(40));
        assert!(extract_callback(&bytes, "wrong").is_err());
        // This self-signed synthetic callback is accepted only as UNTRUSTED
        // metadata; no Apple certificate or live device is involved.
        let mut corrupted = bytes.clone();
        let middle = corrupted.len() / 2;
        corrupted[middle] ^= 0x40;
        assert!(extract_callback(&corrupted, "right").is_err());
        assert!(extract_callback(b"<plist>unsigned</plist>", "right").is_err());
        assert!(extract_callback(&vec![0; MAX_CALLBACK_BYTES + 1], "right").is_err());
    }
    fn app() -> Arc<App> {
        Arc::new(App {
            sessions: tokio::sync::RwLock::new(std::collections::HashMap::new()),
            last_start: Mutex::new(None),
            enrollments: tokio::sync::RwLock::new(std::collections::HashMap::new()),
            last_enrollment_start: Mutex::new(None),
            allowed_origin: "https://bootstrap.example".into(),
            allowed_host: "bootstrap.example".into(),
        })
    }
    #[tokio::test]
    async fn synthetic_enrollment_roundtrip_is_cookie_bound_and_one_shot() {
        use tower::ServiceExt;
        let app = app();
        let router = crate::routes(app.clone());
        let response = router
            .clone()
            .oneshot(
                axum::http::Request::builder()
                    .method("POST")
                    .uri("/v1/device-enrollments")
                    .header("host", "bootstrap.example")
                    .header("origin", "https://bootstrap.example")
                    .header("content-type", "application/json")
                    .body(axum::body::Body::from(
                        r#"{"consent":"collect-device-udid"}"#,
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::CREATED);
        let cookie = response.headers()[header::SET_COOKIE]
            .to_str()
            .unwrap()
            .to_string();
        for flag in ["Secure", "HttpOnly", "SameSite=Lax", "Max-Age=600"] {
            assert!(cookie.contains(flag));
        }
        let json: serde_json::Value = serde_json::from_slice(
            &axum::body::to_bytes(response.into_body(), 8192)
                .await
                .unwrap(),
        )
        .unwrap();
        assert!(json.get("enrollmentToken").is_none());
        let id = json["enrollmentId"].as_str().unwrap();
        let record = app.enrollments.read().await.get(id).unwrap().clone();
        let signed = signed_metadata(record.challenge.as_str());
        let callback = format!("/v1/device-enrollments/{id}/callback");
        let request = |bytes: Vec<u8>| {
            axum::http::Request::builder()
                .method("POST")
                .uri(&callback)
                .header("host", "bootstrap.example")
                .header("content-type", "application/pkcs7-signature")
                .body(axum::body::Body::from(bytes))
                .unwrap()
        };
        let accepted = router
            .clone()
            .oneshot(request(signed.clone()))
            .await
            .unwrap();
        assert_eq!(accepted.status(), StatusCode::MOVED_PERMANENTLY);
        assert_eq!(
            accepted.headers()[header::LOCATION],
            "https://bootstrap.example/#device-collected"
        );
        assert_eq!(
            router
                .clone()
                .oneshot(request(signed))
                .await
                .unwrap()
                .status(),
            StatusCode::CONFLICT
        );
        let status_url = format!("/v1/device-enrollments/{id}");
        let status_request = |cookie: &str| {
            axum::http::Request::builder()
                .uri(&status_url)
                .header("host", "bootstrap.example")
                .header("cookie", cookie)
                .body(axum::body::Body::empty())
                .unwrap()
        };
        assert_eq!(
            router
                .clone()
                .oneshot(status_request(""))
                .await
                .unwrap()
                .status(),
            StatusCode::UNAUTHORIZED
        );
        let result = router
            .oneshot(status_request(cookie.split(';').next().unwrap()))
            .await
            .unwrap();
        assert_eq!(result.status(), StatusCode::OK);
        let json: serde_json::Value = serde_json::from_slice(
            &axum::body::to_bytes(result.into_body(), 8192)
                .await
                .unwrap(),
        )
        .unwrap();
        assert_eq!(json["state"], "received");
        assert_eq!(json["verification"], "untrustedDeviceMetadata");
        assert_eq!(json["device"]["udid"], "0".repeat(40));
    }
    #[tokio::test]
    async fn cancelled_or_expired_enrollment_cannot_be_used() {
        let app = app();
        let id = Uuid::new_v4().to_string();
        let record = Arc::new(Enrollment {
            created: Instant::now() - ENROLLMENT_TTL,
            token: Zeroizing::new(secret()),
            download_ticket: Zeroizing::new(secret()),
            challenge: Zeroizing::new(secret()),
            state: Mutex::new(EnrollmentState::default()),
        });
        app.enrollments.write().await.insert(id.clone(), record);
        assert!(matches!(
            entry(&app, &id).await,
            Err(ApiError(StatusCode::GONE, _))
        ));
        let id = Uuid::new_v4().to_string();
        let record = Arc::new(Enrollment {
            created: Instant::now(),
            token: Zeroizing::new(secret()),
            download_ticket: Zeroizing::new(secret()),
            challenge: Zeroizing::new(secret()),
            state: Mutex::new(EnrollmentState {
                cancelled: true,
                ..Default::default()
            }),
        });
        app.enrollments.write().await.insert(id.clone(), record);
        assert!(matches!(
            entry(&app, &id).await,
            Err(ApiError(StatusCode::GONE, _))
        ));
    }
    #[tokio::test]
    async fn disconnected_callback_retains_blocking_parser_capacity() {
        let semaphore = Arc::new(Semaphore::new(1));
        let (started_tx, started_rx) = tokio::sync::oneshot::channel();
        let (release_tx, release_rx) = std::sync::mpsc::channel();
        let child_semaphore = semaphore.clone();
        let task = tokio::spawn(async move {
            bounded_parser(child_semaphore, move || {
                let _ = started_tx.send(());
                release_rx.recv().unwrap();
                Ok(())
            })
            .await
        });
        started_rx.await.unwrap();
        task.abort();
        let _ = task.await;
        assert!(semaphore.clone().try_acquire_owned().is_err());
        release_tx.send(()).unwrap();
        let permit = tokio::time::timeout(Duration::from_secs(2), semaphore.acquire_owned())
            .await
            .unwrap()
            .unwrap();
        drop(permit);
    }
}
